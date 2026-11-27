"""A copyable Qt editor for ordered RGB color lists."""

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)


class _Swatches(QWidget):
    def __init__(self, read, parent):
        super().__init__(parent)
        self._read = read
        self.setMinimumHeight(18)

    def sizeHint(self):
        return QSize(120, 22)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        colors = self._read()
        width = self.width() / max(1, len(colors))
        for index, text in enumerate(colors):
            color = QColor(text)
            painter.fillRect(QRectF(index * width, 0, width, self.height()),
                             color if color.isValid() else self.palette().midlight())


class ColorListEditor(QWidget):
    """Read and write an ordered list of QColor-compatible RGB strings."""

    TITLE = "Farbliste bearbeiten"
    value_changed = Signal(object)
    value_edited = Signal(object)

    def __init__(self, parent=None, *, value=(), minimum=0, maximum=None,
                 compact=True, read_only=False):
        super().__init__(parent)
        if minimum < 0 or (maximum is not None and maximum < minimum):
            raise ValueError("Invalid list limits")
        self.minimum, self.maximum = minimum, maximum
        self._options = dict(minimum=minimum, maximum=maximum)
        self._read_only, self._dialog = read_only, None
        self._values = []
        self.list = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self._sample = _Swatches(self.value, self)
        self._sample.setAccessibleName("Farbliste")
        row.addWidget(self._sample, 1)
        self._count = QLabel(self)
        row.addWidget(self._count)
        layout.addLayout(row)
        if compact:
            button = QPushButton("Details…", self)
            button.setAccessibleName("Farbliste öffnen")
            button.clicked.connect(self.open_detail)
            row.addWidget(button)
        else:
            self.list = QListWidget(self)
            self.list.setAccessibleName("Geordnete Farben")
            self.list.itemChanged.connect(self._edited)
            self.list.currentRowChanged.connect(self._buttons)
            layout.addWidget(self.list)
            buttons = QHBoxLayout()
            self.add_button = self._button(buttons, "+", "Farbe hinzufügen", self.add_color)
            self.remove_button = self._button(buttons, "−", "Farbe entfernen", self.remove_color)
            self.up_button = self._button(buttons, "↑", "Farbe nach oben", lambda: self.move_color(-1))
            self.down_button = self._button(buttons, "↓", "Farbe nach unten", lambda: self.move_color(1))
            self.pick_button = self._button(buttons, "Farbe…", "Farbe auswählen", self._pick)
            layout.addLayout(buttons)
        self._status = QLabel(self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self.set_value(value)

    def _button(self, layout, text, label, callback):
        button = QPushButton(text, self)
        button.setAccessibleName(label)
        button.setToolTip(label)
        button.clicked.connect(lambda: callback())
        layout.addWidget(button)
        return button

    def value(self):
        return list(self._values)

    def set_value(self, values):
        self._values = [str(value) for value in values]
        self._rebuild(0)

    def error(self):
        count = len(self._values)
        if count < self.minimum or self.maximum is not None and count > self.maximum:
            return f"Erlaubte Anzahl: {self.minimum} bis {self.maximum if self.maximum is not None else 'unbegrenzt'}."
        for index, value in enumerate(self._values, 1):
            color = QColor(value)
            if not color.isValid() or color.alpha() != 255:
                return f"Farbe {index}: Gib eine RGB-Farbe ein, z. B. #00C066."
        return ""

    def set_read_only(self, state):
        self._read_only = state
        if self._dialog is not None:
            self._dialog.reject()
        index = self.list.currentRow() if self.list is not None else 0
        self._rebuild(index)

    def add_color(self, color="#FFFFFF"):
        if not self._read_only and (self.maximum is None or len(self._values) < self.maximum):
            self._values.append(color)
            self._changed(len(self._values) - 1)

    def remove_color(self):
        if self.list is None:
            return
        index = self.list.currentRow()
        if not self._read_only and index >= 0 and len(self._values) > self.minimum:
            del self._values[index]
            self._changed(min(index, len(self._values) - 1))

    def move_color(self, offset):
        if self.list is None:
            return
        index = self.list.currentRow()
        target = index + offset
        if not self._read_only and index >= 0 and 0 <= target < len(self._values) and offset:
            self._values.insert(target, self._values.pop(index))
            self._changed(target)

    def _pick(self):
        index = self.list.currentRow()
        if self._read_only or index < 0:
            return
        color = QColorDialog.getColor(QColor(self._values[index]), self, "RGB-Farbe")
        if color.isValid() and not self._read_only:
            self._values[index] = color.name().upper()
            self._changed(index)

    def _swatch(self, item):
        icon = QPixmap(16, 16)
        color = QColor(item.text())
        icon.fill(color if color.isValid() else self.palette().mid().color())
        item.setIcon(QIcon(icon))

    def _rebuild(self, index):
        if self.list is not None:
            self.list.blockSignals(True)
            try:
                self.list.clear()
                for value in self._values:
                    item = QListWidgetItem(value)
                    if not self._read_only:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    self._swatch(item)
                    self.list.addItem(item)
                self.list.setCurrentRow(index)
            finally:
                self.list.blockSignals(False)
            self._buttons()
        self._count.setText(f"{len(self._values)} Farben")
        self._refresh_preview()

    def _buttons(self):
        count, index = len(self._values), self.list.currentRow()
        edit = not self._read_only
        self.add_button.setEnabled(edit and (self.maximum is None or count < self.maximum))
        self.remove_button.setEnabled(edit and index >= 0 and count > self.minimum)
        self.up_button.setEnabled(edit and index > 0)
        self.down_button.setEnabled(edit and 0 <= index < count - 1)
        self.pick_button.setEnabled(edit and index >= 0)

    def _edited(self, item):
        self._values[self.list.row(item)] = item.text()
        self.list.blockSignals(True)
        try:
            self._swatch(item)
        finally:
            self.list.blockSignals(False)
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
