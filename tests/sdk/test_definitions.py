"""Form rules: what each of the four definition types may and must declare."""

from __future__ import annotations

import dataclasses

import pytest

from lefx.sdk import (
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    DefinitionKind,
    DefinitionType,
    DurationField,
    EventDefinition,
    InputMode,
    InputSamplingPolicy,
    OverlayMode,
    ParamDefinition,
    ParamType,
    SchemaError,
    StateDefinition,
    StateSlot,
    TimedOverlayDefinition,
    resolved_default_configuration,
)

COLOR = ParamDefinition(name="color", type=ParamType.COLOR, default="blue")
BRIGHTNESS = ParamDefinition(
    name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=1.0
)
SPEED = ParamDefinition(name="speed", type=ParamType.FLOAT, default=1.0, minimum=0.05)
REVERSE = ParamDefinition(name="reverse", type=ParamType.BOOL, default=False)
DURATION = ParamDefinition(
    name="duration_ms", type=ParamType.DURATION_MS, default=600, minimum=1
)

MONO = {"color": COLOR, "brightness": BRIGHTNESS}


def state(**overrides) -> StateDefinition:
    kwargs: dict[str, object] = {
        "id": "sample_state",
        "title": "Sample",
        "description": "A sample state.",
        "parameter_schema": dict(MONO),
        "color_model": ColorModel.MONO,
    }
    kwargs.update(overrides)
    return StateDefinition(**kwargs)  # type: ignore[arg-type]


def controlled(**overrides) -> ControlledOverlayDefinition:
    kwargs: dict[str, object] = {
        "id": "sample_overlay",
        "title": "Sample",
        "description": "A sample controlled overlay.",
        "parameter_schema": dict(MONO),
        "color_model": ColorModel.MONO,
        "composition": CompositionMode.TRANSPARENT,
    }
    kwargs.update(overrides)
    return ControlledOverlayDefinition(**kwargs)  # type: ignore[arg-type]


def timed(**overrides) -> TimedOverlayDefinition:
    kwargs: dict[str, object] = {
        "id": "sample_timed",
        "title": "Sample",
        "description": "A sample timed overlay.",
        "parameter_schema": {**MONO, "duration_ms": DURATION},
        "color_model": ColorModel.MONO,
    }
    kwargs.update(overrides)
    return TimedOverlayDefinition(**kwargs)  # type: ignore[arg-type]


def event(**overrides) -> EventDefinition:
    kwargs: dict[str, object] = {
        "id": "sample_event",
        "title": "Sample",
        "description": "A sample event.",
        "parameter_schema": {**MONO, "duration_ms": DURATION},
        "color_model": ColorModel.MONO,
    }
    kwargs.update(overrides)
    return EventDefinition(**kwargs)  # type: ignore[arg-type]


# -- the four forms exist and report themselves consistently ----------------


def test_each_form_reports_its_kind_and_user_facing_vocabulary():
    assert state().kind is DefinitionKind.STATE
    assert state().definition_type is DefinitionType.STATE
    assert state().overlay_mode is None

    assert controlled().kind is DefinitionKind.CONTROLLED_OVERLAY
    assert controlled().definition_type is DefinitionType.OVERLAY
    assert controlled().overlay_mode is OverlayMode.CONTROLLED

    assert timed().overlay_mode is OverlayMode.TIMED
    assert event().definition_type is DefinitionType.EVENT
    assert event().overlay_mode is None


@pytest.mark.parametrize("factory", [state, timed, event])
def test_only_the_controlled_overlay_can_carry_runtime_inputs(factory):
    definition = factory()
    assert definition.runtime_input_schema == {}
    assert definition.input_sampling is None
    # Structural, not merely validated: there is no field to declare them on.
    field_names = {field.name for field in dataclasses.fields(definition)}
    assert "runtime_inputs" not in field_names
    assert "sampling" not in field_names


# -- identity and shared rules ----------------------------------------------


@pytest.mark.parametrize("bad_id", ["", "SampleState", "sample-state", "_hidden", "2fast"])
def test_definition_id_must_be_lowercase_snake_case(bad_id):
    with pytest.raises(SchemaError, match="snake_case"):
        state(id=bad_id)


def test_title_and_description_are_mandatory():
    with pytest.raises(SchemaError, match="must declare a title"):
        state(title="   ")
    with pytest.raises(SchemaError, match="must declare a description"):
        state(description="")


def test_schema_key_must_match_the_parameter_name():
    with pytest.raises(SchemaError, match="key/name mismatch"):
        state(parameter_schema={"colour": COLOR, "brightness": BRIGHTNESS})


def test_parameter_schema_is_immutable_after_construction():
    definition = state()
    with pytest.raises(TypeError):
        definition.parameter_schema["color"] = COLOR  # type: ignore[index]


# -- configuration is total -------------------------------------------------


def test_every_configuration_field_must_declare_a_default():
    bare = ParamDefinition(name="segment_length", type=ParamType.INT, minimum=1)
    with pytest.raises(SchemaError, match="must declare a default"):
        state(parameter_schema={**MONO, "segment_length": bare})


def test_configuration_must_not_be_required():
    required = ParamDefinition(name="segment_length", type=ParamType.INT, required=True, minimum=1)
    with pytest.raises(SchemaError, match="must declare a default instead"):
        state(parameter_schema={**MONO, "segment_length": required})


def test_configuration_may_be_nullable_to_express_transparency():
    """``None`` and black are different answers and both must be expressible.

    A background colour of ``None`` leaves the layer below visible; black hides
    it. Collapsing the two would cost the definition that distinction.
    """
    transparent_default = ParamDefinition(
        name="background_color", type=ParamType.COLOR, nullable=True, default=None
    )
    definition = state(parameter_schema={**MONO, "background_color": transparent_default})
    assert definition.parameter_schema["background_color"].default is None

    black_default = ParamDefinition(
        name="background_color", type=ParamType.COLOR, nullable=True, default="black"
    )
    assert black_default.default == "#000000"


def test_resolved_defaults_cover_every_declared_key():
    definition = state()
    assert resolved_default_configuration(definition) == {
        "color": "#0000FF",
        "brightness": 1.0,
    }


# -- colour model -----------------------------------------------------------


def test_color_model_requires_its_fields():
    with pytest.raises(SchemaError, match="requires config fields: secondary_color"):
        state(color_model=ColorModel.DUAL)
    with pytest.raises(SchemaError, match="requires config fields: colors"):
        state(color_model=ColorModel.PALETTE)


def test_colored_definition_must_declare_brightness():
    with pytest.raises(SchemaError, match="must declare config.brightness"):
        state(parameter_schema={"color": COLOR}, color_model=ColorModel.MONO)


def test_color_model_none_forbids_colour_configuration():
    with pytest.raises(SchemaError, match="declares color configuration"):
        state(color_model=ColorModel.NONE)
    with pytest.raises(SchemaError, match="must not declare brightness"):
        state(parameter_schema={"brightness": BRIGHTNESS}, color_model=ColorModel.NONE)


def test_random_range_needs_both_range_and_seed():
    color_range = ParamDefinition(
        name="color_range",
        type=ParamType.COLOR_RANGE,
        default={"hue": [0.0, 360.0], "saturation": [0.0, 1.0], "brightness": [0.0, 1.0]},
    )
    with pytest.raises(SchemaError, match="requires config fields: random_seed"):
        state(
            parameter_schema={"color_range": color_range, "brightness": BRIGHTNESS},
            color_model=ColorModel.RANDOM_RANGE,
        )


# -- visual flags -----------------------------------------------------------


def test_animated_and_speed_must_agree_in_both_directions():
    assert state(parameter_schema={**MONO, "speed": SPEED}, animated=True).animated
    with pytest.raises(SchemaError, match="must declare config.speed"):
        state(animated=True)
    with pytest.raises(SchemaError, match="not marked animated"):
        state(parameter_schema={**MONO, "speed": SPEED})


def test_directional_and_reverse_must_agree_in_both_directions():
    assert state(parameter_schema={**MONO, "reverse": REVERSE}, directional=True).directional
    with pytest.raises(SchemaError, match="must declare config.reverse"):
        state(directional=True)
    with pytest.raises(SchemaError, match="not marked directional"):
        state(parameter_schema={**MONO, "reverse": REVERSE})


# -- aliases share one namespace --------------------------------------------


def test_alias_must_not_shadow_a_canonical_field():
    aliased = ParamDefinition(name="color", type=ParamType.COLOR, default="blue", aliases=("brightness",))
    with pytest.raises(SchemaError, match="collides with a canonical field"):
        state(parameter_schema={"color": aliased, "brightness": BRIGHTNESS})


def test_two_fields_cannot_share_one_alias():
    a = ParamDefinition(name="color", type=ParamType.COLOR, default="blue", aliases=("tint",))
    b = ParamDefinition(name="background_color", type=ParamType.COLOR, default="black", aliases=("tint",))
    with pytest.raises(SchemaError, match="is shared by"):
        state(parameter_schema={"color": a, "background_color": b, "brightness": BRIGHTNESS})


def test_config_alias_cannot_shadow_a_runtime_input_name():
    aliased = ParamDefinition(
        name="color", type=ParamType.COLOR, default="blue", aliases=("direction_deg",)
    )
    direction = ParamDefinition(
        name="direction_deg", type=ParamType.ANGLE_DEG, required=True, nullable=True
    )
    with pytest.raises(SchemaError, match="collides with a canonical field"):
        controlled(
            parameter_schema={"color": aliased, "brightness": BRIGHTNESS},
            runtime_inputs={"direction_deg": direction},
        )


# -- state ------------------------------------------------------------------


def test_state_defaults_to_the_primary_slot():
    assert state().slots == (StateSlot.PRIMARY,)


def test_state_slots_must_be_present_and_unique():
    with pytest.raises(SchemaError, match="at least one slot"):
        state(slots=())
    with pytest.raises(SchemaError, match="declares a slot twice"):
        state(slots=(StateSlot.PRIMARY, StateSlot.PRIMARY))


def test_only_a_background_state_may_be_restorable():
    assert state(slots=(StateSlot.BACKGROUND,), restorable=True).restorable
    with pytest.raises(SchemaError, match="only the background state is persisted"):
        state(restorable=True)


@pytest.mark.parametrize("field_name", ["duration_ms", "total_ms"])
def test_state_cannot_declare_a_duration(field_name):
    duration = ParamDefinition(name=field_name, type=ParamType.DURATION_MS, default=600, minimum=1)
    with pytest.raises(SchemaError, match="states are indefinite"):
        state(parameter_schema={**MONO, field_name: duration})


# -- controlled overlay -----------------------------------------------------


def test_controlled_overlay_accepts_runtime_inputs_and_defaults_to_push():
    direction = ParamDefinition(
        name="direction_deg", type=ParamType.ANGLE_DEG, required=True, nullable=True
    )
    definition = controlled(runtime_inputs={"direction_deg": direction})
    assert definition.input_sampling.mode is InputMode.PUSH
    assert set(definition.runtime_input_schema) == {"direction_deg"}


def test_required_runtime_input_must_be_nullable():
    direction = ParamDefinition(name="direction_deg", type=ParamType.ANGLE_DEG, required=True)
    with pytest.raises(SchemaError, match="must be nullable"):
        controlled(runtime_inputs={"direction_deg": direction})


def test_optional_runtime_input_must_declare_a_default():
    detection = ParamDefinition(
        name="detection_state", type=ParamType.ENUM, enum_values=("none", "sound")
    )
    with pytest.raises(SchemaError, match="required or declare a default"):
        controlled(runtime_inputs={"detection_state": detection})


def test_runtime_input_cannot_shadow_configuration():
    shadow = ParamDefinition(name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=1.0)
    with pytest.raises(SchemaError, match="must not be able to shadow stable configuration"):
        controlled(runtime_inputs={"brightness": shadow})


def test_pull_sampling_requires_runtime_inputs():
    with pytest.raises(SchemaError, match="declares no runtime inputs"):
        controlled(sampling=InputSamplingPolicy(mode=InputMode.PULL))


def test_provider_id_requires_pull_mode_and_content():
    with pytest.raises(SchemaError, match="only allowed with pull sampling"):
        InputSamplingPolicy(mode=InputMode.PUSH, provider_id="doa")
    with pytest.raises(SchemaError, match="must not be empty"):
        InputSamplingPolicy(mode=InputMode.PULL, provider_id="  ")


def test_sampling_bounds_are_enforced():
    with pytest.raises(SchemaError, match="interval_ms must be >= 0"):
        InputSamplingPolicy(interval_ms=-1)
    with pytest.raises(SchemaError, match="heartbeat_interval_ms must be >= 100"):
        InputSamplingPolicy(heartbeat_interval_ms=50)
    with pytest.raises(SchemaError, match="max_missed_heartbeats must be >= 1"):
        InputSamplingPolicy(max_missed_heartbeats=0)


def test_failure_window_is_derived_from_the_heartbeat_settings():
    policy = InputSamplingPolicy(heartbeat_interval_ms=500, max_missed_heartbeats=4)
    assert policy.failure_after_ms == 2000


# -- finite forms -----------------------------------------------------------


@pytest.mark.parametrize("factory", [timed, event])
def test_finite_form_must_declare_the_duration_it_points_at(factory):
    with pytest.raises(SchemaError, match="has no config.total_ms"):
        factory(duration_field=DurationField.TOTAL_MS)


@pytest.mark.parametrize("factory", [timed, event])
def test_finite_form_cannot_declare_two_lengths(factory):
    total = ParamDefinition(name="total_ms", type=ParamType.DURATION_MS, default=600, minimum=1)
    with pytest.raises(SchemaError, match="declares both duration_ms and total_ms"):
        factory(parameter_schema={**MONO, "duration_ms": DURATION, "total_ms": total})


@pytest.mark.parametrize("factory", [timed, event])
def test_finite_form_defaults_to_no_duration_override(factory):
    assert factory().supports_duration_override is False
    assert factory(supports_duration_override=True).supports_duration_override is True


def test_event_accepts_a_default_priority():
    assert event().default_priority is None
    assert event(default_priority=610).default_priority == 610


def test_total_ms_is_a_valid_alternative_length():
    total = ParamDefinition(name="total_ms", type=ParamType.DURATION_MS, default=2000, minimum=1)
    definition = timed(
        parameter_schema={**MONO, "total_ms": total}, duration_field=DurationField.TOTAL_MS
    )
    assert definition.duration_field is DurationField.TOTAL_MS
