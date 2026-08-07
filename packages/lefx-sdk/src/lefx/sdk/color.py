"""Generic colour and ring geometry maths available to effect packages.

Everything here is free of concrete meaning: no defaults for named effects, no
per-definition branches, no ring size baked in. Functions that depend on the
ring take ``led_count`` as an argument, because the ring size is a runtime
setting and not a property of this module.
"""

from __future__ import annotations


def clamp_channel(value: float) -> int:
    return max(0, min(255, int(value)))


def rgb(r: float, g: float, b: float) -> int:
    return (clamp_channel(r) << 16) | (clamp_channel(g) << 8) | clamp_channel(b)


def scale_color(color: int, factor: float) -> int:
    """Multiply every channel by ``factor``, clamping at full brightness."""
    factor = max(0.0, factor)
    return rgb(
        ((color >> 16) & 0xFF) * factor,
        ((color >> 8) & 0xFF) * factor,
        (color & 0xFF) * factor,
    )


def blend(color_a: int, color_b: int, mix: float) -> int:
    """Linear interpolation; ``mix=0`` yields ``color_a``, ``mix=1`` ``color_b``."""
    mix = max(0.0, min(1.0, mix))
    inverse = 1.0 - mix
    return rgb(
        ((color_a >> 16) & 0xFF) * inverse + ((color_b >> 16) & 0xFF) * mix,
        ((color_a >> 8) & 0xFF) * inverse + ((color_b >> 8) & 0xFF) * mix,
        (color_a & 0xFF) * inverse + (color_b & 0xFF) * mix,
    )


def segment_lengths(count: int, led_count: int) -> list[int]:
    """Split a ring of ``led_count`` LEDs into ``count`` segments as evenly as possible.

    The remainder is distributed to the leading segments, so the lengths differ
    by at most one and always sum to ``led_count``.
    """
    if count <= 0 or led_count <= 0:
        return []
    base = led_count // count
    remainder = led_count % count
    return [base + (1 if index < remainder else 0) for index in range(count)]


def evenly_spaced_positions(count: int, led_count: int) -> list[int]:
    """LED indices for ``count`` markers spread evenly around the ring."""
    if count <= 0 or led_count <= 0:
        return []
    step = led_count / float(count)
    return [int(round(index * step)) % led_count for index in range(count)]


def position_for_angle(angle_deg: float, led_count: int) -> int:
    """Map an angle in degrees to the nearest LED index.

    Rounds half away from zero rather than using :func:`round`, whose
    banker's rounding would make ``0.5`` and ``1.5`` land on the same side.
    """
    if led_count <= 0:
        raise ValueError("led_count must be greater than zero")
    degrees_per_led = 360.0 / led_count
    position = (angle_deg % 360.0) / degrees_per_led
    return int(position + 0.5) % led_count
