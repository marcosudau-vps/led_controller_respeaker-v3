"""Embeddable configurator and explicit accept/reject dialog."""

from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .mapping import HostCapabilities
from .mapping_editor import FeedbackMappingEditor, _equal


class LedFeedbackConfigurator(QWidget):
    applied = Signal(object)
    cancelled = Signal()
    back_requested = Signal()
    draft_changed = Signal(object)
    validation_failed = Signal(object)

    def __init__(self, events, catalogue, parent=None, *, rules=None,
                 capabilities=HostCapabilities(), preview_factory=None, read_only=False,
                 show_actions=True, show_back=True, show_status=True):
        super().__init__(parent)
        self._initial = deepcopy(dict({} if rules is None else rules))
        self._read_only = read_only
        layout = QVBoxLayout(self)
        self.back_button = QPushButton("‹ Zum Host", self)
        self.back_button.clicked.connect(self.request_back)
        self.back_button.setVisible(show_back)
        header = QHBoxLayout()
        header.addWidget(self.back_button)
        header.addStretch()
        layout.addLayout(header)
        self.mapping = FeedbackMappingEditor(
            events, catalogue, self, rules=self._initial, capabilities=capabilities,
            read_only=read_only, preview_factory=preview_factory,
        )
        layout.addWidget(self.mapping, 1)
        self.status = QLabel(self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Entwurfsstatus")
        self.status.setVisible(show_status)
        layout.addWidget(self.status)
        self.actions = QWidget(self)
        buttons = QHBoxLayout(self.actions)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch()
        self.cancel_button = QPushButton("Entwurf verwerfen", self.actions)
        self.apply_button = QPushButton("Zuordnung übernehmen", self.actions)
        self.cancel_button.clicked.connect(self._confirm_cancel)
        self.apply_button.clicked.connect(self.apply)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button)
        self.actions.setVisible(show_actions)
        layout.addWidget(self.actions)
        self.mapping.draft_changed.connect(self._changed)
        self.set_read_only(read_only)
        self._update_status()

    def value(self):
        return self.mapping.value()

    def set_value(self, rules):
        self._initial = deepcopy(dict(rules))
        self.mapping.set_value(self._initial)
        self._update_status()

    def set_draft(self, rules):
        """Restore a previously saved working copy for the current input."""
        self.mapping.set_draft(rules)
        self._update_status()

    def is_dirty(self):
        return not _equal(self._initial, self.value())

    def validate(self):
        return self.mapping.validate()

    def warnings(self):
        return self.mapping.warnings()

    def export(self):
        if errors := self.validate():
            raise ValueError("\n".join(map(str, errors)))
        return self.value()

    def apply(self):
        if self._read_only:
            return False
        errors = self.validate()
        if errors:
            self._update_status(errors)
            self.validation_failed.emit(errors)
            return False
        self.mapping.accept_baseline()
        self._initial = self.value()
        self._update_status()
        self.applied.emit(self.value())
        return True

    def cancel(self):
        dirty = self.is_dirty()
        self.mapping.set_value(self._initial)
        self._update_status()
        if dirty:
            self.draft_changed.emit(self.value())
        self.cancelled.emit()

    def _confirm_cancel(self):
        from .call_editor import confirm

        if not self.is_dirty() or confirm(self, "Entwurf verwerfen",
                                         "Alle Änderungen seit der letzten Übernahme verwerfen?"):
            self.cancel()

    def request_back(self):
        self.mapping.show_overview()
        self.back_requested.emit()

    def set_read_only(self, state):
        self._read_only = state
        self.mapping.set_read_only(state)
        self.apply_button.setDisabled(state)
        self.cancel_button.setDisabled(state)
        self._update_status()

    def refresh_catalogue(self):
        """Refresh the UI after the host's catalogue provider has been updated."""
        self.mapping.refresh_catalogue()

    def _changed(self, _snapshot):
        self._update_status()
        self.draft_changed.emit(self.value())

    def _update_status(self, errors=None):
        errors = self.validate() if errors is None else errors
        warnings = self.warnings()
        messages = []
        if self._read_only:
            messages.append("Schreibgeschützt")
        if self.is_dirty():
            messages.append("Änderungen im Entwurf")
        if errors:
            messages.append(f"{len(errors)} Fehler · {errors[0]}")
        if warnings:
            messages.append(f"{len(warnings)} schreibgeschützte Regeln werden unverändert weitergegeben.")
        self.status.setText("\n".join(messages))


class LedFeedbackDialog(QDialog):
    """Accept only a valid draft. Reject restores the supplied configuration."""

    def __init__(self, events, catalogue, parent=None, **options):
        super().__init__(parent)
        self.setWindowTitle("LED-Effekte konfigurieren")
        self.result_rules = None
        layout = QVBoxLayout(self)
        self.configurator = LedFeedbackConfigurator(
            events, catalogue, self, **{**options, "show_back": False, "show_actions": False}
        )
        layout.addWidget(self.configurator)
        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("Verwerfen" if not options.get("read_only") else "Schließen", self)
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        self.accept_button = QPushButton("Übernehmen", self)
        self.accept_button.setDefault(True)
        self.accept_button.clicked.connect(self.accept)
        self.accept_button.setVisible(not options.get("read_only", False))
        buttons.addWidget(self.accept_button)
        layout.addLayout(buttons)

    def accept(self):
        if self.configurator.apply():
            self.result_rules = self.configurator.value()
            super().accept()

    def reject(self):
        self.result_rules = None
        self.configurator.cancel()
        super().reject()
