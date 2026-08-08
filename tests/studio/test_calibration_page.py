"""The calibration procedure, run end to end against a device.

The simulator is the device here, and that is the point rather than a
convenience: its DoA can be told what to report, so a run can be given a device
with a *known* rotation and the answer checked against it. Against hardware the
same code path would produce a number nobody could verify — you would be testing
the room.

The timer is driven by hand. There is no event loop in a test run, and stepping
the state machine directly is both deterministic and the only way to control
what the device says at each point.
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("PySide6", reason="the calibration page needs Qt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from lefx.sdk import DoaCalibration, InputContext, load_calibration  # noqa: E402
from lefx.studio.calibrate import sector_angle  # noqa: E402
from lefx.studio.calibration_page import PROBE_EFFECT, CalibrationPage  # noqa: E402
from lefx.studio.session import StudioSession  # noqa: E402

from tests.device.conftest import FakeWindow, until  # noqa: E402

ROTATION = 129.1
"""A real number from a real board, so the test measures something plausible."""


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qt_app, built_catalogue, tmp_path, monkeypatch):
    """A calibration page over a simulator whose DoA can be steered."""
    from respeaker_led.simulator.registration import reset_shared_link

    monkeypatch.setenv("LEFX_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("LEFX_DOA_CALIBRATION", str(tmp_path / "doa_calibration.json"))

    reset_shared_link()
    session = StudioSession(
        led_count=12, fps=60.0, search_paths=[built_catalogue],
        state_file=tmp_path / "background.json",
    )
    session.open("simulator", port=0)
    window = FakeWindow(session.service.sink.inner.link.host, session.service.sink.inner.link.port)
    until(lambda: session.service.sink.inner.link.connected, "the window never connected")

    built = CalibrationPage(session)
    built.window = window
    built.refresh()
    try:
        yield built
    finally:
        built.close()
        window.close()
        session.close()
        reset_shared_link()


def context(session) -> InputContext:
    return InputContext(now=time.monotonic(), led_count=12, config={}, previous_inputs={})


def run_calibration(page, *, rotation: float, reverse: bool = False, noise=()) -> None:
    """Walk the whole procedure, with the device rotated by a known amount."""
    provider = page.session.service.providers["doa"]
    page.dwell.setValue(1.0)
    page._start()  # noqa: SLF001 — what the Start button calls

    index = 0
    while page.current_sector is not None:
        page.timer.stop()
        expected = sector_angle(page.current_sector, page.session.led_count)
        raw = (expected - rotation) % 360.0
        if reverse:
            raw = (-(expected - rotation)) % 360.0
        if noise:
            raw = (raw + noise[index % len(noise)]) % 360.0

        page.window.send_inputs(raw, "sound")
        until(
            lambda: (provider.sample(context(page.session)) or {}).get("direction_deg") == raw,
            "the reading never reached the provider",
        )
        for _ in range(3):
            page._take_reading()  # noqa: SLF001
        page._finish_sector()  # noqa: SLF001
        index += 1


# -- the page before a run --------------------------------------------------


def test_the_page_needs_a_device_that_reports_directions(page):
    assert page.session.output_name == "simulator"
    assert page._provider() is not None  # noqa: SLF001
    assert page.start_button.isEnabled() is True


def test_the_probe_is_an_ordinary_definition_in_the_catalogue(page):
    """The ring is driven through the engine, not past it.

    A back door for the calibration would be measuring a path that nothing else
    uses, which is the one thing a calibration must not do.
    """
    assert PROBE_EFFECT in page.session.registry.effects


def test_a_run_lights_the_sector_it_is_asking_about(page):
    provider = page.session.service.providers["doa"]
    page.dwell.setValue(1.0)
    page._start()  # noqa: SLF001

    assert page.current_sector is not None
    assert page.monitor._marked_sector == page.current_sector  # noqa: SLF001

    running = page.session.status()["layers"]["primary_state"]
    assert running["effect_id"] == PROBE_EFFECT
    assert running["config"]["direction_deg"] == pytest.approx(
        sector_angle(page.current_sector, 12)
    )
    del provider
    page._cancel()  # noqa: SLF001


def test_the_device_is_measured_raw_while_a_run_is_in_progress(page):
    """Measuring through the calibration being replaced would converge, but you
    could never read what the device actually reports off the screen."""
    provider = page.session.service.providers["doa"]
    provider.calibration = DoaCalibration(angle_offset_deg=42.0)

    page._start()  # noqa: SLF001
    assert provider.calibration.identity is True
    assert page.suspended.angle_offset_deg == 42.0

    page._cancel()  # noqa: SLF001
    assert provider.calibration.angle_offset_deg == 42.0


# -- a whole run ------------------------------------------------------------


def test_a_run_recovers_the_rotation_the_device_was_given(page):
    run_calibration(page, rotation=ROTATION)

    assert page.fit is not None
    assert page.fit.calibration.angle_offset_deg == pytest.approx(ROTATION, abs=1.0)
    assert page.fit.calibration.reverse is False
    assert page.fit.trustworthy is True
    assert page.save_button.isEnabled() is True


def test_a_run_survives_a_device_that_does_not_hear_every_point(page):
    """Someone did not speak loudly enough at one of them."""
    provider = page.session.service.providers["doa"]
    page.dwell.setValue(1.0)
    page._start()  # noqa: SLF001

    skipped = 0
    while page.current_sector is not None:
        page.timer.stop()
        expected = sector_angle(page.current_sector, page.session.led_count)
        if skipped < 2:
            # Silence: a valid reading of the room, and useless for this.
            page.window.send_inputs(expected, "none")
            skipped += 1
            page._take_reading()  # noqa: SLF001
        else:
            raw = (expected - ROTATION) % 360.0
            page.window.send_inputs(raw, "sound")
            until(
                lambda: (provider.sample(context(page.session)) or {}).get("direction_deg") == raw,
                "the reading never arrived",
            )
            for _ in range(3):
                page._take_reading()  # noqa: SLF001
        page._finish_sector()  # noqa: SLF001

    assert page.fit is not None
    assert len(page.fit.samples) == 6
    assert page.fit.calibration.angle_offset_deg == pytest.approx(ROTATION, abs=1.0)


def test_a_run_puts_the_previous_calibration_back_when_it_ends(page):
    provider = page.session.service.providers["doa"]
    provider.calibration = DoaCalibration(angle_offset_deg=42.0)

    run_calibration(page, rotation=ROTATION)

    # Measured, but not applied — that is a separate button, on purpose.
    assert provider.calibration.angle_offset_deg == 42.0
    assert page.fit.calibration.angle_offset_deg == pytest.approx(ROTATION, abs=1.0)


def test_cancelling_puts_the_calibration_back_too(page):
    provider = page.session.service.providers["doa"]
    provider.calibration = DoaCalibration(angle_offset_deg=42.0, reverse=True)

    page._start()  # noqa: SLF001
    page._cancel()  # noqa: SLF001

    assert provider.calibration == DoaCalibration(angle_offset_deg=42.0, reverse=True)


# -- keeping the answer -----------------------------------------------------


def test_applying_changes_the_device_without_writing_anything_down(page, tmp_path):
    run_calibration(page, rotation=ROTATION)
    page._apply(persist=False)  # noqa: SLF001

    provider = page.session.service.providers["doa"]
    assert provider.calibration.angle_offset_deg == pytest.approx(ROTATION, abs=1.0)
    assert not (tmp_path / "doa_calibration.json").exists()


def test_saving_records_it_under_the_device_it_was_measured_on(page, tmp_path):
    run_calibration(page, rotation=ROTATION)
    page._apply(persist=True)  # noqa: SLF001

    recorded = load_calibration("simulator", path=tmp_path / "doa_calibration.json")
    assert recorded.angle_offset_deg == pytest.approx(ROTATION, abs=1.0)
    # And nothing was written for a device that was not measured.
    assert load_calibration("respeaker", path=tmp_path / "doa_calibration.json").identity


def test_the_recorded_calibration_is_what_the_next_provider_picks_up(page, tmp_path):
    """The whole point of writing it down: the next process starts corrected."""
    from respeaker_led.simulator.registration import DEVICE_NAME, create_doa_provider

    run_calibration(page, rotation=ROTATION)
    page._apply(persist=True)

    fresh = create_doa_provider(led_count=12, port=0)
    try:
        assert DEVICE_NAME == "simulator"
        assert fresh.calibration.angle_offset_deg == pytest.approx(ROTATION, abs=1.0)
    finally:
        fresh.close()
