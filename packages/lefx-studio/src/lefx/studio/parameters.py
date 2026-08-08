"""Editors built from a definition's declared schema.

A ``ParamDefinition`` already says everything an editor needs: the type, the
bounds, the unit, the allowed values, whether null is a value. So the studio
does not carry a form per effect — it carries one editor per *type*, and an
effect written tomorrow gets a full set of controls without this file changing.

That is the difference between a tester and a tool. A hand-written form knows
one catalogue; this knows the schema, which is the thing every catalogue is
made of.

Two rules run through all of it:

* **The schema decides, not the widget.** Bounds come from ``minimum`` and
  ``maximum``, choices from ``enum_values``, the suffix from ``unit``. Nothing
  here invents a range, because a range invented here would disagree with the
  one the definition is validated against.
* **Editing is continuous.** Every editor reports on each change rather than on
  commit, because the point is to watch the ring while you drag.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDial,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lefx.sdk import ParamDefinition, ParamType, format_color, parse_color

SLIDER_STEPS = 1000
"""How finely a float slider divides its range. Fine enough to look continuous,
coarse enough that the spin box beside it stays the precise way in."""


def _hex(color: int) -> str:
    return f"#{color & 0xFFFFFF:06X}"


def _qcolor(value: Any, fallback: int = 0x000000) -> QColor:
    try:
        return QColor(_hex(parse_color(value)))
    except Exception:
        return QColor(_hex(fallback))


class ParameterEditor(QWidget):
    """One control for one declared parameter.

    Subclasses implement :meth:`read` and :meth:`write` for their type; the
    nullability and the change signal are handled once, here, because they mean
    the same thing whatever the type is.
    """

    changed = Signal()

    def __init__(self, parameter: ParamDefinition, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.parameter = parameter
        self._null: QCheckBox | None = None
        self._body = QWidget(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._body, stretch=1)

        if parameter.nullable:
            # A nullable parameter has two states a person cares about — a value,
            # and deliberately no value — and one control cannot show both. The
            # box is the honest way to reach "null" without typing it.
            self._null = QCheckBox("null")
            self._null.setToolTip("Send no value for this parameter")
            self._null.toggled.connect(self._on_null_toggled)
            layout.addWidget(self._null)

        self.build(QVBoxLayout(self._body))

    # -- subclass contract --------------------------------------------------

    def build(self, layout: QVBoxLayout) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def read(self) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def write(self, value: Any) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- the shared part ----------------------------------------------------

    def value(self) -> Any:
        if self._null is not None and self._null.isChecked():
            return None
        return self.read()

    def set_value(self, value: Any) -> None:
        with_signals = self.blockSignals(True)
        try:
            if value is None and self._null is not None:
                self._null.setChecked(True)
                self._body.setEnabled(False)
                return
            if self._null is not None:
                self._null.setChecked(False)
                self._body.setEnabled(True)
            if value is not None:
                self.write(value)
        finally:
            self.blockSignals(with_signals)

    def _on_null_toggled(self, checked: bool) -> None:
        self._body.setEnabled(not checked)
        self.changed.emit()

    def _announce(self, *_: Any) -> None:
        self.changed.emit()


class BoolEditor(ParameterEditor):
    def build(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(0, 0, 0, 0)
        self.box = QCheckBox(self.parameter.description or "")
        self.box.toggled.connect(self._announce)
        layout.addWidget(self.box)

    def read(self) -> Any:
        return self.box.isChecked()

    def write(self, value: Any) -> None:
        self.box.setChecked(bool(value))


class NumberEditor(ParameterEditor):
    """A spin box, plus a slider whenever the schema gives both bounds.

    Without bounds a slider has nothing to span, and inventing a range so that
    one could be drawn would put a limit on the control that the definition does
    not put on the value.
    """

    integral = False

    def build(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        parameter = self.parameter
        self.spin: QSpinBox | QDoubleSpinBox
        if self.integral:
            self.spin = QSpinBox()
            self.spin.setRange(
                int(parameter.minimum) if parameter.minimum is not None else -10**9,
                int(parameter.maximum) if parameter.maximum is not None else 10**9,
            )
        else:
            self.spin = QDoubleSpinBox()
            self.spin.setDecimals(3)
            self.spin.setRange(
                float(parameter.minimum) if parameter.minimum is not None else -1e9,
                float(parameter.maximum) if parameter.maximum is not None else 1e9,
            )
            self.spin.setSingleStep(self._step())
        if parameter.unit:
            self.spin.setSuffix(f" {parameter.unit}")
        self.spin.valueChanged.connect(self._on_spin)

        self.slider: QSlider | None = None
        if parameter.minimum is not None and parameter.maximum is not None:
            self.slider = QSlider(Qt.Orientation.Horizontal)
            self.slider.setRange(0, SLIDER_STEPS)
            self.slider.valueChanged.connect(self._on_slider)
            row.addWidget(self.slider, stretch=1)
        row.addWidget(self.spin)
        layout.addLayout(row)

    def _step(self) -> float:
        parameter = self.parameter
        if parameter.minimum is None or parameter.maximum is None:
            return 0.1
        span = float(parameter.maximum) - float(parameter.minimum)
        return max(0.001, span / 100.0)

    def _on_spin(self, value: float) -> None:
        if self.slider is not None:
            self.slider.blockSignals(True)
            self.slider.setValue(self._to_slider(float(value)))
            self.slider.blockSignals(False)
        self._announce()

    def _on_slider(self, position: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(self._from_slider(position))
        self.spin.blockSignals(False)
        self._announce()

    def _to_slider(self, value: float) -> int:
        low, high = float(self.parameter.minimum), float(self.parameter.maximum)
        if high <= low:
            return 0
        return int(round((value - low) / (high - low) * SLIDER_STEPS))

    def _from_slider(self, position: int) -> Any:
        low, high = float(self.parameter.minimum), float(self.parameter.maximum)
        value = low + (high - low) * (position / SLIDER_STEPS)
        return int(round(value)) if self.integral else value

    def read(self) -> Any:
        return int(self.spin.value()) if self.integral else float(self.spin.value())

    def write(self, value: Any) -> None:
        self.spin.setValue(int(value) if self.integral else float(value))
        if self.slider is not None:
            self.slider.blockSignals(True)
            self.slider.setValue(self._to_slider(float(value)))
            self.slider.blockSignals(False)


class IntEditor(NumberEditor):
    integral = True


class FloatEditor(NumberEditor):
    integral = False


class DurationEditor(NumberEditor):
    """Milliseconds, which are integers and want saying so."""

    integral = True

    def build(self, layout: QVBoxLayout) -> None:
        super().build(layout)
        if not self.parameter.unit:
            self.spin.setSuffix(" ms")


class AngleEditor(ParameterEditor):
    """A dial, because a bearing is a bearing and a slider makes 359 and 0 far apart."""

    def build(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        self.dial = QDial()
        self.dial.setRange(0, 359)
        self.dial.setWrapping(True)
        self.dial.setNotchesVisible(True)
        self.dial.setFixedSize(64, 64)
        self.dial.valueChanged.connect(self._on_dial)

        self.spin = QDoubleSpinBox()
        self.spin.setRange(0.0, 359.999)
        self.spin.setDecimals(1)
        self.spin.setSuffix(" °")
        self.spin.valueChanged.connect(self._on_spin)

        row.addWidget(self.dial)
        row.addWidget(self.spin, stretch=1)
        layout.addLayout(row)

    def _on_dial(self, value: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(float(value))
        self.spin.blockSignals(False)
        self._announce()

    def _on_spin(self, value: float) -> None:
        self.dial.blockSignals(True)
        self.dial.setValue(int(round(value)) % 360)
        self.dial.blockSignals(False)
        self._announce()

    def read(self) -> Any:
        return float(self.spin.value()) % 360.0

    def write(self, value: Any) -> None:
        degrees = float(value) % 360.0
        self.spin.setValue(degrees)
        self.dial.blockSignals(True)
        self.dial.setValue(int(round(degrees)) % 360)
        self.dial.blockSignals(False)


class EnumEditor(ParameterEditor):
    def build(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.addItems([str(item) for item in self.parameter.enum_values])
        self.combo.currentTextChanged.connect(self._announce)
        layout.addWidget(self.combo)

    def read(self) -> Any:
        return self.combo.currentText()

    def write(self, value: Any) -> None:
        index = self.combo.findText(str(value))
        if index >= 0:
            self.combo.setCurrentIndex(index)


class ColorButton(QPushButton):
    """A swatch that opens a picker. Shows the colour rather than naming it."""

    picked = Signal(str)

    def __init__(self, value: Any = "#000000", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(56)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._color = _qcolor(value)
        self._paint()
        self.clicked.connect(self._choose)

    def color_hex(self) -> str:
        return self._color.name().upper()

    def set_color(self, value: Any) -> None:
        self._color = _qcolor(value)
        self._paint()

    def _paint(self) -> None:
        # A readable contrast against whichever colour is showing, so the hex
        # stays legible from black through to white.
        ink = "#000000" if self._color.lightnessF() > 0.55 else "#FFFFFF"
        self.setStyleSheet(
            f"background-color: {self._color.name()}; color: {ink};"
            "border: 1px solid #555; padding: 4px;"
        )
        self.setText(self._color.name().upper()[1:])

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(self._color, self, "Farbe wählen")
        if chosen.isValid():
            self._color = chosen
            self._paint()
            self.picked.emit(self.color_hex())


class ColorEditor(ParameterEditor):
    """A swatch and a text field, because both ways of saying a colour are useful.

    The field accepts everything the normaliser does — ``#RRGGBB``, a named
    colour from the catalogue — and only reports a change when what was typed
    actually parses, so a half-typed name does not repaint the ring.
    """

    def build(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        self.button = ColorButton("#000000")
        self.button.picked.connect(self._on_picked)
        self.text = QLineEdit("#000000")
        self.text.setPlaceholderText("#RRGGBB oder Farbname")
        self.text.textEdited.connect(self._on_typed)

        row.addWidget(self.button)
        row.addWidget(self.text, stretch=1)
        layout.addLayout(row)

    def _on_picked(self, value: str) -> None:
        self.text.blockSignals(True)
        self.text.setText(value)
        self.text.blockSignals(False)
        self._announce()

    def _on_typed(self, text: str) -> None:
        try:
            canonical = format_color(text)
        except Exception:
            return
        self.button.set_color(canonical)
        self._announce()

    def read(self) -> Any:
        return self.text.text().strip()

    def write(self, value: Any) -> None:
        canonical = format_color(value)
        self.text.setText(canonical)
        self.button.set_color(canonical)


class ColorListEditor(ParameterEditor):
    """A column of swatches, with the schema's length limits enforced live."""

    def build(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.rows: list[ColorButton] = []
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        layout.addLayout(self._rows_layout)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        self.add = QToolButton()
        self.add.setText("+")
        self.add.clicked.connect(lambda: self._add_row("#FFFFFF"))
        self.remove = QToolButton()
        self.remove.setText("−")
        self.remove.clicked.connect(self._remove_row)
        self.count = QLabel("0")
        controls.addWidget(self.add)
        controls.addWidget(self.remove)
        controls.addWidget(self.count)
        controls.addStretch(1)
        layout.addLayout(controls)

    def _limits(self) -> tuple[int, int]:
        low = int(self.parameter.minimum) if self.parameter.minimum is not None else 1
        high = int(self.parameter.maximum) if self.parameter.maximum is not None else 32
        return max(1, low), max(low, high)

    def _add_row(self, value: Any) -> None:
        low, high = self._limits()
        if len(self.rows) >= high:
            return
        button = ColorButton(value)
        button.picked.connect(self._announce)
        self.rows.append(button)
        self._rows_layout.addWidget(button)
        self._refresh_controls()
        self._announce()

    def _remove_row(self) -> None:
        low, _ = self._limits()
        if len(self.rows) <= low:
            return
        button = self.rows.pop()
        button.setParent(None)
        button.deleteLater()
        self._refresh_controls()
        self._announce()

    def _refresh_controls(self) -> None:
        low, high = self._limits()
        self.count.setText(f"{len(self.rows)} ({low}–{high})")
        self.add.setEnabled(len(self.rows) < high)
        self.remove.setEnabled(len(self.rows) > low)

    def read(self) -> Any:
        return [button.color_hex() for button in self.rows]

    def write(self, value: Any) -> None:
        while self.rows:
            button = self.rows.pop()
            button.setParent(None)
            button.deleteLater()
        for item in list(value or []):
            button = ColorButton(item)
            button.picked.connect(self._announce)
            self.rows.append(button)
            self._rows_layout.addWidget(button)
        low, _ = self._limits()
        while len(self.rows) < low:
            self._add_row("#FFFFFF")
        self._refresh_controls()


class GradientEditor(ParameterEditor):
    """Stops as position-and-colour rows, with the ends pinned where the schema wants them.

    A gradient must start at 0 and end at 1 and be sorted. Rather than let those
    be typed wrongly and rejected on apply, the first and last positions are
    fixed and the middle ones are sorted on read — the editor can only produce
    gradients that validate.
    """

    def build(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.stops: list[tuple[QDoubleSpinBox, ColorButton]] = []
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        layout.addLayout(self._rows_layout)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        self.add = QToolButton()
        self.add.setText("+")
        self.add.clicked.connect(self._add_middle_stop)
        self.remove = QToolButton()
        self.remove.setText("−")
        self.remove.clicked.connect(self._remove_middle_stop)
        controls.addWidget(self.add)
        controls.addWidget(self.remove)
        controls.addStretch(1)
        layout.addLayout(controls)

    def _make_row(self, at: float, color: Any, *, pinned: bool) -> None:
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)

        position = QDoubleSpinBox()
        position.setRange(0.0, 1.0)
        position.setSingleStep(0.05)
        position.setDecimals(2)
        position.setValue(float(at))
        position.setEnabled(not pinned)
        position.valueChanged.connect(self._announce)

        button = ColorButton(color)
        button.picked.connect(self._announce)

        line.addWidget(position)
        line.addWidget(button, stretch=1)
        self._rows_layout.addWidget(row)
        self.stops.append((position, button))

    def _add_middle_stop(self) -> None:
        if len(self.stops) >= 16:
            return
        self.write([*self.read(), {"at": 0.5, "color": "#FFFFFF"}])
        self._announce()

    def _remove_middle_stop(self) -> None:
        stops = self.read()
        if len(stops) <= 2:
            return
        del stops[len(stops) // 2]
        self.write(stops)
        self._announce()

    def _clear(self) -> None:
        self.stops.clear()
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def read(self) -> Any:
        stops = [
            {"at": float(position.value()), "color": button.color_hex()}
            for position, button in self.stops
        ]
        if not stops:
            return [{"at": 0.0, "color": "#000000"}, {"at": 1.0, "color": "#FFFFFF"}]
        # Sorted here rather than refused on apply: a stop dragged past its
        # neighbour is a reordering, not a mistake.
        stops.sort(key=lambda stop: stop["at"])
        stops[0]["at"] = 0.0
        stops[-1]["at"] = 1.0
        return stops

    def write(self, value: Any) -> None:
        stops = list(value or [])
        if len(stops) < 2:
            stops = [{"at": 0.0, "color": "#000000"}, {"at": 1.0, "color": "#FFFFFF"}]
        stops = sorted(stops, key=lambda stop: float(stop["at"]))[:16]
        self._clear()
        for index, stop in enumerate(stops):
            pinned = index in (0, len(stops) - 1)
            at = 0.0 if index == 0 else 1.0 if index == len(stops) - 1 else float(stop["at"])
            self._make_row(at, stop["color"], pinned=pinned)


class ColorRangeEditor(ParameterEditor):
    """Three min/max pairs, each on the scale its channel is actually measured in."""

    CHANNELS = (("hue", 0.0, 360.0, "°"), ("saturation", 0.0, 1.0, ""), ("brightness", 0.0, 1.0, ""))

    def build(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.bounds: dict[str, tuple[QDoubleSpinBox, QDoubleSpinBox]] = {}
        for name, low, high, unit in self.CHANNELS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(QLabel(name[:3]))
            pair = []
            for _ in range(2):
                spin = QDoubleSpinBox()
                spin.setRange(low, high)
                spin.setDecimals(0 if high > 1.0 else 2)
                spin.setSingleStep(1.0 if high > 1.0 else 0.05)
                if unit:
                    spin.setSuffix(f" {unit}")
                spin.valueChanged.connect(self._on_bound_changed)
                row.addWidget(spin)
                pair.append(spin)
            pair[1].setValue(high)
            self.bounds[name] = (pair[0], pair[1])
            holder = QWidget()
            holder.setLayout(row)
            layout.addWidget(holder)

    def _on_bound_changed(self, *_: Any) -> None:
        # A maximum below its minimum is not a range the schema accepts, so the
        # pair is kept ordered as it is edited rather than rejected afterwards.
        for low_spin, high_spin in self.bounds.values():
            if high_spin.value() < low_spin.value():
                high_spin.blockSignals(True)
                high_spin.setValue(low_spin.value())
                high_spin.blockSignals(False)
        self._announce()

    def read(self) -> Any:
        return {
            name: [float(low.value()), float(high.value())]
            for name, (low, high) in self.bounds.items()
        }

    def write(self, value: Any) -> None:
        payload = dict(value or {})
        for name, (low_spin, high_spin) in self.bounds.items():
            pair = payload.get(name)
            if not pair:
                continue
            low_spin.setValue(float(pair[0]))
            high_spin.setValue(float(pair[1]))


EDITORS: dict[ParamType, type[ParameterEditor]] = {
    ParamType.BOOL: BoolEditor,
    ParamType.INT: IntEditor,
    ParamType.FLOAT: FloatEditor,
    ParamType.DURATION_MS: DurationEditor,
    ParamType.ANGLE_DEG: AngleEditor,
    ParamType.ENUM: EnumEditor,
    ParamType.COLOR: ColorEditor,
    ParamType.COLOR_LIST: ColorListEditor,
    ParamType.GRADIENT: GradientEditor,
    ParamType.COLOR_RANGE: ColorRangeEditor,
}


def editor_for(parameter: ParamDefinition, parent: QWidget | None = None) -> ParameterEditor:
    """The editor a declared type gets. Every type has one, by construction.

    The mapping is total and a test asserts that it stays total, so adding a
    parameter type to the SDK without an editor here fails loudly rather than
    producing an effect with an uneditable field.
    """
    try:
        factory = EDITORS[parameter.type]
    except KeyError:  # pragma: no cover - guarded by a test
        raise KeyError(f"No editor for parameter type {parameter.type!r}") from None
    return factory(parameter, parent)


class SchemaForm(QWidget):
    """Every parameter of one definition, as a form that reports on each change."""

    changed = Signal()

    def __init__(
        self,
        schema: Mapping[str, ParamDefinition],
        parent: QWidget | None = None,
        *,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.editors: dict[str, ParameterEditor] = {}

        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        for name, parameter in schema.items():
            editor = editor_for(parameter, self)
            editor.changed.connect(self.changed.emit)
            label = QLabel(name)
            if parameter.description:
                label.setToolTip(parameter.description)
                editor.setToolTip(parameter.description)
            if parameter.required:
                label.setText(f"{name} *")
            layout.addRow(label, editor)
            self.editors[name] = editor

        if on_change is not None:
            self.changed.connect(on_change)

    def values(self) -> dict[str, Any]:
        return {name: editor.value() for name, editor in self.editors.items()}

    def set_values(self, values: Mapping[str, Any]) -> None:
        for name, editor in self.editors.items():
            if name in values:
                editor.set_value(values[name])


__all__ = [
    "EDITORS",
    "SLIDER_STEPS",
    "AngleEditor",
    "BoolEditor",
    "ColorButton",
    "ColorEditor",
    "ColorListEditor",
    "ColorRangeEditor",
    "DurationEditor",
    "EnumEditor",
    "FloatEditor",
    "GradientEditor",
    "IntEditor",
    "ParameterEditor",
    "SchemaForm",
    "editor_for",
]
