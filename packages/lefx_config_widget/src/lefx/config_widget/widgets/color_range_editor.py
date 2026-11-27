"""A copyable HSV range editor using true hue, saturation and value."""

from copy import deepcopy

from PySide6.QtCore import QRectF, QSignalBlocker, QSize, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)


_CHANNELS = (
    ("hue", "Farbton (°)", 360),
    ("saturation", "Sättigung (0–1)", 1),
    ("brightness", "HSV-Wert (0–1)", 1),
)


class _HsvSample(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setMinimumHeight(22)

    def sizeHint(self):
        return QSize(140, 25)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        if self.editor.error():
            return
        values = self.editor.value()
        columns, rows = 36, 8
        w, h = self.width() / columns, self.height() / rows
        hue, saturation, brightness = (tuple(map(float, values[name])) for name, _, _ in _CHANNELS)
        for col in range(columns):
            angle = (hue[0] + (hue[1] - hue[0]) * col / (columns - 1)) % 360
            for row in range(rows):
                fraction = row / (rows - 1)
                sat = saturation[0] + (saturation[1] - saturation[0]) * fraction
                val = brightness[1] - (brightness[1] - brightness[0]) * fraction
                painter.fillRect(QRectF(col * w, row * h, w + .5, h + .5),
                                 QColor.fromHsvF(angle / 360, sat, val))


class ColorRangeEditor(QWidget):
    """HSV dictionary with hue in degrees and saturation/brightness as ratios."""

    TITLE = "HSV-Farbbereich bearbeiten"
    value_changed = Signal(object)
    value_edited = Signal(object)

    def __init__(self, parent=None, *, value=None, compact=True, read_only=False):
        super().__init__(parent)
        self._read_only, self._dialog = read_only, None
        self._options = {}
        self._values = {}
        self.fields = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self._sample = _HsvSample(self)
        self._sample.setAccessibleName("HSV-Farbbereich")
        row.addWidget(self._sample, 1)
        layout.addLayout(row)
        if compact:
            button = QPushButton("Details…", self)
            button.setAccessibleName("HSV-Farbbereich öffnen")
            button.clicked.connect(self.open_detail)
            row.addWidget(button)
        else:
            grid = QGridLayout()
            grid.addWidget(QLabel("Minimum", self), 0, 1)
            grid.addWidget(QLabel("Maximum", self), 0, 2)
            for index, (name, label, _) in enumerate(_CHANNELS, 1):
                grid.addWidget(QLabel(label, self), index, 0)
                pair = []
                for column, bound in enumerate(("Minimum", "Maximum"), 1):
                    field = QLineEdit(self)
                    field.setAccessibleName(f"{label} {bound}")
                    field.textEdited.connect(self._edited)
                    grid.addWidget(field, index, column)
                    pair.append(field)
                self.fields[name] = tuple(pair)
            layout.addLayout(grid)
        self._status = QLabel(self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self.set_read_only(read_only)
        self.set_value(value if value is not None else {
            "hue": [0, 360], "saturation": [0.6, 1], "brightness": [0.45, 1]
        })

    def value(self):
        return deepcopy(self._values)

    def set_value(self, value):
        if set(value) != {name for name, _, _ in _CHANNELS}:
            raise ValueError("Expected exactly hue, saturation and brightness")
        if any(len(pair) != 2 for pair in value.values()):
            raise ValueError("Expected a min/max pair per HSV channel")
        self._values = {key: list(pair) for key, pair in value.items()}
        for name, fields in self.fields.items():
            for field, number in zip(fields, self._values[name]):
                with QSignalBlocker(field):
                    field.setText(str(number))
        self._refresh_preview()

    def error(self):
        for name, label, maximum in _CHANNELS:
            try:
                low, high = map(float, self._values[name])
                valid = 0 <= low <= high <= maximum
            except (TypeError, ValueError):
                valid = False
            if not valid:
                return f"{label}: Gib ein geordnetes Paar zwischen 0 und {maximum} ein."
        return ""

    def set_read_only(self, state):
        self._read_only = state
        if self._dialog is not None:
            self._dialog.reject()
        for pair in self.fields.values():
            for field in pair:
                field.setReadOnly(state)

    def _edited(self):
        for name, fields in self.fields.items():
            pair = []
            for field in fields:
                try:
                    value = float(field.text())
                except ValueError:
                    value = field.text()
                pair.append(value)
            self._values[name] = pair
        self._refresh_preview()
        self._emit()

    def _refresh_preview(self):
        error = self.error()
        self._status.setText(error)
        self._status.setVisible(bool(error))
        self._sample.update()

    def create_detail(self, parent=None):
        """Create an independent full editor, suitable for a host stack page."""
        return type(self)(parent, value=self.value(), compact=False,
                          read_only=self._read_only, **self._options)

    def commit_detail(self, editor):
        """Copy a valid detail value as a user edit. Return whether it was applied."""
        if self._read_only or editor.error():
            return False
        value = editor.value()
        if value != self.value():
            self.set_value(value)
            self._emit()
        return True

    def open_detail(self):
        if self._dialog is not None:
            self._dialog.raise_()
            return
        dialog = QDialog(self)
        self._dialog = dialog
        dialog.setWindowTitle(self.TITLE)
        layout = QVBoxLayout(dialog)
        editor = self.create_detail(dialog)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close if self._read_only else
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)
        if not self._read_only:
            ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
            ok.setText("Übernehmen")
            ok.setEnabled(not editor.error())
            editor.value_edited.connect(lambda _: ok.setEnabled(not editor.error()))
            buttons.accepted.connect(lambda: dialog.accept() if self.commit_detail(editor) else None)
        dialog.finished.connect(self._close_detail)
        dialog.open()

    def _close_detail(self):
        dialog, self._dialog = self._dialog, None
        dialog.deleteLater()

    def _emit(self):
        self.value_changed.emit(self.value())
        self.value_edited.emit(self.value())
