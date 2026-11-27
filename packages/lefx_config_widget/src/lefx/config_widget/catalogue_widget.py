"""Searchable selection of effects and presets."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

from lefx.sdk import DefinitionKind


FORM_LABELS = {
    DefinitionKind.STATE: "Zustand",
    DefinitionKind.TIMED_OVERLAY: "Zeitgesteuertes Overlay",
    DefinitionKind.CONTROLLED_OVERLAY: "Gesteuertes Overlay",
    DefinitionKind.EVENT: "Impuls",
}


class EffectCatalogueWidget(QWidget):
    """Select a stable qualified ID by activating a row or pressing Enter."""

    target_selected = Signal(str)

    def __init__(self, catalogue, parent=None, *, forms=None, predicate=None):
        super().__init__(parent)
        self.catalogue = catalogue
        self.forms = tuple(DefinitionKind if forms is None else forms)
        self.predicate = predicate
        self._entries = ()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Name, ID oder Beschreibung suchen")
        self.search.setAccessibleName("Effektsuche")
        self.form_filter = QComboBox(self)
        self.form_filter.setAccessibleName("Effektform")
        self.form_filter.addItem("Alle Formen", None)
        for form in self.forms:
            self.form_filter.addItem(FORM_LABELS[form], form)
        self.kind_filter = QComboBox(self)
        self.kind_filter.setAccessibleName("Effekte oder Presets")
        for label, value in (("Alle Ziele", None), ("Effekte", False), ("Presets", True)):
            self.kind_filter.addItem(label, value)
        filters = QHBoxLayout()
        filters.addWidget(self.form_filter)
        filters.addWidget(self.kind_filter)
        self.results = QListWidget(self)
        self.results.setAccessibleName("Katalogtreffer")
        self.results.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.description = QLabel(self)
        self.description.setWordWrap(True)
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        self.description.setMaximumHeight(90)
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addLayout(filters)
        layout.addWidget(self.results, 1)
        layout.addWidget(self.description)
        self.search.textChanged.connect(self._filter)
        self.form_filter.currentIndexChanged.connect(self._filter)
        self.kind_filter.currentIndexChanged.connect(self._filter)
        self.results.currentItemChanged.connect(self._describe)
        self.results.itemActivated.connect(lambda item: self.target_selected.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.search.returnPressed.connect(self.activate_current)
        self.refresh()

    def refresh(self):
        self._entries = tuple(
            entry for entry in self.catalogue.entries()
            if entry.form in self.forms and (self.predicate is None or self.predicate(entry))
        )
        self._filter()

    def selected_id(self):
        item = self.results.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def set_selected_id(self, target):
        for index in range(self.results.count()):
            if self.results.item(index).data(Qt.ItemDataRole.UserRole) == target:
                self.results.setCurrentRow(index)
                return True
        return False

    def activate_current(self):
        target = self.selected_id()
        if target is not None:
            self.target_selected.emit(target)

    def _filter(self):
        target = self.selected_id()
        search = self.search.text().casefold().split()
        form, preset = self.form_filter.currentData(), self.kind_filter.currentData()
        self.results.clear()
        for entry in self._entries:
            if form is not None and entry.form != form:
                continue
            if preset is not None and (entry.preset is not None) != preset:
                continue
            haystack = f"{entry.label} {entry.description} {' '.join(entry.tags)}".casefold()
            if all(word in haystack for word in search):
                item = QListWidgetItem(entry.label, self.results)
                item.setData(Qt.ItemDataRole.UserRole, entry.qualified_id)
                details = f"{FORM_LABELS[entry.form]} · Version {entry.definition.version}\n{entry.description}"
                item.setToolTip(details)
                item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, details)
        if not self.set_selected_id(target) and self.results.count():
            self.results.setCurrentRow(0)
        if not self.results.count():
            self.description.setText("Keine passenden Katalogeinträge.")

    def _describe(self, item, _previous):
        self.description.setText(item.data(Qt.ItemDataRole.AccessibleDescriptionRole) if item else "")
