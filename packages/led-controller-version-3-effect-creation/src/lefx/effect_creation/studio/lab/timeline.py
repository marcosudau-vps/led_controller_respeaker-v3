"""The timeline under the editor: transport, a ruler to scrub on, step controls.

Owns no time of its own. The page's :class:`~.clock.PreviewClock` decides what
"now" is; this widget shows it and reports what the user did — play, stop,
a click on the ruler, a step — as signals.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

TRACK_COLOR = QColor(30, 33, 40)
TICK_COLOR = QColor(110, 116, 130)
LABEL_COLOR = QColor(160, 166, 180)
PLAYHEAD_COLOR = QColor(235, 90, 70)
MARK_COLOR = QColor(90, 170, 230)
CURRENT_MARK_COLOR = QColor(250, 210, 90)
NICE_INTERVALS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300)
SPEEDS = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0)


def clock_text(seconds: float) -> str:
    minutes, rest = divmod(max(0.0, seconds), 60)
    return f"{int(minutes):02d}:{rest:06.3f}"


class TimelineRuler(QWidget):
    """A time axis with a playhead; click or drag anywhere on it to seek."""

    seeked = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.start, self.end, self.position = 0.0, 10.0, 0.0
        self.marks: list[float] = []
        self.current_mark: float | None = None
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Klicken oder ziehen, um zu einem Zeitpunkt zu springen")

    def set_range(self, start: float, end: float) -> None:
        self.start, self.end = float(start), max(float(start) + 0.001, float(end))
        self.update()

    def set_position(self, position: float) -> None:
        self.position = float(position)
        self.update()

    def set_marks(self, marks: list[float], current: float | None) -> None:
        self.marks, self.current_mark = marks, current
        self.update()

    def _x(self, seconds: float) -> float:
        width = max(1.0, self.width() - 16.0)
        return 8.0 + (seconds - self.start) / (self.end - self.start) * width

    def time_at(self, x: float) -> float:
        width = max(1.0, self.width() - 16.0)
        ratio = min(1.0, max(0.0, (x - 8.0) / width))
        return self.start + ratio * (self.end - self.start)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt's spelling
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(TRACK_COLOR)
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 5, 5)

        span = self.end - self.start
        pixels_per_second = max(1e-6, (self.width() - 16.0) / span)
        major = next((step for step in NICE_INTERVALS if step * pixels_per_second >= 70), NICE_INTERVALS[-1])
        minor = major / 5
        font = QFont(painter.font())
        font.setPointSizeF(7.5)
        painter.setFont(font)
        first = math.ceil(self.start / minor - 1e-9)
        last = math.floor(self.end / minor + 1e-9)
        for index in range(first, last + 1):
            seconds = index * minor
            x = self._x(seconds)
            is_major = abs(seconds / major - round(seconds / major)) < 1e-6
            painter.setPen(QPen(TICK_COLOR, 1.0))
            painter.drawLine(QPointF(x, 0), QPointF(x, 12 if is_major else 6))
            if is_major:
                painter.setPen(LABEL_COLOR)
                painter.drawText(QRectF(x - 30, 12, 60, 14), Qt.AlignmentFlag.AlignCenter, f"{seconds:g} s")

        visible = [mark for mark in self.marks if self.start <= mark <= self.end]
        if visible and (self.end - self.start) / len(visible) * pixels_per_second >= 3:
            for mark in visible:
                current = self.current_mark is not None and abs(mark - self.current_mark) < 1e-6
                painter.setPen(QPen(CURRENT_MARK_COLOR if current else MARK_COLOR, 2.0 if current else 1.0))
                x = self._x(mark)
                painter.drawLine(QPointF(x, self.height() - 12), QPointF(x, self.height() - 3))

        x = self._x(min(self.end, max(self.start, self.position)))
        painter.setPen(QPen(PLAYHEAD_COLOR, 2.0))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        painter.setBrush(PLAYHEAD_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(x - 5, 0), QPointF(x + 5, 0), QPointF(x, 7)]))
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.seeked.emit(self.time_at(event.position().x()))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.seeked.emit(self.time_at(event.position().x()))


class Timeline(QWidget):
    """Transport row, ruler, and the step row below it."""

    play_toggled = Signal()
    stopped = Signal()
    seeked = Signal(float)
    range_changed = Signal(float)
    speed_changed = Signal(float)
    loop_changed = Signal(bool)
    stepped = Signal(int)
    plan_changed = Signal(str)
    sampling_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(3)

        transport = QHBoxLayout()
        self.play_button = self._tool("▶", "Abspielen / Pausieren (Leertaste)", self.play_toggled.emit)
        self.play_button.setMinimumWidth(36)
        self.stop_button = self._tool("⏹", "Stopp: anhalten und zurück zum Anfang", self.stopped.emit)
        self.time_label = QLabel(clock_text(0))
        self.time_label.setStyleSheet("font-family: Consolas, monospace; font-size: 14px; padding: 0 8px;")
        self.goto = QDoubleSpinBox()
        self.goto.setRange(0.0, 3600.0)
        self.goto.setDecimals(3)
        self.goto.setSingleStep(0.05)
        self.goto.setSuffix(" s")
        self.goto.setKeyboardTracking(False)
        self.goto.setToolTip("Genau zu diesem Zeitpunkt springen")
        self.goto.valueChanged.connect(self.seeked.emit)
        self.span = QDoubleSpinBox()
        self.span.setRange(0.5, 600.0)
        self.span.setValue(10.0)
        self.span.setDecimals(1)
        self.span.setSuffix(" s")
        self.span.setKeyboardTracking(False)
        self.span.setToolTip("Länge des Vorschauzeitraums")
        self.span.valueChanged.connect(self.range_changed.emit)
        self.speed = QComboBox()
        for speed in SPEEDS:
            self.speed.addItem(f"{speed:g}×", speed)
        self.speed.setCurrentIndex(SPEEDS.index(1.0))
        self.speed.setToolTip("Wiedergabegeschwindigkeit der Vorschau (nicht der Effektparameter speed)")
        self.speed.currentIndexChanged.connect(lambda _: self.speed_changed.emit(self.speed.currentData()))
        self.loop = QCheckBox("Schleife")
        self.loop.setChecked(True)
        self.loop.toggled.connect(self.loop_changed.emit)
        transport.addWidget(self.play_button)
        transport.addWidget(self.stop_button)
        transport.addWidget(self.time_label)
        transport.addStretch(1)
        for label, widget in (("Gehe zu", self.goto), ("Zeitraum", self.span), ("Tempo", self.speed)):
            transport.addWidget(QLabel(label))
            transport.addWidget(widget)
        transport.addWidget(self.loop)
        layout.addLayout(transport)

        self.ruler = TimelineRuler()
        self.ruler.seeked.connect(self.seeked.emit)
        layout.addWidget(self.ruler)

        steps = QHBoxLayout()
        steps.addWidget(QLabel("Schritte"))
        self.plans = QComboBox()
        self.plans.setMinimumWidth(260)
        self.plans.setToolTip("Wonach geschrittet wird. Abtastpunkte sind Zeitpunkte, keine Zustände.")
        self.plans.currentIndexChanged.connect(lambda _: self.plan_changed.emit(self.plans.currentData() or ""))
        self.previous_step = self._tool("◀", "Vorheriger Schritt (,)", lambda: self.stepped.emit(-1))
        self.next_step = self._tool("▶", "Nächster Schritt (.)", lambda: self.stepped.emit(1))
        self.sampling = QDoubleSpinBox()
        self.sampling.setRange(0.01, 60.0)
        self.sampling.setDecimals(2)
        self.sampling.setValue(0.25)
        self.sampling.setSuffix(" s")
        self.sampling.setKeyboardTracking(False)
        self.sampling.setToolTip("Abstand der gleichmäßigen Abtastpunkte")
        self.sampling.valueChanged.connect(self.sampling_changed.emit)
        self.samples_per_cycle = QSpinBox()
        self.samples_per_cycle.setRange(2, 64)
        self.samples_per_cycle.setValue(8)
        self.samples_per_cycle.setPrefix("je Periode ")
        self.samples_per_cycle.setToolTip("Abtastpunkte je Periode für stufenlose Animationen")
        self.step_info = QLabel("")
        self.step_info.setStyleSheet("color: #aab;")
        steps.addWidget(self.plans)
        steps.addWidget(self.previous_step)
        steps.addWidget(self.next_step)
        steps.addWidget(self.sampling)
        steps.addWidget(self.samples_per_cycle)
        steps.addWidget(self.step_info, stretch=1)
        layout.addLayout(steps)

    def _tool(self, text: str, tip: str, action) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.clicked.connect(action)
        return button

    # -- shown state --------------------------------------------------------

    def set_playing(self, playing: bool) -> None:
        self.play_button.setText("⏸" if playing else "▶")

    def set_time(self, position: float) -> None:
        self.time_label.setText(f"{clock_text(position)} / {clock_text(self.ruler.end)}")
        self.ruler.set_position(position)
        if not self.goto.hasFocus():
            self.goto.blockSignals(True)
            self.goto.setValue(position)
            self.goto.blockSignals(False)

    def set_range(self, start: float, end: float) -> None:
        self.ruler.set_range(start, end)
        self.goto.setRange(start, end)

    def set_plans(self, plans: list[tuple[str, str]], current: str) -> None:
        self.plans.blockSignals(True)
        self.plans.clear()
        for key, title in plans:
            self.plans.addItem(title, key)
        self.plans.setCurrentIndex(max(0, self.plans.findData(current)))
        self.plans.blockSignals(False)

    def set_sampling_mode(self, uniform: bool) -> None:
        self.sampling.setVisible(uniform)


__all__ = ["Timeline", "TimelineRuler", "clock_text"]
