"""The zulässigkeit matrix: which companion field is allowed on which type.

Every rule gets a passing and a failing case. A rule with only a passing case is
not a rule — it is a coincidence.
"""

from __future__ import annotations

import pytest

from lefx.sdk import MISSING, ParamDefinition, ParamType, SchemaError, normalize_parameter_value

# One valid value per type, used to exercise defaults and normalization.
SAMPLE_VALUES: dict[ParamType, object] = {
    ParamType.BOOL: True,
    ParamType.INT: 3,
    ParamType.FLOAT: 1.5,
    ParamType.DURATION_MS: 500,
    ParamType.ANGLE_DEG: 90,
    ParamType.ENUM: "one",
    ParamType.COLOR: "red",
    ParamType.COLOR_LIST: ["red", "blue"],
    ParamType.GRADIENT: [{"at": 0.0, "color": "red"}, {"at": 1.0, "color": "blue"}],
    ParamType.COLOR_RANGE: {"hue": [0.0, 180.0], "saturation": [0.0, 1.0], "brightness": [0.0, 1.0]},
}

TYPES_WITH_BOUNDS = {
    ParamType.INT,
    ParamType.FLOAT,
    ParamType.DURATION_MS,
    ParamType.COLOR_LIST,
}

TYPES_WITH_UNITS = {
    ParamType.INT,
    ParamType.FLOAT,
    ParamType.DURATION_MS,
    ParamType.ANGLE_DEG,
    ParamType.COLOR_LIST,
}


def make(param_type: ParamType, **overrides) -> ParamDefinition:
    """A minimal valid declaration of ``param_type`` under a non-reserved name."""
    kwargs: dict[str, object] = {"name": "custom_value", "type": param_type}
    if param_type is ParamType.ENUM:
        kwargs["enum_values"] = ("one", "two")
    kwargs.update(overrides)
    return ParamDefinition(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("param_type", list(ParamType))
def test_every_type_is_declarable_and_normalizes_its_sample(param_type):
    param = make(param_type, default=SAMPLE_VALUES[param_type])
    assert param.has_default
    assert normalize_parameter_value(param, SAMPLE_VALUES[param_type]) == param.default


def test_type_must_be_the_enum_not_a_string():
    with pytest.raises(SchemaError, match="declares type"):
        ParamDefinition(name="custom_value", type="colour")  # type: ignore[arg-type]


# -- bounds -----------------------------------------------------------------


@pytest.mark.parametrize("param_type", sorted(TYPES_WITH_BOUNDS, key=lambda item: item.value))
def test_bounds_are_accepted_where_they_apply(param_type):
    param = make(param_type, minimum=0, maximum=8)
    assert param.minimum == 0
    assert param.maximum == 8


@pytest.mark.parametrize(
    "param_type",
    sorted(set(ParamType) - TYPES_WITH_BOUNDS, key=lambda item: item.value),
)
def test_bounds_are_rejected_where_they_do_not_apply(param_type):
    with pytest.raises(SchemaError, match="does not accept minimum or maximum"):
        make(param_type, minimum=0)


def test_inverted_bounds_are_rejected():
    with pytest.raises(SchemaError, match="exceeds maximum"):
        make(ParamType.FLOAT, minimum=1.0, maximum=0.0)


def test_integral_types_reject_fractional_bounds():
    with pytest.raises(SchemaError, match="integral"):
        make(ParamType.DURATION_MS, minimum=1.5)


def test_color_list_length_cannot_be_negative():
    with pytest.raises(SchemaError, match="minimum must be >= 0"):
        make(ParamType.COLOR_LIST, minimum=-1)


# -- enum values ------------------------------------------------------------


def test_enum_requires_values():
    with pytest.raises(SchemaError, match="must declare enum_values"):
        ParamDefinition(name="custom_value", type=ParamType.ENUM)


def test_enum_values_must_be_unique():
    with pytest.raises(SchemaError, match="duplicate enum_values"):
        ParamDefinition(name="custom_value", type=ParamType.ENUM, enum_values=("a", "a"))


@pytest.mark.parametrize(
    "param_type", sorted(set(ParamType) - {ParamType.ENUM}, key=lambda item: item.value)
)
def test_enum_values_are_rejected_on_other_types(param_type):
    with pytest.raises(SchemaError, match="does not accept enum_values"):
        make(param_type, enum_values=("a",))


# -- units ------------------------------------------------------------------


@pytest.mark.parametrize(
    "param_type",
    sorted(set(ParamType) - TYPES_WITH_UNITS, key=lambda item: item.value),
)
def test_units_are_rejected_where_they_are_meaningless(param_type):
    with pytest.raises(SchemaError, match="does not accept a unit"):
        make(param_type, unit="ms")


def test_unit_must_come_from_the_allowed_set_for_the_type():
    assert make(ParamType.DURATION_MS, unit="ms").unit == "ms"
    with pytest.raises(SchemaError, match="allows"):
        make(ParamType.DURATION_MS, unit="deg")
    with pytest.raises(SchemaError, match="allows"):
        make(ParamType.ANGLE_DEG, unit="ms")


# -- required and default ---------------------------------------------------


def test_required_and_default_are_mutually_exclusive():
    with pytest.raises(SchemaError, match="required and declares a default"):
        make(ParamType.COLOR, required=True, default="red")


def test_missing_is_distinguishable_from_a_null_default():
    assert make(ParamType.COLOR).default is MISSING
    assert make(ParamType.COLOR).has_default is False
    nullable = make(ParamType.COLOR, nullable=True, default=None)
    assert nullable.has_default is True
    assert nullable.default is None


def test_default_is_stored_in_canonical_form():
    assert make(ParamType.COLOR, default="blau").default == "#0000FF"
    assert make(ParamType.DURATION_MS, default="1.5s").default == 1500
    assert make(ParamType.ANGLE_DEG, default="450deg").default == 90.0


def test_invalid_default_fails_at_declaration_time():
    with pytest.raises(SchemaError, match="invalid default"):
        make(ParamType.COLOR, default="not-a-color")


def test_default_must_satisfy_its_own_bounds():
    with pytest.raises(SchemaError, match="invalid default"):
        make(ParamType.FLOAT, minimum=0.0, maximum=1.0, default=2.0)


def test_non_nullable_parameter_rejects_a_null_default():
    with pytest.raises(SchemaError, match="invalid default"):
        make(ParamType.COLOR, default=None)


# -- names and aliases ------------------------------------------------------


@pytest.mark.parametrize("name", ["", "Color", "my-color", "_private", "2color", "my color"])
def test_names_must_be_lowercase_snake_case(name):
    with pytest.raises(SchemaError, match="snake_case"):
        ParamDefinition(name=name, type=ParamType.COLOR)


def test_alias_must_differ_from_the_canonical_name():
    with pytest.raises(SchemaError, match="alias equal to its own name"):
        make(ParamType.COLOR, aliases=("custom_value",))


def test_duplicate_alias_is_rejected():
    with pytest.raises(SchemaError, match="alias 'tint' twice"):
        make(ParamType.COLOR, aliases=("tint", "tint"))


def test_malformed_alias_is_rejected():
    with pytest.raises(SchemaError, match="invalid alias"):
        make(ParamType.COLOR, aliases=("Tint",))


# -- reserved names ---------------------------------------------------------


def test_reserved_name_pins_its_type():
    with pytest.raises(SchemaError, match="must use type 'color'"):
        ParamDefinition(name="color", type=ParamType.INT)
    with pytest.raises(SchemaError, match="must use type 'bool'"):
        ParamDefinition(name="reverse", type=ParamType.INT)


def test_brightness_range_is_not_negotiable():
    ok = ParamDefinition(
        name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=1.0
    )
    assert ok.maximum == 1.0
    with pytest.raises(SchemaError, match="must declare maximum 1.0"):
        ParamDefinition(
            name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=255.0
        )
    with pytest.raises(SchemaError, match="must declare minimum 0.0"):
        ParamDefinition(name="brightness", type=ParamType.FLOAT, default=1.0, maximum=1.0)


def test_speed_must_declare_a_positive_minimum():
    assert ParamDefinition(name="speed", type=ParamType.FLOAT, default=1.0, minimum=0.1).minimum == 0.1
    with pytest.raises(SchemaError, match="minimum greater than zero"):
        ParamDefinition(name="speed", type=ParamType.FLOAT, default=1.0, minimum=0.0)


def test_duration_must_declare_a_minimum_of_at_least_one_millisecond():
    assert ParamDefinition(name="duration_ms", type=ParamType.DURATION_MS, default=600, minimum=1)
    with pytest.raises(SchemaError, match="minimum >= 1"):
        ParamDefinition(name="duration_ms", type=ParamType.DURATION_MS, default=600)


# -- value normalization ----------------------------------------------------


def test_percentages_are_only_accepted_where_the_range_makes_them_unambiguous():
    ratio = make(ParamType.FLOAT, minimum=0.0, maximum=1.0, default=1.0)
    percent = make(ParamType.FLOAT, minimum=0.0, maximum=100.0, default=0.0)
    unbounded = make(ParamType.FLOAT, default=0.0)

    assert normalize_parameter_value(ratio, "50%") == 0.5
    assert normalize_parameter_value(percent, "50%") == 50.0
    with pytest.raises(ValueError, match="does not accept a percentage"):
        normalize_parameter_value(unbounded, "50%")


def test_bounds_are_enforced_on_incoming_values():
    param = make(ParamType.INT, minimum=0, maximum=10, default=0)
    assert normalize_parameter_value(param, "7") == 7
    with pytest.raises(ValueError, match="must be <= 10"):
        normalize_parameter_value(param, 11)
    with pytest.raises(ValueError, match="must be >= 0"):
        normalize_parameter_value(param, -1)


def test_null_is_only_accepted_when_declared_nullable():
    with pytest.raises(ValueError, match="must not be null"):
        normalize_parameter_value(make(ParamType.COLOR, default="red"), None)
    assert normalize_parameter_value(make(ParamType.COLOR, nullable=True), None) is None


def test_enum_matching_ignores_case_but_not_meaning():
    param = make(ParamType.ENUM, default="one")
    assert normalize_parameter_value(param, "ONE") == "one"
    with pytest.raises(ValueError, match="must be one of"):
        normalize_parameter_value(param, "three")


def test_color_list_length_bounds_are_enforced():
    param = make(ParamType.COLOR_LIST, minimum=2, maximum=3, default=["red", "blue"])
    assert normalize_parameter_value(param, ["red", "blau"]) == ["#FF0000", "#0000FF"]
    with pytest.raises(ValueError, match="at least 2"):
        normalize_parameter_value(param, ["red"])
    with pytest.raises(ValueError, match="at most 3"):
        normalize_parameter_value(param, ["red"] * 4)


def test_color_list_rejects_a_bare_string():
    param = make(ParamType.COLOR_LIST, default=["red"])
    with pytest.raises(ValueError, match="must be a list of colors"):
        normalize_parameter_value(param, "red")


def test_gradient_requires_sorted_stops_spanning_zero_to_one():
    param = make(ParamType.GRADIENT, default=SAMPLE_VALUES[ParamType.GRADIENT])
    with pytest.raises(ValueError, match="sorted and include positions 0 and 1"):
        normalize_parameter_value(
            param, [{"at": 0.2, "color": "red"}, {"at": 1.0, "color": "blue"}]
        )
    with pytest.raises(ValueError, match="between 2 and 16"):
        normalize_parameter_value(param, [{"at": 0.0, "color": "red"}])
    with pytest.raises(ValueError, match="exactly 'at' and 'color'"):
        normalize_parameter_value(
            param, [{"at": 0.0, "color": "red", "extra": 1}, {"at": 1.0, "color": "blue"}]
        )


def test_color_range_requires_exactly_three_ascending_pairs():
    param = make(ParamType.COLOR_RANGE, default=SAMPLE_VALUES[ParamType.COLOR_RANGE])
    with pytest.raises(ValueError, match="exactly hue, saturation and brightness"):
        normalize_parameter_value(param, {"hue": [0.0, 1.0]})
    with pytest.raises(ValueError, match="must satisfy"):
        normalize_parameter_value(
            param,
            {"hue": [180.0, 0.0], "saturation": [0.0, 1.0], "brightness": [0.0, 1.0]},
        )
    with pytest.raises(ValueError, match="must satisfy"):
        normalize_parameter_value(
            param,
            {"hue": [0.0, 400.0], "saturation": [0.0, 1.0], "brightness": [0.0, 1.0]},
        )
