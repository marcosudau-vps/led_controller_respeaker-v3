"""Cyclic angle entry with exact text and a keyboard-accessible dial."""

from math import isfinite

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QDial, QHBoxLayout, QLabel, QLineEdit, QWidget


class AngleEditor(QWidget):
    value_changed = Signal(object)
    value_edited = Signal(object)

    def __init__(self, parent=None, *, value=0, decimals=1, period=360, read_only=False):
        super().__init__(parent)
        if not isfinite(period) or period <= 0 or not 0 <= decimals <= 6:
            raise ValueError("Invalid angle period or dial precision")
        self.period, self.decimals = period, decimals
        scale = 10 ** decimals
        if period * scale > 2_147_483_647:
            raise ValueError("Angle dial range exceeds Qt's integer range")
        self.dial = QDial(self)
        self.dial.setAccessibleName("Winkel einstellen")
        self.dial.setWrapping(True)
        self.dial.setRange(0, max(0, round(period * scale) - 1))
        self.dial.setFixedSize(40, 40)
        self.field = QLineEdit(self)
        self.field.setAccessibleName("Winkel in Grad")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.field, 1)
        layout.addWidget(QLabel("°", self))
        layout.addWidget(self.dial)
        self.setFocusProxy(self.field)
        self.field.textEdited.connect(self._typed)
        self.dial.valueChanged.connect(self._turned)
        self.set_read_only(read_only)
        self.set_value(value)

    def value(self):
        angle = float(self.field.text())
        if not isfinite(angle):
            raise ValueError("Ein Winkel muss endlich sein.")
        return angle % self.period

    def error(self):
        try:
            self.value()
        except ValueError:
            return "Gib einen Winkel in Grad ein."
        return ""

    def set_value(self, value):
        self.field.setText(str(value))
        self._sync_dial()

    def set_read_only(self, state):
        self.field.setReadOnly(state)
        self.dial.setEnabled(not state)

    def _sync_dial(self):
        if not self.error():
            with QSignalBlocker(self.dial):
                self.dial.setValue(round(self.value() * 10 ** self.decimals)
                                   % (self.dial.maximum() + 1))

    def _typed(self):
        self._sync_dial()
        self._emit()

    def _turned(self, position):
        self.field.setText(str(position / 10 ** self.decimals))
        self._emit()

    def _emit(self):
        value = self.field.text() if self.error() else self.value()
        self.value_changed.emit(value)
        self.value_edited.emit(value)
