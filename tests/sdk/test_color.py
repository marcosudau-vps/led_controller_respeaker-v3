from __future__ import annotations

import pytest

from lefx.sdk import (
    blend,
    clamp_channel,
    evenly_spaced_positions,
    position_for_angle,
    positions_for_angle,
    rgb,
    scale_color,
    sector_for_angle,
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


# -- half-LED sectors -------------------------------------------------------


def test_the_ring_divides_into_twice_as_many_sectors_as_leds():
    """Twelve LEDs, twenty-four sectors: 15° each, alternating LED and gap."""
    assert sector_for_angle(0.0, 12) == 0
    assert sector_for_angle(15.0, 12) == 1
    assert sector_for_angle(30.0, 12) == 2
    assert sector_for_angle(345.0, 12) == 23
    assert sector_for_angle(360.0, 12) == 0
    # Every sector is reachable and none is reachable twice.
    assert {sector_for_angle(step * 15.0, 12) for step in range(24)} == set(range(24))


def test_the_sector_size_follows_the_ring_size():
    assert sector_for_angle(45.0, 4) == 1  # 4 LEDs, 8 sectors of 45°
    assert sector_for_angle(45.0, 24) == 6  # 24 LEDs, 48 sectors of 7.5°


def test_a_direction_on_an_led_marks_that_led_alone():
    assert positions_for_angle(0.0, 12) == (0,)
    assert positions_for_angle(30.0, 12) == (1,)
    assert positions_for_angle(180.0, 12) == (6,)
    assert positions_for_angle(330.0, 12) == (11,)


def test_a_direction_between_two_leds_marks_both():
    """The case a nearest-LED mapping cannot express.

    Zero degrees on a reSpeaker is where the cable enters, which is between the
    twelfth LED and the first — so "between two" is not an edge case here, it is
    half of all the directions there are.
    """
    assert positions_for_angle(15.0, 12) == (0, 1)
    assert positions_for_angle(165.0, 12) == (5, 6)
    # The last gap wraps back to the first LED rather than running off the ring.
    assert positions_for_angle(345.0, 12) == (11, 0)


def test_every_angle_marks_one_or_two_adjacent_leds():
    for degrees in range(0, 3600):
        marked = positions_for_angle(degrees / 10.0, 12)
        assert len(marked) in (1, 2)
        assert all(0 <= position < 12 for position in marked)
        if len(marked) == 2:
            assert (marked[0] + 1) % 12 == marked[1]


def test_sectors_require_a_ring():
    with pytest.raises(ValueError):
        sector_for_angle(0.0, 0)
