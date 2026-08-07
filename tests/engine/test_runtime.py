"""Lifecycles: activation, replacement, channels, the event queue and health."""

from __future__ import annotations

import pytest

from lefx.engine import (
    ChannelNotFoundError,
    CommandError,
    EffectRuntime,
    EngineConfig,
    InputHealth,
    LayerId,
    WrongTargetTypeError,
    build_registry,
    evaluate_health,
)
from lefx.sdk import InputContext, ParameterValidationError

from .sample_effects import ALL_EFFECTS


def runtime(**kwargs) -> EffectRuntime:
    return EffectRuntime(
        build_registry(ALL_EFFECTS), config=EngineConfig(led_count=4), **kwargs
    )


# -- states -----------------------------------------------------------------


def test_setting_a_state_is_idempotent():
    engine = runtime()
    first = engine.set_state("solid_state", now=0.0)
    second = engine.set_state("solid_state", now=1.0)
    assert first is not None and second is not None
    assert engine.store.active(LayerId.PRIMARY_STATE) is second


def test_a_new_state_replaces_the_previous_one_on_its_layer():
    engine = runtime()
    engine.set_state("solid_state", {"color": "red"}, now=0.0)
    engine.set_state("solid_state", {"color": "green"}, now=1.0)
    active = engine.store.active(LayerId.PRIMARY_STATE)
    assert active is not None
    assert active.params["color"] == "#00FF00"


def test_the_two_state_slots_are_independent():
    engine = runtime()
    engine.set_state("solid_state", {"color": "red"}, slot="background", now=0.0)
    engine.set_state("solid_state", {"color": "green"}, slot="primary", now=0.0)
    assert engine.store.active(LayerId.BACKGROUND_STATE) is not None
    assert engine.store.active(LayerId.PRIMARY_STATE) is not None

    engine.clear_state(slot="primary")
    assert engine.store.active(LayerId.PRIMARY_STATE) is None
    assert engine.store.active(LayerId.BACKGROUND_STATE) is not None


def test_off_and_toggle_are_explicit_while_plain_set_always_activates():
    engine = runtime()
    assert engine.set_state("solid_state", action="on", now=0.0) is not None
    assert engine.set_state("solid_state", action="off", now=1.0) is None
    assert engine.store.active(LayerId.PRIMARY_STATE) is None

    assert engine.set_state("solid_state", action="toggle", now=2.0) is not None
    assert engine.set_state("solid_state", action="toggle", now=3.0) is None


def test_an_unknown_action_is_refused():
    engine = runtime()
    with pytest.raises(CommandError, match="Unknown action"):
        engine.set_state("solid_state", action="flip", now=0.0)


def test_switching_off_a_different_target_leaves_the_layer_alone():
    engine = runtime()
    engine.set_state("solid_state", now=0.0)
    engine.set_state("background_only", action="off", slot="background", now=1.0)
    assert engine.store.active(LayerId.PRIMARY_STATE) is not None


def test_a_state_cannot_be_set_with_the_overlay_verb():
    engine = runtime()
    with pytest.raises(WrongTargetTypeError, match="is a state, not a overlay"):
        engine.set_overlay("solid_state", channel="x", now=0.0)


# -- controlled overlays ----------------------------------------------------


def test_a_controlled_overlay_needs_a_channel():
    engine = runtime()
    with pytest.raises(CommandError, match="requires a non-empty channel"):
        engine.set_overlay("direction_marker", now=0.0)


def test_the_channel_is_normalized_once_and_used_for_every_later_command():
    engine = runtime()
    engine.set_overlay("direction_marker", channel="  DoA  ", now=0.0)
    engine.update_overlay("doa", {"direction_deg": 90}, now=1.0)
    active = engine.store.find_channel("doa")
    assert active is not None
    assert active.inputs["direction_deg"] == 90.0
    engine.clear_overlay("DOA")
    assert engine.store.active(LayerId.CONTROLLED_OVERLAY) is None


def test_updating_an_unknown_channel_fails():
    engine = runtime()
    with pytest.raises(ChannelNotFoundError, match="doa"):
        engine.update_overlay("doa", {"direction_deg": 90}, now=0.0)


def test_a_partial_update_leaves_other_values_alone():
    engine = runtime()
    engine.set_overlay(
        "direction_marker", channel="doa", inputs={"direction_deg": 90}, now=0.0
    )
    engine.update_overlay("doa", {}, now=1.0)
    active = engine.store.find_channel("doa")
    assert active is not None and active.inputs["direction_deg"] == 90.0


def test_one_bad_field_rejects_the_whole_update():
    engine = runtime()
    engine.set_overlay(
        "direction_marker", channel="doa", inputs={"direction_deg": 90}, now=0.0
    )
    with pytest.raises(ParameterValidationError):
        engine.update_overlay("doa", {"direction_deg": 180, "unknown": 1}, now=1.0)
    active = engine.store.find_channel("doa")
    assert active is not None and active.inputs["direction_deg"] == 90.0


def test_a_declared_input_alias_is_accepted():
    engine = runtime()
    engine.set_overlay("direction_marker", channel="doa", now=0.0)
    engine.update_overlay("doa", {"direction": 120}, now=1.0)
    active = engine.store.find_channel("doa")
    assert active is not None and active.inputs["direction_deg"] == 120.0


def test_a_new_controlled_overlay_replaces_the_running_one():
    engine = runtime()
    engine.set_overlay("direction_marker", channel="doa", now=0.0)
    engine.set_overlay("direction_marker", channel="volume", now=1.0)
    assert engine.store.find_channel("doa") is None
    assert engine.store.find_channel("volume") is not None


def test_a_pull_overlay_does_not_accept_pushed_updates():
    engine = runtime()
    engine.set_overlay("pulled_marker", channel="doa", now=0.0)
    with pytest.raises(CommandError, match="does not accept pushed updates"):
        engine.update_overlay("doa", {"direction_deg": 90}, now=1.0)


# -- timed overlays ---------------------------------------------------------


def test_a_timed_overlay_takes_no_channel_and_no_inputs():
    engine = runtime()
    with pytest.raises(CommandError, match="has no channel"):
        engine.set_overlay("flash_overlay", channel="x", now=0.0)
    with pytest.raises(CommandError, match="has no runtime inputs"):
        engine.set_overlay("flash_overlay", inputs={"direction_deg": 1}, now=0.0)


def test_a_timed_overlay_supports_only_activation():
    engine = runtime()
    with pytest.raises(CommandError, match="supports only action 'on'"):
        engine.set_overlay("flash_overlay", action="toggle", now=0.0)


def test_a_timed_overlay_is_removed_when_its_time_is_up():
    engine = runtime()
    engine.set_overlay("flash_overlay", config={"duration_ms": 500}, now=0.0)
    engine.render_once(now=0.4)
    assert engine.store.active(LayerId.TIMED_OVERLAY) is not None
    engine.render_once(now=0.5)
    assert engine.store.active(LayerId.TIMED_OVERLAY) is None


def test_a_duration_override_is_only_honoured_where_it_is_declared():
    engine = runtime()
    overlay = engine.set_overlay("flash_overlay", now=0.0)
    assert overlay is not None and overlay.duration_ms == 600

    from lefx.engine import duration_from_config

    from .sample_effects import FlashOverlay, PulseEvent

    params = {"duration_ms": 600}
    assert duration_from_config(FlashOverlay.definition, params, override_ms=100) == 100
    with pytest.raises(CommandError, match="does not support a duration override"):
        duration_from_config(PulseEvent.definition, params, override_ms=100)


# -- events -----------------------------------------------------------------


def test_an_event_activates_immediately_when_the_layer_is_free():
    engine = runtime()
    invocation = engine.emit_event("pulse_event", now=0.0)
    assert invocation.is_active
    assert engine.store.active(LayerId.EVENT) is invocation


def test_a_running_event_is_never_cut_short():
    engine = runtime()
    first = engine.emit_event("pulse_event", now=0.0)
    second = engine.emit_event("critical_event", now=0.1)
    assert engine.store.active(LayerId.EVENT) is first
    assert not second.is_active


def test_priority_orders_the_queue_and_ties_keep_arrival_order():
    engine = runtime()
    engine.emit_event("pulse_event", now=0.0)          # runs
    engine.emit_event("pulse_event", now=0.1)          # queued, default priority
    engine.emit_event("pulse_event", now=0.2)          # queued, later
    engine.emit_event("critical_event", now=0.3)       # queued, higher priority

    queued = engine.store.layer(LayerId.EVENT).queue
    assert [item.effect_id for item in queued] == [
        "critical_event",
        "pulse_event",
        "pulse_event",
    ]
    assert queued[1].created_at < queued[2].created_at


def test_the_queue_advances_when_the_running_event_ends():
    engine = runtime()
    engine.emit_event("pulse_event", {"duration_ms": 500}, now=0.0)
    queued = engine.emit_event("critical_event", {"duration_ms": 500}, now=0.1)

    engine.render_once(now=0.5)
    assert engine.store.active(LayerId.EVENT) is queued
    assert queued.activated_at == 0.5


def test_an_event_duration_starts_when_it_becomes_visible():
    engine = runtime()
    engine.emit_event("pulse_event", {"duration_ms": 500}, now=0.0)
    queued = engine.emit_event("pulse_event", {"duration_ms": 500}, now=0.0)

    engine.render_once(now=0.5)
    assert queued.remaining_ms(0.5) == 500
    engine.render_once(now=0.9)
    assert engine.store.active(LayerId.EVENT) is queued
    engine.render_once(now=1.0)
    assert engine.store.active(LayerId.EVENT) is None


def test_an_explicit_priority_beats_the_declared_one():
    engine = runtime()
    engine.emit_event("pulse_event", now=0.0)
    engine.emit_event("critical_event", now=0.1)
    urgent = engine.emit_event("pulse_event", priority=1000, now=0.2)
    assert engine.store.layer(LayerId.EVENT).queue[0] is urgent


def test_an_event_cannot_be_emitted_with_the_state_verb():
    engine = runtime()
    with pytest.raises(WrongTargetTypeError, match="Use 'emit event'"):
        engine.set_state("pulse_event", now=0.0)


# -- input health -----------------------------------------------------------


def test_an_instance_without_a_value_starts_waiting():
    engine = runtime()
    invocation = engine.set_overlay("direction_marker", channel="doa", now=0.0)
    assert invocation is not None
    assert evaluate_health(invocation.definition, invocation, 0.0) is InputHealth.WAITING


def test_an_initial_value_counts_as_a_successful_reception():
    engine = runtime()
    invocation = engine.set_overlay(
        "direction_marker", channel="doa", inputs={"direction_deg": 90}, now=0.0
    )
    assert invocation is not None
    assert evaluate_health(invocation.definition, invocation, 0.0) is InputHealth.HEALTHY


def test_an_empty_update_is_a_heartbeat():
    engine = runtime()
    invocation = engine.set_overlay("direction_marker", channel="doa", now=0.0)
    assert invocation is not None
    engine.update_overlay("doa", {}, now=2.0)
    assert evaluate_health(invocation.definition, invocation, 2.5) is InputHealth.HEALTHY


def test_values_survive_the_grace_period_then_read_null():
    engine = runtime()
    engine.set_state("solid_state", {"color": "blue"}, now=0.0)
    engine.set_overlay(
        "direction_marker", channel="doa", config={"color": "green"},
        inputs={"direction_deg": 90}, now=0.0,
    )
    # Default policy: 1000ms heartbeat, 3 misses tolerated.
    assert engine.render_once(now=2.9).leds == (0x0000FF, 0x00FF00, 0x0000FF, 0x0000FF)
    assert engine.render_once(now=3.0).leds == (0x0000FF,) * 4


def test_health_is_reported_in_the_status():
    engine = runtime()
    engine.set_overlay(
        "direction_marker", channel="doa", inputs={"direction_deg": 90}, now=0.0
    )
    health = engine.status(now=1.5)["layers"]["controlled_overlay"]["input_health"]
    assert health["mode"] == "push"
    assert health["status"] == "healthy"
    assert health["missed_heartbeats"] == 1
    assert health["failure_after_ms"] == 3000
    assert health["last_error"] is None


# -- pull sampling ----------------------------------------------------------


def test_a_provider_supplies_values_without_the_package_touching_hardware():
    calls: list[InputContext] = []

    def provider(ctx: InputContext):
        calls.append(ctx)
        return {"direction_deg": 90.0}

    engine = EffectRuntime(
        build_registry(ALL_EFFECTS),
        config=EngineConfig(led_count=4),
        input_providers={"test_doa": provider},
    )
    engine.set_state("solid_state", {"color": "blue"}, now=0.0)
    engine.set_overlay("pulled_marker", channel="doa", config={"color": "green"}, now=0.0)

    assert engine.render_once(now=0.0).leds == (0x0000FF, 0x00FF00, 0x0000FF, 0x0000FF)
    assert calls and calls[0].led_count == 4


def test_a_missing_provider_is_a_health_problem_not_a_crash():
    engine = runtime()
    invocation = engine.set_overlay("pulled_marker", channel="doa", now=0.0)
    assert invocation is not None
    engine.render_once(now=0.0)
    assert invocation.input_error is not None
    assert "is not available" in invocation.input_error


def test_a_package_may_sample_its_own_values():
    engine = runtime()
    engine.set_state("solid_state", {"color": "blue"}, now=0.0)
    engine.set_overlay(
        "self_sampled_marker", channel="own", config={"color": "green"}, now=0.0
    )
    assert engine.render_once(now=0.0).leds == (0x00FF00, 0x0000FF, 0x0000FF, 0x0000FF)


def test_sampling_respects_the_declared_interval():
    calls: list[float] = []

    def provider(ctx: InputContext):
        calls.append(ctx.now)
        return {"direction_deg": 0.0}

    engine = EffectRuntime(
        build_registry(ALL_EFFECTS),
        config=EngineConfig(led_count=4),
        input_providers={"test_doa": provider},
    )
    engine.set_overlay("pulled_marker", channel="doa", now=0.0)
    for moment in (0.0, 0.01, 0.02):
        engine.render_once(now=moment)
    # interval_ms is 0 for this definition: one sample per frame.
    assert len(calls) == 3


# -- status -----------------------------------------------------------------


def test_status_reports_placement_without_naming_any_definition_specially():
    engine = runtime()
    engine.set_state("solid_state", {"color": "red"}, slot="background", now=0.0)
    engine.emit_event("pulse_event", now=0.0)
    status = engine.status(now=0.0)

    assert status["led_count"] == 4
    assert status["output"] == {"brightness": 1.0, "enabled": True}
    assert status["layers"]["background_state"]["slot"] == "background"
    assert status["layers"]["background_state"]["config"]["color"] == "#FF0000"
    assert status["layers"]["primary_state"] is None
    assert status["layers"]["event"]["effect_id"] == "pulse_event"


def test_clear_all_empties_every_layer():
    engine = runtime()
    engine.set_state("solid_state", now=0.0)
    engine.set_overlay("direction_marker", channel="doa", now=0.0)
    engine.emit_event("pulse_event", now=0.0)
    engine.clear_all()
    assert engine.store.ordered_active() == []
