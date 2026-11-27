"""Host-driven ordered editor container with stable row identities."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


@dataclass(frozen=True)
class _Row:
    id: UUID
    widget: QWidget
    editor: QWidget
    buttons: tuple[QPushButton, QPushButton, QPushButton]


class RepeatableContainer(QWidget):
    """make_editor(value, parent), read_editor(widget) and new_value() are host callbacks.

    Children may emit value_edited to publish their edits through the container.
    """

    value_changed = Signal(object)
    value_edited = Signal(object)

    def __init__(self, make_editor, read_editor, new_value, parent=None, *,
                 minimum=0, maximum=None, read_only=False, values=()):
        super().__init__(parent)
        if minimum < 0 or (maximum is not None and maximum < minimum):
            raise ValueError("Invalid length limits")
        self._make_editor, self._read_editor, self._new_value = make_editor, read_editor, new_value
        self.minimum, self.maximum = minimum, maximum
        self._read_only = read_only
        self._rows = []
        layout = QVBoxLayout(self)
        self._items = QVBoxLayout()
        layout.addLayout(self._items)
        self._add = QPushButton("Eintrag hinzufügen", self)
        self._add.clicked.connect(self.add)
        layout.addWidget(self._add)
        self._status = QLabel(self)
        layout.addWidget(self._status)
        self.set_value(values)

    def ids(self):
        return tuple(row.id for row in self._rows)

    def value(self):
        return [self._read_editor(row.editor) for row in self._rows]

    def set_value(self, values):
        rows = []
        try:
            for value in values:
                rows.append(self._create_row(value))
        except Exception:
            for row in rows:
                row.widget.deleteLater()
            raise
        for row in self._rows:
            self._dispose(row)
        self._rows = rows
        self._refresh()

    def set_read_only(self, state):
        self._read_only = state
        self._refresh()

    def error(self):
        count = len(self._rows)
        if count < self.minimum:
            return f"Mindestens {self.minimum} Einträge erforderlich."
        if self.maximum is not None and count > self.maximum:
            return f"Höchstens {self.maximum} Einträge erlaubt."
        return ""

    def add(self):
        if self._read_only or (self.maximum is not None and len(self._rows) >= self.maximum):
            return None
        row = self._create_row(self._new_value())
        self._rows.append(row)
        self._refresh()
        self._emit()
        row.editor.setFocus()
        return row.id

    def remove(self, row_id):
        if self._read_only or len(self._rows) <= self.minimum:
            return False
        row = self._rows.pop(self.ids().index(row_id))
        self._dispose(row)
        self._refresh()
        self._emit()
        return True

    def move(self, row_id, offset):
        index = self.ids().index(row_id)
        target = index + offset
        if self._read_only or target == index or not 0 <= target < len(self._rows):
            return False
        self._rows.insert(target, self._rows.pop(index))
        self._refresh()
        self._emit()
        return True

    def _create_row(self, value):
        panel = QWidget(self)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        row_id = uuid4()
        try:
            editor = self._make_editor(value, panel)
        except Exception:
            panel.deleteLater()
            raise
        label = QLabel(panel)
        label.setBuddy(editor)
        layout.addWidget(label)
        layout.addWidget(editor, 1)
        buttons = []
        for glyph, label_text, callback in (
            ("↑", "Eintrag nach oben", lambda: self.move(row_id, -1)),
            ("↓", "Eintrag nach unten", lambda: self.move(row_id, 1)),
            ("−", "Eintrag entfernen", lambda: self.remove(row_id)),
        ):
            button = QPushButton(glyph, panel)
            button.setToolTip(label_text)
            button.setAccessibleName(label_text)
            button.clicked.connect(callback)
            layout.addWidget(button)
            buttons.append(button)
        if hasattr(editor, "value_edited"):
            editor.value_edited.connect(lambda *_: self._emit() if row_id in self.ids() else None)
        return _Row(row_id, panel, editor, tuple(buttons))

    def _dispose(self, row):
        self._items.removeWidget(row.widget)
        row.widget.hide()
        row.widget.deleteLater()

    def _refresh(self):
        count = len(self._rows)
        for index, row in enumerate(self._rows):
            self._items.removeWidget(row.widget)
            self._items.addWidget(row.widget)
            row.widget.show()
            row.widget.layout().itemAt(0).widget().setText(str(index + 1))
            setter = getattr(row.editor, "set_read_only", None)
            if callable(setter):
                setter(self._read_only)
            else:
                row.editor.setDisabled(self._read_only)
            up, down, remove = row.buttons
            up.setEnabled(not self._read_only and index > 0)
            down.setEnabled(not self._read_only and index < count - 1)
            remove.setEnabled(not self._read_only and count > self.minimum)
        self._add.setEnabled(not self._read_only and (self.maximum is None or count < self.maximum))
        self._status.setText(self.error())
        self._status.setVisible(bool(self.error()))

    def _emit(self):
        if not self._read_only:
            self.value_changed.emit(self.value())
            self.value_edited.emit(self.value())
