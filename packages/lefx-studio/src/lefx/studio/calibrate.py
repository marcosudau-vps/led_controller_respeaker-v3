"""Working out how a microphone array is rotated against its LED ring.

The procedure is the one a person would do by hand, made repeatable: light a
known bearing, speak from it, write down what the device measured, and do that
often enough that the noise averages out. What comes back is the difference
between the two zeros — a property of the board, which is why the answer belongs
to the device and not to any effect.

Angles do not average the way numbers do. The mean of 350° and 10° is 0°, not
180°, and a calibration computed with an arithmetic mean would be quietly wrong
for exactly the bearings that cross the seam. So everything here goes through
unit vectors.

No Qt: this is the part with the arithmetic in it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from lefx.sdk import DoaCalibration

MIN_SAMPLES = 3
"""Below this a "calibration" is one reading and a rounding error."""


def circular_mean(angles: list[float]) -> float:
    """The average direction, on a circle where 359° and 1° are two degrees apart."""
    if not angles:
        raise ValueError("no angles to average")
    x = sum(math.cos(math.radians(angle)) for angle in angles)
    y = sum(math.sin(math.radians(angle)) for angle in angles)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        # Readings spread evenly around the circle have no mean direction. Any
        # answer here would be arbitrary, and arbitrary is what a calibration
        # must never be.
        raise ValueError("these angles have no mean direction")
    degrees = math.degrees(math.atan2(y, x)) % 360.0
    # A mean of 350° and 10° is zero, and floating point reaches it from below:
    # a hair under 360 wrapped to just under 360 rather than to 0. Say zero.
    return 0.0 if degrees >= 360.0 - 1e-9 else degrees


def circular_spread(angles: list[float]) -> float:
    """How far apart the readings are, in degrees, as one number.

    Zero when they all agree, rising towards 90° as they scatter. This is what
    says whether a calibration is worth keeping: a tight cluster means the
    device heard the same direction every time, and a wide one means it did not
    and the mean of it is not a measurement.
    """
    if not angles:
        return 0.0
    x = sum(math.cos(math.radians(angle)) for angle in angles) / len(angles)
    y = sum(math.sin(math.radians(angle)) for angle in angles) / len(angles)
    strength = math.hypot(x, y)
    if strength >= 1.0:
        return 0.0
    # The circular standard deviation, which is the honest version of "spread"
    # for directions. It grows without bound as readings scatter, so it is
    # capped at 180°: beyond that the number stops meaning anything a person
    # could act on, and "as disagreeing as two directions can be" is the answer.
    deviation = math.degrees(math.sqrt(-2.0 * math.log(max(strength, 1e-12))))
    return min(180.0, deviation)


def difference(expected_deg: float, measured_deg: float) -> float:
    """How far the ring's bearing is from the array's, as a rotation."""
    return (expected_deg - measured_deg) % 360.0


@dataclass(slots=True, frozen=True)
class Sample:
    """One reading: where the light was, and what the device heard."""

    expected_deg: float
    """The bearing the probe was lighting — known, because we chose it."""

    measured_deg: float
    """What the device reported, with no calibration applied."""

    def residual(self, calibration: DoaCalibration) -> float:
        """How wrong this reading still is once a calibration is applied.

        Signed and folded into ±180, so residuals average to zero when the fit
        is right rather than to 180 when it is exactly opposite.
        """
        corrected = calibration.apply(self.measured_deg)
        return (corrected - self.expected_deg + 180.0) % 360.0 - 180.0


@dataclass(slots=True, frozen=True)
class Fit:
    """What a set of samples says the calibration should be."""

    calibration: DoaCalibration
    spread_deg: float
    """The scatter of the underlying rotations. Small means the device agreed
    with itself; large means the samples are not describing one rotation."""

    residual_deg: float
    """The worst remaining error once the calibration is applied."""

    samples: tuple[Sample, ...] = field(default_factory=tuple)

    @property
    def trustworthy(self) -> bool:
        """Whether this is a measurement or a shrug.

        Half an LED on a twelve-LED ring is 15°, which is also the resolution
        the ring can express. A fit scattered wider than that is not saying
        anything the ring could show.
        """
        return len(self.samples) >= MIN_SAMPLES and self.spread_deg <= 15.0


def fit_calibration(samples: list[Sample], *, allow_reverse: bool = True) -> Fit:
    """The rotation that best explains the readings, and how well it does.

    Both senses are tried when ``allow_reverse``. Which way an array counts is
    not something to be assumed from a datasheet, and the samples answer it for
    free: with the wrong sense, no single rotation lines the readings up, and
    the scatter says so.
    """
    if len(samples) < MIN_SAMPLES:
        raise ValueError(f"a calibration needs at least {MIN_SAMPLES} readings")

    candidates: list[Fit] = []
    for reverse in (False, True) if allow_reverse else (False,):
        rotations = [
            difference(
                sample.expected_deg,
                (-sample.measured_deg) % 360.0 if reverse else sample.measured_deg,
            )
            for sample in samples
        ]
        try:
            offset = circular_mean(rotations)
        except ValueError:
            continue
        calibration = DoaCalibration(angle_offset_deg=offset, reverse=reverse)
        candidates.append(
            Fit(
                calibration=calibration,
                spread_deg=circular_spread(rotations),
                residual_deg=max(abs(sample.residual(calibration)) for sample in samples),
                samples=tuple(samples),
            )
        )

    if not candidates:
        raise ValueError("these readings do not describe a rotation")
    return min(candidates, key=lambda fit: fit.spread_deg)


def sector_angle(sector: int, led_count: int) -> float:
    """The bearing at the centre of one of the ``2 * led_count`` sectors."""
    sectors = 2 * led_count
    return (sector % sectors) * 360.0 / sectors


def suggested_sectors(led_count: int, *, count: int = 8) -> list[int]:
    """Which sectors to walk, spread evenly around the ring.

    Evenly, because a calibration measured only across one side would fit the
    rotation to that side. Fewer than every sector, because the point is to
    cover the circle rather than to stand in twenty-four places.
    """
    sectors = 2 * led_count
    step = max(1, sectors // max(1, count))
    return sorted({(index * step) % sectors for index in range(min(count, sectors))})


__all__ = [
    "MIN_SAMPLES",
    "Fit",
    "Sample",
    "circular_mean",
    "circular_spread",
    "difference",
    "fit_calibration",
    "sector_angle",
    "suggested_sectors",
]
