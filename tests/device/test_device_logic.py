"""The reasoning inside each device, exercised without the device.

What the conformance suite cannot reach: change detection, payload validation,
what happens the moment a connection drops, what a window that misbehaves gets
told. These run against doubles and always run — the CI has no reSpeaker, and
this is the part that does not need one.

The complement is :mod:`tests.device.test_hardware`, which holds what a double
would only answer with whatever it was told to say.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from lefx.sdk import InputContext, OutputFrame
from lefx.device.respeaker import xvf
from lefx.device.respeaker.provider import ReSpeakerDoaProvider, decode_doa
from lefx.device.respeaker.sink import ReSpeakerFrameSink
from lefx.device.respeaker.transport import ConnectionState, UsbTransport
from lefx.device.simulated_respeaker import protocol
from lefx.device.simulated_respeaker.link import SimulatorLink
from lefx.device.simulated_respeaker.provider import SimulatorDoaProvider
from lefx.device.simulated_respeaker.sink import SimulatorFrameSink

from .conftest import FakeWindow, free_port, until

RING = xvf.RING_LED_COUNT


def context() -> InputContext:
    return InputContext(now=time.monotonic(), led_count=RING, config={}, previous_inputs={})


def ring_frame(color: int = 0x223344) -> OutputFrame:
    return OutputFrame(leds=tuple([color] * RING), timestamp=0.0)


# -- doubles ----------------------------------------------------------------


class FakeDevice:
    """A reSpeaker that answers from a script instead of from a bus."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, list]] = []
        self.doa: tuple = (90, 1)
        self.fail_with: Exception | None = None
        self.disposed = False
        self.dev = object()

    def write(self, name: str, data: list) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.writes.append((name, list(data)))

    def read(self, name: str):
        if self.fail_with is not None:
            raise self.fail_with
        return (3, 0, 0) if name == "VERSION" else self.doa


class FakeTransport:
    """Enough transport for the sink and the provider to be judged on their own."""

    probe_command = "VERSION"

    def __init__(self) -> None:
        self.is_connected = True
        self.writes: list[tuple[str, list]] = []
        self.reads: list[str] = []
        self.doa: tuple = (90, 1)
        self.fail_with: Exception | None = None
        self.last_error: str | None = None
        self.closed = 0
        self._dirty = True

    def consume_session_dirty(self) -> bool:
        dirty, self._dirty = self._dirty, False
        return dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def write(self, name: str, data: list) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.writes.append((name, list(data)))

    def read(self, name: str):
        self.reads.append(name)
        if self.fail_with is not None:
            raise self.fail_with
        return self.doa

    def close(self) -> None:
        self.closed += 1


# -- what the entry points build --------------------------------------------


def test_the_two_hardware_halves_share_one_usb_connection():
    """Output and input are separate objects over *one* cable.

    Separate so a failing read cannot take the LEDs down with it; one cable
    because there is one, and two transports would spend their time taking it
    from each other.
    """
    from lefx.device.respeaker import registration

    registration.reset_shared_transport()
    try:
        # The service passes the same keywords to every installed factory, so
        # an unfamiliar one has to be tolerated rather than raise.
        sink = registration.create_frame_sink(led_count=12, host="ignored")
        provider = registration.create_doa_provider(led_count=12, host="ignored")
        assert sink.transport is provider.transport
    finally:
        registration.reset_shared_transport()


def test_the_two_simulator_halves_share_one_link():
    """The same arrangement, for the same reason: one window, one connection."""
    from lefx.device.simulated_respeaker import registration

    registration.reset_shared_link()
    try:
        sink = registration.create_frame_sink(led_count=12, port=0, force_claim="ignored")
        provider = registration.create_doa_provider(led_count=12, force_claim="ignored")
        assert sink.link is provider.link
        assert sink.link.led_count == 12
    finally:
        registration.reset_shared_link()


# -- the USB transport ------------------------------------------------------


def test_a_device_that_enumerates_but_refuses_transfers_is_not_connected():
    """Being on the bus is not being reachable.

    A reSpeaker on the wrong driver enumerates and then denies every transfer.
    Calling that "connected" would push the discovery into the frame path, one
    failed write at a time, instead of answering it once here.
    """
    device = FakeDevice()
    device.fail_with = OSError("Access denied (insufficient permissions)")
    transport = UsbTransport(
        retry_interval_s=0.01, heartbeat_interval_s=0.01, finder=lambda: device
    )
    transport.start()
    try:
        time.sleep(0.1)
        assert transport.is_connected is False
        assert "Access denied" in (transport.last_error or "")
    finally:
        transport.close()


def test_the_transport_connects_and_reconnects():
    present = [True]
    device = FakeDevice()
    transport = UsbTransport(
        retry_interval_s=0.01,
        heartbeat_interval_s=0.01,
        finder=lambda: device if present[0] else None,
    )
    transport.start()
    try:
        until(lambda: transport.is_connected, "never connected")

        present[0] = False
        device.fail_with = OSError("cable pulled")
        until(lambda: not transport.is_connected, "never noticed the unplug")
        assert transport.state is ConnectionState.DISCONNECTED

        device.fail_with = None
        present[0] = True
        until(lambda: transport.is_connected, "never came back")
        assert transport.stats()["connect_count"] >= 2
    finally:
        transport.close()


def test_a_write_failure_disconnects_and_is_reported_to_the_caller():
    device = FakeDevice()
    transport = UsbTransport(
        retry_interval_s=60.0, heartbeat_interval_s=60.0, finder=lambda: device
    )
    transport.start()
    try:
        until(lambda: transport.is_connected, "never connected")
        device.fail_with = OSError("pipe error")
        with pytest.raises(OSError):
            transport.write("LED_EFFECT", [5])
        assert transport.is_connected is False
        assert "pipe error" in (transport.last_error or "")
    finally:
        transport.close()


def test_lifecycle_callbacks_run_off_the_caller_thread():
    """Listeners must not inherit the transport's locks.

    A listener taking its own lock, called while the I/O lock is held, would
    deadlock against a render thread holding that lock and waiting for I/O.
    """
    seen: list[str] = []
    ready = threading.Event()
    device = FakeDevice()

    def on_connected() -> None:
        seen.append(threading.current_thread().name)
        ready.set()

    transport = UsbTransport(
        retry_interval_s=0.01,
        heartbeat_interval_s=60.0,
        finder=lambda: device,
        on_connected=on_connected,
    )
    transport.start()
    try:
        assert ready.wait(2.0)
        assert seen and "respeaker-usb-monitor" not in seen[0]
    finally:
        transport.close()


def test_the_transport_never_stops_another_process_unless_asked(monkeypatch):
    """Force-claiming is opt-in, and the default path must not reach it at all."""
    from lefx.device.respeaker import contention

    calls: list[object] = []
    monkeypatch.setattr(contention, "release_device", lambda *a, **k: calls.append(1))

    device = FakeDevice()
    device.fail_with = OSError("Access denied (insufficient permissions)")
    transport = UsbTransport(
        retry_interval_s=0.01, heartbeat_interval_s=0.01, finder=lambda: device
    )
    transport.start()
    try:
        time.sleep(0.15)
        assert calls == []
        assert transport.is_connected is False
    finally:
        transport.close()


def test_an_absent_device_is_not_treated_as_contention(monkeypatch):
    """Nothing plugged in is not somebody else holding it.

    Hunting for a process to stop because a cable is out would be both useless
    and, given what it does when it finds one, worse than useless.
    """
    from lefx.device.respeaker import contention

    calls: list[object] = []
    monkeypatch.setattr(contention, "release_device", lambda *a, **k: calls.append(1))

    transport = UsbTransport(
        retry_interval_s=0.01,
        heartbeat_interval_s=0.01,
        finder=lambda: None,
        force_claim=True,
    )
    transport.start()
    try:
        time.sleep(0.15)
        assert calls == []
    finally:
        transport.close()


def test_force_claim_runs_once_and_then_reconnects(monkeypatch):
    from lefx.device.respeaker import contention

    device = FakeDevice()
    device.fail_with = OSError("Access denied (insufficient permissions)")
    calls: list[object] = []

    def release(probe, **kwargs):
        del probe, kwargs
        calls.append(1)
        device.fail_with = None  # the other process let go
        return contention.ReleaseReport(reachable_before=False, reachable_after=True)

    monkeypatch.setattr(contention, "release_device", release)
    monkeypatch.setattr(contention, "device_probe", lambda *a, **k: lambda: True)

    transport = UsbTransport(
        retry_interval_s=0.01,
        heartbeat_interval_s=0.01,
        finder=lambda: device,
        force_claim=True,
    )
    transport.start()
    try:
        until(lambda: transport.is_connected, "the claim never led to a connection")
        # The retry loop runs every few milliseconds here. Stopping processes on
        # that schedule would be a menace, so it happens once per connection.
        time.sleep(0.15)
        assert calls == [1]
    finally:
        transport.close()


def test_a_claim_that_does_not_help_is_not_repeated_every_retry(monkeypatch):
    from lefx.device.respeaker import contention

    device = FakeDevice()
    device.fail_with = OSError("Access denied (insufficient permissions)")
    calls: list[object] = []

    def release(probe, **kwargs):
        del probe, kwargs
        calls.append(1)
        return contention.ReleaseReport(
            reachable_before=False, reachable_after=False, note="nothing eligible"
        )

    monkeypatch.setattr(contention, "release_device", release)
    monkeypatch.setattr(contention, "device_probe", lambda *a, **k: lambda: False)

    transport = UsbTransport(
        retry_interval_s=0.01,
        heartbeat_interval_s=0.01,
        finder=lambda: device,
        force_claim=True,
    )
    transport.start()
    try:
        time.sleep(0.2)
        assert calls == [1]
        assert transport.is_connected is False
        # last_error keeps reporting the current problem — access is still
        # denied. What the claim concluded is separate information, and lives
        # where it does not overwrite it.
        assert "Access denied" in (transport.last_error or "")
        assert "nothing eligible" in (transport.stats()["last_claim"] or "")
    finally:
        transport.close()


def test_closing_the_transport_twice_is_not_an_error():
    transport = UsbTransport(finder=lambda: None)
    transport.start()
    transport.close()
    transport.close()
    assert transport.is_connected is False


# -- the hardware sink ------------------------------------------------------


def test_the_ring_mode_is_asserted_once_and_unchanged_frames_are_skipped():
    """USB writes are the expensive part of a frame; a still ring costs nothing."""
    transport = FakeTransport()
    sink = ReSpeakerFrameSink(transport)

    sink.apply_frame(ring_frame(0x010203))
    sink.apply_frame(ring_frame(0x010203))
    sink.apply_frame(ring_frame(0x040506))

    assert [name for name, _ in transport.writes] == [
        "LED_EFFECT",
        "LED_RING_COLOR",
        "LED_RING_COLOR",
    ]


def test_a_reconnected_device_is_told_the_ring_mode_again():
    """It forgot everything with the old handle, including that it is a ring."""
    transport = FakeTransport()
    sink = ReSpeakerFrameSink(transport)
    sink.apply_frame(ring_frame(0x010203))
    transport.writes.clear()

    transport.mark_dirty()
    sink.apply_frame(ring_frame(0x010203))

    assert [name for name, _ in transport.writes] == ["LED_EFFECT", "LED_RING_COLOR"]


def test_a_frame_sent_while_disconnected_is_not_an_exception():
    transport = FakeTransport()
    transport.is_connected = False
    transport.last_error = "cable pulled"
    sink = ReSpeakerFrameSink(transport)

    sink.apply_frame(ring_frame())

    assert transport.writes == []
    assert sink.status().available is False
    # The transport owns the explanation while the cable is out.
    assert sink.status().detail == "cable pulled"


def test_a_write_failure_is_absorbed_and_surfaces_in_status():
    transport = FakeTransport()
    sink = ReSpeakerFrameSink(transport)
    transport.fail_with = OSError("pipe error")

    sink.apply_frame(ring_frame())

    status = sink.status()
    assert status.available is False
    assert "pipe error" in (status.detail or "")


def test_recovery_after_a_failed_write_resends_everything():
    """Nothing may be skipped as "unchanged" against a device that never got it."""
    transport = FakeTransport()
    sink = ReSpeakerFrameSink(transport)
    sink.apply_frame(ring_frame(0x010203))
    transport.fail_with = OSError("pipe error")
    sink.apply_frame(ring_frame(0x040506))
    transport.fail_with = None
    transport.writes.clear()

    sink.apply_frame(ring_frame(0x040506))

    assert [name for name, _ in transport.writes] == ["LED_EFFECT", "LED_RING_COLOR"]
    assert sink.status().available is True


def test_a_ring_size_the_device_does_not_have_is_reported_not_reshaped():
    """The ring size comes from the firmware's command table, not from a constant."""
    sink = ReSpeakerFrameSink(FakeTransport(), led_count=RING + 1)
    status = sink.status()
    assert status.available is False
    assert str(RING) in (status.detail or "")


# -- the DoA payload --------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ((0, 0), {"direction_deg": 0.0, "detection_state": "none"}),
        ((359, 1), {"direction_deg": 359.0, "detection_state": "sound"}),
        ((180, 0), {"direction_deg": 180.0, "detection_state": "none"}),
    ],
)
def test_a_well_formed_payload_decodes(payload, expected):
    assert decode_doa(payload) == expected


def test_silence_is_a_healthy_reading_not_a_failure():
    """The microphones heard nothing. That is an answer, not an error."""
    assert decode_doa((42, 0))["detection_state"] == "none"


@pytest.mark.parametrize(
    "payload",
    [
        (90,),
        (90, 1, 0),
        "not a payload",
        (360, 1),
        (-1, 1),
        (float("nan"), 1),
        (True, 1),
        (90, 7),
        (90, "yes"),
    ],
)
def test_a_malformed_payload_is_rejected(payload):
    with pytest.raises(ValueError):
        decode_doa(payload)


# -- the hardware provider --------------------------------------------------

def test_the_provider_reads_at_its_own_rate_not_the_render_rate():
    transport = FakeTransport()
    provider = ReSpeakerDoaProvider(transport, max_hz=10.0)

    now = time.monotonic()
    for step in range(30):
        # Thirty render frames inside one polling interval.
        provider.refresh(now + step * 0.001)

    assert len(transport.reads) == 1


def test_a_failed_read_drops_the_cached_direction():
    """A disconnected device has no current direction; the last one is not it."""
    transport = FakeTransport()
    provider = ReSpeakerDoaProvider(transport, max_hz=1000.0)
    provider.refresh(1.0)
    assert provider.sample(context()) == {"direction_deg": 90.0, "detection_state": "sound"}

    transport.fail_with = OSError("cable pulled")
    provider.refresh(2.0)

    assert provider.sample(context()) is None
    assert "cable pulled" in (provider.status(2.0)["last_error"] or "")


def test_a_malformed_reading_is_a_provider_error_not_a_bad_value():
    transport = FakeTransport()
    transport.doa = (999, 1)
    provider = ReSpeakerDoaProvider(transport, max_hz=1000.0)
    provider.refresh(1.0)

    assert provider.sample(context()) is None
    assert "out of range" in (provider.status(1.0)["last_error"] or "")


# -- the simulator protocol -------------------------------------------------


def test_a_message_survives_the_round_trip():
    message = protocol.frame((1, 2, 3), 12.5)
    encoded = protocol.encode(message)
    assert protocol.decode(encoded[protocol.HEADER_SIZE :]) == message


def test_framing_holds_when_the_stream_arrives_in_pieces():
    """TCP is a byte stream: two messages can arrive as one read, and one as two."""

    class TrickleSocket:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def recv(self, count: int) -> bytes:
            # One byte at a time — the worst case the length prefix exists for.
            chunk, self.data = self.data[:1], self.data[1:]
            del count
            return chunk

    stream = TrickleSocket(
        protocol.encode(protocol.hello(led_count=12))
        + protocol.encode(protocol.frame((7, 8), 1.0))
    )
    first = protocol.read_message(stream)
    second = protocol.read_message(stream)

    assert first["type"] == protocol.HELLO
    assert second["leds"] == [7, 8]


def test_a_clean_close_reads_as_the_end_not_as_an_error():
    class ClosedSocket:
        def recv(self, count: int) -> bytes:
            del count
            return b""

    assert protocol.read_message(ClosedSocket()) is None


def test_an_oversized_announcement_is_refused_before_it_is_read():
    with pytest.raises(protocol.ProtocolError):
        protocol.payload_length((protocol.MAX_MESSAGE_BYTES + 1).to_bytes(4, "big"))


# -- the simulator link -----------------------------------------------------


def test_a_port_that_cannot_be_bound_leaves_the_link_unavailable():
    """The service runs without a display, exactly as it runs without a cable."""
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    taken = blocker.getsockname()[1]
    link = SimulatorLink(host="127.0.0.1", port=taken)
    try:
        link.start()
        assert link.connected is False
        assert "cannot listen" in (link.detail() or "")
    finally:
        link.close()
        blocker.close()


def test_a_window_is_told_the_ring_size_when_it_connects():
    link = SimulatorLink(host="127.0.0.1", port=free_port(), led_count=24)
    link.start()
    window = FakeWindow(link.host, link.port)
    try:
        until(lambda: window.led_count == 24, "the ring size never arrived")
    finally:
        window.close()
        link.close()


def test_the_reading_is_dropped_when_the_last_window_goes():
    """Same meaning as an unplugged cable: nothing is measuring anything."""
    link = SimulatorLink(host="127.0.0.1", port=free_port())
    link.start()
    window = FakeWindow(link.host, link.port)
    try:
        until(lambda: link.connected, "the window never connected")
        window.send_inputs(45.0, "speech")
        until(lambda: link.latest_inputs() is not None, "the reading never arrived")

        window.close()
        until(lambda: not link.connected, "the disconnect went unnoticed")
        assert link.latest_inputs() is None
    finally:
        link.close()


def test_frames_reach_the_window():
    link = SimulatorLink(host="127.0.0.1", port=free_port(), led_count=4)
    link.start()
    sink = SimulatorFrameSink(link, led_count=4)
    window = FakeWindow(link.host, link.port)
    try:
        until(lambda: link.connected, "the window never connected")
        sink.apply_frame(OutputFrame(leds=(1, 2, 3, 4), timestamp=0.0))
        until(lambda: window.frames, "no frame arrived")
        assert window.frames[-1] == [1, 2, 3, 4]
    finally:
        window.close()
        sink.close()


@pytest.mark.parametrize("led_count", [1, 5, 12, 24])
def test_any_ring_size_travels_end_to_end(led_count):
    """The ring size is configuration, and the whole path carries it.

    Not just the frame: the window is told the size when it connects, because
    it has to draw the ring before the first frame arrives. Twelve is the
    hardware's number, not the system's.
    """
    link = SimulatorLink(host="127.0.0.1", port=free_port(), led_count=led_count)
    link.start()
    sink = SimulatorFrameSink(link, led_count=led_count)
    window = FakeWindow(link.host, link.port)
    try:
        until(lambda: window.led_count == led_count, "the ring size never arrived")
        for step in range(3):
            sink.apply_frame(OutputFrame(leds=tuple([step] * led_count), timestamp=float(step)))
            until(lambda: len(window.frames) > step, "a frame went missing")
        assert [frame[0] for frame in window.frames[:3]] == [0, 1, 2]
        assert all(len(frame) == led_count for frame in window.frames)
        assert sink.status().available is True
    finally:
        window.close()
        sink.close()


def test_black_stays_black_on_the_wire():
    """``0x000000`` is a colour that covers, not an LED that is off.

    Nothing may drop it on the way — a transport that treated zero as "nothing
    to send" would turn a deliberate black ring into whatever was there before.
    """
    link = SimulatorLink(host="127.0.0.1", port=free_port(), led_count=3)
    link.start()
    sink = SimulatorFrameSink(link, led_count=3)
    window = FakeWindow(link.host, link.port)
    try:
        until(lambda: link.connected, "the window never connected")
        sink.apply_frame(OutputFrame(leds=(0xFFFFFF,) * 3, timestamp=0.0))
        until(lambda: window.frames, "no frame arrived")
        sink.apply_frame(OutputFrame(leds=(0x000000,) * 3, timestamp=1.0))
        until(lambda: len(window.frames) > 1, "the black frame never arrived")
        assert window.frames[-1] == [0, 0, 0]
    finally:
        window.close()
        sink.close()


def test_a_closed_link_comes_back_when_it_is_started_again():
    """Both devices are reached through one shared instance per process.

    A service that stops closes it, and the next one in the same process starts
    it again. The USB transport revives there; the link has to as well, or the
    two devices would behave differently at exactly the point where the whole
    design says they must not.
    """
    link = SimulatorLink(host="127.0.0.1", port=free_port())
    link.start()
    assert link.detail() is not None and "no ring window" in link.detail()

    link.close()
    assert link.detail() == "simulator link closed"

    link.start()
    try:
        window = FakeWindow(link.host, link.port)
        until(lambda: link.connected, "the revived link accepted no window")
        window.close()
    finally:
        link.close()


def test_a_window_reporting_nonsense_is_held_to_the_same_contract_as_the_firmware():
    """A laxer simulator would stop being interchangeable with the hardware."""

    class FixedLink:
        def __init__(self, reading) -> None:
            self.reading = reading

        def latest_inputs(self):
            return self.reading

        def detail(self):
            return None

    provider = SimulatorDoaProvider(FixedLink({"direction_deg": 400.0, "detection_state": "sound"}))
    provider.refresh(1.0)
    assert provider.sample(context()) is None
    assert "out of range" in (provider.status(1.0)["last_error"] or "")

    provider = SimulatorDoaProvider(FixedLink({"direction_deg": 10.0, "detection_state": "shouting"}))
    provider.refresh(1.0)
    assert provider.sample(context()) is None
    assert "detection_state" in (provider.status(1.0)["last_error"] or "")


def test_a_null_direction_is_a_legitimate_reading():
    """The runtime input is nullable, and an effect has to survive it."""

    class NullLink:
        def latest_inputs(self):
            return {"direction_deg": None, "detection_state": "none"}

        def detail(self):
            return None

    provider = SimulatorDoaProvider(NullLink())
    provider.refresh(1.0)
    assert provider.sample(context()) == {"direction_deg": None, "detection_state": "none"}
