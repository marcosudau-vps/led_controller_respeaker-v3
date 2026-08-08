"""The calibration page: light a bearing, speak from it, keep the answer.

The measurement is only meaningful against *raw* readings, so while a run is in
progress the device's calibration is set aside and put back afterwards. The
alternative — measuring through the calibration being replaced — would converge
eventually but would never let you see what the device actually reports, which
is the one number worth looking at while standing next to it.

The ring is driven through ``ring_probe``, an ordinary state in the catalogue,
rather than by writing frames past the engine. There is no back door to the
device here for the same reason there is none anywhere else: the path the
calibration is measured over has to be the path everything else uses, or it
would be calibrating something slightly different from what runs afterwards.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lefx.sdk import DoaCalibration, calibration_path, save_calibration

from .calibrate import Fit, Sample, fit_calibration, sector_angle, suggested_sectors
from .ring import RingMonitor
from .session import NULL_OUTPUT, StudioSession

logger = logging.getLogger("lefx.studio.calibration")

PROBE_EFFECT = "ring_probe"
SAMPLE_INTERVAL_MS = 100
"""How often a reading is taken while a sector is being measured."""


class CalibrationPage(QWidget):
    """Walk the ring in half-LED steps and work out how the array is rotated."""

    frame_received = Signal(tuple)

    def __init__(self, session: StudioSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.samples: list[Sample] = []
        self.queue: list[int] = []
        self.current_sector: int | None = None
        self.readings: list[float] = []
        self.suspended: DoaCalibration | None = None
        self.fit: Fit | None = None

        self.timer = QTimer(self)
        self.timer.setInterval(SAMPLE_INTERVAL_MS)
        self.timer.timeout.connect(self._take_reading)

        self._build()
        self.frame_received.connect(self.monitor.set_colors)

    # -- construction -------------------------------------------------------

    def _build(self) -> None:
        layout = QHBoxLayout(self)

        self.monitor = RingMonitor(self.session.led_count)
        self.monitor.set_show_sectors(True)
        layout.addWidget(self.monitor, stretch=3)

        side = QVBoxLayout()
        side.addWidget(self._build_setup())
        side.addWidget(self._build_run())
        side.addWidget(self._build_result())
        side.addStretch(1)
        layout.addLayout(side, stretch=2)

    def _build_setup(self) -> QGroupBox:
        box = QGroupBox("Messpunkte")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Richtungen"))
        self.point_count = QSpinBox()
        self.point_count.setRange(3, 2 * self.session.led_count)
        self.point_count.setValue(8)
        self.point_count.setToolTip(
            "Gleichmäßig über den Ring verteilt. Weniger als der ganze Kreis reicht, "
            "aber nur eine Seite zu messen legt die Drehung auf diese Seite fest."
        )
        row.addWidget(self.point_count)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Messdauer je Punkt"))
        self.dwell = QDoubleSpinBox()
        self.dwell.setRange(1.0, 20.0)
        self.dwell.setValue(4.0)
        self.dwell.setSuffix(" s")
        row.addWidget(self.dwell)
        layout.addLayout(row)

        self.allow_reverse = QCheckBox("Zählrichtung mitbestimmen")
        self.allow_reverse.setChecked(True)
        self.allow_reverse.setToolTip(
            "Beide Drehsinne durchrechnen und den nehmen, der die Messungen erklärt."
        )
        layout.addWidget(self.allow_reverse)
        return box

    def _build_run(self) -> QGroupBox:
        box = QGroupBox("Messung")
        layout = QVBoxLayout(box)

        self.instruction = QLabel("Ausgabe wählen und starten.")
        self.instruction.setWordWrap(True)
        self.instruction.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.instruction)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.live = QLabel("—")
        self.live.setStyleSheet("color: #888;")
        layout.addWidget(self.live)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start)
        self.skip_button = QPushButton("Punkt überspringen")
        self.skip_button.clicked.connect(self._finish_sector)
        self.skip_button.setEnabled(False)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.skip_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.collected = QListWidget()
        self.collected.setMaximumHeight(140)
        layout.addWidget(self.collected)
        return box

    def _build_result(self) -> QGroupBox:
        box = QGroupBox("Ergebnis")
        layout = QVBoxLayout(box)

        self.result = QLabel("Noch nichts gemessen.")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)

        self.current = QLabel("")
        self.current.setStyleSheet("color: #888;")
        self.current.setWordWrap(True)
        layout.addWidget(self.current)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Speichern")
        self.save_button.clicked.connect(self._save)
        self.save_button.setEnabled(False)
        self.apply_button = QPushButton("Nur übernehmen")
        self.apply_button.setToolTip("Für diese Sitzung anwenden, ohne sie zu hinterlegen")
        self.apply_button.clicked.connect(lambda: self._apply(persist=False))
        self.apply_button.setEnabled(False)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        return box

    # -- what the page knows about the session ------------------------------

    def refresh(self) -> None:
        """Called when the page is shown or the output changed."""
        self.monitor.set_led_count(self.session.led_count)
        self.point_count.setMaximum(2 * self.session.led_count)
        provider = self._provider()
        ready = provider is not None and self.session.output_name != NULL_OUTPUT
        self.start_button.setEnabled(ready and not self.timer.isActive())
        if not ready:
            self.instruction.setText(
                "Diese Seite braucht ein Gerät mit Richtungsdaten.\n"
                "Wähle oben eine Ausgabe, die einen doa-Provider mitbringt."
            )
        elif not self.timer.isActive():
            self.instruction.setText(
                f"Bereit. Das Gerät „{self.session.output_name}“ liefert Richtungsdaten."
            )
        self._show_current_calibration()

    def _provider(self) -> Any | None:
        if self.session.service is None:
            return None
        return self.session.service.providers.get("doa")

    def _show_current_calibration(self) -> None:
        provider = self._provider()
        if provider is None:
            self.current.setText("")
            return
        calibration = self.suspended or getattr(provider, "calibration", DoaCalibration())
        where = self._calibration_path()
        self.current.setText(
            f"Aktuell am Gerät: {calibration.angle_offset_deg:.1f}°"
            f"{', gespiegelt' if calibration.reverse else ''}\nDatei: {where}"
        )

    def _calibration_path(self):
        """The project's calibration file, or the usual place without one."""
        project = getattr(self.session, "project", None)
        return project.calibration_file if project is not None else calibration_path()

    # -- the run ------------------------------------------------------------

    def _start(self) -> None:
        provider = self._provider()
        if provider is None:
            return
        if PROBE_EFFECT not in self.session.registry.effects:
            QMessageBox.warning(
                self,
                "Sonde fehlt",
                f"„{PROBE_EFFECT}“ ist nicht geladen. Es gehört zum core-set — "
                "einmal 'uv run python scripts/build_effects.py' und Quellen neu laden.",
            )
            return

        # Measure what the device actually reports. Calibrating through a
        # calibration would still converge, but you could never read the raw
        # bearing off the screen while standing next to the thing.
        self.suspended = getattr(provider, "calibration", DoaCalibration())
        provider.calibration = DoaCalibration()

        self.samples.clear()
        self.collected.clear()
        self.fit = None
        self.queue = suggested_sectors(self.session.led_count, count=self.point_count.value())
        self.progress.setRange(0, len(self.queue))
        self.progress.setValue(0)
        self.save_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.skip_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self._next_sector()

    def _next_sector(self) -> None:
        if not self.queue:
            self._conclude()
            return
        self.current_sector = self.queue.pop(0)
        self.readings.clear()

        angle = sector_angle(self.current_sector, self.session.led_count)
        self.monitor.mark_sector(self.current_sector)
        try:
            self.session.play_state(
                PROBE_EFFECT,
                {"direction_deg": angle, "color": "#FFB000", "brightness": 1.0},
            )
        except Exception as exc:
            logger.warning("could not light the probe: %s", exc)

        self.instruction.setText(
            f"Sprich aus Richtung {angle:.0f}° — dort, wo der Ring gerade leuchtet."
        )
        self._deadline = self.dwell.value() * 1000.0
        self._elapsed = 0.0
        self.timer.start()

    def _take_reading(self) -> None:
        provider = self._provider()
        if provider is None:
            self._cancel()
            return

        reading = provider.sample(_context(self.session))
        if reading is not None and reading.get("direction_deg") is not None:
            # Silence is a valid measurement of the room and a useless one for
            # this: an angle is only a bearing to something while something is
            # making a sound.
            if reading.get("detection_state") in ("sound", "speech"):
                self.readings.append(float(reading["direction_deg"]))

        self.live.setText(
            f"{len(self.readings)} Messwerte"
            + (f", zuletzt {self.readings[-1]:.0f}°" if self.readings else ", noch nichts gehört")
        )

        self._elapsed += SAMPLE_INTERVAL_MS
        if self._elapsed >= self._deadline:
            self._finish_sector()

    def _finish_sector(self) -> None:
        self.timer.stop()
        if self.current_sector is not None and self.readings:
            from .calibrate import circular_mean, circular_spread

            expected = sector_angle(self.current_sector, self.session.led_count)
            try:
                measured = circular_mean(self.readings)
            except ValueError:
                measured = None
            if measured is not None:
                self.samples.append(Sample(expected_deg=expected, measured_deg=measured))
                self.collected.addItem(
                    f"{expected:6.1f}° → gemessen {measured:6.1f}°  "
                    f"(±{circular_spread(self.readings):.0f}°, {len(self.readings)} Werte)"
                )
        elif self.current_sector is not None:
            self.collected.addItem(
                f"{sector_angle(self.current_sector, self.session.led_count):6.1f}° → nichts gehört"
            )

        self.progress.setValue(self.progress.value() + 1)
        self._next_sector()

    def _conclude(self) -> None:
        self.timer.stop()
        self.monitor.mark_sector(None)
        self.current_sector = None
        self.skip_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.instruction.setText("Messung beendet.")

        try:
            self.fit = fit_calibration(self.samples, allow_reverse=self.allow_reverse.isChecked())
        except ValueError as exc:
            self._restore()
            self.result.setText(f"Keine Kalibrierung ableitbar: {exc}")
            return

        calibration = self.fit.calibration
        verdict = "brauchbar" if self.fit.trustworthy else "zu unruhig — noch einmal messen"
        self.result.setText(
            f"Offset {calibration.angle_offset_deg:.1f}°"
            f"{', gespiegelt' if calibration.reverse else ''}\n"
            f"Streuung {self.fit.spread_deg:.1f}°, größter Restfehler "
            f"{self.fit.residual_deg:.1f}°, {len(self.fit.samples)} Punkte — {verdict}"
        )
        self.save_button.setEnabled(True)
        self.apply_button.setEnabled(True)
        self._restore()

    def _cancel(self) -> None:
        self.timer.stop()
        self.monitor.mark_sector(None)
        self.current_sector = None
        self.queue.clear()
        self.skip_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.instruction.setText("Abgebrochen.")
        self._restore()

    def _restore(self) -> None:
        """Put back the calibration the device had before the run."""
        provider = self._provider()
        if provider is not None and self.suspended is not None:
            provider.calibration = self.suspended
        self.suspended = None
        self._show_current_calibration()

    # -- keeping the answer -------------------------------------------------

    def _apply(self, *, persist: bool) -> None:
        if self.fit is None:
            return
        provider = self._provider()
        if provider is None:
            return
        provider.calibration = self.fit.calibration

        if persist:
            target = save_calibration(
                self.session.output_name, self.fit.calibration, path=self._calibration_path()
            )
            self.result.setText(f"{self.result.text()}\nGespeichert in {target}")
        self._show_current_calibration()

    def _save(self) -> None:
        if self.fit is not None and not self.fit.trustworthy:
            answer = QMessageBox.question(
                self,
                "Streuung ist hoch",
                f"Die Messwerte streuen um {self.fit.spread_deg:.0f}°, mehr als eine halbe LED.\n"
                "Trotzdem speichern?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._apply(persist=True)

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt's spelling
        self._restore()
        super().closeEvent(event)


def _context(session: StudioSession):
    from lefx.sdk import InputContext
    import time

    return InputContext(
        now=time.monotonic(), led_count=session.led_count, config={}, previous_inputs={}
    )


__all__ = ["PROBE_EFFECT", "SAMPLE_INTERVAL_MS", "CalibrationPage"]
