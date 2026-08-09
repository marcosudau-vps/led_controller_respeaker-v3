"""The source editor: design a definition, watch it run, write it out.

Three columns, and the middle one is the point. On the left the definition is
described; in the middle its parameters are built up; on the right it renders on
the actual device while you do it.

The rule the whole page is built on: **nothing invalid can be entered.** Not
"is rejected on save" — cannot be entered. Which companion fields a parameter
type accepts is decided by the type, so the rest are disabled rather than
ignored. Reserved names come with their fixed type and range already filled in.
The combinations no single field can see — a coloured definition without
brightness, an animated one without speed, a finite one without its duration —
are checked by constructing the real definition on every keystroke, and the
Save button is simply off while that fails.

Every number box is bounded, generously but finitely. The schema will accept a
duration of four hours; a form that offers it invites a typo nobody notices.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lefx.effect_creation import SourceError
from lefx.sdk import (
    ColorModel,
    CompositionMode,
    DefinitionKind,
    DurationField,
    InputMode,
    ParamType,
    StateSlot,
)

from .blueprint import (
    BOUND_LIMIT,
    COLOR_LIST_LIMIT,
    DURATION_LIMIT_MS,
    PRIORITY_LIMIT,
    TYPE_SUPPORT,
    VERSION_LIMIT,
    EffectBlueprint,
    ParameterBlueprint,
    build_package,
    compile_blueprint,
    default_for,
    reserved_blueprint,
    starting_blueprint,
)
from .catalogue import KIND_LABELS
from .parameters import editor_for
from .ring import RingMonitor
from .session import STUDIO_CHANNEL, StudioSession

logger = logging.getLogger("lefx.effect_creation.studio.source_editor")

PREVIEW_ID_PREFIX = "studio_preview"


def _chosen(combo: QComboBox, enum_class):
    """The enum a combo box is on.

    Qt stores item data as a QVariant, and every enum in the schema is a
    ``str`` subclass — so what comes back out is a plain string that compares
    equal to the member and hashes like it, but has no ``.value`` and is not an
    instance of anything. That is a bug that hides until the one line that asks
    the enum for something, so the conversion happens here, once.
    """
    return enum_class(combo.currentData())


class ParameterEditorRow(QWidget):
    """One parameter's whole declaration, with the fields its type does not have
    switched off rather than left to be filled in wrongly."""

    changed = Signal()
    removed = Signal()

    def __init__(self, blueprint: ParameterBlueprint, *, runtime: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.blueprint = blueprint
        self.runtime = runtime
        self._building = True
        self._build()
        self._load()
        self._building = False

    def _build(self) -> None:
        box = QGroupBox()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        layout = QFormLayout(box)

        head = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("name")
        self.name.textEdited.connect(self._on_name_edited)
        self.type_box = QComboBox()
        for kind in ParamType:
            self.type_box.addItem(kind.value, kind)
        self.type_box.currentIndexChanged.connect(self._on_type_changed)
        self.drop = QToolButton()
        self.drop.setText("✕")
        self.drop.setToolTip("Parameter entfernen")
        self.drop.clicked.connect(self.removed.emit)
        head.addWidget(self.name, stretch=2)
        head.addWidget(self.type_box, stretch=1)
        head.addWidget(self.drop)
        holder = QWidget()
        holder.setLayout(head)
        layout.addRow(holder)

        self.reserved_note = QLabel("")
        self.reserved_note.setWordWrap(True)
        self.reserved_note.setStyleSheet("color: #d9a441;")
        layout.addRow(self.reserved_note)

        self.default_host = QWidget()
        self.default_layout = QVBoxLayout(self.default_host)
        self.default_layout.setContentsMargins(0, 0, 0, 0)
        self.default_editor: Any = None
        layout.addRow("Vorgabe", self.default_host)

        bounds = QHBoxLayout()
        self.has_minimum = QCheckBox("min")
        self.has_minimum.toggled.connect(self._announce)
        self.minimum = QDoubleSpinBox()
        self.minimum.setRange(-BOUND_LIMIT, BOUND_LIMIT)
        self.minimum.setDecimals(3)
        self.minimum.valueChanged.connect(self._announce)
        self.has_maximum = QCheckBox("max")
        self.has_maximum.toggled.connect(self._announce)
        self.maximum = QDoubleSpinBox()
        self.maximum.setRange(-BOUND_LIMIT, BOUND_LIMIT)
        self.maximum.setDecimals(3)
        self.maximum.valueChanged.connect(self._announce)
        for widget in (self.has_minimum, self.minimum, self.has_maximum, self.maximum):
            bounds.addWidget(widget)
        self.bounds_host = QWidget()
        self.bounds_host.setLayout(bounds)
        layout.addRow("Grenzen", self.bounds_host)

        self.unit = QComboBox()
        self.unit.currentIndexChanged.connect(self._announce)
        layout.addRow("Einheit", self.unit)

        self.enum_values = QLineEdit()
        self.enum_values.setPlaceholderText("a, b, c")
        self.enum_values.textEdited.connect(self._announce)
        layout.addRow("Werte", self.enum_values)

        flags = QHBoxLayout()
        self.nullable = QCheckBox("nullable")
        self.nullable.toggled.connect(self._announce)
        self.required = QCheckBox("required")
        self.required.toggled.connect(self._announce)
        flags.addWidget(self.nullable)
        flags.addWidget(self.required)
        flags.addStretch(1)
        self.flags_host = QWidget()
        self.flags_host.setLayout(flags)
        layout.addRow("", self.flags_host)

        self.description = QLineEdit()
        self.description.textEdited.connect(self._announce)
        layout.addRow("Beschreibung", self.description)

        self.problem = QLabel("")
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #d76;")
        layout.addRow(self.problem)

    # -- moving values in and out ------------------------------------------

    def _load(self) -> None:
        blueprint = self.blueprint
        self.name.setText(blueprint.name)
        self.type_box.setCurrentIndex(self.type_box.findData(blueprint.type))
        self.description.setText(blueprint.description)
        self.nullable.setChecked(blueprint.nullable)
        self.required.setChecked(blueprint.required)
        self.has_minimum.setChecked(blueprint.minimum is not None)
        self.minimum.setValue(blueprint.minimum or 0.0)
        self.has_maximum.setChecked(blueprint.maximum is not None)
        self.maximum.setValue(blueprint.maximum if blueprint.maximum is not None else 1.0)
        self.enum_values.setText(", ".join(blueprint.enum_values))
        self._rebuild_default_editor()
        self._apply_type_rules()

    def _rebuild_default_editor(self) -> None:
        """The default is edited with the same widget the player would use.

        Which means a colour default is picked from a colour dialog and a
        duration is typed in milliseconds — and it is already canonical when it
        reaches the generated source.
        """
        while self.default_layout.count():
            widget = self.default_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        blueprint = self.blueprint
        probe = ParameterBlueprint(
            name=blueprint.name or "value",
            type=blueprint.type,
            default=blueprint.default,
            enum_values=blueprint.enum_values or ("a",),
            nullable=blueprint.nullable,
        )
        try:
            self.default_editor = editor_for(probe.build())
        except Exception:
            # A half-declared parameter has no editable default yet; the row
            # already says what is missing.
            self.default_editor = None
            return
        try:
            self.default_editor.set_value(
                blueprint.default if blueprint.default is not None else default_for(blueprint.type)
            )
        except Exception:
            self.default_editor.set_value(default_for(blueprint.type))
        self.default_editor.changed.connect(self._announce)
        self.default_layout.addWidget(self.default_editor)

    def _apply_type_rules(self) -> None:
        """Grey out what this type does not have. The schema's matrix, as a form."""
        support = TYPE_SUPPORT[self.blueprint.type]
        self.bounds_host.setEnabled(support.bounds)
        self.minimum.setDecimals(0 if support.integral_bounds else 3)
        self.maximum.setDecimals(0 if support.integral_bounds else 3)
        if self.blueprint.type is ParamType.DURATION_MS:
            self.minimum.setRange(0, DURATION_LIMIT_MS)
            self.maximum.setRange(0, DURATION_LIMIT_MS)
        elif self.blueprint.type is ParamType.COLOR_LIST:
            self.minimum.setRange(0, COLOR_LIST_LIMIT)
            self.maximum.setRange(0, COLOR_LIST_LIMIT)
        else:
            self.minimum.setRange(-BOUND_LIMIT, BOUND_LIMIT)
            self.maximum.setRange(-BOUND_LIMIT, BOUND_LIMIT)

        self.unit.setEnabled(support.unit_allowed)
        current = self.unit.currentText()
        self.unit.blockSignals(True)
        self.unit.clear()
        self.unit.addItem("—", None)
        for unit in support.units:
            self.unit.addItem(unit, unit)
        index = self.unit.findText(current)
        self.unit.setCurrentIndex(max(0, index))
        self.unit.blockSignals(False)

        self.enum_values.setEnabled(support.enum_values)
        # nullable and required are only meaningful for a runtime input: a
        # configuration field must always resolve, so it always has a default.
        self.nullable.setEnabled(self.runtime)
        self.required.setEnabled(self.runtime)

        reserved = self.blueprint.reserved
        self.type_box.setEnabled(not reserved)
        self.reserved_note.setVisible(reserved)
        if reserved:
            self.reserved_note.setText(
                f"„{self.blueprint.name}“ ist ein reservierter Name: Typ und Bereich sind "
                "systemweit festgelegt und werden hier nicht zur Wahl gestellt."
            )
            self.bounds_host.setEnabled(False)

    def collect(self) -> None:
        """Read the form back into the blueprint."""
        blueprint = self.blueprint
        blueprint.name = self.name.text().strip()
        blueprint.type = _chosen(self.type_box, ParamType)
        blueprint.description = self.description.text().strip()
        support = TYPE_SUPPORT[blueprint.type]
        blueprint.minimum = (
            float(self.minimum.value()) if support.bounds and self.has_minimum.isChecked() else None
        )
        blueprint.maximum = (
            float(self.maximum.value()) if support.bounds and self.has_maximum.isChecked() else None
        )
        blueprint.unit = self.unit.currentData() if support.unit_allowed else None
        blueprint.enum_values = (
            tuple(part.strip() for part in self.enum_values.text().split(",") if part.strip())
            if support.enum_values
            else ()
        )
        blueprint.nullable = self.runtime and self.nullable.isChecked()
        blueprint.required = self.runtime and self.required.isChecked()
        if self.default_editor is not None and not blueprint.required:
            blueprint.default = self.default_editor.value()

    def show_problem(self) -> None:
        self.problem.setText(self.blueprint.problem() or "")

    # -- reacting ----------------------------------------------------------

    def _on_name_edited(self, text: str) -> None:
        name = text.strip()
        if name in {"brightness", "speed", "reverse", "progress", "direction_deg",
                    "duration_ms", "total_ms", "color", "secondary_color",
                    "background_color", "colors", "gradient", "color_range", "random_seed"}:
            # Typing a reserved name adopts its fixed declaration rather than
            # letting a wrong type be entered and rejected afterwards.
            fixed = reserved_blueprint(name)
            fixed.description = self.blueprint.description
            self.blueprint = fixed
            self._building = True
            self._load()
            self._building = False
        self._announce()

    def _on_type_changed(self) -> None:
        if self._building:
            return
        self.blueprint.type = _chosen(self.type_box, ParamType)
        self.blueprint.default = default_for(self.blueprint.type)
        self._apply_type_rules()
        self._rebuild_default_editor()
        self._announce()

    def _announce(self, *_: Any) -> None:
        if self._building:
            return
        self.collect()
        self.show_problem()
        self.changed.emit()


class SourceEditorPage(QWidget):
    """Design a definition, render it on the device, write it out and pack it."""

    frame_received = Signal(tuple)

    def __init__(self, session: StudioSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.blueprint = starting_blueprint(DefinitionKind.STATE)
        self.rows: list[ParameterEditorRow] = []
        self.input_rows: list[ParameterEditorRow] = []
        self.written: Path | None = None
        self._loading = False

        self._build()
        self.frame_received.connect(self.monitor.set_colors)
        self._load_blueprint()

    # -- construction -------------------------------------------------------

    def _build(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_identity())
        splitter.addWidget(self._build_parameters())
        splitter.addWidget(self._build_output())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def _build_identity(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        box = QGroupBox("Definition")
        form = QFormLayout(box)

        self.kind_box = QComboBox()
        for kind in DefinitionKind:
            self.kind_box.addItem(KIND_LABELS[kind], kind)
        self.kind_box.currentIndexChanged.connect(self._on_kind_changed)
        form.addRow("Form", self.kind_box)

        self.effect_id = QLineEdit()
        self.effect_id.setPlaceholderText("mein_effekt")
        self.effect_id.textEdited.connect(self._on_edited)
        form.addRow("Id", self.effect_id)

        self.title = QLineEdit()
        self.title.textEdited.connect(self._on_edited)
        form.addRow("Titel", self.title)

        self.description = QPlainTextEdit()
        self.description.setMaximumHeight(64)
        self.description.textChanged.connect(self._on_edited)
        form.addRow("Beschreibung", self.description)

        self.source_id = QLineEdit("my-set")
        self.source_id.textEdited.connect(self._on_edited)
        form.addRow("Set", self.source_id)

        self.tags = QLineEdit()
        self.tags.setPlaceholderText("core, overlay")
        self.tags.textEdited.connect(self._on_edited)
        form.addRow("Tags", self.tags)

        self.version = QSpinBox()
        self.version.setRange(1, VERSION_LIMIT)
        self.version.valueChanged.connect(self._on_edited)
        form.addRow("Version", self.version)
        layout.addWidget(box)

        visual = QGroupBox("Darstellung")
        vform = QFormLayout(visual)
        self.color_model = QComboBox()
        for model in ColorModel:
            self.color_model.addItem(model.value, model)
        self.color_model.currentIndexChanged.connect(self._on_structure_changed)
        vform.addRow("Farbmodell", self.color_model)

        self.composition = QComboBox()
        for mode in CompositionMode:
            self.composition.addItem(mode.value, mode)
        self.composition.currentIndexChanged.connect(self._on_edited)
        vform.addRow("Komposition", self.composition)

        self.animated = QCheckBox("animiert (verlangt speed)")
        self.animated.toggled.connect(self._on_structure_changed)
        self.directional = QCheckBox("gerichtet (verlangt reverse)")
        self.directional.toggled.connect(self._on_structure_changed)
        vform.addRow("", self.animated)
        vform.addRow("", self.directional)
        layout.addWidget(visual)

        self.form_box = QGroupBox("Formspezifisch")
        self.form_layout = QFormLayout(self.form_box)
        self._build_form_specific()
        layout.addWidget(self.form_box)
        layout.addStretch(1)
        return panel

    def _build_form_specific(self) -> None:
        self.slot_primary = QCheckBox("primary")
        self.slot_primary.setChecked(True)
        self.slot_primary.toggled.connect(self._on_edited)
        self.slot_background = QCheckBox("background")
        self.slot_background.toggled.connect(self._on_edited)
        self.restorable = QCheckBox("restorable (nur mit background)")
        self.restorable.toggled.connect(self._on_edited)
        slots = QHBoxLayout()
        slots.addWidget(self.slot_primary)
        slots.addWidget(self.slot_background)
        self.slots_host = QWidget()
        self.slots_host.setLayout(slots)
        self.form_layout.addRow("Plätze", self.slots_host)
        self.form_layout.addRow("", self.restorable)

        self.duration_field = QComboBox()
        for field in DurationField:
            self.duration_field.addItem(field.value, field)
        self.duration_field.currentIndexChanged.connect(self._on_structure_changed)
        self.form_layout.addRow("Längenfeld", self.duration_field)

        self.duration_override = QCheckBox("Länge beim Auslösen überschreibbar")
        self.duration_override.toggled.connect(self._on_edited)
        self.form_layout.addRow("", self.duration_override)

        self.has_priority = QCheckBox("Standardpriorität")
        self.has_priority.toggled.connect(self._on_edited)
        self.priority = QSpinBox()
        self.priority.setRange(-PRIORITY_LIMIT, PRIORITY_LIMIT)
        self.priority.valueChanged.connect(self._on_edited)
        priority = QHBoxLayout()
        priority.addWidget(self.has_priority)
        priority.addWidget(self.priority)
        self.priority_host = QWidget()
        self.priority_host.setLayout(priority)
        self.form_layout.addRow("", self.priority_host)

        self.sampling_mode = QComboBox()
        for mode in InputMode:
            self.sampling_mode.addItem(mode.value, mode)
        self.sampling_mode.currentIndexChanged.connect(self._on_edited)
        self.form_layout.addRow("Eingaben", self.sampling_mode)

        self.provider_id = QLineEdit()
        self.provider_id.setPlaceholderText("doa")
        self.provider_id.textEdited.connect(self._on_edited)
        self.form_layout.addRow("Capability", self.provider_id)

        self.interval_ms = QSpinBox()
        self.interval_ms.setRange(0, 60_000)
        self.interval_ms.setSuffix(" ms")
        self.interval_ms.valueChanged.connect(self._on_edited)
        self.form_layout.addRow("Abtastintervall", self.interval_ms)

    def _build_parameters(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Parameter</b>"))
        header.addStretch(1)
        self.fill_button = QPushButton("Pflichtfelder ergänzen")
        self.fill_button.setToolTip(
            "Fügt hinzu, was Farbmodell, Flags und Form verlangen — korrekt typisiert"
        )
        self.fill_button.clicked.connect(self._fill_required)
        add = QPushButton("+ Parameter")
        add.clicked.connect(lambda: self._add_row(ParameterBlueprint(), runtime=False))
        header.addWidget(self.fill_button)
        header.addWidget(add)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.rows_host = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.rows_host)
        layout.addWidget(self.scroll, stretch=3)

        self.inputs_header = QHBoxLayout()
        self.inputs_label = QLabel("<b>Runtime-Eingaben</b>")
        self.inputs_header.addWidget(self.inputs_label)
        self.inputs_header.addStretch(1)
        self.add_input = QPushButton("+ Eingabe")
        self.add_input.clicked.connect(
            lambda: self._add_row(ParameterBlueprint(nullable=True, required=True), runtime=True)
        )
        self.inputs_header.addWidget(self.add_input)
        layout.addLayout(self.inputs_header)

        self.inputs_scroll = QScrollArea()
        self.inputs_scroll.setWidgetResizable(True)
        self.inputs_host = QWidget()
        self.inputs_layout = QVBoxLayout(self.inputs_host)
        self.inputs_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.inputs_scroll.setWidget(self.inputs_host)
        layout.addWidget(self.inputs_scroll, stretch=2)
        return panel

    def _build_output(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.monitor = RingMonitor(self.session.led_count)
        self.monitor.setMinimumHeight(200)
        layout.addWidget(self.monitor, stretch=2)

        code_box = QGroupBox("render()")
        code_layout = QVBoxLayout(code_box)
        self.code = QPlainTextEdit()
        self.code.setFont(QFont("Consolas, Menlo, monospace"))
        self.code.setTabStopDistance(32)
        self.code.textChanged.connect(self._on_edited)
        code_layout.addWidget(self.code)
        layout.addWidget(code_box, stretch=3)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.preview_button = QPushButton("Vorschau")
        self.preview_button.setToolTip("Auf dem gewählten Gerät abspielen")
        self.preview_button.clicked.connect(self._preview)
        self.save_button = QPushButton("Quelle schreiben …")
        self.save_button.clicked.connect(self._write)
        self.pack_button = QPushButton("Als .lefx bauen …")
        self.pack_button.clicked.connect(self._pack)
        self.pack_button.setEnabled(False)
        buttons.addWidget(self.preview_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.pack_button)
        layout.addLayout(buttons)

        source_box = QGroupBox("effect.py — erzeugt, nicht getippt")
        source_layout = QVBoxLayout(source_box)
        self.preview_source = QPlainTextEdit()
        self.preview_source.setReadOnly(True)
        self.preview_source.setFont(QFont("Consolas, Menlo, monospace"))
        source_layout.addWidget(self.preview_source)
        layout.addWidget(source_box, stretch=3)
        return panel

    # -- moving the blueprint in and out ------------------------------------

    def _load_blueprint(self) -> None:
        self._loading = True
        blueprint = self.blueprint
        self.kind_box.setCurrentIndex(self.kind_box.findData(blueprint.kind))
        self.effect_id.setText(blueprint.effect_id)
        self.title.setText(blueprint.title)
        self.description.setPlainText(blueprint.description)
        self.source_id.setText(blueprint.source_id)
        self.tags.setText(", ".join(blueprint.tags))
        self.version.setValue(blueprint.version)
        self.color_model.setCurrentIndex(self.color_model.findData(blueprint.color_model))
        self.composition.setCurrentIndex(self.composition.findData(blueprint.composition))
        self.animated.setChecked(blueprint.animated)
        self.directional.setChecked(blueprint.directional)
        self.slot_primary.setChecked(StateSlot.PRIMARY in blueprint.slots)
        self.slot_background.setChecked(StateSlot.BACKGROUND in blueprint.slots)
        self.restorable.setChecked(blueprint.restorable)
        self.duration_field.setCurrentIndex(self.duration_field.findData(blueprint.duration_field))
        self.duration_override.setChecked(blueprint.supports_duration_override)
        self.has_priority.setChecked(blueprint.default_priority is not None)
        self.priority.setValue(blueprint.default_priority or 0)
        self.sampling_mode.setCurrentIndex(self.sampling_mode.findData(blueprint.sampling_mode))
        self.provider_id.setText(blueprint.provider_id or "")
        self.interval_ms.setValue(blueprint.interval_ms)
        self.code.setPlainText(blueprint.render_body)
        self._rebuild_rows()
        self._loading = False
        self._refresh()

    def _rebuild_rows(self) -> None:
        for rows, layout in ((self.rows, self.rows_layout), (self.input_rows, self.inputs_layout)):
            for row in rows:
                row.setParent(None)
                row.deleteLater()
            rows.clear()
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
        for parameter in self.blueprint.parameters:
            self._attach_row(parameter, runtime=False)
        for parameter in self.blueprint.runtime_inputs:
            self._attach_row(parameter, runtime=True)

    def _attach_row(self, parameter: ParameterBlueprint, *, runtime: bool) -> ParameterEditorRow:
        row = ParameterEditorRow(parameter, runtime=runtime)
        row.changed.connect(self._on_edited)
        row.removed.connect(lambda r=row: self._remove_row(r))
        if runtime:
            self.input_rows.append(row)
            self.inputs_layout.addWidget(row)
        else:
            self.rows.append(row)
            self.rows_layout.addWidget(row)
        return row

    def _add_row(self, parameter: ParameterBlueprint, *, runtime: bool) -> None:
        target = self.blueprint.runtime_inputs if runtime else self.blueprint.parameters
        target.append(parameter)
        self._attach_row(parameter, runtime=runtime)
        self._refresh()

    def _remove_row(self, row: ParameterEditorRow) -> None:
        target = self.blueprint.runtime_inputs if row.runtime else self.blueprint.parameters
        if row.blueprint in target:
            target.remove(row.blueprint)
        rows = self.input_rows if row.runtime else self.rows
        if row in rows:
            rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh()

    def collect(self) -> None:
        blueprint = self.blueprint
        blueprint.kind = _chosen(self.kind_box, DefinitionKind)
        blueprint.effect_id = self.effect_id.text().strip()
        blueprint.title = self.title.text().strip()
        blueprint.description = self.description.toPlainText().strip()
        blueprint.source_id = self.source_id.text().strip()
        blueprint.tags = tuple(
            part.strip() for part in self.tags.text().split(",") if part.strip()
        )
        blueprint.version = self.version.value()
        blueprint.color_model = _chosen(self.color_model, ColorModel)
        blueprint.composition = _chosen(self.composition, CompositionMode)
        blueprint.animated = self.animated.isChecked()
        blueprint.directional = self.directional.isChecked()
        slots = []
        if self.slot_primary.isChecked():
            slots.append(StateSlot.PRIMARY)
        if self.slot_background.isChecked():
            slots.append(StateSlot.BACKGROUND)
        blueprint.slots = tuple(slots)
        blueprint.restorable = self.restorable.isChecked()
        blueprint.duration_field = _chosen(self.duration_field, DurationField)
        blueprint.supports_duration_override = self.duration_override.isChecked()
        blueprint.default_priority = self.priority.value() if self.has_priority.isChecked() else None
        blueprint.sampling_mode = _chosen(self.sampling_mode, InputMode)
        blueprint.provider_id = self.provider_id.text().strip() or None
        blueprint.interval_ms = self.interval_ms.value()
        blueprint.render_body = self.code.toPlainText()
        for row in [*self.rows, *self.input_rows]:
            row.collect()

    # -- reacting -----------------------------------------------------------

    def _on_kind_changed(self) -> None:
        if self._loading:
            return
        kind = _chosen(self.kind_box, DefinitionKind)
        keep_id = self.effect_id.text().strip()
        keep_source = self.source_id.text().strip() or "my-set"
        # Switching form changes which parameters are mandatory and which are
        # forbidden, so the blueprint is started again rather than patched into
        # a shape that would need untangling.
        self.blueprint = starting_blueprint(kind, effect_id=keep_id, source_id=keep_source)
        self.blueprint.title = self.title.text().strip()
        self.blueprint.description = self.description.toPlainText().strip()
        self._load_blueprint()

    def _on_structure_changed(self) -> None:
        if self._loading:
            return
        self.collect()
        self._refresh()

    def _on_edited(self) -> None:
        if self._loading:
            return
        self.collect()
        self._refresh()

    def _fill_required(self) -> None:
        self.collect()
        added = self.blueprint.add_missing_parameters()
        for name in added:
            parameter = next(p for p in self.blueprint.parameters if p.name == name)
            self._attach_row(parameter, runtime=False)
        if not added:
            self.status.setText("Es fehlt nichts.")
        self._refresh()

    def _refresh(self) -> None:
        blueprint = self.blueprint
        controlled = blueprint.kind is DefinitionKind.CONTROLLED_OVERLAY
        state = blueprint.kind is DefinitionKind.STATE

        self.slots_host.setVisible(state)
        self.restorable.setVisible(state)
        self.restorable.setEnabled(state and self.slot_background.isChecked())
        self.duration_field.setVisible(blueprint.finite)
        self.duration_override.setVisible(blueprint.finite)
        self.priority_host.setVisible(blueprint.kind is DefinitionKind.EVENT)
        self.sampling_mode.setVisible(controlled)
        self.provider_id.setVisible(controlled)
        self.provider_id.setEnabled(controlled and blueprint.sampling_mode is InputMode.PULL)
        self.interval_ms.setVisible(controlled)
        for index in range(self.form_layout.rowCount()):
            label = self.form_layout.itemAt(index, QFormLayout.ItemRole.LabelRole)
            field = self.form_layout.itemAt(index, QFormLayout.ItemRole.FieldRole)
            if label is not None and field is not None and field.widget() is not None:
                label.widget().setVisible(field.widget().isVisible())

        self.inputs_label.setVisible(controlled)
        self.add_input.setVisible(controlled)
        self.inputs_scroll.setVisible(controlled)

        missing = blueprint.required_parameters()
        forbidden = blueprint.forbidden_parameters()
        self.fill_button.setEnabled(bool(missing))

        for row in [*self.rows, *self.input_rows]:
            row.show_problem()

        problems = blueprint.problems()
        if forbidden:
            problems.insert(0, "Nicht erlaubt bei dieser Wahl: " + ", ".join(forbidden))
        if missing:
            problems.insert(0, "Es fehlen: " + ", ".join(missing))

        self.save_button.setEnabled(not problems)
        self.preview_button.setEnabled(not problems)
        if problems:
            self.status.setText("• " + "\n• ".join(problems[:6]))
            self.status.setStyleSheet("color: #d76;")
            self.preview_source.setPlainText("")
            return

        self.status.setText("Gültig — kann geschrieben und gebaut werden.")
        self.status.setStyleSheet("color: #4c9;")
        try:
            self.preview_source.setPlainText(blueprint.source_code())
        except Exception as exc:  # pragma: no cover — problems() already passed
            self.preview_source.setPlainText(f"# {exc}")

    # -- doing something with it -------------------------------------------

    def _preview(self) -> None:
        """Render the definition being written, on the device that is attached.

        Built in memory and registered under a throwaway id, so previewing does
        not collide with a catalogue entry of the same name and leaves nothing
        behind when the page is closed.
        """
        self.collect()
        if self.blueprint.problems() or self.session.service is None:
            return
        try:
            effect_class = compile_blueprint(self.blueprint)
        except Exception as exc:
            self.status.setText(f"render() lässt sich nicht laden: {exc}")
            self.status.setStyleSheet("color: #d76;")
            return

        service = self.session.service
        try:
            from lefx.engine import build_registry

            merged = list(service.library.registry.list_effects())
            classes = [entry.effect_class for entry in merged]
            service.library._registry = build_registry(  # noqa: SLF001
                [*classes, effect_class], source_id="studio-preview"
            )
            service.runtime.set_registry(service.library.registry)

            definition = effect_class.definition
            config = {name: p.default for name, p in definition.parameter_schema.items()}
            if definition.kind is DefinitionKind.STATE:
                self.session.play_state(definition.id, config)
            elif definition.kind is DefinitionKind.EVENT:
                self.session.emit(definition.id, config)
            else:
                inputs = {
                    name: p.default
                    for name, p in definition.runtime_input_schema.items()
                    if p.has_default
                }
                self.session.play_overlay(
                    definition.id,
                    config,
                    inputs,
                    channel=STUDIO_CHANNEL if definition.runtime_input_schema else None,
                )
            self.status.setText(f"{definition.id} läuft auf {self.session.output_name}.")
            self.status.setStyleSheet("color: #4c9;")
        except Exception as exc:
            self.status.setText(f"Vorschau fehlgeschlagen: {exc}")
            self.status.setStyleSheet("color: #d76;")

    def _write(self) -> None:
        self.collect()
        parent = QFileDialog.getExistingDirectory(
            self, "Wohin soll das Quellverzeichnis?", str(Path.cwd())
        )
        if not parent:
            return
        try:
            self.written = self.blueprint.write(parent)
        except SourceError as exc:
            QMessageBox.critical(self, "Nicht geschrieben", str(exc))
            return
        self.pack_button.setEnabled(True)
        self.status.setText(f"Geschrieben nach {self.written}")
        self.status.setStyleSheet("color: #4c9;")

    def _pack(self) -> None:
        if self.written is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Paket speichern", f"{self.blueprint.effect_id}.lefx", "LEFX (*.lefx)"
        )
        if not target:
            return
        try:
            report = build_package(self.written, target)
        except SourceError as exc:
            QMessageBox.critical(self, "Build fehlgeschlagen", str(exc))
            return
        QMessageBox.information(
            self,
            "Gebaut",
            f"{report['effect_id']} → {target}\n{report['size_bytes']} Bytes",
        )
        self.status.setText(f"Gebaut: {target}")

    def refresh(self) -> None:
        self.monitor.set_led_count(self.session.led_count)
        self._refresh()


__all__ = ["PREVIEW_ID_PREFIX", "ParameterEditorRow", "SourceEditorPage"]
