from queue import Queue
from threading import Event, get_ident
from time import monotonic, sleep

import pytest

from lefx.sdk import parse_color, scale_color
from lefx.config_widget import PreviewRequest, PreviewSession
from lefx.config_widget.preview import PreviewWorker


def test_real_static_gradient_and_animation(catalogue):
    session = PreviewSession(catalogue.registry)
    session.start(PreviewRequest("solid_fill", {"color": "#204060", "brightness": 1},
                                 led_count=7), 10)
    assert session.frame(10).leds == (0x204060,) * 7
    sink = session.sink
    session.start(PreviewRequest("gradient_ring"), 20)
    assert sink.closed
    assert len(set(session.frame(20).leds)) > 3
    session.start(PreviewRequest("breathing_ring"), 30)
    assert session.frame(30).leds != session.frame(30.7).leds
    session.close()
    assert session.sink.closed
    with pytest.raises(RuntimeError, match="stopped"):
        session.frame(31)


def test_real_preset_and_timed_forms(catalogue):
    session = PreviewSession(catalogue.registry)
    try:
        preset = next(entry for entry in catalogue.entries()
                      if entry.definition.id == "solid_fill" and entry.preset)
        params = preset.resolve_config()
        session.start(PreviewRequest(preset.qualified_id), 3)
        assert session.frame(3).leds[0] == scale_color(parse_color(params["color"]), params["brightness"])
        session.start(PreviewRequest("success_event", {"duration_ms": 700}), 4)
        assert any(session.frame(4.2).leds)
        assert not any(session.frame(4.9).leds)
        session.start(PreviewRequest("countdown_ring", {"duration_ms": 1000}), 6)
        assert session.frame(6).leds != session.frame(6.6).leds
        assert not any(session.frame(7).leds)
    finally:
        session.close()


def test_controlled_overlay_push_and_isolated_pull(catalogue):
    session = PreviewSession(catalogue.registry)
    try:
        with pytest.raises(ValueError, match="progress"):
            session.start(PreviewRequest("level_meter"), 0)
        session.start(PreviewRequest("level_meter", inputs={"progress": 50}), 0)
        assert 0 < sum(color != 0 for color in session.frame(0).leds) < 12
        with pytest.raises(ValueError, match="direction_deg"):
            session.start(PreviewRequest("direction_indicator"), 0)
        session.start(PreviewRequest("direction_indicator", inputs={
            "direction_deg": 90, "detection_state": "speech",
        }), 0)
        assert any(session.frame(0.1).leds)
    finally:
        session.close()


def test_worker_replaces_jobs_and_releases_sink(catalogue):
    created = Queue()
    released = Event()
    caller = get_ident()

    class Observed(PreviewSession):
        def __init__(self):
            super().__init__(catalogue.registry)
            created.put(get_ident())

        def close(self):
            had_runtime = self.runtime is not None
            super().close()
            if had_runtime:
                released.set()

    worker = PreviewWorker(fps=100)
    request = PreviewRequest("solid_fill", {"color": "#123456", "brightness": 1})
    try:
        worker.play(Observed, request)
        assert created.get(timeout=2) != caller
        end = monotonic() + 3
        frame = worker.take()
        while frame is None and monotonic() < end:
            sleep(.015)
            frame = worker.take()
        assert frame.leds == (0x123456,) * 12
        worker.stop()
        assert released.wait(2)
        assert worker.take() is None
    finally:
        worker.close()
        assert worker.wait(2)
