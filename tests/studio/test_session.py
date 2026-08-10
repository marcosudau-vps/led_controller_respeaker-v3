"""The studio's controller half, checked without a window.

Everything here is deliberately reachable with no display: what the studio
*does* is separable from how it is drawn, and this is the half that would
otherwise only ever be tested by a person clicking.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest

from lefx.sdk import OutputFrame, SinkStatus
from lefx.effect_creation.studio import catalogue, session as studio_session
from lefx.effect_creation.studio.session import StudioSession, TappedSink, available_outputs, device_in_use


class RecordingSink:
    name = "recording"

    def __init__(self) -> None:
        self.frames: list[OutputFrame] = []
        self.closed = False

    def apply_frame(self, frame: OutputFrame) -> None:
        self.frames.append(frame)

    def status(self) -> SinkStatus:
        return SinkStatus(available=True, detail=None)

    def close(self) -> None:
        self.closed = True


# -- the tap ----------------------------------------------------------------


def test_the_device_gets_the_frame_and_so_does_the_watcher():
    """One path, watched on the way past.

    A monitor that re-rendered the effect separately would agree with the device
    until it did not, and that moment is exactly when it is being relied on.
    """
    inner = RecordingSink()
    seen: list[tuple[int, ...]] = []
    tapped = TappedSink(inner, seen.append)

    tapped.apply_frame(OutputFrame(leds=(1, 2, 3), timestamp=0.0))

    assert [tuple(frame.leds) for frame in inner.frames] == [(1, 2, 3)]
    assert seen == [(1, 2, 3)]


def test_the_tap_reports_the_name_of_the_device_it_wraps():
    """The service derives the input device from the sink's name, so a wrapper
    that answered with its own would start the wrong device's providers."""
    assert TappedSink(RecordingSink()).name == "recording"


def test_a_watcher_that_raises_does_not_cost_the_device_a_frame():
    inner = RecordingSink()
    tapped = TappedSink(inner, lambda _frame: 1 / 0)

    tapped.apply_frame(OutputFrame(leds=(4, 5), timestamp=0.0))

    assert len(inner.frames) == 1


def test_closing_the_tap_closes_the_device():
    inner = RecordingSink()
    TappedSink(inner).close()
    assert inner.closed is True


# -- choosing an output -----------------------------------------------------


def test_the_outputs_offered_are_the_ones_installed():
    """Read from the entry points, like the service does. A machine without the
    hardware package is not offered hardware."""
    outputs = available_outputs()
    assert "null" in outputs
    assert "simulator" in outputs


def test_no_running_service_means_the_device_is_free(tmp_path, monkeypatch):
    monkeypatch.setenv("LEFX_STATE_ROOT", str(tmp_path))
    assert device_in_use() is None


@contextmanager
def a_live_process_that_is_not_this_one():
    """A pid that is certainly alive, certainly not ours, and ours to end.

    ``os.getppid()`` looks like the cheap way to get one and is not. Windows
    keeps no parent/child relationship, so the parent may already be gone by the
    time it is asked about — and its number may since have been recycled onto an
    unrelated process. Which of the two happens depends on how the test run was
    launched: a shell that waits keeps its child's parent alive, a short-lived
    launcher shim does not, and neither is under this test's control.

    A test that depends on the liveness of a process it did not start is flaky
    by construction. Starting one costs a few hundred milliseconds once and
    makes the answer the same everywhere.
    """
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield process.pid
    finally:
        process.kill()
        process.wait(timeout=10)


def test_a_running_service_is_reported_rather_than_fought_with(tmp_path, monkeypatch):
    """Two processes cannot hold one reSpeaker, and finding that out by watching
    writes fail is a poor way to be told."""
    from lefx.interfaces import hosting, paths

    monkeypatch.setenv("LEFX_STATE_ROOT", str(tmp_path))
    with a_live_process_that_is_not_this_one() as pid:
        assert pid != os.getpid()
        hosting.write_instance(
            paths.instance_file(),
            hosting.InstanceInfo(
                pid=pid,
                host="127.0.0.1",
                port=8765,
                requested_port=8765,
                started_at=time.time(),
                status="ready",
            ),
        )
        # Asked while the process is demonstrably running, not after.
        message = device_in_use()

    assert message is not None
    assert "8765" in message
    assert str(pid) in message


def test_an_abandoned_instance_file_does_not_block_the_studio(tmp_path, monkeypatch):
    """A service that was killed rather than stopped leaves its note behind.

    Refusing to open a device because of a message from a process that no longer
    exists would be a worse failure than the one being prevented.
    """
    from lefx.interfaces import hosting, paths

    monkeypatch.setenv("LEFX_STATE_ROOT", str(tmp_path))
    hosting.write_instance(
        paths.instance_file(),
        hosting.InstanceInfo(
            pid=2**30, host="127.0.0.1", port=8765, requested_port=8765,
            started_at=time.time(), status="ready",
        ),
    )
    assert device_in_use() is None


def test_a_stopping_service_is_not_in_the_way(tmp_path, monkeypatch):
    from lefx.interfaces import hosting, paths

    monkeypatch.setenv("LEFX_STATE_ROOT", str(tmp_path))
    hosting.write_instance(
        paths.instance_file(),
        hosting.InstanceInfo(
            pid=os.getpid(), host="127.0.0.1", port=8765, requested_port=8765,
            started_at=time.time(), status="stopping",
        ),
    )
    assert device_in_use() is None


# -- the session ------------------------------------------------------------


@pytest.fixture
def opened(tmp_path):
    session = StudioSession(led_count=12, fps=60.0, search_paths=[],
                            state_file=tmp_path / "background.json")
    session.open("null")
    try:
        yield session
    finally:
        session.close()


def test_opening_an_output_starts_a_controller(opened):
    assert opened.service is not None
    assert opened.output_name == "null"
    assert opened.sink_status().available is True


def test_switching_output_lets_go_of_the_previous_device(opened):
    """Building the next device before releasing the previous one would have
    them contend for the same endpoint."""
    first = opened.service
    opened.open("simulator", port=0)
    try:
        assert opened.service is not first
        assert opened.output_name == "simulator"
        # Naming the device is what starts *its* providers; the sink is handed
        # over as an object, so the service cannot work it out.
        assert opened.service.input_device == "simulator"
        assert set(opened.service.providers) == {"doa"}
    finally:
        opened.open("null")


def test_the_studio_sees_the_frames_its_effects_produce(tmp_path):
    from lefx.engine import build_registry

    from tests.engine.sample_effects import ALL_EFFECTS

    seen: list[tuple[int, ...]] = []
    session = StudioSession(led_count=4, fps=60.0, search_paths=[],
                            state_file=tmp_path / "background.json")
    session.set_frame_listener(seen.append)
    session.open("null")
    try:
        session.service.library._registry = build_registry(  # noqa: SLF001
            ALL_EFFECTS, source_id="test-set"
        )
        session.service.runtime.set_registry(session.service.library.registry)
        session.play_state("solid_state", {"color": "#FF0000"})
        assert seen, "playing a state should have produced a frame"
        assert len(seen[-1]) == 4
    finally:
        session.close()


def test_a_listener_can_be_swapped_while_an_output_is_open(opened):
    seen: list[tuple[int, ...]] = []
    opened.set_frame_listener(seen.append)
    opened.service.render_once(time.monotonic())
    assert seen

    opened.set_frame_listener(None)
    before = len(seen)
    opened.service.render_once(time.monotonic())
    assert len(seen) == before


def test_commands_need_an_output(tmp_path):
    session = StudioSession(search_paths=[], state_file=tmp_path / "background.json")
    with pytest.raises(RuntimeError, match="no output is open"):
        session.play_state("anything", {})


def test_closing_twice_is_not_an_error(opened):
    opened.close()
    opened.close()
    assert opened.service is None


# -- what the browser needs to know -----------------------------------------


def test_each_lifecycle_form_says_how_it_is_played():
    from tests.engine.sample_effects import ALL_EFFECTS

    verbs = {}
    for effect in ALL_EFFECTS:
        playback = catalogue.playback_for(effect.definition)
        verbs[effect.definition.kind.value] = playback.verb

    assert verbs["state"] == "state"
    assert verbs["event"] == "event"
    assert verbs["controlled_overlay"] == "overlay"


def test_an_event_is_never_replayed_by_a_moving_slider():
    """Emitting one thirty times a second because a control moved would be a
    different effect than the one under test."""
    from tests.engine.sample_effects import ALL_EFFECTS

    for effect in ALL_EFFECTS:
        playback = catalogue.playback_for(effect.definition)
        assert playback.repeatable is (effect.definition.kind.value != "event")


def test_a_controlled_overlay_is_addressed_by_channel():
    from tests.engine.sample_effects import ALL_EFFECTS

    controlled = [
        effect for effect in ALL_EFFECTS
        if effect.definition.kind.value == "controlled_overlay"
    ]
    assert controlled
    for effect in controlled:
        assert catalogue.playback_for(effect.definition).needs_channel is True


def test_the_studio_channel_is_its_own():
    """So clearing the studio's overlay cannot take down one something else set."""
    assert studio_session.STUDIO_CHANNEL == "studio"
