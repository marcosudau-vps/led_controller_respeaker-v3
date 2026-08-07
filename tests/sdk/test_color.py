from __future__ import annotations

import pytest

from lefx.sdk import (
    blend,
    clamp_channel,
    evenly_spaced_positions,
    position_for_angle,
    rgb,
    scale_color,
    segment_lengths,
)


def test_channels_are_clamped_not_wrapped():
    assert clamp_channel(-5) == 0
    assert clamp_channel(300) == 255
    assert rgb(300, -5, 128) == 0xFF0080


def test_scale_color_dims_every_channel():
    assert scale_color(0xFFFFFF, 0.5) == 0x7F7F7F
    assert scale_color(0xFFFFFF, 0.0) == 0x000000
    assert scale_color(0x808080, 4.0) == 0xFFFFFF


def test_blend_interpolates_between_endpoints():
    assert blend(0x000000, 0xFFFFFF, 0.0) == 0x000000
    assert blend(0x000000, 0xFFFFFF, 1.0) == 0xFFFFFF
    assert blend(0x000000, 0xFFFFFF, 0.5) == 0x7F7F7F


@pytest.mark.parametrize("led_count", [5, 12, 24])
def test_segment_lengths_cover_the_whole_ring(led_count):
    for count in range(1, led_count + 1):
        lengths = segment_lengths(count, led_count)
        assert len(lengths) == count
        assert sum(lengths) == led_count
        assert max(lengths) - min(lengths) <= 1


def test_geometry_helpers_are_empty_for_degenerate_input():
    assert segment_lengths(0, 12) == []
    assert segment_lengths(3, 0) == []
    assert evenly_spaced_positions(0, 12) == []


@pytest.mark.parametrize("led_count", [5, 12, 24])
def test_evenly_spaced_positions_stay_in_range(led_count):
    positions = evenly_spaced_positions(4, led_count)
    assert len(positions) == 4
    assert all(0 <= position < led_count for position in positions)


def test_angle_maps_to_nearest_led_without_bankers_rounding():
    # 12 LEDs means 30 degrees each; 15 degrees sits exactly between LED 0 and 1
    # and must resolve upwards rather than to the nearest even index.
    assert position_for_angle(0.0, 12) == 0
    assert position_for_angle(15.0, 12) == 1
    assert position_for_angle(45.0, 12) == 2
    assert position_for_angle(90.0, 12) == 3
    assert position_for_angle(359.0, 12) == 0
    assert position_for_angle(-30.0, 12) == 11


def test_angle_requires_a_ring():
    with pytest.raises(ValueError):
        position_for_angle(0.0, 0)
