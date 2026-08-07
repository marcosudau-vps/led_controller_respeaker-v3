"""Payload-level validation: aliases, unknown fields and error aggregation."""

from __future__ import annotations

import pytest

from lefx.sdk import (
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    ParamDefinition,
    ParamType,
    ParameterValidationError,
    StateDefinition,
    initial_runtime_inputs,
    normalize_runtime_inputs,
    resolve_configuration,
)

COLOR = ParamDefinition(name="color", type=ParamType.COLOR, default="blue", aliases=("tint",))
BRIGHTNESS = ParamDefinition(
    name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=1.0
)
SEGMENT = ParamDefinition(name="segment_length", type=ParamType.INT, default=3, minimum=1, maximum=12)

STATE = StateDefinition(
    id="rotating_segment",
    title="Rotating Segment",
    description="A lit segment travelling around the ring.",
    parameter_schema={"color": COLOR, "brightness": BRIGHTNESS, "segment_length": SEGMENT},
    color_model=ColorModel.MONO,
)

DIRECTION = ParamDefinition(
    name="direction_deg",
    type=ParamType.ANGLE_DEG,
    required=True,
    nullable=True,
    aliases=("direction",),
)
DETECTION = ParamDefinition(
    name="detection_state",
    type=ParamType.ENUM,
    enum_values=("none", "sound", "speech"),
    default="none",
)

OVERLAY = ControlledOverlayDefinition(
    id="direction_indicator",
    title="Direction Indicator",
    description="Marks a direction supplied at runtime.",
    parameter_schema={"color": COLOR, "brightness": BRIGHTNESS},
    runtime_inputs={"direction_deg": DIRECTION, "detection_state": DETECTION},
    color_model=ColorModel.MONO,
    composition=CompositionMode.TRANSPARENT,
)


# -- configuration ----------------------------------------------------------


def test_configuration_resolves_defaults_preset_and_overrides_to_canonical_values():
    resolved = resolve_configuration(
        STATE,
        preset={"color": "gruen", "segment_length": 4},
        overrides={"brightness": "50%"},
    )
    assert resolved == {"color": "#00FF00", "brightness": 0.5, "segment_length": 4}


def test_explicit_values_win_over_the_preset():
    resolved = resolve_configuration(
        STATE, preset={"color": "green"}, overrides={"color": "rot"}
    )
    assert resolved["color"] == "#FF0000"


def test_resolution_is_total_even_with_an_empty_payload():
    assert set(resolve_configuration(STATE)) == set(STATE.parameter_schema)


def test_unknown_field_is_rejected_with_suggestions():
    with pytest.raises(ParameterValidationError) as exc_info:
        resolve_configuration(STATE, overrides={"colour": "red"})

    issue = exc_info.value.issues[0]
    assert issue.code == "unknown_field"
    assert issue.field == "config.colour"
    assert "color" in issue.suggestions


def test_every_problem_is_reported_at_once():
    with pytest.raises(ParameterValidationError) as exc_info:
        resolve_configuration(
            STATE, overrides={"colour": "red", "brightness": 5.0, "segment_length": "x"}
        )

    codes = {issue.field: issue.code for issue in exc_info.value.issues}
    assert codes == {
        "config.colour": "unknown_field",
        "config.brightness": "invalid_value",
        "config.segment_length": "invalid_value",
    }
    assert exc_info.value.to_dict()["code"] == "validation_failed"


def test_declared_alias_is_canonicalized():
    resolved = resolve_configuration(STATE, overrides={"tint": "rot"})
    assert resolved["color"] == "#FF0000"


def test_alias_and_canonical_name_cannot_be_sent_together():
    with pytest.raises(ParameterValidationError) as exc_info:
        resolve_configuration(STATE, overrides={"color": "red", "tint": "blue"})

    issue = exc_info.value.issues[0]
    assert issue.code == "conflicting_fields"
    assert issue.field == "config.tint"


def test_an_invalid_payload_changes_nothing():
    before = resolve_configuration(STATE)
    with pytest.raises(ParameterValidationError):
        resolve_configuration(STATE, overrides={"brightness": 9.0})
    assert resolve_configuration(STATE) == before


# -- runtime inputs ---------------------------------------------------------


def test_initial_inputs_cover_every_declared_key():
    assert initial_runtime_inputs(OVERLAY) == {
        "direction_deg": None,
        "detection_state": "none",
    }


def test_states_start_with_no_runtime_inputs():
    assert initial_runtime_inputs(STATE) == {}


def test_runtime_update_may_be_partial():
    assert normalize_runtime_inputs(OVERLAY, {"direction_deg": "90deg"}) == {
        "direction_deg": 90.0
    }


def test_empty_runtime_update_is_a_valid_heartbeat():
    assert normalize_runtime_inputs(OVERLAY, {}) == {}
    assert normalize_runtime_inputs(OVERLAY, None) == {}


def test_runtime_input_alias_is_canonicalized():
    assert normalize_runtime_inputs(OVERLAY, {"direction": 120}) == {"direction_deg": 120.0}


def test_configuration_field_is_not_accepted_as_a_runtime_input():
    with pytest.raises(ParameterValidationError) as exc_info:
        normalize_runtime_inputs(OVERLAY, {"brightness": 0.5})

    assert exc_info.value.issues[0].code == "unknown_field"
    assert exc_info.value.issues[0].field == "inputs.brightness"


def test_runtime_input_is_not_accepted_as_configuration():
    with pytest.raises(ParameterValidationError) as exc_info:
        resolve_configuration(OVERLAY, overrides={"direction_deg": 90})

    assert exc_info.value.issues[0].field == "config.direction_deg"


def test_nullable_runtime_input_accepts_null():
    assert normalize_runtime_inputs(OVERLAY, {"direction_deg": None}) == {"direction_deg": None}


def test_non_nullable_runtime_input_rejects_null():
    with pytest.raises(ParameterValidationError) as exc_info:
        normalize_runtime_inputs(OVERLAY, {"detection_state": None})

    assert exc_info.value.issues[0].field == "inputs.detection_state"


def test_one_bad_field_rejects_the_whole_update():
    with pytest.raises(ParameterValidationError):
        normalize_runtime_inputs(OVERLAY, {"direction_deg": 90, "detection_state": "loud"})
