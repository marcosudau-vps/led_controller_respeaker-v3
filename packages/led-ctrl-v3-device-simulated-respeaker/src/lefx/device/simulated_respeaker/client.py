"""The window-side half of the transport, without any window.

Kept apart from the Qt code so the connection can be tested headlessly, and so
the ring window contains drawing and controls rather than sockets. It dials the
service, reconnects when the service is not up yet or goes away, reports frames
through a callback and sends the current control values back.

Reconnection matters more here than it might look: the natural way to work is to
leave the window open and restart the service, and a window that had to be
reopened each time would be a worse device than a cable.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Callable

from . import protocol
from .link import default_port

logger = logging.getLogger("lefx.device.simulated_respeaker.client")

RECONNECT_INTERVAL_S = 1.0
CONNECT_TIMEOUT_S = 2.0

FrameCallback = Callable[[list[int], float], None]
StateCallback = Callable[[bool, str | None], None]


class SimulatorClient:
    """Keeps a connection to the service, or keeps trying to."""

    def __init__(
        self,
        *,
        host: str = protocol.DEFAULT_HOST,
        port: int | None = None,
        on_frame: FrameCallback | None = None,
        on_state: StateCallback | None = None,
        on_led_count: Callable[[int], None] | None = None,
    ) -> None:
        self.host = host
        self.port = default_port() if port is None else int(port)
        self.on_frame = on_frame
        self.on_state = on_state
        self.on_led_count = on_led_count

        self._lock = threading.RLock()
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self._announced: bool | None = None
        self._last_error: str | None = None
        # Sent on every (re)connection, so a window that has been sitting at a
        # given angle reports it again rather than looking silent.
        self._controls: dict[str, Any] = {"direction_deg": 0.0, "detection_state": "none"}

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="lefx-simulator-client", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Idempotent."""
        self._stop.set()
        self._drop("stopped")
        thread = self._thread
        if thread is not None:
            thread.join(timeout=CONNECT_TIMEOUT_S + 1.0)
            self._thread = None

    close = stop

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    # -- controls -----------------------------------------------------------

    def set_controls(self, *, direction_deg: float | None, detection_state: str) -> None:
        """Publish what the sliders currently say. Safe to call from the GUI thread."""
        with self._lock:
            controls = {"direction_deg": direction_deg, "detection_state": detection_state}
            self._controls = controls
            sock = self._sock
        if sock is not None:
            self._send(sock, protocol.inputs(**controls))

    def _send(self, sock: socket.socket, message: dict[str, Any]) -> None:
        try:
            sock.sendall(protocol.encode(message))
        except OSError as exc:
            self._drop(f"send failed: {exc}")

    # -- the connection thread ----------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._connect():
                self._read_until_closed()
            if self._stop.wait(RECONNECT_INTERVAL_S):
                return

    def _connect(self) -> bool:
        try:
            sock = socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT_S)
        except OSError as exc:
            with self._lock:
                self._last_error = f"cannot reach the service on {self.host}:{self.port}: {exc}"
            self._announce(False)
            return False

        # Blocking from here on: the reader should wait for frames, not spin.
        sock.settimeout(None)
        with self._lock:
            self._sock = sock
            self._connected = True
            self._last_error = None
            controls = dict(self._controls)
        logger.info("connected to the service on %s:%s", self.host, self.port)
        self._announce(True)
        self._send(sock, protocol.inputs(**controls))
        return True

    def _read_until_closed(self) -> None:
        with self._lock:
            sock = self._sock
        if sock is None:
            return
        try:
            while not self._stop.is_set():
                message = protocol.read_message(sock)
                if message is None:
                    break
                self._handle(message)
        except (OSError, protocol.ProtocolError) as exc:
            self._drop(str(exc))
            return
        self._drop("the service closed the connection")

    def _handle(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == protocol.HELLO:
            led_count = message.get("led_count")
            if self.on_led_count is not None and isinstance(led_count, int) and led_count > 0:
                self.on_led_count(led_count)
        elif kind == protocol.FRAME and self.on_frame is not None:
            leds = message.get("leds")
            if isinstance(leds, list):
                self.on_frame([int(value) for value in leds], float(message.get("timestamp", 0.0)))

    def _drop(self, reason: str) -> None:
        with self._lock:
            sock, self._sock = self._sock, None
            was_connected = self._connected
            self._connected = False
            self._last_error = reason
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if was_connected:
            logger.info("disconnected: %s", reason)
            self._announce(False)

    def _announce(self, connected: bool) -> None:
        """Report a change, not a heartbeat.

        A failed connection attempt happens once a second for as long as the
        service is down; telling the window each time would turn a steady
        "waiting" into a stream of identical updates.
        """
        with self._lock:
            if connected == self._announced:
                return
            self._announced = connected
            detail = self._last_error
        if self.on_state is None:
            return
        try:
            self.on_state(connected, detail)
        except Exception:
            logger.exception("connection state callback failed")


__all__ = ["CONNECT_TIMEOUT_S", "RECONNECT_INTERVAL_S", "SimulatorClient"]
