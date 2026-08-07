"""Name resolution, global uniqueness and presets."""

from __future__ import annotations

import pytest

from lefx.engine import (
    AmbiguousTargetError,
    EffectRegistry,
    Preset,
    RegistrationError,
    TargetNotFoundError,
    WrongTargetTypeError,
    build_registry,
)
from lefx.sdk import DefinitionType

from .sample_effects import ALL_EFFECTS, DirectionMarker, PulseEvent, SolidState


def registry() -> EffectRegistry:
    return build_registry(ALL_EFFECTS, source_id="core")


CALM = Preset(
    preset_id="solid_calm",
    source_id="core",
    effect_id="solid_state",
    params={"color": "#4A7BFF", "brightness": 0.45},
    title="Solid Calm",
)


# -- resolution -------------------------------------------------------------


def test_the_short_id_is_the_canonical_form():
    assert registry().resolve("solid_state").effect.effect_id == "solid_state"


def test_qualified_and_package_forms_are_exact_aliases():
    reg = registry()
    for form in ("core::solid_state", "core.solid_state"):
        assert reg.resolve(form).effect.effect_id == "solid_state"


def test_a_miss_suggests_near_matches_and_runs_nothing():
    with pytest.raises(TargetNotFoundError) as exc_info:
        registry().resolve("solid_stat")
    assert "solid_state" in exc_info.value.suggestions
    assert "Did you mean" in str(exc_info.value)


def test_an_empty_target_is_a_miss():
    with pytest.raises(TargetNotFoundError):
        registry().resolve("   ")


def test_the_expected_form_is_checked_and_the_right_verb_suggested():
    reg = registry()
    with pytest.raises(WrongTargetTypeError, match="Use 'emit event'"):
        reg.resolve("pulse_event", expected_type=DefinitionType.STATE)
    with pytest.raises(WrongTargetTypeError, match="Use 'set overlay'"):
        reg.resolve("direction_marker", expected_type=DefinitionType.EVENT)


# -- global uniqueness ------------------------------------------------------


def test_a_definition_id_cannot_be_registered_twice():
    reg = registry()
    with pytest.raises(RegistrationError, match="already registered"):
        reg.register_effect(SolidState, source_id="other")


def test_a_preset_cannot_take_a_definition_id():
    reg = registry()
    with pytest.raises(RegistrationError, match="collides with a definition"):
        reg.register_preset(
            Preset(preset_id="solid_state", source_id="core", effect_id="solid_state")
        )


def test_a_definition_cannot_take_a_preset_id():
    reg = registry()
    reg.register_preset(CALM)

    class Clashing(SolidState):
        pass

    Clashing.definition = DirectionMarker.definition  # not reached; id check comes first
    with pytest.raises(RegistrationError):
        reg.register_preset(CALM)


def test_a_definition_and_a_preset_of_the_same_name_are_refused_either_way():
    reg = EffectRegistry()
    reg.register_effect(SolidState, source_id="core")
    reg.register_preset(CALM)
    assert reg.resolve("solid_calm").kind == "preset"
    assert reg.resolve("solid_state").kind == "definition"


# -- presets ----------------------------------------------------------------


def test_a_preset_resolves_to_its_definition_and_carries_its_configuration():
    reg = registry()
    reg.register_preset(CALM)
    resolved = reg.resolve("solid_calm")
    assert resolved.effect.effect_id == "solid_state"
    assert resolved.preset is not None
    assert resolved.preset.params["color"] == "#4A7BFF"


def test_a_preset_is_validated_when_it_is_registered():
    reg = registry()
    with pytest.raises(RegistrationError, match="does not satisfy the schema"):
        reg.register_preset(
            Preset(
                preset_id="broken",
                source_id="core",
                effect_id="solid_state",
                params={"color": "not-a-color"},
            )
        )


def test_a_preset_must_reference_a_known_definition():
    reg = registry()
    with pytest.raises(RegistrationError, match="unknown definition"):
        reg.register_preset(
            Preset(preset_id="orphan", source_id="core", effect_id="nothing_here")
        )


def test_preset_qualified_forms_resolve_too():
    reg = registry()
    reg.register_preset(CALM)
    for form in ("core::solid_calm", "core.solid_calm"):
        assert reg.resolve(form).preset is not None


def test_a_preset_does_not_restrict_what_a_caller_may_override():
    from lefx.engine import EffectRuntime, EngineConfig

    reg = registry()
    reg.register_preset(CALM)
    engine = EffectRuntime(reg, config=EngineConfig(led_count=2))
    engine.set_state("solid_calm", {"color": "rot"}, now=0.0)
    assert engine.render_once(now=0.0).leds == (0xFF0000, 0xFF0000)


# -- listings and sources ---------------------------------------------------


def test_listings_are_grouped_by_user_facing_type():
    reg = registry()
    states = [item.effect_id for item in reg.list_effects(definition_type=DefinitionType.STATE)]
    overlays = [
        item.effect_id for item in reg.list_effects(definition_type=DefinitionType.OVERLAY)
    ]
    events = [item.effect_id for item in reg.list_effects(definition_type=DefinitionType.EVENT)]

    assert states == ["background_only", "solid_state"]
    assert "flash_overlay" in overlays and "direction_marker" in overlays
    assert events == ["critical_event", "pulse_event"]


def test_removing_a_source_takes_its_definitions_and_presets_with_it():
    reg = registry()
    reg.register_preset(CALM)
    reg.remove_source("core")
    assert len(reg) == 0
    assert reg.list_presets() == []
    with pytest.raises(TargetNotFoundError):
        reg.resolve("core::solid_state")


def test_a_class_without_a_definition_is_refused():
    reg = EffectRegistry()

    class NotAnEffect:
        pass

    with pytest.raises(RegistrationError, match="does not declare a LEFX V3 definition"):
        reg.register_effect(NotAnEffect, source_id="core")  # type: ignore[arg-type]
