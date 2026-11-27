"""Standalone numeric pair with precise input, increment controls and a range bar."""

from math import isfinite

from PySide6.QtCore import QRectF, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class _RangeBar(QWidget):
    def __init__(self, read, limits, parent):
        super().__init__(parent)
        self.read, self.limits = read, limits
        self.setMinimumHeight(9)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().brush(QPalette.ColorRole.Midlight))
        try:
            low, high = self.read()
        except ValueError:
            return
        minimum, maximum = self.limits
        minimum = min(0, low) if minimum is None else minimum
        maximum = max(1, high) if maximum is None else maximum
        span = maximum - minimum or 1
        start, end = (low - minimum) / span, (high - minimum) / span
        painter.fillRect(QRectF(start * self.width(), 0, max(2, (end - start) * self.width()),
                                self.height()), self.palette().brush(QPalette.ColorRole.Highlight))


class RangeEditor(QWidget):
    value_changed = Signal(object)
    value_edited = Signal(object)

    def __init__(self, parent=None, *, value=(0, 1), number_type=float, minimum=None,
                 maximum=None, step=1, decimals=6, unit="", read_only=False):
        super().__init__(parent)
        if (number_type not in (int, float) or step <= 0 or decimals < 0
                or (minimum is not None and maximum is not None and minimum > maximum)
                or (number_type is int and int(step) != step)):
            raise ValueError("Invalid numeric range configuration")
        self.number_type = number_type
        self.step = int(step) if number_type is int else step
        self.decimals = decimals
        self.minimum, self.maximum = minimum, maximum
        self.fields = []
        self._controls = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        inputs = QHBoxLayout()
        for label in ("Minimum", "Maximum"):
            field = QLineEdit(self)
            field.setAccessibleName(f"{label} {unit}".strip())
            field.textEdited.connect(self._edited)
            self.fields.append(field)
            title = QLabel(f"{label} {unit}".strip(), self)
            title.setBuddy(field)
            row = QHBoxLayout()
            row.addWidget(title)
            row.addWidget(field, 1)
            for delta, glyph in ((-1, "−"), (1, "+")):
                button = QPushButton(glyph, self)
                button.setAccessibleName(f"{label} {'senken' if delta < 0 else 'erhöhen'}")
                button.setToolTip(button.accessibleName())
                button.clicked.connect(lambda checked=False, f=field, d=delta: self._step(f, d))
                self._controls.append(button)
                row.addWidget(button)
            inputs.addLayout(row, 1)
        layout.addLayout(inputs)
        self.setFocusProxy(self.fields[0])
        self._bar = _RangeBar(self.value, (minimum, maximum), self)
        layout.addWidget(self._bar)
        self._error = QLabel(self)
        self._error.setWordWrap(True)
        layout.addWidget(self._error)
        self.set_read_only(read_only)
        self.set_value(value)

    def _number(self, text):
        number = self.number_type(text)
        if self.number_type is float and not isfinite(number):
            raise ValueError("Endliche Zahl erforderlich.")
        return number

    def value(self):
        try:
            low, high = (self._number(field.text()) for field in self.fields)
        except ValueError as exc:
            raise ValueError("Gib zwei gültige Zahlen ein.") from exc
        if low > high:
            raise ValueError("Minimum darf das Maximum nicht überschreiten.")
        if self.minimum is not None and low < self.minimum:
            raise ValueError(f"Untere Grenze: {self.minimum}")
        if self.maximum is not None and high > self.maximum:
            raise ValueError(f"Obere Grenze: {self.maximum}")
        return low, high

    def error(self):
        try:
            self.value()
        except ValueError as exc:
            return str(exc)
        return ""

    def set_value(self, value):
        low, high = value
        for field, number in zip(self.fields, (low, high)):
            field.setText(str(number))
        self._refresh()

    def set_read_only(self, state):
        for field in self.fields:
            field.setReadOnly(state)
        for button in self._controls:
            button.setDisabled(state)

    def _step(self, field, direction):
        try:
            number = self._number(field.text()) + direction * self.step
        except ValueError:
            return
        if self.minimum is not None and number < self.minimum:
            return
        if self.maximum is not None and number > self.maximum:
            return
        if self.number_type is float:
            number = round(number, self.decimals)
        field.setText(str(number))
        self._edited()

    def _refresh(self):
        error = self.error()
        self._error.setText(error)
        self._error.setVisible(bool(error))
        self._bar.update()

    def _edited(self):
        self._refresh()
        value = tuple(field.text() for field in self.fields) if self.error() else self.value()
        self.value_changed.emit(value)
        self.value_edited.emit(value)
