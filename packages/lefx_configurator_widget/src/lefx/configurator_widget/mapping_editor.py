"""Ordered event rules and staged Qt editing."""

from collections.abc import Mapping
from copy import deepcopy
from json import dumps

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .call_editor import LABELS, LedCallEditor, _empty_call, call_summary, confirm
from .mapping import Diagnostic, HostCapabilities, ordered_calls, unsupported_call, validate_call


def _equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, Mapping):
        return left.keys() == right.keys() and all(_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    return left == right


def _notice(parent, name):
    label = QLabel(parent)
    label.setAccessibleName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def _button(layout, text, parent, callback, *, label=None):
    button = QPushButton(text, parent)
    if label:
        button.setAccessibleName(label)
        button.setToolTip(label)
    button.clicked.connect(callback)
    layout.addWidget(button)
    return button


class FeedbackMappingEditor(QWidget):
    """Edit a map of event IDs to raw LED rules with three navigation levels."""

    draft_changed = Signal(object)

    def __init__(self, events, catalogue, parent=None, *, rules=None,
                 capabilities=HostCapabilities(), read_only=False, preview_factory=None):
        super().__init__(parent)
        events = tuple(events)
        self.events = {event.id: event for event in events}
        if len(self.events) != len(events):
            raise ValueError("Event IDs must be unique")
        self.catalogue, self.capabilities = catalogue, capabilities
        self._read_only, self.preview_factory = read_only, preview_factory
        self._event = None
        self._call = None
        self._call_page = None
        self._call_index = None
        self._initial = {}
        self._rules = {}
        self.stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self._create_overview()
        self._create_event_page()
        self.set_value({} if rules is None else rules)

    @property
    def call_editor(self):
        return self._call

    def _create_overview(self):
        self.overview_page = QWidget(self.stack)
        layout = QVBoxLayout(self.overview_page)
        title = QLabel("<b>LED-Ereignisse</b>", self.overview_page)
        layout.addWidget(title)
        self.tree = QTreeWidget(self.overview_page)
        self.tree.setAccessibleName("Ereignisübersicht")
        self.tree.setHeaderLabels(["Ereignis", "LED-Zuordnung"])
        self.tree.setColumnWidth(0, 235)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree, 1)
        self.event_description = _notice(self.overview_page, "Ereignisbeschreibung")
        layout.addWidget(self.event_description)
        actions = QHBoxLayout()
        actions.addStretch()
        self.open_event_button = _button(actions, "Ereignis öffnen", self.overview_page, self._open_current)
        layout.addLayout(actions)
        self.tree.currentItemChanged.connect(self._describe)
        self.tree.itemActivated.connect(lambda *_: self._open_current())
        self.stack.addWidget(self.overview_page)

    def _create_event_page(self):
        self.event_page = QWidget(self.stack)
        layout = QVBoxLayout(self.event_page)
        header = QHBoxLayout()
        _button(header, "‹ Ereignisse", self.event_page, self.show_overview)
        self.event_title = _notice(self.event_page, "Ereignisname")
        header.addWidget(self.event_title, 1)
        layout.addLayout(header)
        self.calls = QListWidget(self.event_page)
        self.calls.setAccessibleName("LED-Aufrufe in Ausführungsreihenfolge")
        self.calls.itemActivated.connect(lambda *_: self.edit_call())
        self.calls.currentRowChanged.connect(self._event_buttons)
        layout.addWidget(self.calls, 1)
        self.event_status = _notice(self.event_page, "Regeldiagnosen")
        layout.addWidget(self.event_status)
        actions = QHBoxLayout()
        self.add = _button(actions, "+", self.event_page, self._add_call, label="Aufruf hinzufügen")
        self.remove = _button(actions, "−", self.event_page, self._remove_call, label="Aufruf entfernen")
        self.up = _button(actions, "↑", self.event_page, lambda: self._move_call(-1), label="Aufruf nach oben")
        self.down = _button(actions, "↓", self.event_page, lambda: self._move_call(1), label="Aufruf nach unten")
        actions.addStretch()
        self.open_call_button = _button(actions, "Aufruf öffnen", self.event_page, self.edit_call)
        layout.addLayout(actions)
        self.stack.addWidget(self.event_page)

    def value(self, *, include_open=True):
        result = deepcopy(self._rules)
        if include_open and self._call is not None and not self._locked():
            calls = self._calls()
            if self._call_index == len(calls):
                calls.append(self._call.value())
            else:
                calls[self._call_index] = self._call.value()
            self._write_calls(result, self._event, calls)
        return result

    def set_value(self, rules):
        self.set_draft(rules)
        self._initial = self.value()

    def set_draft(self, rules):
        """Load a saved working copy while retaining the accepted baseline."""
        self._rules = deepcopy(dict(rules))
        self.show_overview(keep_call=False)

    def accept_baseline(self):
        """Use the current mapping as the reference for subsequent edits."""
        self.commit_open_call()
        self._initial = self.value()

    def validate(self):
        return self._diagnostics(self.value(), opaque=False)

    def warnings(self):
        return self._diagnostics(self.value(), opaque=True)

    def _diagnostics(self, rules, *, opaque):
        results = []
        for event in self.events.values():
            raw = rules.get(event.id)
            blocked = self._unsupported(raw)
            if blocked and opaque:
                results.append(Diagnostic(event.id, blocked))
            if blocked or opaque:
                continue
            for index, call in enumerate(ordered_calls(raw), 1):
                results.extend(
                    Diagnostic(f"{event.id}.led[{index}].{issue.field}", issue.message)
                    for issue in validate_call(call, self.catalogue, self.capabilities, event)
                )
        return tuple(results)

    def show_overview(self, *, keep_call=True):
        if self._call is not None:
            self._close_call(keep=keep_call)
        self._refresh_overview()
        self.stack.setCurrentWidget(self.overview_page)
        self.tree.setFocus()

    def open_event(self, event_id):
        if event_id not in self.events:
            raise KeyError(event_id)
        if self._call is not None:
            self._close_call(keep=True)
        self._event = event_id
        self.event_title.setText(self.events[event_id].label)
        self._refresh_calls(0)
        self.stack.setCurrentWidget(self.event_page)
        self.calls.setFocus()

    def _open_current(self):
        current = self.tree.currentItem()
        if current is not None and (event := current.data(0, Qt.ItemDataRole.UserRole)) is not None:
            self.open_event(event)

    def _describe(self, current, _previous):
        event_id = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        event = self.events.get(event_id)
        self.open_event_button.setEnabled(event is not None)
        self.event_description.setText(event.description if event else "")
        self.event_description.setVisible(bool(event and event.description))

    def _refresh_overview(self):
        self.tree.clear()
        groups = {}
        selected = None
        first = None
        for event in self.events.values():
            group = self.tree
            if event.group:
                if event.group not in groups:
                    groups[event.group] = QTreeWidgetItem(self.tree, [event.group])
                    groups[event.group].setExpanded(True)
                group = groups[event.group]
            row = QTreeWidgetItem(group, [event.label, self._summary(event)])
            row.setData(0, Qt.ItemDataRole.UserRole, event.id)
            row.setToolTip(0, event.description or event.id)
            row.setToolTip(1, row.text(1))
            if event.id == self._event:
                selected = row
            if first is None:
                first = row
        self.tree.setCurrentItem(selected or first)
        self.open_event_button.setEnabled(first is not None)

    def _summary(self, event):
        if event.id not in self._rules:
            return "Nicht konfiguriert"
        raw = self._rules[event.id]
        if self._unsupported(raw):
            return "Nicht unterstützte Daten · schreibgeschützt"
        calls = ordered_calls(raw)
        if not calls:
            return "Leer"
        invalid = any(validate_call(call, self.catalogue, self.capabilities, event) for call in calls)
        summary = call_summary(calls[0])
        if len(calls) > 1:
            summary = f"{len(calls)} Aufrufe · {summary}"
        return f"Ungültig · {summary}" if invalid else summary

    @staticmethod
    def _unsupported(raw):
        try:
            calls = ordered_calls(raw)
        except ValueError as exc:
            return str(exc)
        for call in calls:
            if message := unsupported_call(call):
                return message
        return None

    def _calls(self):
        try:
            return ordered_calls(self._rules.get(self._event))
        except ValueError:
            return []

    def _locked(self):
        return self._read_only or bool(self._unsupported(self._rules.get(self._event)))

    def _refresh_calls(self, index=0):
        raw = self._rules.get(self._event)
        opaque = self._unsupported(raw)
        self.calls.clear()
        for call in self._calls():
            issues = validate_call(call, self.catalogue, self.capabilities, self.events[self._event])
            text = call_summary(call)
            self.calls.addItem(f"⚠ {text}" if issues else text)
            if issues:
                self.calls.item(self.calls.count() - 1).setToolTip("\n".join(map(str, issues)))
        if opaque:
            message = "Schreibgeschützt · " + opaque
            if not self.calls.count():
                message += "\n" + dumps(raw, ensure_ascii=False, default=repr)
        elif self.calls.count():
            message = ""
        elif self._event in self._rules:
            message = "Keine LED-Aufrufe"
        else:
            message = "Für dieses Ereignis fehlt eine LED-Zuordnung."
        self.event_status.setText(message)
        self.event_status.setVisible(bool(message))
        self.calls.setCurrentRow(min(index, self.calls.count() - 1))
        self._event_buttons()

    def _event_buttons(self):
        if self._event is None:
            return
        index, count = self.calls.currentRow(), self.calls.count()
        edit = not self._locked()
        self.add.setEnabled(edit and bool(self.capabilities.allowed(self.events[self._event])))
        self.remove.setEnabled(edit and index >= 0)
        self.up.setEnabled(edit and index > 0)
        self.down.setEnabled(edit and 0 <= index < count - 1)
        self.open_call_button.setEnabled(index >= 0)

    def _write_calls(self, target, event_id, calls):
        original = self._initial.get(event_id)
        if not self._unsupported(original) and _equal(ordered_calls(original), calls):
            if event_id in self._initial:
                target[event_id] = deepcopy(original)
            else:
                target.pop(event_id, None)
        elif not isinstance(original, (list, tuple)) and len(calls) == 1:
            target[event_id] = deepcopy(calls[0])
        else:
            target[event_id] = deepcopy(calls)

    def _change_calls(self, calls, index):
        self._write_calls(self._rules, self._event, calls)
        self._refresh_calls(index)
        self.draft_changed.emit(self.value())

    def _remove_call(self):
        index = self.calls.currentRow()
        if self._locked() or index < 0:
            return
        calls = self._calls()
        if confirm(self, "Aufruf entfernen", f"{call_summary(calls[index])} aus dem Entwurf entfernen?"):
            del calls[index]
            self._change_calls(calls, index)

    def _move_call(self, offset):
        index = self.calls.currentRow()
        calls = self._calls()
        target = index + offset
        if self._locked() or index < 0 or not 0 <= target < len(calls):
            return
        calls.insert(target, calls.pop(index))
        self._change_calls(calls, target)

    def _add_call(self):
        verbs = self.capabilities.allowed(self.events[self._event])
        if self._locked() or not verbs:
            return
        if len(verbs) == 1:
            self._open_call(len(self._calls()), _empty_call(verbs[0], self.capabilities))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Aufruf hinzufügen")
        layout = QVBoxLayout(dialog)

        def choose(verb):
            dialog.accept()
            self._open_call(len(self._calls()), _empty_call(verb, self.capabilities))

        for verb in verbs:
            _button(layout, LABELS[verb], dialog, lambda checked=False, v=verb: choose(v))
        _button(layout, "Abbrechen", dialog, dialog.reject)
        dialog.finished.connect(dialog.deleteLater)
        dialog.open()

    def edit_call(self):
        index = self.calls.currentRow()
        if index >= 0:
            self._open_call(index, self._calls()[index])

    def _open_call(self, index, call):
        event = self.events[self._event]
        page = QWidget(self.stack)
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        _button(header, "‹ Zurück · Entwurf behalten" if not self._locked() else "‹ Zurück",
                page, lambda: self._close_call(keep=True))
        title = _notice(page, "Aufrufpfad")
        title.setText(f"{event.label} / Aufruf {index + 1}")
        header.addWidget(title, 1)
        layout.addLayout(header)
        editor = LedCallEditor(self.catalogue, page, value=call, event=event,
                               capabilities=self.capabilities, read_only=self._locked(),
                               preview_factory=self.preview_factory)
        layout.addWidget(editor, 1)
        if not self._locked():
            footer = QHBoxLayout()
            footer.addStretch()
            _button(footer, "Aufrufänderungen verwerfen", page, lambda: self._close_call(keep=False))
            apply = _button(footer, "Aufruf übernehmen", page, lambda: self._close_call(keep=True))
            apply.setEnabled(not editor.validate())
            editor.draft_changed.connect(lambda _: apply.setEnabled(not editor.validate()))
            layout.addLayout(footer)
        self._call_index, self._call_page, self._call = index, page, editor
        editor.draft_changed.connect(lambda _: self.draft_changed.emit(self.value()))
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self.draft_changed.emit(self.value())

    def _close_call(self, *, keep):
        if self._call is None:
            return
        changed = keep and not self._locked()
        current = self.value() if changed else None
        page, index = self._call_page, self._call_index
        for dialog in page.findChildren(QDialog):
            dialog.reject()
        self._call = self._call_page = self._call_index = None
        if changed:
            self._rules = current
        self.stack.setCurrentWidget(self.event_page)
        self.stack.removeWidget(page)
        page.deleteLater()
        self._refresh_calls(index)
        self.calls.setFocus()
        self.draft_changed.emit(self.value())

    def commit_open_call(self):
        """Keep the current subdraft and return to its event."""
        self._close_call(keep=True)

    def set_read_only(self, state):
        if self._read_only != state:
            self.commit_open_call()
            self._read_only = state
            if self._event is not None:
                self._event_buttons()

    def refresh_catalogue(self):
        self.commit_open_call()
        self._refresh_overview()
        if self._event is not None:
            self._refresh_calls(self.calls.currentRow())
        self.draft_changed.emit(self.value())
