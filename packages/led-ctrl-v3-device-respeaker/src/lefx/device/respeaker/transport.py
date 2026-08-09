"""The USB connection to the device: discovery, reconnection and locked I/O.

One transport serves both directions. The frame sink and the DoA provider are
separate objects — a failing read must not take the LED output down — but they
share this, because two objects opening the same USB endpoint would fight over
it.

The connection is *managed*, not merely opened: a background thread reconnects
after an unplug and proves a live connection with a periodic ``VERSION`` read.
Callers therefore never handle "is the cable in" themselves; they read
:attr:`is_connected` and get on with it.
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from typing import Any, Callable

import usb.util

from . import xvf

logger = logging.getLogger("lefx.device.respeaker.transport")


class ConnectionState(enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


class UsbTransport:
    """Keeps a reSpeaker reachable, and serialises access to it."""

    probe_command = "VERSION"
    """Read to prove a link is real — on connecting, and as the heartbeat.

    Read-only and cheap, so asking repeatedly costs nothing and changes nothing.
    """

    def __init__(
        self,
        *,
        retry_interval_s: float = 3.0,
        heartbeat_interval_s: float = 2.0,
        on_connected: Callable[[], None] | None = None,
        on_disconnected: Callable[[str], None] | None = None,
        finder: Callable[[], Any] | None = None,
        force_claim: bool = False,
        claim_unrelated: bool = False,
    ) -> None:
        self.retry_interval_s = retry_interval_s
        self.heartbeat_interval_s = heartbeat_interval_s
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.force_claim = force_claim
        self.claim_unrelated = claim_unrelated
        # Injectable so the reconnect and heartbeat logic can be exercised
        # without a device on the bus. Defaults to the real one.
        self._finder = finder if finder is not None else xvf.find

        self._state = ConnectionState.DISCONNECTED
        self._device: Any | None = None

        self._io_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None

        # Set whenever a fresh device appears, so whoever configures the device
        # on connect knows its settings were lost with the old handle.
        self._session_dirty = True

        # Force-claiming is allowed once per connection cycle, not once per
        # retry. The retry loop runs every few seconds forever; a transport that
        # terminated processes on that schedule would be a menace. Cleared again
        # on a successful connect, so a device lost and re-taken later can still
        # be fought for once more.
        self._claim_spent = False
        self._last_claim: Any | None = None

        self._connect_count = 0
        self._disconnect_count = 0
        self._last_connected_at: float | None = None
        self._last_error: str | None = None
        self._retry_count = 0

    # -- state --------------------------------------------------------------

    @property
    def state(self) -> ConnectionState:
        with self._state_lock:
            return self._state

    @property
    def is_connected(self) -> bool:
        return self.state is ConnectionState.CONNECTED

    @property
    def last_error(self) -> str | None:
        with self._state_lock:
            return self._last_error

    def stats(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "state": self._state.value,
                "connect_count": self._connect_count,
                "disconnect_count": self._disconnect_count,
                "last_connected_at": self._last_connected_at,
                "last_error": self._last_error,
                "retry_count": self._retry_count,
                "force_claim": self.force_claim,
                "last_claim": None if self._last_claim is None else self._last_claim.summary(),
            }

    def consume_session_dirty(self) -> bool:
        """Report — once — that the device handle was replaced since last asked.

        A reconnected device has forgotten everything that was written to it, so
        the sink uses this to re-send its mode instead of assuming the ring is
        still where it left it.
        """
        with self._state_lock:
            dirty = self._session_dirty
            self._session_dirty = False
            return dirty

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        with self._state_lock:
            if self._monitor is not None and self._monitor.is_alive():
                return
            self._stop.clear()
            self._monitor = threading.Thread(
                target=self._run, name="respeaker-usb-monitor", daemon=True
            )
            self._monitor.start()

    def stop(self) -> None:
        self._stop.set()
        monitor = self._monitor
        if monitor is not None:
            monitor.join(timeout=self.retry_interval_s + 1.0)
            self._monitor = None
        self._disconnect("transport stopped")

    def close(self) -> None:
        """Idempotent. Stopping an already stopped transport is not an error."""
        self.stop()

    def __enter__(self) -> "UsbTransport":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # -- I/O ----------------------------------------------------------------

    def write(self, name: str, data: list) -> None:
        with self._io_lock:
            device = self._require_device()
            try:
                device.write(name, data)
            except Exception as exc:
                self._disconnect(f"write {name} failed: {exc}")
                raise

    def read(self, name: str) -> tuple:
        with self._io_lock:
            device = self._require_device()
            try:
                return device.read(name)
            except Exception as exc:
                self._disconnect(f"read {name} failed: {exc}")
                raise

    def _require_device(self) -> Any:
        if not self.is_connected or self._device is None:
            raise ConnectionError("reSpeaker is not connected")
        return self._device

    # -- the monitor thread -------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.state is ConnectionState.CONNECTED:
                if self._heartbeat() and self._stop.wait(self.heartbeat_interval_s):
                    break
                continue
            if self._try_connect():
                if self._stop.wait(self.heartbeat_interval_s):
                    break
            elif self._stop.wait(self.retry_interval_s):
                break

    def _try_connect(self) -> bool:
        with self._state_lock:
            self._state = ConnectionState.CONNECTING
            self._retry_count += 1

        try:
            with self._io_lock:
                device = self._finder()
                if device is not None:
                    # Enumerating a device is not the same as being able to use
                    # it: on Windows a reSpeaker bound to the wrong driver shows
                    # up on the bus and refuses every transfer. Proving the link
                    # here keeps is_connected meaning "reachable" rather than
                    # "listed", so the sink reports the problem instead of
                    # discovering it one frame at a time.
                    device.read(self.probe_command)
                    self._device = device
                    with self._state_lock:
                        self._state = ConnectionState.CONNECTED
                        self._connect_count += 1
                        self._last_connected_at = time.time()
                        self._retry_count = 0
                        self._session_dirty = True
                        self._last_error = None
                        self._claim_spent = False
                    logger.info("reSpeaker connected")
                    self._notify(self.on_connected, "on_connected")
                    return True
        except Exception as exc:
            # No device on the bus is the normal case while nothing is plugged
            # in; it is not worth a warning on every retry.
            logger.debug("connection attempt failed: %s", exc)
            with self._state_lock:
                self._last_error = str(exc)
            if self._should_claim(exc):
                return self._claim_and_retry()

        with self._state_lock:
            self._state = ConnectionState.DISCONNECTED
        return False

    def _should_claim(self, exc: Exception) -> bool:
        """Whether this failure is the kind another process could be causing.

        A device that is simply absent is not contended, and running a process
        hunt for it would be noise. The signature that matters is access being
        denied to a device that *is* on the bus.
        """
        if not self.force_claim:
            return False
        with self._state_lock:
            if self._claim_spent:
                return False
        text = str(exc).casefold()
        return "access" in text or "errno 13" in text or "permission" in text

    def _claim_and_retry(self) -> bool:
        """Try to take the device from whatever is holding it, then reconnect.

        Only reached when force-claiming was asked for explicitly. It runs at
        most once between successful connections.
        """
        from . import contention

        with self._state_lock:
            self._claim_spent = True

        logger.warning("the reSpeaker is held by another process; force claim was requested")
        try:
            report = contention.release_device(
                contention.device_probe(), only_related=not self.claim_unrelated
            )
        except Exception as exc:
            logger.warning("force claim failed: %s", exc)
            with self._state_lock:
                self._state = ConnectionState.DISCONNECTED
            return False

        self._last_claim = report
        logger.warning("force claim: %s", report.summary())
        if not report.reachable_after:
            with self._state_lock:
                self._state = ConnectionState.DISCONNECTED
                self._last_error = report.note or report.summary()
            return False
        # The device answers now, so an ordinary connection attempt will work.
        # Recursion is bounded: _claim_spent is set above, so the retry cannot
        # come back here.
        return self._try_connect()

    def _heartbeat(self) -> bool:
        """Prove the handle still works. A dead cable often reads fine until asked."""
        try:
            self.read(self.probe_command)
            return True
        except Exception as exc:
            logger.warning("heartbeat failed: %s", exc)
            return False

    def _disconnect(self, reason: str) -> None:
        with self._state_lock:
            if self._state is ConnectionState.DISCONNECTED:
                return
            logger.warning("reSpeaker disconnected: %s", reason)
            self._state = ConnectionState.DISCONNECTED
            self._disconnect_count += 1
            self._last_error = reason
            self._session_dirty = True

        with self._io_lock:
            device = self._device
            self._device = None
        if device is not None:
            try:
                handle = getattr(device, "dev", None)
                if handle is not None:
                    usb.util.dispose_resources(handle)
            except Exception as exc:
                logger.debug("could not dispose USB resources: %s", exc)

        self._notify(self.on_disconnected, "on_disconnected", reason)

    def _notify(self, callback: Callable[..., None] | None, label: str, *args: Any) -> None:
        """Run a lifecycle callback off the caller's thread.

        Both ``_try_connect`` and the read/write error paths hold ``_io_lock``
        when a transition happens. Calling a listener inline would let one that
        takes its own lock deadlock against a render thread holding that lock
        and waiting for ``_io_lock``, so callbacks never inherit our locks.
        """
        if callback is None:
            return

        def run() -> None:
            try:
                callback(*args)
            except Exception:
                logger.exception("%s callback failed", label)

        threading.Thread(target=run, name=f"respeaker-{label}", daemon=True).start()


__all__ = ["ConnectionState", "UsbTransport"]
