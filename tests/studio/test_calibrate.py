"""Working out the rotation between an array's zero and a ring's.

All arithmetic, no display. The one thing worth stating up front: angles do not
average like numbers, and every test here exists because the version that
treated them as numbers looked right until a bearing crossed 360.
"""

from __future__ import annotations

import pytest

from lefx.sdk import DoaCalibration
from lefx.effect_creation.studio.calibrate import (
    MIN_SAMPLES,
    Sample,
    circular_mean,
    circular_spread,
    difference,
    fit_calibration,
    sector_angle,
    suggested_sectors,
)


# -- averaging on a circle --------------------------------------------------


def test_the_mean_of_two_angles_across_the_seam_is_between_them():
    """350° and 10° are twenty degrees apart, and their mean is zero.

    An arithmetic mean says 180°, which is the opposite direction — wrong for
    exactly the bearings a reSpeaker reports most, since its zero is the cable.
    """
    assert circular_mean([350.0, 10.0]) == pytest.approx(0.0)
    assert circular_mean([355.0, 5.0, 0.0]) == pytest.approx(0.0)


def test_the_mean_of_a_cluster_is_inside_it():
    assert circular_mean([100.0, 104.0, 96.0]) == pytest.approx(100.0)


def test_angles_with_no_mean_direction_are_refused():
    """Three readings 120° apart point nowhere in particular, and any answer
    would be arbitrary — which is the one thing a calibration must not be."""
    with pytest.raises(ValueError, match="no mean direction"):
        circular_mean([0.0, 120.0, 240.0])


def test_no_angles_at_all_is_an_error_not_a_zero():
    with pytest.raises(ValueError):
        circular_mean([])


def test_spread_is_zero_when_the_readings_agree():
    assert circular_spread([90.0, 90.0, 90.0]) == pytest.approx(0.0)


def test_spread_grows_with_disagreement_and_stays_readable():
    tight = circular_spread([100.0, 102.0, 98.0])
    loose = circular_spread([100.0, 160.0, 40.0])
    assert tight < loose <= 180.0
    assert circular_spread([0.0, 120.0, 240.0]) == 180.0


def test_spread_does_not_care_where_on_the_circle_the_cluster_sits():
    """A cluster around zero is as tight as one around 180."""
    assert circular_spread([358.0, 0.0, 2.0]) == pytest.approx(
        circular_spread([178.0, 180.0, 182.0])
    )


def test_a_difference_is_a_rotation_not_a_subtraction():
    assert difference(10.0, 350.0) == pytest.approx(20.0)
    assert difference(350.0, 10.0) == pytest.approx(340.0)


# -- fitting ----------------------------------------------------------------


def rotated(offset: float, *, reverse: bool = False, bearings=(0.0, 45.0, 90.0, 180.0, 270.0)):
    """Samples from a device whose array is rotated by ``offset``."""
    calibration = DoaCalibration(angle_offset_deg=offset, reverse=reverse)
    samples = []
    for expected in bearings:
        # Search for the raw reading that the calibration would turn into the
        # expected bearing: this is the device, run backwards.
        measured = next(
            candidate
            for candidate in [step / 10.0 for step in range(3600)]
            if abs(((calibration.apply(candidate) - expected + 180.0) % 360.0) - 180.0) < 0.06
        )
        samples.append(Sample(expected_deg=expected, measured_deg=measured))
    return samples


def test_a_clean_run_recovers_the_rotation_it_was_made_from():
    """The number from the old repo, put back through the whole procedure."""
    fit = fit_calibration(rotated(129.1))
    assert fit.calibration.angle_offset_deg == pytest.approx(129.1, abs=0.2)
    assert fit.calibration.reverse is False
    assert fit.spread_deg < 1.0
    assert fit.trustworthy is True


def test_a_mirrored_array_is_recognised_rather_than_fudged():
    """Which way an array counts is not something to take on faith.

    With the wrong sense no single rotation lines the readings up, so trying
    both and keeping the tighter one answers it for free.
    """
    fit = fit_calibration(rotated(40.0, reverse=True))
    assert fit.calibration.reverse is True
    assert fit.calibration.angle_offset_deg == pytest.approx(40.0, abs=0.2)
    assert fit.spread_deg < 1.0


def test_the_fit_can_be_told_not_to_consider_mirroring():
    fit = fit_calibration(rotated(40.0, reverse=True), allow_reverse=False)
    assert fit.calibration.reverse is False
    # Forced into the wrong sense, no rotation explains the readings, and the
    # spread is what says so rather than a plausible-looking wrong number.
    assert fit.spread_deg > 15.0
    assert fit.trustworthy is False


def test_noisy_readings_still_recover_the_rotation():
    noise = (2.0, -3.0, 1.0, -1.0, 4.0)
    samples = [
        Sample(expected_deg=sample.expected_deg, measured_deg=(sample.measured_deg + shift) % 360.0)
        for sample, shift in zip(rotated(129.1), noise)
    ]
    fit = fit_calibration(samples)
    assert fit.calibration.angle_offset_deg == pytest.approx(129.1, abs=3.0)
    assert fit.trustworthy is True


def test_readings_that_describe_nothing_are_not_trusted():
    """Someone walked around the room while it measured."""
    samples = [
        Sample(expected_deg=0.0, measured_deg=10.0),
        Sample(expected_deg=90.0, measured_deg=200.0),
        Sample(expected_deg=180.0, measured_deg=45.0),
        Sample(expected_deg=270.0, measured_deg=300.0),
    ]
    fit = fit_calibration(samples)
    assert fit.trustworthy is False
    assert fit.spread_deg > 15.0


def test_too_few_readings_is_refused_outright():
    with pytest.raises(ValueError, match=f"at least {MIN_SAMPLES}"):
        fit_calibration(rotated(30.0, bearings=(0.0, 90.0)))


def test_the_residual_says_how_wrong_the_worst_point_still_is():
    fit = fit_calibration(rotated(129.1))
    assert fit.residual_deg < 1.0
    for sample in fit.samples:
        assert abs(sample.residual(fit.calibration)) <= fit.residual_deg + 1e-9


def test_a_fit_is_only_trusted_within_half_an_led():
    """Fifteen degrees on a twelve-LED ring is the finest thing the ring can
    say, so a fit scattered wider is not saying anything it could show."""
    fit = fit_calibration(rotated(129.1))
    assert fit.spread_deg <= 15.0 and fit.trustworthy


# -- where the measurements are taken ---------------------------------------


def test_sectors_are_half_led_steps_around_the_whole_ring():
    assert sector_angle(0, 12) == 0.0
    assert sector_angle(1, 12) == 15.0
    assert sector_angle(2, 12) == 30.0
    assert sector_angle(24, 12) == 0.0


def test_the_suggested_points_cover_the_circle_evenly():
    """Measuring one side only would fit the rotation to that side."""
    chosen = suggested_sectors(12, count=8)
    assert len(chosen) == 8
    angles = [sector_angle(sector, 12) for sector in chosen]
    gaps = [(b - a) % 360.0 for a, b in zip(angles, angles[1:] + angles[:1])]
    assert len(set(gaps)) == 1


def test_more_points_than_sectors_is_capped_at_the_sectors_there_are():
    assert len(suggested_sectors(12, count=100)) <= 24
