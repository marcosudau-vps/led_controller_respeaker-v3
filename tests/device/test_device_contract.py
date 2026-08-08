"""The port contract, as something that runs.

Every test here is parametrised over the installed devices: the simulator always,
the reSpeaker when one is plugged in. That is what "the simulator is a device,
not a preview mode" means in practice — the claim is either checked by the same
assertions that check the hardware, or it is just a sentence in a README.

These tests describe the contract, never an implementation. Nothing below knows
what a socket or a USB endpoint is; the moment one of them needed to, the thing
it was checking would have stopped being shared.
"""

from __future__ import annotations

import time

import pytest

from lefx.sdk import FrameSink, InputContext, InputProvider, OutputFrame, SinkStatus
from lefx.sdk import normalize_runtime_inputs


def frame_of(device, color: int = 0x112233) -> OutputFrame:
    return OutputFrame(leds=tuple([color] * device.led_count), timestamp=time.time())


def context_for(device) -> InputContext:
    return InputContext(
        now=time.monotonic(), led_count=device.led_count, config={}, previous_inputs={}
    )


# -- the ports --------------------------------------------------------------


def test_both_halves_satisfy_the_declared_ports(device):
    assert isinstance(device.sink, FrameSink)
    assert isinstance(device.provider, InputProvider)


def test_output_and_input_are_separate_objects(device):
    """No isinstance test decides whether direction data is available.

    Registering the two halves separately is what lets one of them fail without
    the other, so they must not turn out to be the same object wearing two hats.
    """
    assert device.sink is not device.provider


# -- the sink ---------------------------------------------------------------


def test_a_frame_of_the_right_size_is_accepted(device):
    device.attach()
    device.sink.apply_frame(frame_of(device))
    assert device.sink.status().available is True


def test_apply_frame_does_not_raise_when_the_device_is_gone(device):
    """The rule that keeps the render loop free of device handling.

    A frame arrives thirty times a second; a device that went away between two
    of them is an ordinary condition, and one the sink answers in status()
    rather than by throwing at the engine.
    """
    device.detach()
    for _ in range(3):
        device.sink.apply_frame(frame_of(device))
    assert device.sink.status().available is False


def test_an_unavailable_sink_says_why(device):
    device.detach()
    status = device.sink.status()
    assert isinstance(status, SinkStatus)
    assert status.available is False
    assert status.detail, "an unavailable sink must carry a reason"


@pytest.mark.parametrize("difference", [-1, +1])
def test_a_frame_of_the_wrong_size_is_refused_rather_than_reshaped(device, difference):
    """Padding or truncating would light positions the sender never addressed.

    Both directions, because they fail differently: a short frame would leave
    the tail showing whatever it showed last, and a long one would be silently
    cut. A device says how many LEDs it has and takes exactly that many.
    """
    device.attach()
    wrong = max(1, device.led_count + difference)
    if wrong == device.led_count:
        pytest.skip("a one-LED ring has no shorter frame")
    device.sink.apply_frame(OutputFrame(leds=(0x00FF00,) * wrong, timestamp=0.0))
    assert device.sink.status().available is False


def test_closing_the_sink_twice_is_not_an_error(device):
    device.sink.close()
    device.sink.close()
    assert device.sink.status().available is False


# -- the provider -----------------------------------------------------------


def test_a_reading_validates_against_the_schema_effects_declare(device, direction_effect):
    """Whatever a device reports, an effect must be able to consume unchanged.

    Validated against ``direction_indicator``'s own runtime inputs, so both
    devices are held to the schema the catalogue really uses rather than to a
    restatement of it here.
    """
    device.attach()
    device.publish(137.0, "sound")
    device.provider.refresh(time.monotonic())

    sampled = device.provider.sample(context_for(device))
    if sampled is None:
        pytest.skip(f"{device.name} reported no direction to check")

    normalized = normalize_runtime_inputs(direction_effect.definition, sampled)
    assert 0.0 <= normalized["direction_deg"] < 360.0
    assert normalized["detection_state"] in ("none", "sound", "speech")

    if device.steerable_inputs:
        assert normalized["direction_deg"] == 137.0
        assert normalized["detection_state"] == "sound"


def test_sampling_returns_none_when_the_device_is_gone(device):
    """The same answer from both, so the engine needs only one behaviour.

    ``None`` becomes ``waiting`` and then, once the grace period lapses,
    ``failed``. A device that instead handed out its last reading would let an
    effect keep pointing somewhere nothing is being measured.
    """
    device.detach()
    device.provider.refresh(time.monotonic())
    assert device.provider.sample(context_for(device)) is None


def test_sampling_does_not_touch_the_device(device):
    """Ten overlays cost one device read per interval, not ten per frame.

    Sampling many times between refreshes must therefore change nothing: the
    reading is a cache, and only refresh fills it.
    """
    device.attach()
    now = time.monotonic()
    device.provider.refresh(now)

    before = device.provider.status(now)
    for _ in range(20):
        device.provider.sample(context_for(device))
    after = device.provider.status(now)

    counter = "poll_count" if "poll_count" in before else "refresh_count"
    assert after[counter] == before[counter]


def test_refresh_keeps_to_its_own_rate(device):
    """The provider polls on its schedule, not the render loop's."""
    interval = device.provider.interval_s
    now = time.monotonic()

    assert device.provider.refresh(now) is True
    assert device.provider.refresh(now + interval / 2.0) is False
    assert device.provider.refresh(now + interval * 1.5) is True


def test_the_provider_reports_its_own_state(device):
    status = device.provider.status(time.monotonic())
    assert status["provider_id"] == "doa"
    assert set(status) >= {"provider_id", "age_ms", "last_error", "available", "calibration"}


# -- the calibration --------------------------------------------------------


def test_a_device_reports_a_bearing_on_its_own_ring(device):
    """How the array is rotated against the LEDs is the device's business.

    Every device carries the rotation and applies it before handing the bearing
    out, so an effect gets a direction it can point at without knowing which
    way round anything was fitted — and without a per-device parameter of its
    own, which two devices would need two of.
    """
    from lefx.sdk import DoaCalibration

    device.attach()
    device.publish(90.0, "sound")

    turned = device.calibrated(DoaCalibration(angle_offset_deg=90.0))
    turned.refresh(time.monotonic())
    reading = turned.sample(context_for(device))
    if reading is None:
        pytest.skip(f"{device.name} reported no direction to check")

    assert 0.0 <= reading["direction_deg"] < 360.0
    assert turned.status(time.monotonic())["calibration"]["angle_offset_deg"] == 90.0

    if device.steerable_inputs:
        assert reading["direction_deg"] == pytest.approx(180.0)


def test_an_uncalibrated_device_hands_out_what_it_measured(device):
    """The default has to be the identity, or every reading would be adjusted
    by an amount nobody chose."""
    from lefx.sdk import DoaCalibration

    plain = device.calibrated(DoaCalibration())
    assert plain.status(time.monotonic())["calibration"] == {
        "angle_offset_deg": 0.0,
        "reverse": False,
    }


def test_closing_the_provider_twice_is_not_an_error(device):
    device.provider.close()
    device.provider.close()
    assert device.provider.sample(context_for(device)) is None


# -- through the service ----------------------------------------------------


def test_the_service_drives_the_device_end_to_end(device, direction_effect, tmp_path):
    """One pass through the real stack: commands in, a frame out at the device.

    Uses the shipped ``direction_indicator`` rather than a stand-in, because it
    is the definition that consumes what these devices produce — this is where
    "provider_id='doa' resolves to whichever device is attached" is actually
    exercised end to end.

    The sink is handed over as an object rather than by name: what is under test
    is the device, not entry point resolution, which the interfaces suite covers.
    """
    from lefx.engine import build_registry
    from lefx.interfaces import ControllerService

    from tests.engine.sample_effects import ALL_EFFECTS

    device.attach()
    device.publish(90.0, "sound")

    service = ControllerService(
        sink=device.sink,
        led_count=device.led_count,
        fps=60.0,
        search_paths=[],
        state_file=tmp_path / "background.json",
        autostart_providers=False,
    )
    service.providers = {"doa": device.provider}
    service.runtime.composer.set_input_providers({"doa": device.provider.sample})
    service.library._registry = build_registry(  # noqa: SLF001
        (*ALL_EFFECTS, direction_effect), source_id="test-set"
    )
    service.runtime.set_registry(service.library.registry)

    try:
        service.set_state("solid_state", {"color": "#FF0000"})
        service.set_overlay("direction_indicator", channel="doa")
        service.emit_event("pulse_event")
        service.render_once(time.monotonic())

        status = service.status()
        assert service.health()["sink"]["available"] is True
        assert status["input_providers"]["doa"]["provider_id"] == "doa"

        running = [
            entry
            for entry in status["layers"].values()
            if entry and entry["effect_id"] == "direction_indicator"
        ]
        assert running, "the controlled overlay should be on a layer"
        assert running[0]["input_health"]["provider_id"] == "doa"

        if device.steerable_inputs:
            # The whole chain, in one assertion: the window's slider reached an
            # effect that never named a device.
            assert running[0]["input_health"]["status"] == "healthy"
            assert running[0]["inputs"]["direction_deg"] == 90.0
    finally:
        # The device fixture owns the sink, so stopping the service here would
        # close it underneath the next test in this module.
        service.library.close()
