"""The property inspector: one field per declared property, nothing hand-made.

Every block and every layer already describes its properties in
:mod:`lefx.effect_creation.visual.blocks` — label, kind, range, default. The
fields here are built from those descriptors, so a block added there is
editable here without touching this file.

The inspector never changes the document. It reports what the user did —
``committed`` for a value meant to stay, ``previewed`` for a value while a
slider is still being dragged — and the page hands that to the editor, which
validates it. What the inspector then shows is what the editor accepted: the
next document arrives and every field is set from it again, so a rejected value
simply springs back, with the reason next to it rather than in a dialog.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lefx.effect_creation.visual.blocks import BLOCKS, LAYER_PROPERTIES, Property
from lefx.sdk import DefinitionKind

RING_FRACTIONS = frozenset({"position", "length", "mask_start", "mask_length"})
"""Properties measured as a share of the ring, which get an LED helper."""

BLENDS = [("over", "Überdecken"), ("add", "Addieren"), ("max", "Maximum")]
COMPOSITIONS = [("opaque", "Deckend (unbedeckt = schwarz)"),
                ("transparent", "Transparent (unbedeckt = durchlässig)")]
KINDS = [(kind.value, kind.value) for kind in DefinitionKind]
SLIDER_STEPS = 1000


class Field(QWidget):
    """One property's editor. Subclasses emit ``committed`` and ``previewed``."""

    committed = Signal(object)
    previewed = Signal(object)

    def set_value(self, value: Any) -> None:  # pragma: no cover — abstract
        raise NotImplementedError


class BoolField(Field):
    def __init__(self, spec: Property) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.box = QCheckBox()
        self.box.toggled.connect(lambda checked: self.committed.emit(bool(checked)))
        layout.addWidget(self.box)
        layout.addStretch(1)

    def set_value(self, value: Any) -> None:
        self.box.blockSignals(True)
        self.box.setChecked(bool(value))
        self.box.blockSignals(False)


class IntField(Field):
    def __init__(self, spec: Property) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.spin = QSpinBox()
        self.spin.setRange(int(spec.minimum if spec.minimum is not None else -2**31),
                           int(min(spec.maximum if spec.maximum is not None else 2**31 - 1, 2**31 - 1)))
        self.spin.setKeyboardTracking(False)
        self.spin.valueChanged.connect(lambda value: self.committed.emit(int(value)))
        layout.addWidget(self.spin, stretch=1)

    def set_value(self, value: Any) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(int(value))
        self.spin.blockSignals(False)


class FloatField(Field):
    """Slider for reach, spin box for precision; ring shares also in LEDs.

    Dragging the slider previews without committing, so a single drag is one
    undo step rather than a hundred. Releasing it commits.
    """

    def __init__(self, spec: Property, name: str, led_count: int) -> None:
        super().__init__()
        self.minimum = float(spec.minimum if spec.minimum is not None else -1000.0)
        self.maximum = float(spec.maximum if spec.maximum is not None else 1000.0)
        span = self.maximum - self.minimum
        # Wide ranges (rates up to 100/s) are mostly used near the bottom;
        # a squared slider keeps the useful part from being three pixels wide.
        self.exponent = 2.0 if span > 10 else 1.0
        self.led_count = max(1, int(led_count))
        self._value = float(spec.default)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.sliderReleased.connect(lambda: self.committed.emit(self._from_slider(self.slider.value())))
        self.slider.actionTriggered.connect(self._on_slider_action)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(self.minimum, self.maximum)
        self.spin.setDecimals(4 if span <= 1 else 3)
        self.spin.setSingleStep(0.01 if span <= 2 else 0.1)
        self.spin.setKeyboardTracking(False)
        self.spin.valueChanged.connect(lambda value: self.committed.emit(float(value)))
        layout.addWidget(self.slider, stretch=3)
        layout.addWidget(self.spin, stretch=2)

        self.leds: QSpinBox | None = None
        if name in RING_FRACTIONS:
            self.leds = QSpinBox()
            self.leds.setRange(0, self.led_count)
            self.leds.setSuffix(" LED")
            self.leds.setToolTip(f"Als Anzahl LEDs eines {self.led_count}er-Rings eingeben")
            self.leds.setKeyboardTracking(False)
            self.leds.valueChanged.connect(
                lambda count: self.committed.emit(min(self.maximum, count / self.led_count)))
            layout.addWidget(self.leds, stretch=1)

    def _from_slider(self, position: int) -> float:
        ratio = (position / SLIDER_STEPS) ** self.exponent
        return round(self.minimum + (self.maximum - self.minimum) * ratio, 6)

    def _to_slider(self, value: float) -> int:
        span = self.maximum - self.minimum
        ratio = 0.0 if span <= 0 else max(0.0, min(1.0, (value - self.minimum) / span))
        return int(round(ratio ** (1 / self.exponent) * SLIDER_STEPS))

    def _on_slider_moved(self, position: int) -> None:
        self.previewed.emit(self._from_slider(position))

    def _on_slider_action(self, action: int) -> None:
        # Clicks on the groove and arrow keys move without a drag: commit those.
        if action != QSlider.SliderAction.SliderMove:
            self.committed.emit(self._from_slider(self.slider.sliderPosition()))

    def set_value(self, value: Any) -> None:
        self._value = float(value)
        for widget in (self.slider, self.spin, self.leds):
            if widget is not None:
                widget.blockSignals(True)
        if not self.slider.isSliderDown():
            self.slider.setValue(self._to_slider(self._value))
        self.spin.setValue(self._value)
        if self.leds is not None:
            # The kernel's own rounding, so the count shown is the count lit.
            self.leds.setValue(min(self.led_count, int(self._value * self.led_count + 0.5)))
        for widget in (self.slider, self.spin, self.leds):
            if widget is not None:
                widget.blockSignals(False)


class ColorField(Field):
    """A swatch that opens a colour dialog, and the hex value to type into."""

    def __init__(self, spec: Property) -> None:
        super().__init__()
        self._value = str(spec.default)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.swatch = QPushButton()
        self.swatch.setFixedWidth(46)
        self.swatch.setToolTip("Farbe wählen")
        self.swatch.clicked.connect(self._choose)
        self.text = QLineEdit()
        self.text.setMaxLength(7)
        self.text.setPlaceholderText("#RRGGBB")
        self.text.editingFinished.connect(self._typed)
        layout.addWidget(self.swatch)
        layout.addWidget(self.text, stretch=1)

    def _typed(self) -> None:
        value = self.text.text().strip()
        if not value.startswith("#"):
            value = "#" + value
        if value.upper() != self._value.upper():
            self.committed.emit(value.upper())

    def _choose(self) -> None:
        dialog = QColorDialog(QColor(self._value), self)
        dialog.setWindowTitle("Farbe wählen")
        dialog.currentColorChanged.connect(lambda color: self.previewed.emit(color.name().upper()))
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            self.committed.emit(dialog.currentColor().name().upper())
        else:
            self.committed.emit(self._value)  # restores the preview of the stored value

    def set_value(self, value: Any) -> None:
        self._value = str(value).upper()
        self.text.blockSignals(True)
        self.text.setText(self._value)
        self.text.blockSignals(False)
        self.swatch.setStyleSheet(
            f"background: {self._value}; border: 1px solid #555; border-radius: 3px; min-height: 18px;")


def field_for(spec: Property, name: str, led_count: int) -> Field:
    if spec.kind == "color":
        return ColorField(spec)
    if spec.kind == "bool":
        return BoolField(spec)
    if spec.kind == "int":
        return IntField(spec)
    return FloatField(spec, name, led_count)


class ChoiceField(Field):
    def __init__(self, choices: list[tuple[str, str]]) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.box = QComboBox()
        for value, label in choices:
            self.box.addItem(label, value)
        self.box.currentIndexChanged.connect(lambda _: self.committed.emit(self.box.currentData()))
        layout.addWidget(self.box, stretch=1)

    def set_value(self, value: Any) -> None:
        self.box.blockSignals(True)
        self.box.setCurrentIndex(max(0, self.box.findData(value)))
        self.box.blockSignals(False)


class TextField(Field):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.editingFinished.connect(lambda: self.committed.emit(self.edit.text()))
        layout.addWidget(self.edit, stretch=1)

    def set_value(self, value: Any) -> None:
        if self.edit.hasFocus() and self.edit.isModified():
            return
        self.edit.blockSignals(True)
        self.edit.setText(str(value))
        self.edit.setModified(False)
        self.edit.blockSignals(False)


class Inspector(QWidget):
    """Shows the selected object; reports edits as (target, field, value).

    ``target`` is an object id, or ``None`` for the whole effect. ``field`` is a
    property name, or one of ``@name``, ``@enabled``, ``@blend`` for a layer's
    own settings, or ``effect.<key>`` for the effect metadata.
    """

    committed = Signal(object, str, object)
    previewed = Signal(object, str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shape: tuple | None = None
        self._fields: dict[str, Field] = {}
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.subheading = QLabel()
        self.subheading.setWordWrap(True)
        self.subheading.setStyleSheet("color: #888;")
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #e07a5f; padding-top: 6px;")
        self.problem.hide()
        layout.addWidget(self.heading)
        layout.addWidget(self.subheading)
        layout.addWidget(self.form_host)
        layout.addWidget(self.problem)

    # -- what is shown ------------------------------------------------------

    def show_object(self, document: dict, target: str | None, led_count: int) -> None:
        item, kind = locate(document, target)
        if item is None:
            target, item, kind = None, document["effect"], "effect"
        shape = (target, kind, item.get("type"), led_count)
        if shape != self._shape:
            self._rebuild(document, target, item, kind, led_count)
            self._shape = shape
        self._fill(document, item, kind)

    def show_problem(self, text: str | None) -> None:
        self.problem.setText(text or "")
        self.problem.setVisible(bool(text))

    def field(self, name: str) -> Field:
        return self._fields[name]

    # -- building -----------------------------------------------------------

    def _rebuild(self, document: dict, target: str | None, item: dict, kind: str, led_count: int) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._fields = {}
        self.show_problem(None)

        if kind == "effect":
            self.heading.setText("Gesamteffekt")
            self.subheading.setText(
                "Kein Runtime-Layer: das ganze Projekt und seine zusammengesetzte Vorschau. "
                "Diese Angaben gehen in den exportierten LEFX-Effekt ein.")
            self._add(target, "effect.title", "Titel", TextField())
            self._add(target, "effect.id", "Effekt-ID", TextField())
            self._add(target, "effect.description", "Beschreibung", TextField())
            self._add(target, "effect.kind", "Lebenszyklus", ChoiceField(KINDS))
            self._add(target, "effect.composition", "Runtime-Komposition", ChoiceField(COMPOSITIONS))
            spin = IntField(Property("Dauer", "int", 2000, 1, 600000))
            spin.spin.setSuffix(" ms")
            spin.setToolTip("Nur für Events und Timed Overlays von Bedeutung")
            self._add(target, "effect.duration_ms", "Dauer", spin)
            return

        if kind == "layer":
            self.heading.setText(f"Ebene · {item['name']}")
            self.subheading.setText("Eine Studio-Ebene: eigene Elemente, eigene Animationen, "
                                    "eigene Mischung mit den Ebenen darunter.")
            self._add(target, "@name", "Name", TextField())
            visible = BoolField(Property("Sichtbar", "bool", True))
            self._add(target, "@enabled", "Sichtbar", visible)
            self._add(target, "@blend", "Mischmodus", ChoiceField(BLENDS))
            specs = LAYER_PROPERTIES
        elif kind == "group":
            self.heading.setText(f"Gruppe · {item['name']}")
            self.subheading.setText("Gruppen sind im Lab nur sichtbar; ihre künftige Rolle ist offen.")
            self._add(target, "@name", "Name", TextField())
            return
        else:
            block = BLOCKS[item["type"]]
            role = "Animation der Ebene" if kind == "animation" else "Visuelles Element"
            self.heading.setText(block.label)
            layer = _layer_name(document, item, kind)
            self.subheading.setText(f"{role} · {layer}" if layer else role)
            specs = block.properties
        for name, spec in specs.items():
            self._add(target, name, spec.label, field_for(spec, name, led_count))

    def _add(self, target: str | None, name: str, label: str, field: Field) -> None:
        field.committed.connect(lambda value, n=name: self.committed.emit(target, n, value))
        field.previewed.connect(lambda value, n=name: self.previewed.emit(target, n, value))
        self._fields[name] = field
        self.form.addRow(label, field)

    def _fill(self, document: dict, item: dict, kind: str) -> None:
        for name, field in self._fields.items():
            if name.startswith("effect."):
                field.set_value(document["effect"][name.split(".", 1)[1]])
            elif name.startswith("@"):
                field.set_value(item[name[1:]])
            else:
                field.set_value(item["properties"][name])


def locate(document: dict, target: str | None) -> tuple[dict | None, str]:
    if target is None:
        return None, "effect"

    def visit(children):
        for child in children:
            if child["id"] == target:
                return child
            if child.get("type") == "group":
                found = visit(child["children"])
                if found is not None:
                    return found
        return None

    for layer in document["layers"]:
        if layer["id"] == target:
            return layer, "layer"
        found = visit(layer["children"])
        if found is not None:
            return found, "group" if found.get("type") == "group" else "element"
    for animation in document["animations"]:
        if animation["id"] == target:
            return animation, "animation"
    return None, "effect"


def _layer_name(document: dict, item: dict, kind: str) -> str | None:
    if kind == "animation":
        return next((layer["name"] for layer in document["layers"] if layer["id"] == item["target"]), None)

    def contains(children):
        return any(child["id"] == item["id"] or (child.get("type") == "group" and contains(child["children"]))
                   for child in children)

    return next((layer["name"] for layer in document["layers"] if contains(layer["children"])), None)


__all__ = ["Inspector", "field_for", "locate"]
