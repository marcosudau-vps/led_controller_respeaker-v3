"""Local desktop demonstration of the reusable configurator components."""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import replace
from json import dumps, loads
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from lefx.sdk import DefinitionKind

from .call_editor import confirm
from .catalogue import LefxCatalogueAdapter, MemoryCatalogue
from .catalogue_widget import EffectCatalogueWidget
from .configurator import LedFeedbackConfigurator
from .mapping import EventSpec, FeedbackDocument, HostCapabilities, LedVerb
from .parameters import EffectEditor, ParameterForm
from .preview import PreviewPanel, PreviewRequest, PreviewSession
from .widgets import (
    AngleEditor, ColorListEditor, ColorRangeEditor, GradientEditor,
    LedRingPreview, RangeEditor, RepeatableContainer,
)


EVENTS = (
    EventSpec("device.available", "Gerät bereit", "Gerät", "Zustand nach dem Start."),
    EventSpec("device.shutdown", "Gerät beendet", "Gerät", "Entfernt die Zustandsanzeige.",
              frozenset({LedVerb.CLEAR_STATE, LedVerb.SET_OUTPUT})),
    EventSpec("task.finished", "Aufgabe abgeschlossen", "Aufgaben", "Bestätigung mit zwei Aufrufen."),
    EventSpec("task.pending", "Aufgabe wartet", "Aufgaben", "Beispiel für eine leere Regel."),
    EventSpec("task.retry", "Aufgabe erneut starten", "Aufgaben"),
)
STT_EVENTS = (
    EventSpec("server.transcription.completed", "Transkription abgeschlossen", "Server"),
    EventSpec("client.lifecycle.stopping", "Anwendung wird beendet", "Client"),
    EventSpec("client.dictation.timeout_warning", "Warnung vor Zeitlimit", "Client"),
)
SAMPLE = {
    "schema_version": 2,
    "events": {
        "device.available": {"led": {"set_state": "solid_fill"}},
        "device.shutdown": {"led": {"clear_state": "primary"}},
        "task.finished": {"led": [{"emit_event": "success_event"}, {"set_state": "ready_state"}]},
        "task.pending": {"led": []},
    },
}
STT_SAMPLE = {
    "schema_version": 2,
    "events": {
        "server.transcription.completed": {
            "led": [{"emit_event": "success_event", "config": {"duration_ms": 700}},
                    {"set_state": "ready_state", "action": None}],
            "sound": {"cue": "complete", "volume": 1.0},
            "app": {"action": "indicator.success"},
        },
        "client.lifecycle.stopping": {"led": {"clear_state": "primary"}},
        "client.dictation.timeout_warning": {"led": {
            "set_overlay": "countdown_ring", "config": {"duration_ms": 3000,
            "colors": ["#00C066", "#FFE000", "#FF0000"], "brightness": 1.0},
        }},
    },
}


def _plain_label(parent, text=""):
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def _action(layout, parent, text, callback):
    button = QPushButton(text, parent)
    button.clicked.connect(callback)
    layout.addWidget(button)
    return button


class _LabCatalogue:
    def __init__(self):
        self.adapter = LefxCatalogueAdapter.installed()
        self.collisions = False

    def provider(self):
        if not self.collisions:
            return self.adapter
        items = self.adapter.entries()
        original = self.adapter.resolve("solid_fill")
        collision = replace(original, qualified_id="lab-demo::solid_fill", source_id="lab-demo",
                            title="Solid Fill (Kollisionsbeispiel)", package_id=None)
        return MemoryCatalogue((*items, collision))

    def entries(self):
        return self.provider().entries()

    def resolve(self, target):
        return self.provider().resolve(target)

    def preview_factory(self):
        registry = self.adapter.registry
        return lambda: PreviewSession(registry)

    def replace(self, names, collisions=False):
        new = LefxCatalogueAdapter.installed(names)
        old = self.adapter
        self.adapter, self.collisions = new, collisions
        old.close()

    def close(self):
        self.adapter.close()


class _EffectBrowser(QWidget):
    def __init__(self, catalogue, parent=None):
        super().__init__(parent)
        self.catalogue = catalogue
        self.selected = None
        self._saved = {}
        self.picker = EffectCatalogueWidget(catalogue, self)
        pick = QPushButton("Ziel öffnen", self)
        pick.clicked.connect(self.picker.activate_current)
        left = QWidget(self)
        navigation = QVBoxLayout(left)
        navigation.addWidget(self.picker, 1)
        navigation.addWidget(pick)
        self.picker.target_selected.connect(self.open_target)
        self.panel = QScrollArea(self)
        self.panel.setWidgetResizable(True)
        self.panel.setWidget(_plain_label(self, "Wähle einen Effekt oder ein Preset."))
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(1, 1)
        layout = QHBoxLayout(self)
        layout.addWidget(splitter)
        self.effect_editor = self.inputs = self.preview = None

    def refresh(self):
        self.picker.refresh()
        if self.selected is not None:
            self.open_target(self.selected)

    def open_target(self, target):
        if self.selected is not None and self.effect_editor is not None:
            self._saved[self.selected] = self.effect_editor.value()
        self.selected = target
        old = self.panel.takeWidget()
        if old is not None:
            old.hide()
            old.deleteLater()
        self.effect_editor = self.inputs = self.preview = None
        try:
            entry = self.catalogue.resolve(target)
        except ValueError as exc:
            self.panel.setWidget(_plain_label(self, str(exc)))
            return
        content = QWidget(self.panel)
        layout = QVBoxLayout(content)
        layout.addWidget(_plain_label(content, entry.description))
        self.effect_editor = EffectEditor(entry, content, config=self._saved.get(target))
        layout.addWidget(self.effect_editor)
        diagnostics = _plain_label(content)
        layout.addWidget(diagnostics)

        def change(_snapshot):
            diagnostics.setText("\n".join(map(str, self.effect_editor.validate())))
            self.preview.schedule_update()

        if entry.form is DefinitionKind.CONTROLLED_OVERLAY:
            title = _plain_label(content, "Laufzeitwerte der Vorschau")
            layout.addWidget(title)
            self.inputs = ParameterForm(entry.definition.runtime_input_schema, content, prefix="inputs")
            layout.addWidget(self.inputs)
            self.inputs.draft_changed.connect(change)
        self.preview = PreviewPanel(self.catalogue.preview_factory, self._request, content)
        self.effect_editor.draft_changed.connect(change)
        layout.addWidget(self.preview)
        layout.addStretch()
        self.panel.setWidget(content)
        diagnostics.setText("\n".join(map(str, self.effect_editor.validate())))

    def _request(self, count, brightness):
        inputs = self.inputs.value() if self.inputs is not None else {}
        errors = list(self.effect_editor.validate())
        if self.inputs is not None:
            errors.extend(self.inputs.validate())
            errors.extend(f"inputs.{name}: Testwert fehlt." for name, value in inputs.items()
                          if value is None and self.inputs.schema[name].required)
        if errors:
            raise ValueError("\n".join(map(str, errors)))
        return PreviewRequest(self.selected, self.effect_editor.value(), inputs,
                              led_count=count, brightness=brightness)


class _Gallery(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        content = QWidget(self)
        layout = QVBoxLayout(content)
        read_only = QCheckBox("Editoren schreibschützen", content)
        layout.addWidget(read_only)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        repeat = RepeatableContainer(
            lambda value, parent: QLineEdit(value, parent), lambda field: field.text(),
            lambda: "", content, maximum=4, values=("Erster Eintrag", "Zweiter Eintrag"),
        )
        self.builders = (
            ("Farbliste", ColorListEditor(content, value=["#00C066", "#FFC547", "#00C066"],
                                          minimum=1, maximum=5)),
            ("Farbverlauf", GradientEditor(content)),
            ("HSV-Farbbereich", ColorRangeEditor(content)),
            ("Zahlenbereich", RangeEditor(content, value=(0.125, 0.75), minimum=0,
                                           maximum=1, step=0.05, unit="ratio")),
            ("Winkel", AngleEditor(content, value=45.678901)),
            ("Wiederholbare Einträge", repeat),
        )
        for label, widget in self.builders:
            form.addRow(label, widget)
            read_only.toggled.connect(widget.set_read_only)
        ring = LedRingPreview(content, led_count=12, diameter=130)
        ring.set_value((0x00B790, 0x1369DF, None, 0xF88237) * 3)
        form.addRow("Ring mit RGB-Eingabeframe", ring)
        layout.addStretch()
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        wrapper = QVBoxLayout(self)
        wrapper.addWidget(scroll)


class TestLab(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LEFX Configurator · TestLab")
        self._catalogue = _LabCatalogue()
        self.destroyed.connect(lambda *_, catalogue=self._catalogue: catalogue.close())
        self._initial_palette = QApplication.palette()
        self._initial_style = QApplication.style().objectName()
        self._document = FeedbackDocument(SAMPLE)
        self.configurator = None

        main = QWidget(self)
        self.setCentralWidget(main)
        layout = QVBoxLayout(main)
        bar = QHBoxLayout()
        self.sources = QComboBox(main)
        self.sources.setAccessibleName("Katalogquellen")
        self.sources.addItems(["Core + Smartspeaker", "Nur Core", "Nur Smartspeaker", "Namenskollision (Demo)"])
        self.sources.activated.connect(self._change_sources)
        self.catalogue_status = _plain_label(main)
        bar.addWidget(self.sources)
        bar.addWidget(self.catalogue_status, 1)
        self.theme = QComboBox(main)
        self.theme.setAccessibleName("TestLab-Farbschema")
        self.theme.addItems(["System", "Hell", "Dunkel"])
        self.theme.currentIndexChanged.connect(self._theme)
        bar.addWidget(self.theme)
        layout.addLayout(bar)

        self.tabs = QTabWidget(main)
        layout.addWidget(self.tabs, 1)
        self.browser = _EffectBrowser(self._catalogue, self)
        self.tabs.addTab(self.browser, "Effekte und Presets")
        mapping = QWidget(self)
        self.mapping_layout = QVBoxLayout(mapping)
        toolbar = QHBoxLayout()
        self.show_stt = QCheckBox("Voice-STT-Beispiel", mapping)
        self.read_only = QCheckBox("Schreibgeschützt", mapping)
        self.show_stt.toggled.connect(self._switch_sample)
        self.read_only.toggled.connect(lambda state: self.configurator.set_read_only(state))
        toolbar.addWidget(self.show_stt)
        toolbar.addWidget(self.read_only)
        toolbar.addStretch()
        self.mapping_layout.addLayout(toolbar)
        self.tabs.addTab(mapping, "Ereigniszuordnung")
        self.gallery = _Gallery(self)
        self.tabs.addTab(self.gallery, "Widget-Galerie")
        self.exchange = QWidget(self)
        self._create_exchange()
        self.tabs.addTab(self.exchange, "Import / Export")
        self._sample = False
        self._drafts = {}
        self._install_document(self._document)
        self._catalogue_summary()
        self.resize(self.sizeHint().boundedTo(self.screen().availableGeometry().size() * 0.88))

    def _catalogue_summary(self):
        entries = self._catalogue.entries()
        preset_count = sum(entry.preset is not None for entry in entries)
        errors = [source["error"] for source in self._catalogue.adapter.sources() if source["error"]]
        self.catalogue_status.setText(f"{len(entries) - preset_count} Effekte · {preset_count} Presets")
        self.catalogue_status.setToolTip("\n".join(errors))

    def _change_sources(self, index):
        included = (
            ("core-set", "smartspeaker-set"), ("core-set",),
            ("smartspeaker-set",), ("core-set", "smartspeaker-set"),
        )[index]
        if self.browser.preview is not None:
            self.browser.preview.stop()
        self._catalogue.replace(included, collisions=index == 3)
        self.browser.refresh()
        self.configurator.refresh_catalogue()
        self._catalogue_summary()

    def _create_exchange(self):
        layout = QVBoxLayout(self.exchange)
        layout.addWidget(_plain_label(
            self.exchange, "JSON für feedback_mappings einfügen, aus einer Datei laden oder den Entwurf exportieren."
        ))
        self.json = QPlainTextEdit(self.exchange)
        self.json.setAccessibleName("Feedback-Daten als JSON")
        layout.addWidget(self.json, 1)
        self.message = _plain_label(self.exchange)
        layout.addWidget(self.message)
        import_actions = QHBoxLayout()
        _action(import_actions, self.exchange, "Datei öffnen…", self._open_json)
        _action(import_actions, self.exchange, "JSON als Entwurf importieren", self._import)
        layout.addLayout(import_actions)
        export_actions = QHBoxLayout()
        _action(export_actions, self.exchange, "Entwurf anzeigen", self._show_export)
        _action(export_actions, self.exchange, "JSON speichern…", self._save_json)
        layout.addLayout(export_actions)

    def _switch_sample(self, use_stt):
        if self.configurator is not None:
            self._drafts[self._sample] = (self._document, self.configurator.value())
        self._sample = use_stt
        document, rules = self._drafts.get(
            use_stt, (FeedbackDocument(STT_SAMPLE if use_stt else SAMPLE), None)
        )
        self._install_document(document, rules=rules)

    def _install_document(self, document, *, rules=None):
        present = document.led_rules()
        base = STT_EVENTS if self._sample else EVENTS
        known = {item.id for item in base}
        opaque = set(document.opaque_events())
        events = (
            *(item for item in base if item.id not in opaque),
            *(EventSpec(key, key, "Import") for key in present if key not in known),
        )
        if self.configurator is not None:
            self.mapping_layout.removeWidget(self.configurator)
            self.configurator.hide()
            self.configurator.deleteLater()
        self._document = document
        self.configurator = LedFeedbackConfigurator(
            events, self._catalogue, self, rules=present,
            capabilities=HostCapabilities.voice_stt() if self._sample else HostCapabilities(),
            preview_factory=self._catalogue.preview_factory, show_back=False,
            read_only=self.read_only.isChecked(),
        )
        self.configurator.applied.connect(self._applied)
        if rules is not None:
            self.configurator.set_draft(rules)
        self.mapping_layout.addWidget(self.configurator)
        self.json.setPlainText(dumps(document.with_led_rules(self.configurator.value()), indent=2, ensure_ascii=False))

    def _applied(self, snapshot):
        self._document = FeedbackDocument(self._document.with_led_rules(snapshot))
        self._show_export()

    def _import(self):
        try:
            data = loads(self.json.toPlainText())
            if not isinstance(data, dict):
                raise ValueError("Erwartet wird ein JSON-Objekt.")
            document = FeedbackDocument(data)
            if self.configurator.is_dirty() and not confirm(
                self, "Entwurf ersetzen", "Den aktuellen Entwurf durch die geladenen JSON-Daten ersetzen?"
            ):
                return
            self._install_document(document)
        except (TypeError, ValueError) as exc:
            self.message.setText(str(exc))
            return
        opaque = document.opaque_events()
        self.message.setText(
            f"JSON geladen. {len(opaque)} unbekannte Ereignisregeln bleiben unverändert."
            if opaque else "JSON geladen."
        )
        self.tabs.setCurrentIndex(1)

    def _show_export(self):
        try:
            self.json.setPlainText(dumps(self._document.with_led_rules(self.configurator.export()),
                                        indent=2, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError) as exc:
            self.message.setText(str(exc))
            return False
        self.message.setText("Export gültig.")
        return True

    def _open_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Feedback-Daten öffnen", filter="JSON (*.json)")
        if path:
            try:
                self.json.setPlainText(Path(path).read_text(encoding="utf-8"))
                self.message.setText("Datei geladen. Import prüft die Abschnittsstruktur.")
            except OSError as exc:
                self.message.setText(str(exc))

    def _save_json(self):
        if not self._show_export():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Feedback-Daten speichern", filter="JSON (*.json)")
        if path:
            try:
                Path(path).write_text(self.json.toPlainText() + "\n", encoding="utf-8")
                self.message.setText("Export gespeichert.")
            except OSError as exc:
                self.message.setText(str(exc))

    def _theme(self, choice):
        if not choice:
            QApplication.setStyle(self._initial_style)
            QApplication.setPalette(self._initial_palette)
            return
        QApplication.setStyle("Fusion")
        dark = choice == 2
        palette = QPalette()
        roles = QPalette.ColorRole
        text = "#f3f5f7" if dark else "#24282e"
        surface = "#24282e" if dark else "#f4f6f8"
        panel = "#343c46" if dark else "#e7edf4"
        for role, name in (
            (roles.Window, surface), (roles.WindowText, text),
            (roles.Base, "#171a20" if dark else "#ffffff"),
            (roles.AlternateBase, "#272d35" if dark else "#eef2f6"),
            (roles.Text, text), (roles.Button, panel), (roles.ButtonText, text),
            (roles.Highlight, "#29639c"), (roles.HighlightedText, "#ffffff"),
            (roles.Mid, "#63707d" if dark else "#a0afbf"),
            (roles.Midlight, "#434e5c" if dark else "#d4deea"),
            (roles.PlaceholderText, "#a4afbb" if dark else "#536173"),
            (roles.ToolTipBase, panel), (roles.ToolTipText, text),
        ):
            palette.setColor(QPalette.ColorGroup.Active, role, QColor(name))
            palette.setColor(QPalette.ColorGroup.Inactive, role, QColor(name))
        for role in (roles.WindowText, roles.Text, roles.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#96a1ac" if dark else "#6a7480"))
        QApplication.setPalette(palette)

    def closeEvent(self, event):
        if self.theme.currentIndex():
            self.theme.setCurrentIndex(0)
        super().closeEvent(event)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Open TestLab and exit after Qt paints it")
    options = parser.parse_args(argv)
    app = QApplication([])
    app.setApplicationName("lefx_configurator_widget")
    window = TestLab()
    window.show()
    if options.smoke:
        QTimer.singleShot(160, window.close)
    return app.exec()
