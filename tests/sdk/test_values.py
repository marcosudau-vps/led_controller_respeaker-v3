from __future__ import annotations

import pytest

from lefx.sdk import (
    ValueNormalizationError,
    describe_color,
    format_color,
    parse_angle_degrees,
    parse_bool,
    parse_color,
    parse_duration_ms,
    parse_ratio,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#00ff00", 0x00FF00),
        ("0x00FF00", 0x00FF00),
        ("green", 0x00FF00),
        ("gruen", 0x00FF00),
        ("grün", 0x00FF00),
        ("WEISS", 0xFFFFFF),
        ("weiß", 0xFFFFFF),
        ("  blau  ", 0x0000FF),
        (0x123456, 0x123456),
    ],
)
def test_parse_color_accepts_canonical_and_named_aliases(value, expected):
    assert parse_color(value) == expected


def test_unknown_color_returns_machine_readable_suggestions():
    with pytest.raises(ValueNormalizationError) as exc_info:
        parse_color("gren")

    assert exc_info.value.code == "unknown_color"
    assert "green" in exc_info.value.suggestions
    assert exc_info.value.to_dict(field="config.color")["field"] == "config.color"


@pytest.mark.parametrize("value", [True, False, None, [], 0x1000000, -1, "#12345", "#GGGGGG"])
def test_parse_color_rejects_non_colors(value):
    with pytest.raises(ValueNormalizationError):
        parse_color(value)


def test_color_output_is_canonical_and_names_exact_catalog_values():
    assert format_color("red") == "#FF0000"
    assert describe_color("#FF0000") == {"hex": "#FF0000", "name": "red", "aliases": ["rot"]}
    assert describe_color("#123456") == {"hex": "#123456"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1500, 1500), ("1500ms", 1500), ("1.5s", 1500), ("0.25 s", 250), (1500.4, 1500)],
)
def test_duration_normalization(value, expected):
    assert parse_duration_ms(value) == expected


def test_duration_honours_minimum():
    with pytest.raises(ValueNormalizationError) as exc_info:
        parse_duration_ms(0, minimum=1)
    assert exc_info.value.code == "duration_out_of_range"


@pytest.mark.parametrize(("value", "expected"), [(0.5, 0.5), ("0.5", 0.5), ("50%", 0.5)])
def test_ratio_normalization(value, expected):
    assert parse_ratio(value) == expected


@pytest.mark.parametrize("value", [1.5, "150%", -0.1])
def test_ratio_rejects_values_outside_zero_to_one(value):
    with pytest.raises(ValueNormalizationError):
        parse_ratio(value)


def test_angle_wraps_into_a_single_turn():
    assert parse_angle_degrees("450deg") == 90.0
    assert parse_angle_degrees("90°") == 90.0
    assert parse_angle_degrees(-90) == 270.0


def test_boolean_accepts_english_and_german_switches():
    assert parse_bool("an") is True
    assert parse_bool("aus") is False
    assert parse_bool("ja") is True
    assert parse_bool("nein") is False
    assert parse_bool("ON") is True
    assert parse_bool(1) is True
    assert parse_bool(0) is False


@pytest.mark.parametrize("value", ["vielleicht", 2, None, ""])
def test_boolean_rejects_ambiguous_input(value):
    with pytest.raises(ValueNormalizationError):
        parse_bool(value)
