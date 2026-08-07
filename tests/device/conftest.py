"""Assembling each device the same way, so one suite can run against both.

A ``Device`` is whatever answers the two SDK ports, plus the little the tests
need around it: how to make it available and how to make it report a reading.
Everything below that — a socket, a USB endpoint — stays inside the package it
belongs to, which is the point: the contract is stated in terms neither
implementation can restate in its own favour.

The hardware device is collected either way and skips itself when nothing is
plugged in, so a run without a reSpeaker reports "not exercised" rather than
quietly testing half as much.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DIRECTION_INDICATOR = REPO_ROOT / "effects/core-set/sources/overlays/direction_indicator"


def until(condition: Callable[[], bool], message: str, timeout: float = 3.0) -> None:
    """Wait for what another thread is doing, rather than sleeping and hoping."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(message)


@dataclass
class Device:
    """One device under test, reduced to what the port contract talks about."""

    name: str
    led_count: int
    sink: Any
    provider: Any
    close: Callable[[], None]

    attach: Callable[[], None]
    """Make the device available — plug the cable in, open the window."""

    detach: Callable[[], None]
    """Take it away again. Skips where that needs hands."""

    publish: Callable[[float, str], None]
    """Ask for a specific reading. A no-op where the world decides instead."""

    steerable_inputs: bool = field(default=False)
    """Whether :attr:`publish` really determines what the device then reports.

    False for hardware: its readings come from a room. Assertions about *what*
    was read are for the simulator; assertions about the *shape* apply to both,
    and those are the contract.
    """


# -- the simulator ----------------------------------------------------------


class FakeWindow:
    """A ring window with no Qt in it.

    The real window is Qt drawing what this receives and sending what this
    sends. Driving the simulator through the protocol rather than through the
    GUI keeps the display out of the assertions and the suite out of a
    headless-Qt problem.
    """

    def __init__(self, host: str, port: int) -> None:
        from respeaker_led.simulator import protocol

        self.protocol = protocol
        self.sock = socket.create_connection((host, port), timeout=2.0)
        self.frames: list[list[int]] = []
        self.led_count: int | None = None
        self._stop = threading.Event()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        try:
            while not self._stop.is_set():
                message = self.protocol.read_message(self.sock)
                if message is None:
                    return
                if message.get("type") == self.protocol.HELLO:
                    self.led_count = message["led_count"]
                elif message.get("type") == self.protocol.FRAME:
                    self.frames.append(list(message["leds"]))
        except (OSError, self.protocol.ProtocolError):
            return

    def send_inputs(self, direction_deg: float | None, detection_state: str) -> None:
        self.sock.sendall(
            self.protocol.encode(
                self.protocol.inputs(direction_deg=direction_deg, detection_state=detection_state)
            )
        )

    def close(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


def free_port() -> int:
    """A port the OS says is free, so two runs at once do not collide."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def build_simulator(led_count: int = 12) -> Device:
    from respeaker_led.simulator import SimulatorDoaProvider, SimulatorFrameSink, SimulatorLink

    link = SimulatorLink(host="127.0.0.1", port=free_port(), led_count=led_count)
    link.start()
    sink = SimulatorFrameSink(link, led_count=led_count)
    provider = SimulatorDoaProvider(link)
    windows: list[FakeWindow] = []

    def attach() -> None:
        if windows:
            return
        windows.append(FakeWindow(link.host, link.port))
        until(lambda: link.connected, "the window never connected")

    def detach() -> None:
        while windows:
            windows.pop().close()
        until(lambda: not link.connected, "the window never disconnected")

    def publish(direction_deg: float, detection_state: str) -> None:
        assert windows, "attach the window before publishing a reading"
        windows[0].send_inputs(direction_deg, detection_state)
        until(
            lambda: (link.latest_inputs() or {}).get("direction_deg") == direction_deg,
            "the reading never arrived",
        )

    def close() -> None:
        detach()
        provider.close()
        sink.close()

    return Device(
        name="simulator",
        led_count=led_count,
        sink=sink,
        provider=provider,
        close=close,
        attach=attach,
        detach=detach,
        publish=publish,
        steerable_inputs=True,
    )


# -- the hardware -----------------------------------------------------------


def hardware_reachable() -> tuple[bool, str]:
    """Whether a reSpeaker can actually be talked to, and why not if it cannot.

    Enumeration is not enough. A device bound to the wrong driver, or one the
    process may not open, appears on the bus and refuses every transfer — and
    "no reSpeaker connected" would be the wrong thing to print when one is
    plugged in and the real answer is a permission. Probing with the same
    read-only command the transport uses as its heartbeat gives the true answer.
    """
    try:
        from respeaker_led.device import UsbTransport, xvf
    except Exception as exc:
        return False, f"the hardware package will not import: {exc}"

    try:
        device = xvf.find()
    except Exception as exc:
        return False, f"the USB backend is unavailable: {exc}"
    if device is None:
        return False, "no reSpeaker connected"

    try:
        device.read(UsbTransport.probe_command)
    except Exception as exc:
        return False, f"a reSpeaker is connected but unreachable: {exc}"
    finally:
        try:
            device.close()
        except Exception:
            pass
    return True, ""


def build_hardware() -> Device:
    from respeaker_led.device import (
        RING_LED_COUNT,
        ReSpeakerDoaProvider,
        ReSpeakerFrameSink,
        UsbTransport,
    )

    transport = UsbTransport()
    transport.start()
    until(lambda: transport.is_connected, "the reSpeaker never connected")

    sink = ReSpeakerFrameSink(transport, led_count=RING_LED_COUNT)
    provider = ReSpeakerDoaProvider(transport)

    def close() -> None:
        provider.close()
        sink.close()

    return Device(
        name="respeaker",
        led_count=RING_LED_COUNT,
        sink=sink,
        provider=provider,
        close=close,
        # Attaching already happened above; unplugging needs a person, and the
        # tests that need one say so by carrying the hardware marker.
        attach=lambda: None,
        detach=lambda: pytest.skip("unplugging the cable needs a person"),
        publish=lambda *_: None,
        steerable_inputs=False,
    )


# -- fixtures ---------------------------------------------------------------


@pytest.fixture(params=["simulator", "respeaker"])
def device(request) -> Iterator[Device]:
    """One device, built the same way whichever it is."""
    if request.param == "respeaker":
        reachable, reason = hardware_reachable()
        if not reachable:
            pytest.skip(reason)
        built = build_hardware()
    else:
        built = build_simulator()
    try:
        yield built
    finally:
        built.close()


@pytest.fixture(scope="session")
def direction_effect():
    """``direction_indicator`` as the catalogue really ships it.

    Loaded from the source rather than restated here. A device's readings are
    only correct against the schema effects actually use, and a copy of that
    schema living in the tests would be free to drift away from it. It is also
    the one definition that consumes what these devices produce, so the
    end-to-end test runs the real thing rather than a stand-in.
    """
    from lefx.authoring import import_effect_class, load_effect_source

    return import_effect_class(load_effect_source(DIRECTION_INDICATOR))
