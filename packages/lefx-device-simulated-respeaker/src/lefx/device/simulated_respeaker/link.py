"""The service-side transport: a loopback socket the ring window connects to.

The service listens and the window dials in, not the other way round. That
matches how the hardware behaves — the controller runs whether or not anything
is plugged in, and a device appearing later is an ordinary event rather than a
restart. A window can be opened, closed and reopened as often as you like.

One link carries both directions, the same way one USB cable does: frames go out
to the window, slider values come back. The sink and the provider stay separate
objects over it, so a window that stops reporting inputs does not stop the
display.

No Qt here, and none reachable from here. Installing the simulator must not pull
a GUI toolkit into the service process.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
from typing import Any

from . import protocol

logger = logging.getLogger("lefx.device.simulated_respeaker.link")

SEND_TIMEOUT_S = 2.0
"""A window that cannot absorb a few hundred bytes in this long is gone,
whatever its socket still claims."""


def default_port() -> int:
    """The port both halves use unless told otherwise."""
    raw = os.environ.get(protocol.PORT_ENV_VAR)
    if not raw:
        return protocol.DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        logger.warning("ignoring %s=%r: not a port number", protocol.PORT_ENV_VAR, raw)
        return protocol.DEFAULT_PORT


class _Window:
    """One connected ring window, with its own writer thread.

    Frames are dropped rather than queued when a window falls behind: a frame is
    a snapshot of *now*, and delivering a backlog of stale rings late is worse
    than skipping to the current one. Control messages are queued, because
    missing one loses meaning rather than a redraw.
    """

    def __init__(self, sock: socket.socket, address: Any) -> None:
        self.sock = sock
        self.address = address
        self.alive = True
        self._lock = threading.Lock()
        self._wakeup = threading.Condition(self._lock)
        self._pending_frame: bytes | None = None
        self._control: list[bytes] = []
        self._writer = threading.Thread(
            target=self._write_loop, name="lefx-simulator-writer", daemon=True
        )
        self._writer.start()

    def send_frame(self, message: bytes) -> None:
        with self._wakeup:
            self._pending_frame = message
            self._wakeup.notify()

    def send_control(self, message: bytes) -> None:
        with self._wakeup:
            self._control.append(message)
            self._wakeup.notify()

    def _write_loop(self) -> None:
        while True:
            with self._wakeup:
                while self.alive and self._pending_frame is None and not self._control:
                    self._wakeup.wait()
                if not self.alive:
                    return
                control, self._control = self._control, []
                frame, self._pending_frame = self._pending_frame, None
            try:
                for message in control:
                    self.sock.sendall(message)
                if frame is not None:
                    self.sock.sendall(frame)
            except OSError as exc:
                logger.debug("window %s went away while writing: %s", self.address, exc)
                self.close()
                return

    def close(self) -> None:
        with self._wakeup:
            if not self.alive:
                return
            self.alive = False
            self._wakeup.notify_all()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class SimulatorLink:
    """Accepts ring windows, sends them frames and collects their inputs."""

    def __init__(
        self,
        *,
        host: str = protocol.DEFAULT_HOST,
        port: int | None = None,
        led_count: int = 12,
    ) -> None:
        self.host = host
        self.requested_port = default_port() if port is None else int(port)
        self.led_count = int(led_count)

        self._lock = threading.RLock()
        self._server: socket.socket | None = None
        self._accepting: threading.Thread | None = None
        self._windows: list[_Window] = []
        self._latest_inputs: dict[str, Any] | None = None
        self._last_input_at: float | None = None
        self._closed = False
        self._last_error: str | None = None
        self._frames_sent = 0
        self.port: int | None = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Bind and listen. Failing to bind leaves the link simply unavailable.

        The service must run without a display, exactly as it runs without a
        cable; a taken port is a reason for ``status`` to say so, not to refuse
        to start.

        Starting a link that was closed brings it back, the way starting a
        stopped USB transport does. Both devices are reached through one shared
        instance per process, and a shut-down service leaves that instance
        behind; a link that stayed dead would make the next service in the same
        process report a display that can never appear, while the hardware in
        the same situation simply reconnects.
        """
        with self._lock:
            if self._server is not None:
                return
            self._closed = False
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if not sys.platform.startswith("win"):
                    # On POSIX this only skips the TIME_WAIT delay after a
                    # restart. On Windows it means something else entirely —
                    # permission to take a port another socket already holds —
                    # and it turns a plain "in use" into WSAEACCES, which reads
                    # like a privilege problem and sends you looking in the
                    # wrong place. The platform default is what we want there.
                    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.host, self.requested_port))
                server.listen(4)
            except OSError as exc:
                self._last_error = f"cannot listen on {self.host}:{self.requested_port}: {exc}"
                logger.warning("%s", self._last_error)
                return
            self._server = server
            # Port 0 means "any free port"; ask the socket which one it got.
            self.port = server.getsockname()[1]
            self._last_error = None
            self._accepting = threading.Thread(
                target=self._accept_loop, name="lefx-simulator-accept", daemon=True
            )
            self._accepting.start()
            logger.info("simulator link listening on %s:%s", self.host, self.port)

    def close(self) -> None:
        """Idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            server, self._server = self._server, None
            windows, self._windows = self._windows, []
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        for window in windows:
            window.close()

    # -- state --------------------------------------------------------------

    @property
    def connected(self) -> bool:
        with self._lock:
            return any(window.alive for window in self._windows)

    @property
    def window_count(self) -> int:
        with self._lock:
            return sum(1 for window in self._windows if window.alive)

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def detail(self) -> str | None:
        """Why there is no display, in words, or ``None`` when there is one."""
        with self._lock:
            if self._closed:
                return "simulator link closed"
            if self._last_error is not None:
                return self._last_error
            if self._server is None:
                return "simulator link not started"
            if not any(window.alive for window in self._windows):
                return f"no ring window connected on {self.host}:{self.port}"
            return None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "host": self.host,
                "port": self.port,
                "windows": sum(1 for window in self._windows if window.alive),
                "frames_sent": self._frames_sent,
                "last_error": self._last_error,
            }

    # -- output -------------------------------------------------------------

    def send_frame(self, leds: tuple[int, ...] | list[int], timestamp: float) -> bool:
        """Hand the frame to every connected window. False when there is none."""
        message = protocol.encode(protocol.frame(leds, timestamp))
        with self._lock:
            windows = [window for window in self._windows if window.alive]
            if windows:
                self._frames_sent += 1
        for window in windows:
            window.send_frame(message)
        return bool(windows)

    # -- input --------------------------------------------------------------

    def latest_inputs(self) -> dict[str, Any] | None:
        """The most recent slider reading, or ``None`` when nothing reported.

        A reading is *what a connected window says*, so no window means no
        reading — decided here rather than left to the reader thread's cleanup.
        A window's socket closing and its bookkeeping being tidied up are two
        moments, and in between, a caller could otherwise see a reading from a
        window that is already gone. Making it definitional removes the window
        in which that is possible instead of narrowing it.
        """
        with self._lock:
            if not any(window.alive for window in self._windows):
                return None
            return None if self._latest_inputs is None else dict(self._latest_inputs)

    # -- accepting and reading ----------------------------------------------

    def _accept_loop(self) -> None:
        while True:
            with self._lock:
                server = self._server
            if server is None:
                return
            try:
                sock, address = server.accept()
            except OSError:
                return  # The listening socket was closed; that is the exit.
            sock.settimeout(SEND_TIMEOUT_S)
            window = _Window(sock, address)
            with self._lock:
                if self._closed:
                    window.close()
                    return
                self._windows = [item for item in self._windows if item.alive]
                self._windows.append(window)
                led_count = self.led_count
            logger.info("ring window connected from %s", address)
            window.send_control(protocol.encode(protocol.hello(led_count=led_count)))
            threading.Thread(
                target=self._read_loop,
                args=(window,),
                name="lefx-simulator-reader",
                daemon=True,
            ).start()

    def _read_loop(self, window: _Window) -> None:
        try:
            while window.alive:
                try:
                    message = protocol.read_message(window.sock)
                except TimeoutError:
                    # The window has nothing to say. Silence is not a fault:
                    # sliders only report when they move.
                    continue
                if message is None:
                    break
                self._handle(message)
        except (OSError, protocol.ProtocolError) as exc:
            logger.debug("window %s reader stopped: %s", window.address, exc)
        finally:
            window.close()
            with self._lock:
                self._windows = [item for item in self._windows if item.alive]
                if not self._windows:
                    # No window, no reading. Keeping the last one would let an
                    # effect keep pointing at a direction nothing is measuring.
                    self._latest_inputs = None
            logger.info("ring window disconnected: %s", window.address)

    def _handle(self, message: dict[str, Any]) -> None:
        if message.get("type") != protocol.INPUT:
            return
        direction = message.get("direction_deg")
        state = message.get("detection_state", "none")
        with self._lock:
            self._latest_inputs = {
                "direction_deg": None if direction is None else float(direction),
                "detection_state": str(state),
            }


__all__ = ["SEND_TIMEOUT_S", "SimulatorLink", "default_port"]
