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


# -- review R01: the feed and the runtime say the same thing ------------------
#
# Each test names its finding in the first line of its docstring, so
# ``grep -rn "LAB-001-R01-F0" tests/`` lists the regression tests per finding.
# The device fixture leaves the service's own render thread running: these
# tests watch real engine ticks, not only frames rendered by hand.


def settle(session, ticks: int = 4, timeout: float = 1.0) -> None:
    """Let the service's render thread run a few frames, without judging them.

    A tick that raises does not count as a rendered frame, so waiting for the
    counter alone would hang on exactly the failure under test. This waits for
    the counter *or* the timeout, and leaves the verdict to the assertions.
    """
    service = session.service
    start = service.status()["service"]["render_count"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if service.status()["service"]["render_count"] >= start + ticks:
            return
        time.sleep(0.01)


def primary_state(session):
    layer = session.service.runtime.status()["layers"]["primary_state"]
    return None if layer is None else layer["effect_id"]


def test_a_reload_while_the_preview_is_paused_keeps_the_device_fed(device):
    """LAB-001-R01-F01: no further frame is needed after a catalogue reload.

    A paused preview sends nothing new, so a reconnect that waits for the next
    frame never comes. The feed has to be back before the engine's next tick —
    and no tick may fail in between, because a failed tick leaves the service
    reporting an error for as long as it runs.
    """
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)

    session.reload_sources()  # F5; the paused preview pushes nothing afterwards
    settle(session)

    assert session.service.status()["service"]["last_error"] is None
    assert sinks[-1].frames[-1] == FRAME
    assert primary_state(session) == FEED_ID
    assert output.active and output.carried


def test_after_a_reload_the_global_output_settings_still_work(device):
    """LAB-001-R01-F01: a reload must not leave an invocation nobody can resolve.

    Every command renders at once. With the feed's state still on its layer but
    its definition gone from the registry, even dimming the ring would fail.
    """
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    session.reload_sources()

    session.set_output(brightness=0.5)
    session.service.render_once(time.monotonic())

    assert sinks[-1].frames[-1] == tuple(scale_color(value, 0.5) for value in FRAME)


def test_switching_the_output_while_paused_feeds_the_new_device(device):
    """LAB-001-R01-F01: the same holds for a whole new service, not only a new registry."""
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)

    session.open("fake-respeaker")  # a new device, a new service, no push follows
    settle(session)

    assert sinks[0].closed
    assert sinks[-1].frames[-1] == FRAME
    assert session.service.status()["service"]["last_error"] is None


def test_stopping_after_a_reload_really_clears_the_device(device):
    """LAB-001-R01-F01: stop() must take the feed off even after a rebuild.

    It used to compare registry identities and give up on a mismatch — leaving
    the feed's state behind on a device the Lab said it had released.
    """
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    session.reload_sources()

    output.stop()
    settle(session)

    assert session.service.status()["service"]["last_error"] is None
    assert primary_state(session) is None
    assert sinks[-1].frames[-1] == (0,) * 12
    assert not output.active


def test_a_feed_that_cannot_come_back_is_ended_and_said_so(device, monkeypatch):
    """LAB-001-R01-F01: when restoring fails, the output is ended, not left half-alive.

    The other half of "restore or clearly deactivate": the Lab must stop
    claiming to send, the reason must reach whoever shows the status, and the
    engine must not be left with a state it cannot render.
    """
    session, sinks = device
    output = LabOutput(session)
    reasons: list[str] = []
    output.on_ended = reasons.append
    output.start(FRAME)

    def refuse() -> None:
        raise RuntimeError("Registrierung verweigert")

    monkeypatch.setattr(output, "_attach", refuse)
    session.reload_sources()
    settle(session)

    assert not output.active
    assert reasons and "Registrierung verweigert" in reasons[-1]
    assert session.service.status()["service"]["last_error"] is None
    assert primary_state(session) is None


def test_a_global_clear_ends_the_lab_output_instead_of_pretending(device):
    """LAB-001-R01-F02: after "Alles löschen" the Lab must not still claim to send.

    The clear takes the feed's state off the engine. A running preview keeps
    delivering frames, and the old output took each of them without noticing
    that nothing was showing them any more.
    """
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)

    session.clear_everything()  # Ausgabe → Alles löschen
    output.push(FRAME)          # the preview is running and keeps pushing
    settle(session)

    assert not output.active
    assert sinks[-1].frames[-1] == (0,) * 12
    assert primary_state(session) is None


def test_after_a_global_clear_sending_resumes_only_when_asked(device):
    """LAB-001-R01-F02: the resume rule — a clear ends sending until it is started again.

    A stray frame must not take the device back: the user just emptied it on
    purpose. Starting again is explicit, and then it works at once.
    """
    session, sinks = device
    output = LabOutput(session)
    output.start(FRAME)
    session.clear_everything()

    output.push(FRAME)  # a frame from the still-running preview
    settle(session)
    assert not output.active
    assert sinks[-1].frames[-1] == (0,) * 12

    output.start(FRAME)  # what ticking "An Ausgabe senden" again does
    settle(session)
    assert output.active and output.carried
    assert sinks[-1].frames[-1] == FRAME


def test_a_global_clear_is_reported_through_the_ended_callback(device):
    """LAB-001-R01-F02: the page learns about the end at once, with the reason given."""
    session, _ = device
    output = LabOutput(session)
    reasons: list[str] = []
    output.on_ended = reasons.append
    output.start(FRAME)

    session.clear_everything()
    assert output.verify(reason="Alles gelöscht") is False

    assert not output.active
    assert reasons == ["Alles gelöscht"]
    # And asking again changes nothing: there is nothing left to end.
    assert output.verify(reason="noch einmal") is False
    assert reasons == ["Alles gelöscht"]
