"""The Studio Lab's clock and its way to the device, without a window.

The output tests use the session's real path — embedded service, engine,
TappedSink — with a recording sink standing in for the reSpeaker. No hardware
is touched; that the real device shows the same thing is a separate, manual
check.
"""

from __future__ import annotations

import time

import pytest

from lefx.sdk import OutputFrame, SinkStatus, scale_color
from lefx.effect_creation.studio import session as studio_session
from lefx.effect_creation.studio.lab.clock import PreviewClock
from lefx.effect_creation.studio.lab.output import FEED_ID, LabOutput
from lefx.effect_creation.studio.session import StudioSession


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


# -- the clock --------------------------------------------------------------


def test_preview_time_follows_the_monotonic_clock_not_the_frame_count():
    now = FakeTime()
    clock = PreviewClock(end=10.0, now=now)
    clock.play()
    now.now += 0.5
    assert clock.elapsed() == pytest.approx(0.5)
    assert clock.elapsed() == pytest.approx(0.5)  # asking again is not a frame
    now.now += 1.25
    assert clock.elapsed() == pytest.approx(1.75)


def test_pause_seek_and_speed():
    now = FakeTime()
    clock = PreviewClock(end=10.0, now=now)
    clock.play()
    now.now += 2.0
    clock.pause()
    now.now += 5.0
    assert clock.elapsed() == pytest.approx(2.0)
    clock.seek(7.5)
    assert clock.elapsed() == 7.5 and not clock.playing
    clock.set_speed(2.0)
    clock.play()
    now.now += 1.0
    assert clock.elapsed() == pytest.approx(9.5)
    clock.stop()
    assert clock.elapsed() == 0.0 and not clock.playing


def test_the_end_loops_or_holds():
    now = FakeTime()
    clock = PreviewClock(end=4.0, now=now)
    clock.play()
    now.now += 5.0
    assert clock.elapsed() == pytest.approx(1.0)
    clock.loop = False
    now.now += 10.0
    assert clock.elapsed() == 4.0 and not clock.playing
    clock.play()  # from the start again
    assert clock.elapsed() == 0.0


def test_seeking_is_clamped_to_the_range():
    clock = PreviewClock(end=3.0, now=FakeTime())
    clock.seek(-1)
    assert clock.elapsed() == 0.0
    clock.seek(99)
    assert clock.elapsed() == 3.0
    clock.set_range(0.0, 2.0)
    assert clock.elapsed() == 2.0


# -- the output -------------------------------------------------------------


class RecordingSink:
    name = "fake-respeaker"

    def __init__(self) -> None:
        self.frames: list[tuple[int, ...]] = []
        self.closed = False

    def apply_frame(self, frame: OutputFrame) -> None:
        self.frames.append(tuple(frame.leds))

    def status(self) -> SinkStatus:
        return SinkStatus(available=True, detail=None)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def device(tmp_path, monkeypatch):
    """A session opened on a fake hardware output; yields (session, sink)."""
    sinks: list[RecordingSink] = []

    def create_sink(name, **options):
        sink = RecordingSink()
        sinks.append(sink)
        return sink

    monkeypatch.setattr(studio_session.discovery, "create_sink", create_sink)
    session = StudioSession(led_count=12, fps=30.0, search_paths=[],
                            state_file=tmp_path / "background.json")
    session.open("fake-respeaker")
    try:
        yield session, sinks
    finally:
        session.close()


FRAME = (0xFF0000,) * 5 + (0,) * 4 + (0x0000FF,) * 3


def test_the_lab_frame_reaches_the_device_unchanged(device):
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    session.service.render_once(time.monotonic())
    assert sinks[-1].frames[-1] == FRAME
    assert output.active and output.is_hardware


def test_global_brightness_applies_on_the_device_path(device):
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    session.set_output(brightness=0.5)
    session.service.render_once(time.monotonic())
    assert sinks[-1].frames[-1] == tuple(scale_color(value, 0.5) for value in FRAME)


def test_a_new_frame_replaces_the_old_one(device):
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    output.push(tuple(reversed(FRAME)))
    session.service.render_once(time.monotonic())
    assert sinks[-1].frames[-1] == tuple(reversed(FRAME))


def test_a_ring_of_another_size_is_never_sent(device):
    session, sinks = device
    output = LabOutput(session)
    assert "16 LEDs" in output.problem(16)
    with pytest.raises(RuntimeError, match="nichts gesendet"):
        output.start((0xFFFFFF,) * 16)
    assert not output.active
    output.start(FRAME)
    output.push((0xFFFFFF,) * 16)
    assert not output.active  # stopped rather than reshaped


def test_the_takeover_ends_what_the_player_had_and_stop_clears_it(device):
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    assert session.service.runtime.status()["layers"]["primary_state"]["effect_id"] == FEED_ID
    output.stop()
    assert session.service.runtime.status()["layers"]["primary_state"] is None
    session.service.render_once(time.monotonic())
    assert sinks[-1].frames[-1] == (0,) * 12


def test_a_catalogue_reload_does_not_lose_the_feed(device):
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    session.reload_sources()  # builds a fresh registry without the feed
    output.push(FRAME)
    session.service.render_once(time.monotonic())
    assert sinks[-1].frames[-1] == FRAME


def test_switching_the_output_moves_the_feed_along(device):
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    session.open("fake-respeaker")  # a new device, a new service
    assert sinks[0].closed
    output.push(FRAME)
    session.service.render_once(time.monotonic())
    assert sinks[-1].frames[-1] == FRAME


def test_the_feed_is_not_persisted_as_background_state(device, tmp_path):
    session, _ = device
    LabOutput(session).start(FRAME)
    session.service.render_once(time.monotonic())
    assert not (tmp_path / "background.json").exists()


def test_without_an_open_output_nothing_is_sent(tmp_path):
    session = StudioSession(search_paths=[], state_file=tmp_path / "background.json")
    output = LabOutput(session)
    assert output.problem(12) == "Keine Ausgabe geöffnet."
    with pytest.raises(RuntimeError):
        output.start(FRAME)
    output.stop()  # harmless
