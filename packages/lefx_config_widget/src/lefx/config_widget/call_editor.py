"""Editor for one LED call, with a separate target selection page."""

from collections.abc import Mapping
from copy import deepcopy
from json import dumps
from math import isfinite

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from lefx.sdk import StateSlot

from .catalogue_widget import EffectCatalogueWidget
from .mapping import FORMS, EventSpec, HostCapabilities, call_verb, unsupported_call, validate_call
from .mapping import LedVerb
from .parameters import EffectEditor
from .preview import PreviewPanel, PreviewRequest


LABELS = {
    LedVerb.SET_STATE: "Zustand setzen",
    LedVerb.CLEAR_STATE: "Zustand entfernen",
    LedVerb.SET_OVERLAY: "Zeitgesteuertes Overlay",
    LedVerb.EMIT_EVENT: "Impuls auslösen",
    LedVerb.SET_OUTPUT: "LED-Ausgabe einstellen",
}


def call_summary(raw):
    if (verb := call_verb(raw)) is None:
        return "Nicht unterstützter Aufruf"
    value = raw[verb]
    if verb is LedVerb.SET_OUTPUT and isinstance(value, Mapping):
        value = ", ".join(f"{key}={item}" for key, item in value.items())
    slot = f" · {raw['slot']}" if raw.get("slot") else ""
    return f"{LABELS[verb]} · {value if value else '—'}{slot}"


def confirm(parent, title, message):
    return QMessageBox.question(
        parent, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    ) == QMessageBox.StandardButton.Yes


def _combo(parent, options, value, callback, label, *, optional=False):
    combo = QComboBox(parent)
    combo.setAccessibleName(label)
    if optional:
        combo.addItem("Ausgelassen / Standard", None)
    for text, option in options:
        combo.addItem(text, option)
    index = combo.findData(value)
    if index < 0:
        combo.insertItem(0, f"Vorhanden: {value!r}", value)
        combo.model().item(0).setEnabled(False)
        index = 0
    combo.setCurrentIndex(index)
    combo.activated.connect(lambda index: callback(combo.itemData(index)))
    return combo


def _empty_call(verb, capabilities):
    if verb is LedVerb.CLEAR_STATE:
        return {str(verb): StateSlot(capabilities.slots[0]).value if capabilities.slots else ""}
    if verb is LedVerb.SET_OUTPUT:
        return {str(verb): {}}
    return {str(verb): ""}


class LedCallEditor(QWidget):
    """Edit one mapping-form call. Changes affect a private draft."""

    draft_changed = Signal(object)

    def __init__(self, catalogue, parent=None, *, value=None, event=None,
                 capabilities=HostCapabilities(), read_only=False, preview_factory=None):
        super().__init__(parent)
        self.catalogue, self.capabilities = catalogue, capabilities
        self.event_spec = event or EventSpec("", "")
        self._raw = deepcopy(value)
        self._read_only = read_only
        self.preview_factory = preview_factory
        self.effect_editor = None
        self.preview = None
        self.target_picker = None
        self._stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self._build()

    def value(self):
        return deepcopy(self._raw)

    def set_value(self, value):
        self._raw = deepcopy(value)
        self._build()

    def validate(self):
        return validate_call(self._raw, self.catalogue, self.capabilities, self.event_spec)

    def set_read_only(self, state):
        self._read_only = state
        self._build()

    def refresh_catalogue(self):
        self._build()

    def _entry(self):
        verb = call_verb(self._raw)
        target = self._raw.get(verb) if verb in FORMS else None
        if isinstance(target, str) and target.strip():
            try:
                entry = self.catalogue.resolve(target)
            except ValueError:
                return None
            if entry.form is FORMS[verb]:
                return entry
        return None

    def _build(self):
        if self.preview is not None:
            self.preview.stop()
        while self._stack.count():
            old = self._stack.widget(0)
            self._stack.removeWidget(old)
            old.hide()
            old.deleteLater()
        self.effect_editor = self.preview = self.target_picker = None
        page = QWidget(self._stack)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        messages = QLabel(page)
        messages.setTextFormat(Qt.TextFormat.PlainText)
        messages.setWordWrap(True)
        messages.setAccessibleName("Aufrufdiagnosen")
        self.messages = messages
        scroll = QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        panel = QWidget(scroll)
        form = QFormLayout(panel)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scroll.setWidget(panel)
        layout.addWidget(scroll, 1)
        layout.addWidget(messages)
        self._stack.addWidget(page)
        verb = call_verb(self._raw)
        unsupported = unsupported_call(self._raw)
        if unsupported:
            raw_label = QLabel(dumps(self._raw, ensure_ascii=False, default=repr, indent=2), panel)
            raw_label.setTextFormat(Qt.TextFormat.PlainText)
            raw_label.setWordWrap(True)
            raw_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(raw_label)
            self._diagnose()
            return

        self.verb_combo = _combo(panel, [(LABELS[item], str(item)) for item in self.capabilities.allowed(self.event_spec)],
                                 str(verb), self._change_verb, "Aufrufart")
        self.verb_combo.setDisabled(self._read_only)
        form.addRow("Aufrufart", self.verb_combo)
        if verb is LedVerb.CLEAR_STATE:
            self._slot_selector(form, panel, self._raw[verb], verb, None, optional=False)
        elif verb is LedVerb.SET_OUTPUT:
            self._output_section(form, panel)
        else:
            self._effect_section(form, panel, verb)
        self._diagnose()

    def _slot_selector(self, form, parent, value, key, entry, *, optional):
        slots = self.capabilities.slots
        default = self.capabilities.default_state_slot
        if entry is not None:
            slots = tuple(slot for slot in slots if slot in entry.definition.slots)
            if default is None:
                default = entry.definition.slots[0]
        optional = optional and (default is None or default in slots)
        slot = _combo(parent, [(str(item.value), item.value) for item in slots], value,
                      lambda chosen: self._set_modifier(key, chosen), "Slot", optional=optional)
        slot.setDisabled(self._read_only)
        form.addRow("Slot", slot)

    def _effect_section(self, form, parent, verb):
        entry = self._entry()
        target = self._raw[verb]
        choose = QPushButton("Ziel auswählen…", parent)
        choose.clicked.connect(self._open_targets)
        choose.setDisabled(self._read_only)
        selected = QLabel(str(target) if target else "Kein Ziel ausgewählt", parent)
        selected.setTextFormat(Qt.TextFormat.PlainText)
        selected.setWordWrap(True)
        selected.setAccessibleName("Ausgewähltes Ziel")
        target_line = QVBoxLayout()
        target_line.addWidget(selected)
        target_line.addWidget(choose)
        form.addRow("Ziel", target_line)

        if verb is LedVerb.SET_STATE:
            self._slot_selector(form, parent, self._raw.get("slot"), "slot", entry, optional=True)
        if verb in (LedVerb.SET_STATE, LedVerb.SET_OVERLAY):
            actions = self.capabilities.state_actions if verb is LedVerb.SET_STATE else ("on",)
            action = _combo(parent, [(item, item) for item in actions], self._raw.get("action"),
                            lambda value: self._set_modifier("action", value), "Aktion",
                            optional="on" in actions)
            action.setDisabled(self._read_only)
            form.addRow("Aktion", action)
        if verb is LedVerb.EMIT_EVENT:
            if (self.capabilities.allow_duration and entry and entry.definition.supports_duration_override
                    or self._raw.get("duration_ms") is not None):
                maximum = self.capabilities.duration_max
                label = f"Dauer (ms, 1–{maximum})" if maximum else "Dauer (ms)"
                self._number_field(form, parent, label, self._raw.get("duration_ms"),
                                   lambda value: self._set_modifier("duration_ms", value), int,
                                   allow_input=self.capabilities.allow_duration and bool(
                                       entry and entry.definition.supports_duration_override))
            if self.capabilities.allow_priority or self._raw.get("priority") is not None:
                self._number_field(form, parent, "Priorität", self._raw.get("priority"),
                                   lambda value: self._set_modifier("priority", value), int,
                                   allow_input=self.capabilities.allow_priority)

        config = self._raw.get("config")
        if config is not None and (not isinstance(config, Mapping)
                                   or any(not isinstance(key, str) for key in config)):
            self._repair(form, parent, "Parameterobjekt", config,
                         lambda: self._replace_field("config"))
        elif entry is not None:
            self.effect_editor = EffectEditor(entry, parent, config=config, read_only=self._read_only)
            self.effect_editor.draft_changed.connect(lambda value: self._set_modifier("config", value))
            form.addRow(self.effect_editor)
        elif config is not None:
            label = QLabel(dumps(config, ensure_ascii=False, default=repr), parent)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            form.addRow("Vorhandene Parameter", label)

        if entry is not None and self.preview_factory is not None:
            self.preview = PreviewPanel(self.preview_factory, self._preview_request, parent)
            form.addRow("LED-Vorschau", self.preview)

    def _number_field(self, form, parent, label, value, update, number_type, *, allow_input=True):
        field = QLineEdit(parent)
        field.setAccessibleName(label)
        field.setText("" if value is None else str(value))
        field.setPlaceholderText("Ausgelassen")
        field.setReadOnly(self._read_only or not allow_input)

        def edited(text):
            if not text:
                update(None)
                return
            try:
                converted = number_type(text)
                if number_type is float and not isfinite(converted):
                    converted = text
            except ValueError:
                converted = text
            update(converted)

        field.textEdited.connect(edited)
        if not allow_input and value is not None and not self._read_only:
            row = QHBoxLayout()
            row.addWidget(field, 1)
            reset = QPushButton("Entfernen", parent)
            reset.setAccessibleName(f"{label} entfernen")
            reset.clicked.connect(lambda: (update(None), self._build()))
            row.addWidget(reset)
            form.addRow(label, row)
        else:
            form.addRow(label, field)

    def _repair(self, form, parent, label, value, replace):
        field = QLabel(repr(value), parent)
        field.setWordWrap(True)
        field.setTextFormat(Qt.TextFormat.PlainText)
        form.addRow(label, field)
        button = QPushButton(f"{label} zurücksetzen", parent)
        button.setDisabled(self._read_only)
        button.clicked.connect(lambda: replace() if confirm(
            self, "Wert zurücksetzen", "Den vorhandenen Wert im Aufrufentwurf entfernen?"
        ) else None)
        form.addRow(button)

    def _replace_field(self, key, *, output=False):
        self._assign(key, {} if output else None, remove=not output)
        self._build()
        self._emit()

    def _output_section(self, form, parent):
        payload = self._raw[LedVerb.SET_OUTPUT]
        if not isinstance(payload, Mapping):
            self._repair(form, parent, "LED-Ausgabe", payload,
                         lambda: self._replace_field(LedVerb.SET_OUTPUT, output=True))
            return
        self._number_field(form, parent, "Helligkeit (0–1)", payload.get("brightness"),
                           lambda value: self._output("brightness", value), float)
        combo = _combo(parent, [("Aktiv", True), ("Stumm", False)], payload.get("enabled"),
                       lambda value: self._output("enabled", value), "Ausgabestatus", optional=True)
        combo.setDisabled(self._read_only)
        form.addRow("Ausgabestatus", combo)

    def _assign(self, key, value, *, remove=False):
        if remove:
            self._raw.pop(key, None)
        else:
            self._raw[key] = deepcopy(value)

    def _output(self, key, value):
        payload = dict(self._raw[LedVerb.SET_OUTPUT])
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
        self._assign(LedVerb.SET_OUTPUT.value, payload)
        self._emit()

    def _set_modifier(self, key, value):
        if key == LedVerb.CLEAR_STATE:
            self._assign(str(key), value)
        else:
            self._assign(key, value, remove=value is None)
        self._emit()

    def _change_verb(self, value):
        verb = LedVerb(value)
        before = call_verb(self._raw)
        if verb == before:
            return
        if not confirm(self, "Aufrufart wechseln",
                       "Beim Wechsel werden Ziel und Optionen dieses Aufrufentwurfs ersetzt."):
            self.verb_combo.setCurrentIndex(self.verb_combo.findData(str(before)))
            return
        self._raw = _empty_call(verb, self.capabilities)
        self._build()
        self._emit()

    def _open_targets(self):
        verb = call_verb(self._raw)
        if self._read_only or verb not in FORMS:
            return
        page = QWidget(self._stack)
        layout = QVBoxLayout(page)
        back = QPushButton("‹ Zurück zum Aufruf", page)
        back.clicked.connect(self._return_from_targets)
        layout.addWidget(back)
        self.target_picker = EffectCatalogueWidget(
            self.catalogue, page, forms=(FORMS[verb],), predicate=self._target_allowed
        )
        if entry := self._entry():
            self.target_picker.set_selected_id(entry.qualified_id)
        layout.addWidget(self.target_picker, 1)
        choose = QPushButton("Ziel übernehmen", page)
        choose.clicked.connect(self.target_picker.activate_current)
        layout.addWidget(choose)
        self.target_picker.target_selected.connect(self._change_target)
        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)
        self.target_picker.search.setFocus()

    def _target_allowed(self, entry):
        return entry.form != FORMS[LedVerb.SET_STATE] or any(
            slot in self.capabilities.slots for slot in entry.definition.slots
        )

    def _return_from_targets(self):
        page = self._stack.currentWidget()
        self._stack.setCurrentIndex(0)
        self._stack.removeWidget(page)
        page.deleteLater()
        self.target_picker = None

    def _change_target(self, target):
        verb = call_verb(self._raw)
        current = self._entry()
        entry = self.catalogue.resolve(target)
        if current is not None and current.qualified_id == entry.qualified_id:
            self._return_from_targets()
            return
        candidate = deepcopy(self._raw)
        candidate[verb.value] = target
        option_errors = validate_call(candidate, self.catalogue, self.capabilities, self.event_spec)
        incompatible = set()
        for error in option_errors:
            root = error.field.split(".", 1)[0]
            if root in ("config", "slot", "duration_ms") and candidate.get(root) is not None:
                incompatible.add(root)
        if incompatible and not confirm(
            self, "Ziel wechseln",
            "Für dieses Ziel unvereinbare Optionen zurücksetzen: " + ", ".join(sorted(incompatible)),
        ):
            return
        for key in incompatible:
            candidate.pop(key)
        self._raw = candidate
        self._build()
        self._emit()

    def _preview_request(self, count, brightness):
        if errors := self.validate():
            raise ValueError("\n".join(map(str, errors)))
        verb = call_verb(self._raw)
        slot = None
        if verb is LedVerb.SET_STATE:
            slot = self._raw.get("slot") or self.capabilities.default_state_slot
        return PreviewRequest(
            self._raw[verb], self._raw.get("config"), slot=slot,
            priority=self._raw.get("priority"), duration_ms=self._raw.get("duration_ms"),
            led_count=count, brightness=brightness,
        )

    def _diagnose(self):
        errors = self.validate()
        self.messages.setText("\n".join(map(str, errors[:3])) +
                              (f"\nWeitere Fehler: {len(errors) - 3}" if len(errors) > 3 else ""))
        self.messages.setVisible(bool(errors))

    def _emit(self):
        self._diagnose()
        if self.preview is not None:
            self.preview.schedule_update()
        self.draft_changed.emit(self.value())
