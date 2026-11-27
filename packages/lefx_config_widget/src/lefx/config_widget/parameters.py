"""Schema-driven override form. Snapshots retain the raw values loaded by hosts."""

from collections.abc import Mapping
from copy import deepcopy
from json import dumps, loads, JSONDecodeError
from math import isfinite

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from lefx.sdk import MISSING, ParameterValidationError, ParamType
from lefx.sdk.parameters import normalize_parameter_value
from lefx.sdk.validation import normalize_values

from .mapping import Diagnostic
from .widgets import AngleEditor, ColorListEditor, ColorRangeEditor, GradientEditor


def _format(value):
    if value is MISSING:
        return "Kein Wert"
    return dumps(value, ensure_ascii=False, default=repr)


def _normalize(parameter, raw):
    value = normalize_parameter_value(parameter, raw)
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Erwartet wird eine endliche Zahl.")
    return value


def _validate(schema, raw, prefix, *, inherited=None):
    try:
        values = normalize_values(schema, raw, field_prefix=prefix)
    except ParameterValidationError as exc:
        return tuple(Diagnostic(issue.field, issue.message) for issue in exc.issues)
    except (OverflowError, ValueError, TypeError) as exc:
        return (Diagnostic(prefix, str(exc)),)

    errors = []
    for key, parameter in schema.items():
        if parameter.required and key not in values and not (inherited and key in inherited):
            errors.append(Diagnostic(f"{prefix}.{key}", "Dieser Wert ist erforderlich."))
        if isinstance(values.get(key), float) and not isfinite(values[key]):
            errors.append(Diagnostic(f"{prefix}.{key}", "Erwartet wird eine endliche Zahl."))
    return tuple(errors)


def _text_color_button(field, parent):
    button = QToolButton(parent)
    button.setText("Farbe…")
    button.setAccessibleName(f"{field.accessibleName()} auswählen")

    def choose():
        color = QColorDialog.getColor(QColor(field.text()), parent, field.accessibleName())
        if color.isValid():
            text = color.name().upper()
            field.setText(text)
            field.textEdited.emit(text)

    button.clicked.connect(choose)
    return button


class _RawEditor(QPushButton):
    """Explicit repair path for a value the visual editor cannot represent."""

    value_edited = Signal(object)

    def __init__(self, raw, parent):
        super().__init__("Rohwert bearbeiten…", parent)
        self.raw = deepcopy(raw)
        self.setToolTip(_format(raw))
        self.clicked.connect(self.open_detail)
        self._dialog = None

    def open_detail(self):
        if self._dialog is not None:
            self._dialog.raise_()
            return
        dialog = QDialog(self)
        self._dialog = dialog
        dialog.setWindowTitle("Rohwert bearbeiten")
        layout = QVBoxLayout(dialog)
        field = QPlainTextEdit(_format(self.raw), dialog)
        field.setAccessibleName("Parameterwert als JSON")
        error = QLabel(dialog)
        error.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        layout.addWidget(field)
        layout.addWidget(error)
        layout.addWidget(buttons)

        def accept():
            try:
                parsed = loads(field.toPlainText())
            except JSONDecodeError as exc:
                error.setText(str(exc))
                return
            self.raw = parsed
            self.setToolTip(_format(parsed))
            self.value_edited.emit(deepcopy(parsed))
            dialog.accept()

        def finished():
            self._dialog = None
            dialog.deleteLater()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        dialog.finished.connect(finished)
        dialog.open()


class _ParameterRow(QWidget):
    edited = Signal(object)
    omitted = Signal()

    def __init__(self, parameter, inherited, inheritance_label, raw, parent):
        super().__init__(parent)
        self.parameter = parameter
        self.inherited = inherited
        self.raw = deepcopy(raw)
        self._last_override = deepcopy(raw) if raw is not None else MISSING
        self._read_only = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)
        self.mode = QComboBox(self)
        self.mode.setAccessibleName(f"{parameter.name} Wertquelle")
        self.mode.addItem(inheritance_label, "inherit")
        self.mode.addItem("Eigener Wert", "override")
        if parameter.nullable or raw is None:
            self.mode.addItem("Explizit null", "null")
        if raw is not MISSING:
            self.mode.setCurrentIndex(self.mode.findData("null" if raw is None else "override"))
        self._layout.addWidget(self.mode)
        self._holder = QWidget(self)
        self._input_layout = QHBoxLayout(self._holder)
        self._input_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._holder)
        self.notice = QLabel(self)
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        self._layout.addWidget(self.notice)
        self.mode.currentIndexChanged.connect(self._change_mode)
        self._rebuild()
        self._show_notice()

    def _show_notice(self):
        mode = self.mode.currentData()
        if mode == "null":
            value = None
        elif mode == "inherit":
            value = self.inherited
        else:
            value = self.raw
        notice = ""
        if value is not MISSING:
            try:
                _normalize(self.parameter, value)
            except (OverflowError, TypeError, ValueError) as exc:
                notice = str(exc)
        elif self.parameter.required or mode == "override":
            notice = "Ein Wert ist erforderlich."
        elif mode == "inherit":
            notice = "Kein Standardwert definiert."
        if mode == "inherit" and value is None and not notice:
            notice = "null"
        self.notice.setText(notice)
        self.notice.setVisible(bool(notice))

    def _change_mode(self):
        mode = self.mode.currentData()
        if mode == "inherit":
            self.raw = MISSING
        elif mode == "null":
            self.raw = None
        else:
            self.raw = deepcopy(self._last_override)
            if self.raw is MISSING:
                self.raw = deepcopy(self.inherited) if self.inherited is not None else MISSING
            if self.raw is MISSING:
                self.raw = ""
        self._rebuild()
        self._show_notice()
        if self.raw is MISSING:
            self.omitted.emit()
        else:
            self.edited.emit(deepcopy(self.raw))

    def _write(self, raw):
        try:
            value = _normalize(self.parameter, raw)
        except (OverflowError, ValueError, TypeError):
            value = raw
        self.raw = self._last_override = deepcopy(value)
        self._show_notice()
        self.edited.emit(deepcopy(value))

    def _rebuild(self):
        while self._input_layout.count():
            widget = self._input_layout.takeAt(0).widget()
            widget.hide()
            for dialog in widget.findChildren(QDialog):
                dialog.reject()
            widget.deleteLater()

        mode = self.mode.currentData()
        display = self.inherited if mode == "inherit" else self.raw
        self._holder.setVisible(mode == "override" or (mode == "inherit" and display not in (MISSING, None)))
        if self._holder.isHidden():
            return
        locked = self._read_only or mode != "override"
        parameter = self.parameter
        try:
            canonical = _normalize(parameter, display)
        except (OverflowError, TypeError, ValueError):
            canonical = display
        kind = parameter.type

        if kind in (ParamType.BOOL, ParamType.ENUM):
            combo = QComboBox(self._holder)
            values = (True, False) if kind is ParamType.BOOL else parameter.enum_values
            index = next((i for i, value in enumerate(values)
                          if type(value) is type(canonical) and value == canonical), -1)
            if index < 0:
                combo.addItem(f"Ungültig: {_format(display)}")
                combo.model().item(0).setEnabled(False)
            for value in values:
                combo.addItem(_format(value), value)
            combo.setCurrentIndex(max(0, index))
            offset = 1 if index < 0 else 0
            combo.activated.connect(lambda selected: self._write(values[selected - offset])
                                    if selected >= offset else None)
            combo.setAccessibleName(parameter.name)
            combo.setDisabled(locked)
            self._input_layout.addWidget(combo, 1)
            combo.show()
            return

        if kind in (ParamType.COLOR_LIST, ParamType.GRADIENT, ParamType.COLOR_RANGE):
            try:
                editor = self._complex(canonical, locked)
            except (ValueError, TypeError, AttributeError):
                editor = _RawEditor(display, self._holder)
                editor.setDisabled(locked)
            editor.value_edited.connect(self._write)
            editor.setAccessibleName(parameter.name)
            self._input_layout.addWidget(editor, 1)
            editor.show()
            return

        if kind is ParamType.ANGLE_DEG and isinstance(canonical, (int, float)):
            angle = AngleEditor(self._holder, value=canonical, read_only=locked)
            angle.field.setAccessibleName(parameter.name)
            angle.value_edited.connect(self._write)
            self._input_layout.addWidget(angle, 1)
            angle.show()
            return

        field = QLineEdit(self._holder)
        field.setText(str(display) if isinstance(display, str) else _format(display))
        field.setAccessibleName(parameter.name)
        field.setReadOnly(locked)
        field.textEdited.connect(self._write)
        self._input_layout.addWidget(field, 1)
        if kind is ParamType.COLOR:
            button = _text_color_button(field, self._holder)
            button.setDisabled(locked)
            self._input_layout.addWidget(button)
        unit = parameter.unit or {
            ParamType.ANGLE_DEG: "°", ParamType.DURATION_MS: "ms",
        }.get(kind)
        if unit:
            self._input_layout.addWidget(QLabel(unit, self._holder))
        for index in range(self._input_layout.count()):
            self._input_layout.itemAt(index).widget().show()

    def _complex(self, value, locked):
        parameter = self.parameter
        if parameter.type is ParamType.COLOR_LIST:
            if not isinstance(value, (list, tuple)):
                raise ValueError
            return ColorListEditor(self._holder, value=value, minimum=int(parameter.minimum or 0),
                                   maximum=None if parameter.maximum is None else int(parameter.maximum),
                                   read_only=locked)
        if parameter.type is ParamType.GRADIENT:
            if value is None:
                raise ValueError
            return GradientEditor(self._holder, value=value, read_only=locked)
        if not isinstance(value, Mapping):
            raise ValueError
        return ColorRangeEditor(self._holder, value=value, read_only=locked)

    def set_read_only(self, state):
        if self._read_only != state:
            self._read_only = state
            self.mode.setDisabled(state)
            self._rebuild()


class ParameterForm(QWidget):
    """Edit overrides for an SDK schema. User edits emit independent snapshots."""

    draft_changed = Signal(object)

    def __init__(self, schema, parent=None, *, inherited=None, values=None, prefix="config",
                 read_only=False):
        super().__init__(parent)
        self.schema = dict(schema)
        self.inherited = dict(inherited or {})
        self.prefix = prefix
        self._read_only = read_only
        self._raw = {}
        self.rows = {}
        self._layout = QFormLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.set_value({} if values is None else values)

    def value(self):
        return deepcopy(self._raw)

    def set_value(self, values):
        self._raw = deepcopy(dict(values))
        self.rows.clear()
        while self._layout.rowCount():
            self._layout.removeRow(0)
        recognized = set()
        for name, parameter in self.schema.items():
            keys = [key for key in (name, *parameter.aliases) if key in self._raw]
            recognized.update(keys)
            key = keys[0] if keys else name
            inherited = self.inherited.get(name, parameter.default)
            origin = ("Preset" if name in self.inherited else
                      "Standard" if parameter.has_default else "Ausgelassen")
            row = _ParameterRow(parameter, inherited, origin, self._raw.get(key, MISSING), self)
            row.set_read_only(self._read_only or len(keys) > 1)
            info = [
                parameter.description, f"Typ: {parameter.type.value}",
                f"Einheit: {parameter.unit}" if parameter.unit else "",
                f"Min: {parameter.minimum}" if parameter.minimum is not None else "",
                f"Max: {parameter.maximum}" if parameter.maximum is not None else "",
                f"Aliase: {', '.join(parameter.aliases)}" if parameter.aliases else "",
                "Pflichtfeld" if parameter.required else "",
                "Null erlaubt" if parameter.nullable else "",
            ]
            label = QLabel(f"{name} ({key})" if name != key else name, self)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setToolTip("\n".join(filter(None, info)))
            row.mode.setToolTip(label.toolTip())
            label.setBuddy(row.mode)
            if len(keys) > 1:
                self._add_repair_row(row, key, f"Alias-Konflikt: {', '.join(keys)}")
            row.edited.connect(lambda value, k=key: self._update(k, value))
            row.omitted.connect(lambda k=key: self._update(k, MISSING))
            self._layout.addRow(label, row)
            self.rows[name] = row
        for key in self._raw.keys() - recognized:
            self._add_repair_row(None, key, f"Unbekanntes Feld {key!r} · {_format(self._raw[key])}")
        if not self.schema and not self._raw:
            self._layout.addRow(QLabel("Keine Parameter definiert.", self))

    def _add_repair_row(self, row, key, message):
        label = QLabel(message, self)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        button = QPushButton("Feld entfernen", self)
        button.setAccessibleName(f"Feld {key} entfernen")
        button.setDisabled(self._read_only)
        panel = QWidget(self)
        layout = QHBoxLayout(panel)
        layout.addWidget(label, 1)
        layout.addWidget(button)

        def remove():
            self._raw.pop(key, None)
            self.set_value(self._raw)
            self.draft_changed.emit(self.value())

        button.clicked.connect(remove)
        if row is None:
            self._layout.addRow(panel)
        else:
            row._layout.addWidget(panel)

    def _update(self, key, value):
        if value is MISSING:
            self._raw.pop(key, None)
        else:
            self._raw[key] = deepcopy(value)
        self.draft_changed.emit(self.value())

    def set_read_only(self, state):
        if self._read_only != state:
            self._read_only = state
            self.set_value(self._raw)

    def validate(self):
        return _validate(self.schema, self._raw, self.prefix, inherited=self.inherited)


class EffectEditor(QWidget):
    """Inspect one resolved effect or preset and edit its static overrides."""

    draft_changed = Signal(object)

    def __init__(self, entry, parent=None, *, config=None, read_only=False):
        super().__init__(parent)
        self.entry = entry
        self._shape = deepcopy(config)
        title = QLabel(entry.label, self)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setToolTip(entry.description)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        schema = entry.definition.parameter_schema
        preset = normalize_values(schema, entry.preset, field_prefix="preset")
        self.form = ParameterForm(schema, self, inherited=preset,
                                  values=config if isinstance(config, Mapping) else None,
                                  read_only=read_only)
        layout.addWidget(self.form)
        self.form.draft_changed.connect(self._change)

    def _change(self, value):
        self._shape = value
        self.draft_changed.emit(self.value())

    def value(self):
        return deepcopy(self._shape)

    def set_value(self, config):
        if config is not None and not isinstance(config, Mapping):
            raise TypeError("config must be a mapping or None")
        self._shape = deepcopy(config)
        self.form.set_value({} if config is None else config)

    def validate(self):
        if self._shape is not None and not isinstance(self._shape, Mapping):
            return (Diagnostic("config", "Erwartet wird ein Objekt oder null."),)
        errors = self.form.validate()
        if errors:
            return errors
        try:
            self.entry.resolve_config(self._shape)
        except ParameterValidationError as exc:
            return tuple(Diagnostic(issue.field, issue.message) for issue in exc.issues)
        except (OverflowError, ValueError, TypeError) as exc:
            return (Diagnostic("config", str(exc)),)
        return ()

    def resolved_config(self):
        if errors := self.validate():
            raise ValueError("\n".join(map(str, errors)))
        return self.entry.resolve_config(self._shape)

    def set_read_only(self, state):
        self.form.set_read_only(state)
