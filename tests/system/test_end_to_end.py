"""The whole system, from an HTTP request to a lit LED and back again.

Every other suite holds one layer still and checks the one next to it. This one
holds nothing still. The service picks its sink by name through the entry point
metadata, the sink is the real simulator device, the definitions are the ones
the catalogue actually ships, and the frames are read off the wire at the far
end — the same bytes the ring window draws.

Two claims can only be checked here, because they are claims about the joins:

* a command entering at the API comes out as pixels at a device, through the
  runtime and the renderer, for every one of the four lifecycle forms;
* a value produced *by* the device arrives at an effect that never named a
  device, and moving it moves the picture.

The window is driven over the protocol rather than through Qt. What is under
test is the path, and the path ends at the socket; drawing is the window's job
and is checked where the window is.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from lefx.engine import build_registry
from lefx.interfaces import API_PREFIX, ControllerService, create_app
from lefx.sdk import parse_color, scale_color

from tests.device.conftest import FakeWindow, until

LED_COUNT = 12
"""Twelve, so a direction maps to a whole LED: 0° is index 0, 180° is index 6."""

CORE_SOURCES = (
    "states/solid_fill",
    "overlays/level_meter",
    "overlays/direction_indicator",
    "events/pulse_signal",
)

RED = 0xFF0000
PULSE_COLOR = 0xFFB347
MARKER = scale_color(parse_color("#00C066"), 1.0)
METER = scale_color(parse_color("#00C0FF"), 0.9)


def hue_of(color: int) -> float:
    """Which colour it is, independent of how bright it is being shown.

    An event fades in and out, so its brightness at any moment belongs to the
    pulse curve rather than to the path a frame travelled. What the path has to
    preserve is that the colour arriving at the device is the event's.
    """
    import colorsys

    red, green, blue = (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF
    return colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)[0]


@pytest.fixture(scope="session")
def core_effects():
    """The shipped definitions, imported from source once.

    Loaded from ``effects/`` rather than restated: a test that agreed with a
    copy of the catalogue would keep agreeing after the catalogue changed.
    """
    from lefx.effect_creation import import_effect_class, load_effect_source

    from tests.architecture.scan import REPO_ROOT

    root = REPO_ROOT / "effects/core-set/sources"
    loaded = [import_effect_class(load_effect_source(root / name)) for name in CORE_SOURCES]
    return {effect.definition.id: effect for effect in loaded}


class Stack:
    """A running service with the simulator attached, and a window to watch it."""

    def __init__(self, service: ControllerService, client: TestClient) -> None:
        self.service = service
        self.client = client
        self.window: FakeWindow | None = None
        self.events: list[tuple[str, dict]] = []
        # Renders are driven from a clock that starts at the real one and is
        # moved forward by hand, so an event can be looked at part-way through
        # without anything having to wait for it. It only ever moves forward:
        # each rendered frame carries the moment it was rendered at, and that is
        # how a frame is matched to the call that caused it.
        #
        # It also never falls *behind* the real one — see ``render``. The app's
        # lifespan starts the service's own render thread, which polls on
        # time.monotonic(), and anything that rate-limits by comparing
        # timestamps would then see this clock go backwards.
        self.clock = time.monotonic()
        service.add_listener(lambda event, payload: self.events.append((event, payload)))

    # -- the window ---------------------------------------------------------

    @property
    def link(self):
        return self.service.sink.link

    def open_window(self) -> FakeWindow:
        self.window = FakeWindow(self.link.host, self.link.port)
        until(lambda: self.link.connected, "the ring window never connected")
        return self.window

    def close_window(self) -> None:
        assert self.window is not None
        self.window.close()
        until(lambda: not self.link.connected, "the ring window never disconnected")
        self.window = None

    def report(self, direction_deg: float | None, detection_state: str) -> None:
        """Move the window's controls, as a person would.

        Waits for the whole reading, not just the angle: turning the detection
        off without moving the slider changes only the second field, and a wait
        that watched the first would return before the message had arrived.
        """
        assert self.window is not None
        expected = {"direction_deg": direction_deg, "detection_state": detection_state}
        self.window.send_inputs(direction_deg, detection_state)
        until(
            lambda: self.link.latest_inputs() == expected,
            "the reading never reached the service",
        )

    # -- driving ------------------------------------------------------------

    def post(self, path: str, **payload):
        response = self.client.post(f"{API_PREFIX}/{path}", json=payload)
        assert response.status_code == 200, response.text
        return response.json()

    def status(self) -> dict:
        response = self.client.get(f"{API_PREFIX}/status")
        assert response.status_code == 200
        return response.json()

    def render(self, advance_s: float = 0.05) -> list[int]:
        """Render one frame and return the frame *that render* produced.

        Not simply the next one to arrive. A window that falls behind is sent
        the current ring rather than a backlog, so an earlier frame — the one a
        command rendered as it was accepted — can still be in flight and land
        first. Waiting for the render's own timestamp asks for the frame this
        call caused, which is the one the assertions are about.
        """
        # Ahead of the real clock, not merely ahead of the last hand-made
        # moment. The service's own render thread is running and refreshing the
        # input providers with time.monotonic(); a provider that polls at 30 Hz
        # skips any refresh less than 33 ms after its last attempt, and a
        # hand-made moment that had fallen behind real time would be exactly
        # that. The reading then never arrives, and the failure looks like a
        # device fault rather than two clocks disagreeing.
        self.clock = max(self.clock + advance_s, time.monotonic() + advance_s)
        moment = self.clock
        self.service.render_once(moment)
        if self.window is None:
            return []

        stamps = self.window.stamps
        until(
            lambda: any(stamp >= moment for stamp in list(stamps)),
            "the rendered frame never reached the window",
        )
        arrived = list(stamps)
        return self.window.frames[arrived.index(next(s for s in arrived if s >= moment))]

    def wait_out_the_grace_period(self, definition) -> None:
        """Really wait, because this is the one thing a clock cannot be told.

        The status endpoint reads the wall clock, so a render jumped forward
        would be judged against a time that never happened. How long is taken
        from the definition, which is where the grace period is declared.
        """
        time.sleep(definition.input_sampling.failure_after_ms / 1000.0 + 0.2)
        self.clock = max(self.clock, time.monotonic())
        self.service.render_once(self.clock)


def build_stack(tmp_path, core_effects, **device_options):
    from lefx.device.simulated_respeaker.registration import reset_shared_link

    reset_shared_link()
    service = ControllerService(
        # By name, so entry point discovery, the capability mapping and the
        # factories are all part of what this exercises. Port 0 keeps concurrent
        # runs off each other's socket.
        sink="simulator",
        led_count=LED_COUNT,
        fps=60.0,
        search_paths=[],
        state_file=tmp_path / "background.json",
        sink_options={"port": 0, **device_options},
    )
    service.library._registry = build_registry(  # noqa: SLF001
        tuple(core_effects.values()), source_id="core-set"
    )
    service.runtime.set_registry(service.library.registry)

    app = create_app(service)
    with TestClient(app) as client:
        built = Stack(service, client)
        built.open_window()
        try:
            yield built
        finally:
            if built.window is not None:
                built.window.close()
    service.stop()
    reset_shared_link()


@pytest.fixture
def stack(tmp_path, core_effects):
    yield from build_stack(tmp_path, core_effects)


@pytest.fixture
def calibrated_stack(tmp_path, core_effects):
    """The same stack, with the device turned a quarter of the way round."""
    yield from build_stack(tmp_path, core_effects, angle_offset_deg=90.0)


# -- the device the service found -------------------------------------------


def test_the_service_found_its_device_through_the_entry_points(stack):
    """Nothing above imported the simulator; the metadata is how it got here."""
    assert stack.service.sink_name == "simulator"
    assert type(stack.service.sink).__module__.startswith("lefx.device.simulated_respeaker")


def test_the_engine_is_offered_the_capability_and_not_the_device(stack):
    """``simulator.doa`` is what is installed; ``doa`` is what the engine sees."""
    assert set(stack.service.providers) == {"doa"}
    assert stack.service.providers["doa"].name == "simulator.doa"
    assert stack.service.input_device == "simulator"


# -- state: API -> service -> runtime -> renderer -> sink -------------------


def test_a_state_set_over_the_api_arrives_as_pixels_at_the_device(stack):
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    assert stack.render() == [RED] * LED_COUNT


def test_switching_the_state_replaces_what_the_device_shows(stack):
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.render()
    stack.post("set/state", target="solid_fill", config={"color": "#0000FF", "brightness": 1.0})
    assert stack.render() == [0x0000FF] * LED_COUNT


def test_output_settings_reach_the_device_without_touching_the_layers(stack):
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.render()

    stack.post("output", brightness=0.5)
    dimmed = stack.render()
    assert dimmed == [scale_color(RED, 0.5)] * LED_COUNT

    stack.post("output", enabled=False)
    assert stack.render() == [0x000000] * LED_COUNT

    stack.post("output", enabled=True, brightness=1.0)
    assert stack.render() == [RED] * LED_COUNT
    # Blanking the output is not clearing the layer: the state is still set.
    assert stack.status()["layers"]["primary_state"]["effect_id"] == "solid_fill"


# -- overlay: set, update, clear, all the way to the device ------------------


def test_an_overlay_on_a_channel_is_composed_over_the_state_at_the_device(stack):
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.post("set/overlay", target="level_meter", channel="job", inputs={"progress": 50})

    frame = stack.render()
    assert frame[:6] == [METER] * 6
    # The overlay is transparent where it does not draw, so the state shows.
    assert frame[6:] == [RED] * 6


def test_updating_the_channel_changes_the_picture_without_resetting_it(stack):
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.post("set/overlay", target="level_meter", channel="job", inputs={"progress": 25})
    assert stack.render()[:3] == [METER] * 3

    stack.post("update/overlay", channel="job", inputs={"progress": 100})
    assert stack.render() == [METER] * LED_COUNT


def test_clearing_the_channel_takes_the_overlay_off_the_device(stack):
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.post("set/overlay", target="level_meter", channel="job", inputs={"progress": 100})
    stack.render()

    stack.post("clear/overlay", channel="job")
    assert stack.render() == [RED] * LED_COUNT


# -- event: queue, render, lifecycle ----------------------------------------


def test_an_event_covers_the_state_and_then_gives_the_ring_back(stack):
    """The whole life of an event, watched from the far end of the wire."""
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    assert stack.render() == [RED] * LED_COUNT

    stack.post("emit/event", target="pulse_signal", config={"duration_ms": 600, "pulse_count": 2})
    # A quarter of the way in, the first pulse is at its peak: the whole ring
    # carries one shade of the event's colour and none of the state's. The exact
    # shade is the pulse curve, which the catalogue suite owns.
    lit = stack.render(advance_s=0.15)
    assert set(lit) != {RED}
    assert len(set(lit)) == 1
    assert hue_of(lit[0]) == pytest.approx(hue_of(PULSE_COLOR), abs=0.02)

    # Past its declared duration it is gone, and nothing had to clear it.
    assert stack.render(advance_s=0.6) == [RED] * LED_COUNT
    assert stack.status()["layers"]["event"] is None


def test_a_queued_event_takes_over_when_the_running_one_ends(stack):
    """Priority and queueing survive the trip through the API."""
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.post("emit/event", target="pulse_signal", config={"duration_ms": 400}, priority=1)
    stack.post("emit/event", target="pulse_signal", config={"duration_ms": 400}, priority=9)

    running = stack.status()["layers"]["event"]
    assert running is not None
    # A running event is never cut short, so the higher priority one waits.
    first_id = running["invocation_id"]

    stack.render(advance_s=0.5)
    later = stack.status()["layers"]["event"]
    assert later is not None
    assert later["invocation_id"] != first_id


# -- controlled overlay: the device's own readings reach an effect ----------


def test_the_direction_the_window_reports_moves_the_marked_led(stack):
    """The join this whole architecture exists for.

    A slider in one process moves an LED in another, through a definition that
    asks for the capability ``doa`` and has never heard of either device.
    """
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.post("set/overlay", target="direction_indicator", channel="doa",
               config={"brightness": 1.0})

    stack.report(0.0, "sound")
    frame = stack.render()
    assert frame[0] == MARKER
    assert frame[1:] == [RED] * (LED_COUNT - 1)

    stack.report(180.0, "sound")
    frame = stack.render()
    assert frame[6] == MARKER
    assert frame[:6] + frame[7:] == [RED] * (LED_COUNT - 1)

    # Silence is a healthy reading. The marker goes; the state stays.
    stack.report(180.0, "none")
    assert stack.render() == [RED] * LED_COUNT


def test_a_direction_between_two_leds_lights_both_at_the_device(stack):
    """Half the directions on a twelve-LED ring fall between LEDs.

    Zero degrees on a reSpeaker is where the cable enters — between the twelfth
    LED and the first — so this is the ordinary case, not the awkward one.
    """
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.post("set/overlay", target="direction_indicator", channel="doa",
               config={"brightness": 1.0})

    stack.report(15.0, "sound")
    frame = stack.render()
    half = scale_color(parse_color("#00C066"), 0.5)
    assert frame[0] == half
    assert frame[1] == half
    assert frame[2:] == [RED] * (LED_COUNT - 2)

    # And back to a single LED when the direction points straight at one.
    stack.report(30.0, "sound")
    frame = stack.render()
    assert frame[1] == MARKER
    assert frame[0] == RED and frame[2] == RED


def test_the_devices_calibration_moves_the_marker_and_the_effect_never_learns_of_it(
    calibrated_stack,
):
    """The whole reason the offset sits at the device.

    The definition is the one the catalogue ships, with its own
    ``angle_offset_deg`` left at zero. The marker still moves, because what
    arrived at the effect was already a bearing on the ring.
    """
    stack = calibrated_stack
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.post("set/overlay", target="direction_indicator", channel="doa",
               config={"brightness": 1.0})

    stack.report(0.0, "sound")
    frame = stack.render()

    # Measured at zero, drawn at 90° — a quarter of twelve LEDs along.
    assert frame[3] == MARKER
    assert frame[0] == RED

    overlay = next(
        entry for entry in stack.status()["layers"].values()
        if entry and entry["effect_id"] == "direction_indicator"
    )
    assert overlay["inputs"]["direction_deg"] == 90.0
    assert overlay["config"]["angle_offset_deg"] == 0.0
    assert stack.status()["input_providers"]["doa"]["calibration"] == {
        "angle_offset_deg": 90.0,
        "reverse": False,
    }


def test_the_effect_reads_the_capability_and_the_status_says_so(stack):
    stack.post("set/overlay", target="direction_indicator", channel="doa")
    stack.report(90.0, "speech")
    stack.render()

    status = stack.status()
    overlay = next(
        entry for entry in status["layers"].values()
        if entry and entry["effect_id"] == "direction_indicator"
    )
    assert overlay["input_health"]["provider_id"] == "doa"
    assert overlay["input_health"]["status"] == "healthy"
    assert overlay["inputs"] == {"direction_deg": 90.0, "detection_state": "speech"}
    assert status["input_providers"]["doa"]["available"] is True


# -- status, loss and recovery ----------------------------------------------


def test_a_closed_window_is_reported_and_the_service_keeps_running(stack):
    """Closing the display is an unplugged cable, and neither stops the service."""
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.render()
    assert stack.status()["service"]["sink"] == "simulator"
    assert stack.client.get("/health").json()["sink"]["available"] is True

    stack.close_window()
    stack.render()

    health = stack.client.get("/health").json()
    assert health["sink"]["available"] is False
    assert health["sink"]["detail"]
    assert health["running"] is not None
    # No engine state was invented for the occasion.
    assert stack.status()["layers"]["primary_state"]["effect_id"] == "solid_fill"


def test_losing_the_window_is_published_as_an_event_not_acted_on(stack):
    stack.post("set/state", target="solid_fill")
    stack.render()
    stack.close_window()
    stack.render()

    changes = [payload for event, payload in stack.events if event == "sink_changed"]
    assert changes, "the sink going away should be published"
    assert changes[-1]["available"] is False
    assert changes[-1]["sink"] == "simulator"


def test_input_health_moves_from_waiting_through_healthy_to_failed(stack, core_effects):
    stack.post("set/overlay", target="direction_indicator", channel="doa")

    def health() -> dict:
        return next(
            entry for entry in stack.status()["layers"].values()
            if entry and entry["effect_id"] == "direction_indicator"
        )["input_health"]

    assert health()["status"] == "waiting"

    stack.report(45.0, "sound")
    stack.render()
    assert health()["status"] == "healthy"

    stack.close_window()
    stack.wait_out_the_grace_period(core_effects["direction_indicator"].definition)

    assert health()["status"] == "failed"
    assert stack.service.status()["input_providers"]["doa"]["available"] is False
    # Failed means the values read null, not that the instance was taken down.
    assert health()["last_error"]


def test_the_window_can_be_reopened_and_everything_works_again(stack):
    """A device coming back is an ordinary event, not a restart."""
    stack.post("set/state", target="solid_fill", config={"color": "#FF0000", "brightness": 1.0})
    stack.post("set/overlay", target="direction_indicator", channel="doa",
               config={"brightness": 1.0})
    stack.report(0.0, "sound")
    stack.render()

    stack.close_window()
    stack.render()
    assert stack.service.sink.status().available is False

    stack.open_window()
    stack.report(180.0, "sound")
    frame = stack.render()

    assert stack.service.sink.status().available is True
    assert frame[6] == MARKER
    assert stack.status()["input_providers"]["doa"]["available"] is True


def test_a_failing_device_never_raises_into_the_render_loop(stack):
    """The render loop contains no device handling, so nothing may throw at it."""
    stack.post("set/state", target="solid_fill")
    stack.close_window()
    for _ in range(5):
        stack.render()
    assert stack.service.status()["service"]["last_error"] is None
