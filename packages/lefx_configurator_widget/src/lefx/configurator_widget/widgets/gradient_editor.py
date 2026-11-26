"""A copyable color-stop editor with a live gradient and exact positions."""

from copy import deepcopy
from math import isfinite

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QHeaderView, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class _GradientBar(QWidget):
    def __init__(self, read, select, parent):
        super().__init__(parent)
        self._read, self._select = read, select
        self.setMinimumHeight(22)

    def sizeHint(self):
        return QSize(140, 22)

    def stops(self):
        result = []
        for index, stop in enumerate(self._read()):
            try:
                position = float(stop["at"])
                color = QColor(stop["color"])
            except (TypeError, ValueError):
                continue
            if 0 <= position <= 1 and color.isValid():
                result.append((index, position, color))
        return result

    def mousePressEvent(self, event):
        if self._select is not None and (stops := self.stops()):
            at = event.position().x() / max(1, self.width() - 1)
            self._select(min(stops, key=lambda stop: abs(stop[1] - at))[0])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        stops = self.stops()
        if not stops:
            return
        gradient = QLinearGradient(0, 0, self.width(), 0)
        for _, at, color in stops:
            gradient.setColorAt(at, color)
        painter.fillRect(0, 0, self.width(), self.height() - 6, gradient)
        painter.setBrush(self.palette().text())
        painter.setPen(Qt.PenStyle.NoPen)
        for _, at, _ in stops:
            x = at * (self.width() - 1)
            bottom = self.height() - 1
            painter.drawPolygon(QPolygonF([QPointF(x, bottom - 6),
                                           QPointF(x - 4, bottom), QPointF(x + 4, bottom)]))


class GradientEditor(QWidget):
    """Stops are {'at': number in 0..1, 'color': RGB string}, in ascending order."""

    TITLE = "Farbverlauf bearbeiten"
    value_changed = Signal(object)
    value_edited = Signal(object)

    def __init__(self, parent=None, *, value=None, minimum=2, maximum=16,
                 require_endpoints=True, compact=True, read_only=False):
        super().__init__(parent)
        if minimum < 0 or (maximum is not None and maximum < minimum):
            raise ValueError("Invalid stop limits")
        if require_endpoints and (minimum < 2 or (maximum is not None and maximum < 2)):
            raise ValueError("Pinned endpoints require at least two stops")
        self.minimum, self.maximum = minimum, maximum
        self.require_endpoints = require_endpoints
        self._options = dict(minimum=minimum, maximum=maximum, require_endpoints=require_endpoints)
        self._read_only, self._dialog = read_only, None
        self._stops = []
        self.table = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self._sample = _GradientBar(self.value, None if compact else self._select, self)
        self._sample.setAccessibleName("Farbverlauf mit Stützpunkten")
        row.addWidget(self._sample, 1)
        layout.addLayout(row)
        if compact:
            button = QPushButton("Details…", self)
            button.setAccessibleName("Farbverlauf öffnen")
            button.clicked.connect(self.open_detail)
            row.addWidget(button)
        else:
            self.table = QTableWidget(0, 2, self)
            self.table.setAccessibleName("Stützpunkte")
            self.table.setHorizontalHeaderLabels(["Position (0–1)", "RGB-Farbe"])
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table.itemChanged.connect(self._edited)
            self.table.currentCellChanged.connect(self._buttons)
            layout.addWidget(self.table)
            buttons = QHBoxLayout()
            self.add_button = self._button(buttons, "+", "Stützpunkt hinzufügen", self.add_stop)
            self.remove_button = self._button(buttons, "−", "Stützpunkt entfernen", self.remove_stop)
            self.sort_button = self._button(buttons, "Sortieren", "Nach Position sortieren", self.sort_stops)
            self.pick_button = self._button(buttons, "Farbe…", "Farbe auswählen", self._pick)
            layout.addLayout(buttons)
        self._status = QLabel(self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self.set_value(value if value is not None else [
            {"at": 0, "color": "#2616B7"}, {"at": 1, "color": "#00C9A1"}
        ])

    def _button(self, layout, text, label, callback):
        button = QPushButton(text, self)
        button.setAccessibleName(label)
        button.setToolTip(label)
        button.clicked.connect(lambda: callback())
        layout.addWidget(button)
        return button

    def value(self):
        return deepcopy(self._stops)

    def set_value(self, stops):
        values = list(stops)
        if any(not isinstance(stop, dict) or set(stop) != {"at", "color"} for stop in values):
            raise ValueError("Every stop must have exactly at and color")
        self._stops = deepcopy(values)
        self._rebuild(0)

    def _positions(self):
        return [float(stop["at"]) for stop in self._stops]

    def error(self):
        count = len(self._stops)
        if count < self.minimum or self.maximum is not None and count > self.maximum:
            return f"Erlaubte Anzahl: {self.minimum} bis {self.maximum if self.maximum is not None else 'unbegrenzt'}."
        for index, stop in enumerate(self._stops, 1):
            try:
                valid = 0 <= float(stop["at"]) <= 1
            except (TypeError, ValueError):
                valid = False
            color = QColor(str(stop["color"]))
            if not valid:
                return f"Stützpunkt {index}: Position muss zwischen 0 und 1 liegen."
            if not color.isValid() or color.alpha() != 255:
                return f"Stützpunkt {index}: Gib eine RGB-Farbe ein, z. B. #00C066."
        positions = self._positions()
        if positions != sorted(positions):
            return "Sortiere die Stützpunkte nach Position."
        if self.require_endpoints and (positions[0] != 0 or positions[-1] != 1):
            return "Der Verlauf braucht die Endpunkte 0 und 1."
        return ""

    def set_read_only(self, state):
        self._read_only = state
        if self._dialog is not None:
            self._dialog.reject()
        self._rebuild(self.table.currentRow() if self.table is not None else 0)

    def add_stop(self):
        if self._read_only or self.maximum is not None and len(self._stops) >= self.maximum:
            return
        try:
            positions = self._positions()
            if any(not isfinite(at) or not 0 <= at <= 1 for at in positions):
                raise ValueError
            positions = [0, *sorted(set(positions)), 1]
            start, end = max(zip(positions, positions[1:]), key=lambda p: p[1] - p[0])
            at = (start + end) / 2
            index = next((i for i, pos in enumerate(self._positions()) if pos > at), len(self._stops))
        except (ValueError, TypeError):
            at, index = 0.5, len(self._stops)
        self._stops.insert(index, {"at": at, "color": "#FFFFFF"})
        self._changed(index)

    def _pinned(self, index):
        if not self.require_endpoints or len(self._stops) <= 1:
            return False
        try:
            return ((index == 0 and float(self._stops[index]["at"]) == 0)
                    or (index == len(self._stops) - 1 and float(self._stops[index]["at"]) == 1))
        except (TypeError, ValueError):
            return False

    def remove_stop(self):
        if self.table is None:
            return
        index = self.table.currentRow()
        if not self._read_only and index >= 0 and len(self._stops) > self.minimum and not self._pinned(index):
            del self._stops[index]
            self._changed(min(index, len(self._stops) - 1))

    def sort_stops(self):
        if self._read_only:
            return
        try:
            positions = self._positions()
        except (ValueError, TypeError):
            return
        if all(isfinite(at) for at in positions):
            self._stops = [stop for _, stop in sorted(zip(positions, self._stops), key=lambda item: item[0])]
            self._changed(0)

    def _select(self, index):
        self.table.setCurrentCell(index, 0)
        self.table.setFocus()

    def _pick(self):
        index = self.table.currentRow()
        if self._read_only or index < 0:
            return
        color = QColorDialog.getColor(QColor(str(self._stops[index]["color"])), self, "RGB-Farbe")
        if color.isValid() and not self._read_only:
            self._stops[index]["color"] = color.name().upper()
            self._changed(index)

    def _rebuild(self, index):
        if self.table is not None:
            self.table.blockSignals(True)
            try:
                self.table.clearContents()
                self.table.setRowCount(len(self._stops))
                for row, stop in enumerate(self._stops):
                    for column, key in enumerate(("at", "color")):
                        item = QTableWidgetItem(str(stop[key]))
                        if self._read_only or column == 0 and self._pinned(row):
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.table.setItem(row, column, item)
                if 0 <= index < len(self._stops):
                    self.table.setCurrentCell(index, 0)
            finally:
                self.table.blockSignals(False)
            self._buttons()
        self._refresh_preview()

    def _buttons(self):
        count, index = len(self._stops), self.table.currentRow()
        edit = not self._read_only
        self.add_button.setEnabled(edit and (self.maximum is None or count < self.maximum))
        self.remove_button.setEnabled(edit and index >= 0 and count > self.minimum and not self._pinned(index))
        self.pick_button.setEnabled(edit and index >= 0)
        self.sort_button.setEnabled(edit and count > 1)

    def _edited(self, item):
        text = item.text()
        if item.column() == 0:
            try:
                value = float(text)
            except ValueError:
                value = text
            self._stops[item.row()]["at"] = value
        else:
            self._stops[item.row()]["color"] = text
        self._buttons()
        self._refresh_preview()
        self._emit()

    def _changed(self, index):
        self._rebuild(index)
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
