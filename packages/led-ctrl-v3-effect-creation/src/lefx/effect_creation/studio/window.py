"""The workbench: browse on the left, tune in the middle, watch on the right.

The layout is the workflow. You find a definition, you change its parameters,
and you see what that did — in that order, left to right, with nothing to click
between the change and the result.

Two decisions are worth stating, because both could reasonably have gone the
other way:

* **Live by default.** Every change is applied immediately for the forms where
  that means something. Tuning a colour by pressing Apply after each nudge is
  not tuning. Events are the exception and always will be: emitting one thirty
  times a second because a slider moved would be a different effect than the one
  under test.
* **The frames come from the device path.** The monitor draws what the sink was
  handed, not a private re-render. A preview that renders separately agrees with
  the device right up until the moment it does not, which is the moment you
  would be relying on it.

Frames arrive on the service's render thread. They cross into the GUI thread
through a signal, which is the only safe way to touch a widget from elsewhere.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from lefx.sdk import DefinitionKind

from . import catalogue
from .calibration_page import CalibrationPage
from .parameters import SchemaForm
from .preset_dialog import PresetDialog
from .project import Project, iter_paths, remember
from .ring import RingMonitor
from .source_editor import SourceEditorPage
from .session import NULL_OUTPUT, STUDIO_CHANNEL, StudioSession, available_outputs, device_in_use

logger = logging.getLogger("lefx.effect_creation.studio.window")

KIND_FILTERS: list[tuple[str, DefinitionKind | None]] = [
    ("Alle", None),
    ("States", DefinitionKind.STATE),
    ("Controlled Overlays", DefinitionKind.CONTROLLED_OVERLAY),
    ("Timed Overlays", DefinitionKind.TIMED_OVERLAY),
    ("Events", DefinitionKind.EVENT),
]


class StudioWindow(QMainWindow):
    """One window, one session, one effect being looked at."""

    frame_received = Signal(tuple)

    def __init__(self, session: StudioSession, *, initial_output: str = NULL_OUTPUT) -> None:
        super().__init__()
        self.session = session
        self.entries: list[catalogue.Entry] = []
        self.selected: catalogue.Entry | None = None
        self.config_form: SchemaForm | None = None
        self.inputs_form: SchemaForm | None = None
        self._applying = False

        self.setWindowTitle("LEFX Studio")
        self.resize(1280, 760)
        self._build()

        # Queued by Qt because it is emitted from the render thread. Both
        # monitors watch the same frames; whichever page is in front is showing
        # what the device is being sent, not a rendering of its own.
        self.frame_received.connect(self.monitor.set_colors)
        self.frame_received.connect(self.calibration.monitor.set_colors)
        self.frame_received.connect(self.editor.monitor.set_colors)
        self.session.set_frame_listener(self.frame_received.emit)

        self._select_output(initial_output)

    # -- construction -------------------------------------------------------

    def _build(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_browser())
        splitter.addWidget(self._build_editor())
        splitter.addWidget(self._build_monitor())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)

        self.calibration = CalibrationPage(self.session)
        self.editor = SourceEditorPage(self.session)

        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, "Player")
        self.tabs.addTab(self.calibration, "Kalibrierung")
        self.tabs.addTab(self.editor, "Neuer Effekt")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self.setStatusBar(QStatusBar())
        self._build_menu()

    def _on_tab_changed(self, index: int) -> None:
        # The calibration page needs to know which device it is measuring, and
        # the output can have changed since it was last looked at.
        page = self.tabs.widget(index)
        if page is self.calibration:
            self.calibration.refresh()
        elif page is self.editor:
            self.editor.refresh()

    def _build_menu(self) -> None:
        project_menu = self.menuBar().addMenu("&Projekt")
        open_action = QAction("Projekt öffnen …", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._choose_project)
        project_menu.addAction(open_action)
        where_action = QAction("Pfade zeigen", self)
        where_action.triggered.connect(self._show_paths)
        project_menu.addAction(where_action)

        catalogue_menu = self.menuBar().addMenu("&Katalog")
        reload_action = QAction("Quellen neu laden", self)
        reload_action.setShortcut("F5")
        reload_action.triggered.connect(self._reload_sources)
        catalogue_menu.addAction(reload_action)
        build_action = QAction("Katalog bauen", self)
        build_action.setShortcut("Ctrl+B")
        build_action.setToolTip("Jede Quelle packen und die Sets neu bauen")
        build_action.triggered.connect(self._build_catalogue)
        catalogue_menu.addAction(build_action)

        output_menu = self.menuBar().addMenu("&Ausgabe")
        clear_action = QAction("Alles löschen", self)
        clear_action.triggered.connect(self._clear_everything)
        output_menu.addAction(clear_action)

    # -- the project --------------------------------------------------------

    def _choose_project(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        current = self.session.project
        chosen = QFileDialog.getExistingDirectory(
            self, "Projektverzeichnis wählen", str(current.root if current else "")
        )
        if chosen:
            self.use_project(Project.at(chosen))

    def use_project(self, project: Project) -> None:
        """Point the whole window at another checkout.

        Everything derived from the root moves at once — where effects are read
        from, where a calibration is kept, where a new source is offered. A
        studio that changed only some of those would be editing one project and
        writing into another.
        """
        self.session.use(project)
        remember(project)
        self.setWindowTitle(f"LEFX Studio — {project.label}")
        self._reload_sources()
        self.calibration.refresh()
        self.editor.refresh()
        if not project.looks_like_a_project:
            self.statusBar().showMessage(
                f"{project.root} enthält noch keinen Katalog — „Neuer Effekt“ legt den ersten an.",
                12000,
            )

    def _show_paths(self) -> None:
        project = self.session.project
        if project is None:
            return
        lines = "\n".join(f"{label}: {path}" for label, path in iter_paths(project))
        QMessageBox.information(self, "Projektpfade", lines)

    def _build_catalogue(self) -> None:
        """Build every set in the project, without needing a terminal.

        The standalone build has no ``scripts/`` to shell out to, and a tool
        that can write a source should be able to build it.
        """
        project = self.session.project
        if project is None:
            return
        try:
            results = project.build_catalogue()
        except Exception as exc:
            QMessageBox.critical(self, "Build fehlgeschlagen", str(exc))
            return
        if not results:
            QMessageBox.information(
                self, "Nichts zu bauen", f"Keine Effekt-Sets unter {project.catalogue_root}."
            )
            return
        summary = "\n".join(
            f"{item['set_id']}: {item['effect_count']} Definitionen" for item in results
        )
        self._reload_sources()
        QMessageBox.information(self, "Katalog gebaut", summary)

    def _build_browser(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen: Id, Titel, Beschreibung, Quelle, Tag")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh_list)

        self.kind_filter = QComboBox()
        for label, _ in KIND_FILTERS:
            self.kind_filter.addItem(label)
        self.kind_filter.currentIndexChanged.connect(self._refresh_list)

        self.source_filter = QComboBox()
        self.source_filter.addItem("Alle Quellen")
        self.source_filter.currentIndexChanged.connect(self._refresh_list)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_selected)

        layout.addWidget(self.search)
        filters = QHBoxLayout()
        filters.addWidget(self.kind_filter, stretch=1)
        filters.addWidget(self.source_filter, stretch=1)
        layout.addLayout(filters)
        layout.addWidget(self.list, stretch=1)
        return panel

    def _build_editor(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.headline = QLabel("Nichts ausgewählt")
        self.headline.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.subline = QLabel("")
        self.subline.setWordWrap(True)
        self.subline.setStyleSheet("color: #888;")
        layout.addWidget(self.headline)
        layout.addWidget(self.subline)

        self.preset_row = QHBoxLayout()
        self.preset_row.addWidget(QLabel("Preset"))
        self.preset_box = QComboBox()
        self.preset_box.currentIndexChanged.connect(self._on_preset_chosen)
        self.preset_row.addWidget(self.preset_box, stretch=1)
        layout.addLayout(self.preset_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.form_host = QWidget()
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.form_host)
        layout.addWidget(self.scroll, stretch=1)

        actions = QHBoxLayout()
        self.live_box = QCheckBox("Live")
        self.live_box.setChecked(True)
        self.live_box.setToolTip("Jede Änderung sofort anwenden (nie für Events)")
        self.preset_button = QPushButton("Als Preset sichern …")
        self.preset_button.setToolTip(
            "Die aktuellen Werte benennen und in die Quelle des Effekts schreiben"
        )
        self.preset_button.clicked.connect(self._curate_preset)
        self.play_button = QPushButton("Abspielen")
        self.play_button.clicked.connect(self._apply)
        self.stop_button = QPushButton("Beenden")
        self.stop_button.clicked.connect(self._stop_current)
        actions.addWidget(self.live_box)
        actions.addStretch(1)
        actions.addWidget(self.preset_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.play_button)
        layout.addLayout(actions)
        return panel

    def _build_monitor(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        output_box = QGroupBox("Ausgabe")
        output_layout = QVBoxLayout(output_box)
        self.output_box = QComboBox()
        for name in available_outputs():
            self.output_box.addItem(name)
        self.output_box.currentTextChanged.connect(self._select_output)
        output_layout.addWidget(self.output_box)

        self.output_state = QLabel("—")
        self.output_state.setWordWrap(True)
        output_layout.addWidget(self.output_state)
        layout.addWidget(output_box)

        self.monitor = RingMonitor(self.session.led_count)
        layout.addWidget(self.monitor, stretch=1)

        view = QHBoxLayout()
        indices = QCheckBox("Indizes")
        indices.setChecked(True)
        indices.toggled.connect(self.monitor.set_show_indices)
        sectors = QCheckBox("15°-Sektoren")
        sectors.toggled.connect(self.monitor.set_show_sectors)
        view.addWidget(indices)
        view.addWidget(sectors)
        view.addStretch(1)
        layout.addLayout(view)

        global_box = QGroupBox("Global")
        global_layout = QHBoxLayout(global_box)
        global_layout.addWidget(QLabel("Helligkeit"))
        self.brightness = QDoubleSpinBox()
        self.brightness.setRange(0.0, 1.0)
        self.brightness.setSingleStep(0.05)
        self.brightness.setValue(1.0)
        self.brightness.valueChanged.connect(
            lambda value: self._guarded(lambda: self.session.set_output(brightness=float(value)))
        )
        self.enabled = QCheckBox("an")
        self.enabled.setChecked(True)
        self.enabled.toggled.connect(
            lambda value: self._guarded(lambda: self.session.set_output(enabled=bool(value)))
        )
        global_layout.addWidget(self.brightness)
        global_layout.addWidget(self.enabled)
        layout.addWidget(global_box)
        return panel

    # -- the output ---------------------------------------------------------

    def _select_output(self, name: str) -> None:
        if not name:
            return
        if name != NULL_OUTPUT:
            busy = device_in_use()
            if busy is not None:
                QMessageBox.warning(
                    self,
                    "Gerät ist belegt",
                    f"{busy}.\n\nNur ein Prozess kann ein Gerät halten. Beende den Dienst, "
                    "oder wähle eine andere Ausgabe.",
                )
                self._set_output_box(self.session.output_name)
                return
        try:
            self.session.open(name)
        except Exception as exc:
            logger.exception("could not open %s", name)
            QMessageBox.critical(self, "Ausgabe nicht verfügbar", f"{name}: {exc}")
            self._set_output_box(NULL_OUTPUT)
            self.session.open(NULL_OUTPUT)

        self.monitor.set_led_count(self.session.led_count)
        self._reload_sources()
        self._refresh_output_state()
        self.calibration.refresh()
        self.editor.refresh()

    def _set_output_box(self, name: str) -> None:
        self.output_box.blockSignals(True)
        index = self.output_box.findText(name)
        if index >= 0:
            self.output_box.setCurrentIndex(index)
        self.output_box.blockSignals(False)

    def _refresh_output_state(self) -> None:
        status = self.session.sink_status()
        if status.available:
            self.output_state.setText(f"✓ {self.session.output_name}")
            self.output_state.setStyleSheet("color: #4c9;")
        else:
            self.output_state.setText(f"✗ {self.session.output_name}: {status.detail or 'nicht verfügbar'}")
            self.output_state.setStyleSheet("color: #d76;")

    # -- the catalogue ------------------------------------------------------

    def _reload_sources(self) -> None:
        if self.session.service is None:
            return
        try:
            self.session.reload_sources()
        except Exception as exc:
            logger.warning("reloading sources failed: %s", exc)
        registry = self.session.registry
        self.entries = catalogue.entries(registry.list_effects())

        current = self.source_filter.currentText()
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("Alle Quellen")
        for source_id in registry.source_ids():
            self.source_filter.addItem(source_id)
        restored = self.source_filter.findText(current)
        self.source_filter.setCurrentIndex(max(0, restored))
        self.source_filter.blockSignals(False)

        self._refresh_list()
        self.statusBar().showMessage(
            f"{len(self.entries)} Definitionen, {len(registry.list_presets())} Presets", 4000
        )

    def _refresh_list(self) -> None:
        kind = KIND_FILTERS[max(0, self.kind_filter.currentIndex())][1]
        source = self.source_filter.currentText()
        shown = catalogue.filtered(
            self.entries,
            query=self.search.text(),
            kind=kind,
            source_id=None if self.source_filter.currentIndex() <= 0 else source,
        )

        keep = self.selected.effect_id if self.selected is not None else None
        self.list.blockSignals(True)
        self.list.clear()
        for entry in shown:
            item = QListWidgetItem(f"{entry.title}\n{entry.kind_label} · {entry.effect.source_id}")
            item.setData(Qt.ItemDataRole.UserRole, entry.effect_id)
            self.list.addItem(item)
        self.list.blockSignals(False)

        if keep is not None:
            for row in range(self.list.count()):
                if self.list.item(row).data(Qt.ItemDataRole.UserRole) == keep:
                    self.list.setCurrentRow(row)
                    return
        if self.list.count():
            self.list.setCurrentRow(0)

    # -- selection and editing ---------------------------------------------

    def _on_selected(self, item: QListWidgetItem | None, _previous=None) -> None:
        if item is None:
            return
        effect_id = item.data(Qt.ItemDataRole.UserRole)
        entry = next((one for one in self.entries if one.effect_id == effect_id), None)
        if entry is None:
            return
        self.selected = entry
        self._rebuild_forms(entry)

    def _rebuild_forms(self, entry: catalogue.Entry) -> None:
        definition = entry.definition
        playback = catalogue.playback_for(definition)
        provider = catalogue.pulls_a_provider(definition)

        self.headline.setText(f"{entry.title}  ·  {entry.effect_id}")
        notes = [entry.kind_label, f"Quelle: {entry.effect.source_id}"]
        if provider:
            notes.append(f"liest Capability „{provider}“ vom Gerät")
        if definition.description:
            notes.append(definition.description)
        self.subline.setText("  ·  ".join(notes))

        while self.form_layout.count():
            widget = self.form_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.config_form = SchemaForm(definition.parameter_schema, on_change=self._on_edited)
        config_box = QGroupBox("Parameter")
        QVBoxLayout(config_box).addWidget(self.config_form)
        self.form_layout.addWidget(config_box)

        self.inputs_form = None
        schema = getattr(definition, "runtime_input_schema", {}) or {}
        if schema and provider is None:
            # Pushed inputs: nothing supplies them, so the studio does.
            self.inputs_form = SchemaForm(schema, on_change=self._on_edited)
            inputs_box = QGroupBox("Runtime-Eingaben")
            QVBoxLayout(inputs_box).addWidget(self.inputs_form)
            self.form_layout.addWidget(inputs_box)
        elif schema:
            # Pulled inputs: the device supplies them and the studio must not
            # pretend to. Showing editable fields here would produce values that
            # the next sample overwrites, which reads as the controls not working.
            note = QLabel(
                f"Die Werte liefert das Gerät über die Capability „{provider}“.\n"
                "Ausgabe umschalten, um gegen ein anderes Gerät zu prüfen."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #888; padding: 6px;")
            self.form_layout.addWidget(note)

        self.config_form.set_values(catalogue.starting_config(definition))
        if self.inputs_form is not None:
            self.inputs_form.set_values(catalogue.starting_inputs(definition))

        self._rebuild_presets(entry)
        self.play_button.setText("Auslösen" if not playback.repeatable else "Abspielen")
        self.stop_button.setEnabled(playback.verb != "event")
        if playback.repeatable and self.live_box.isChecked():
            self._apply()

    def _rebuild_presets(self, entry: catalogue.Entry) -> None:
        presets = self.session.registry.list_presets(effect_id=entry.effect_id)
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        self.preset_box.addItem("— keins —", None)
        for preset in presets:
            self.preset_box.addItem(preset.title or preset.preset_id, preset.preset_id)
        self.preset_box.blockSignals(False)
        self.preset_box.setEnabled(bool(presets))

    def _on_preset_chosen(self, index: int) -> None:
        if self.selected is None or self.config_form is None or index <= 0:
            return
        preset_id = self.preset_box.currentData()
        preset = next(
            (
                one
                for one in self.session.registry.list_presets(effect_id=self.selected.effect_id)
                if one.preset_id == preset_id
            ),
            None,
        )
        self.config_form.set_values(
            catalogue.starting_config(self.selected.definition, preset)
        )
        self._on_edited()

    def _curate_preset(self) -> None:
        """Keep what is on screen, in the place a build will find it again.

        Written into the *source*, not into the loaded package: a preset that
        lived only in the running catalogue would last until the next build.
        Afterwards the sources are reloaded, so the new preset appears in the
        list it will be chosen from from now on.
        """
        if self.selected is None or self.config_form is None:
            return
        project = self.session.project
        dialog = PresetDialog(
            self.selected.definition,
            self.config_form.values(),
            self,
            source_roots=project.source_roots if project else None,
        )
        if dialog.exec() != PresetDialog.DialogCode.Accepted:
            return

        self.statusBar().showMessage(f"Preset in {dialog.written} geschrieben", 8000)
        QMessageBox.information(
            self,
            "Preset gesichert",
            f"Geschrieben nach:\n{dialog.written}\n\n"
            "Es steckt jetzt in der Quelle. Nach dem nächsten "
            "'scripts/build_effects.py' ist es auch im gebauten Set.",
        )

    def _on_edited(self) -> None:
        if not self.live_box.isChecked() or self.selected is None:
            return
        if not catalogue.playback_for(self.selected.definition).repeatable:
            return
        self._apply()

    # -- driving the engine -------------------------------------------------

    def _apply(self) -> None:
        if self.selected is None or self.config_form is None or self.session.service is None:
            return
        if self._applying:
            return
        self._applying = True
        try:
            definition = self.selected.definition
            playback = catalogue.playback_for(definition)
            config = self.config_form.values()
            inputs = self.inputs_form.values() if self.inputs_form is not None else {}

            if playback.verb == "state":
                self.session.play_state(definition.id, config)
            elif playback.verb == "overlay":
                self.session.play_overlay(
                    definition.id,
                    config,
                    inputs,
                    channel=STUDIO_CHANNEL if playback.needs_channel else None,
                )
            else:
                self.session.emit(definition.id, config)
            self.statusBar().showMessage(f"{definition.id} angewendet", 2000)
        except Exception as exc:
            # A rejected value is ordinary while editing — half a colour name is
            # not a colour yet. It belongs in the status bar, not in a dialog
            # that has to be dismissed before the next keystroke.
            self.statusBar().showMessage(str(exc), 6000)
        finally:
            self._applying = False
            self._refresh_output_state()

    def _stop_current(self) -> None:
        if self.selected is None:
            return
        playback = catalogue.playback_for(self.selected.definition)
        self._guarded(
            self.session.clear_overlay
            if playback.verb == "overlay"
            else lambda: self.session.service.clear_state()
        )

    def _clear_everything(self) -> None:
        self._guarded(self.session.clear_everything)

    def _guarded(self, action) -> Any:
        if self.session.service is None:
            return None
        try:
            return action()
        except Exception as exc:
            self.statusBar().showMessage(str(exc), 6000)
            return None

    # -- shutdown -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt's spelling
        """Let go of the device on the way out.

        The studio holds a USB endpoint or a socket while it runs, and a window
        that closed without releasing it would leave the next thing to start
        unable to find its device with nothing on screen to explain why.
        """
        self.session.set_frame_listener(None)
        # Before the session goes: a calibration run holds the device's own
        # calibration aside while it measures, and it has to be given back.
        self.calibration.close()
        self.session.close()
        super().closeEvent(event)


__all__ = ["KIND_FILTERS", "StudioWindow"]
