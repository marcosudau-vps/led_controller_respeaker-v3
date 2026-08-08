"""The rotation between a device's measured zero and its LED zero."""

from __future__ import annotations

import json

import pytest

from lefx.sdk import (
    DoaCalibration,
    as_flag,
    calibration_path,
    load_calibration,
    resolve_calibration,
    save_calibration,
)


# -- the value --------------------------------------------------------------


def test_an_uncalibrated_device_changes_nothing():
    calibration = DoaCalibration()
    assert calibration.identity is True
    assert calibration.apply(217.0) == 217.0


def test_the_offset_rotates_the_bearing_onto_the_ring():
    """The reSpeaker on this desk measured 129.1° between array and LED zero."""
    calibration = DoaCalibration(angle_offset_deg=129.1)
    assert calibration.apply(230.9) == pytest.approx(0.0)
    assert calibration.apply(0.0) == pytest.approx(129.1)


def test_the_result_stays_on_the_circle():
    calibration = DoaCalibration(angle_offset_deg=300.0)
    for measured in (0.0, 90.0, 359.9):
        assert 0.0 <= calibration.apply(measured) < 360.0


def test_mirroring_happens_before_the_offset():
    """The other order would mirror the mounting angle along with the reading.

    With ``reverse`` the array counts the other way round; the board is still
    screwed on the same way, so the offset applies to the corrected bearing.
    """
    calibration = DoaCalibration(angle_offset_deg=90.0, reverse=True)
    assert calibration.apply(30.0) == pytest.approx(60.0)  # (-30 % 360) + 90
    assert calibration.apply(0.0) == pytest.approx(90.0)


def test_nothing_measured_cannot_be_rotated():
    assert DoaCalibration(angle_offset_deg=129.1).apply(None) is None


def test_an_offset_is_normalised_so_equal_rotations_compare_equal():
    assert DoaCalibration(angle_offset_deg=-30.0) == DoaCalibration(angle_offset_deg=330.0)
    assert DoaCalibration(angle_offset_deg=390.0).angle_offset_deg == 30.0


@pytest.mark.parametrize("offset", ["north", float("nan"), float("inf"), None])
def test_an_unusable_offset_is_refused_at_construction(offset):
    with pytest.raises(ValueError):
        DoaCalibration(angle_offset_deg=offset)


def test_reverse_is_a_flag_not_a_truthy_value():
    with pytest.raises(ValueError):
        DoaCalibration(reverse="yes")


def test_a_calibration_round_trips_through_its_mapping():
    calibration = DoaCalibration(angle_offset_deg=129.1, reverse=True)
    assert DoaCalibration.from_mapping(calibration.to_dict()) == calibration


def test_an_unknown_key_is_refused_rather_than_ignored():
    """A misspelt key silently doing nothing is how a device stays miscalibrated."""
    with pytest.raises(ValueError, match="Unknown calibration keys"):
        DoaCalibration.from_mapping({"angle_offset": 12.0})


# -- the file ---------------------------------------------------------------


def test_no_file_means_an_uncalibrated_device(tmp_path):
    assert load_calibration("respeaker", path=tmp_path / "absent.json").identity is True


def test_entries_are_kept_per_device(tmp_path):
    """One file, several devices. A reSpeaker and a simulator standing in for
    it are two things, and only one of them is screwed to a board."""
    target = tmp_path / "doa_calibration.json"
    save_calibration("respeaker", DoaCalibration(129.1), path=target)
    save_calibration("simulator", DoaCalibration(0.0, reverse=True), path=target)

    assert load_calibration("respeaker", path=target).angle_offset_deg == pytest.approx(129.1)
    assert load_calibration("simulator", path=target).reverse is True
    assert load_calibration("something-else", path=target).identity is True


def test_saving_one_device_leaves_the_others_alone(tmp_path):
    target = tmp_path / "doa_calibration.json"
    save_calibration("respeaker", DoaCalibration(129.1), path=target)
    save_calibration("simulator", DoaCalibration(45.0), path=target)
    save_calibration("respeaker", DoaCalibration(200.0), path=target)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert set(payload) == {"respeaker", "simulator"}
    assert payload["simulator"]["angle_offset_deg"] == 45.0


def test_a_file_that_cannot_be_read_is_an_error_not_a_shrug(tmp_path):
    """Falling back to the identity would look exactly like an uncalibrated
    device, while every direction stayed wrong by the amount being corrected."""
    target = tmp_path / "doa_calibration.json"
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot read the calibration"):
        load_calibration("respeaker", path=target)


def test_a_malformed_entry_names_the_device_it_belongs_to(tmp_path):
    target = tmp_path / "doa_calibration.json"
    target.write_text(json.dumps({"respeaker": {"angle_offset_deg": "north"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="respeaker"):
        load_calibration("respeaker", path=target)


def test_the_path_comes_from_the_argument_then_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LEFX_DOA_CALIBRATION", str(tmp_path / "from-env.json"))
    assert calibration_path() == tmp_path / "from-env.json"
    assert calibration_path(tmp_path / "explicit.json") == tmp_path / "explicit.json"

    monkeypatch.delenv("LEFX_DOA_CALIBRATION")
    assert calibration_path().name == "doa_calibration.json"


# -- resolving against options ----------------------------------------------


def test_options_override_the_file_one_field_at_a_time(tmp_path):
    """Overriding the offset for one run must not discard a recorded reverse."""
    target = tmp_path / "doa_calibration.json"
    save_calibration("respeaker", DoaCalibration(129.1, reverse=True), path=target)

    resolved = resolve_calibration("respeaker", angle_offset_deg=10.0, path=target)
    assert resolved.angle_offset_deg == pytest.approx(10.0)
    assert resolved.reverse is True


def test_options_arrive_as_text_and_are_converted(tmp_path):
    """``--sink-option angle_offset_deg=129.1`` cannot carry a type with it."""
    resolved = resolve_calibration(
        "respeaker", angle_offset_deg="129.1", reverse="true", path=tmp_path / "absent.json"
    )
    assert resolved == DoaCalibration(129.1, reverse=True)


def test_without_options_the_recorded_calibration_is_used_unchanged(tmp_path):
    target = tmp_path / "doa_calibration.json"
    save_calibration("respeaker", DoaCalibration(129.1), path=target)
    assert resolve_calibration("respeaker", path=target) == DoaCalibration(129.1)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("1", True), ("on", True), ("ja", True), ("an", True),
     ("false", False), ("0", False), ("nein", False), (True, True), (False, False)],
)
def test_flags_accept_what_a_person_would_type(value, expected):
    assert as_flag(value) is expected
