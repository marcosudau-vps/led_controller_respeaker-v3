"""The Studio Lab tab: tree, preview, inspector, timeline — one document.

The editor (:class:`lefx.effect_creation.visual.Editor`) owns the document.
Everything on this page is a view of it and is refreshed from it when it
changes; every edit goes back through it. The tree and inspector do not keep
state of their own, so they cannot drift from what will be saved or exported.

Frames come from the compiled design and nowhere else. A document change
compiles the snapshots the current view needs, once; playing, scrubbing and
stepping then only call ``render`` on them for whatever moment the
:class:`~.clock.PreviewClock` names.

The page is quiet while it is not the visible tab: no timer runs, and nothing is
sent to the output, so the Player and the calibration have the device to
themselves.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lefx.effect_creation.visual import Editor, new_document
from lefx.effect_creation.visual.blocks import BLOCKS, DesignError
from lefx.effect_creation.visual.compiler import export_package, verify_package
from lefx.effect_creation.visual.model import validate
from lefx.effect_creation.visual import persistence, steps
from lefx.effect_creation.visual.preview import COMPOSITE, FOCUS, ISOLATED, VIEWS, PreviewCompiler, PreviewPlan

from ..ring import RingMonitor
from ..session import StudioSession, available_outputs
from . import examples
from .clock import PreviewClock
from .inspector import Inspector, locate
from .output import LabOutput
from .timeline import Timeline
from .tree import DesignTree

logger = logging.getLogger("lefx.effect_creation.studio.lab.page")

TICK_MS = 16
UNIFORM = "uniform"
DESIGN_FILTER = "LEFX-Studio-Entwurf (*.lefx-design.json);;JSON (*.json)"
OPEN_FILTER = "Entwürfe und Pakete (*.json *.lefx);;LEFX-Studio-Entwurf (*.lefx-design.json);;LEFX-Paket (*.lefx)"
PALETTE = ("#3399FF", "#FF5533", "#33DD77", "#FFCC33", "#CC55FF", "#33DDDD", "#FF77AA")


def guarded(method: Callable) -> Callable:
    """A slot that reports a rejected edit instead of letting it escape into Qt."""

    @functools.wraps(method)
    def wrapper(self: "LabPage", *args: Any, **kwargs: Any) -> Any:
        try:
            return method(self, *args, **kwargs)
        except DesignError as exc:
            self.report(str(exc), error=True)
            self._refresh_views()
        except Exception as exc:  # the GUI must survive anything an edit can do
            logger.exception("Studio Lab action failed")
            self.report(f"{type(exc).__name__}: {exc}", error=True)
        return None

    return wrapper


def content_key(document: dict) -> str:
    """The document's identity without its revision counter, for "unsaved"."""
    return persistence.digest({**document, "revision": 0})


class LabPage(QWidget):
    def __init__(
        self,
        session: StudioSession,
        parent: QWidget | None = None,
        *,
        choose_output: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.choose_output = choose_output
        self.compiler = PreviewCompiler()
        self.clock = PreviewClock()
        self.output = LabOutput(session)
        self.path: Path | None = None
        self.editor: Editor | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._document: dict = new_document()
        self._saved_key: str | None = None
        self._selected: str | None = None
        self._view = COMPOSITE
        self._led_count = session.led_count
        self._plan: PreviewPlan | None = None
        self._transient: PreviewPlan | None = None
        self.frame = None
        self._step_plans: dict[str, steps.StepPlan] = {}
        self._step_key = UNIFORM
        self._step_summary = ""
        self._marks: list[float] = []
        self._active = False
        self.ask_before_discarding = True

        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        # The device can come and go while the Lab sends; say so within a second.
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_output_state)
        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(lambda: self.message.setText(""))

        self._build()
        self._adopt(Editor(), path=None)

    # -- construction -------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = DesignTree()
        self.tree.selected.connect(self._on_selected)
        self.tree.requested.connect(self._on_requested)
        splitter.addWidget(self.tree)
        splitter.addWidget(self._build_preview())
        self.inspector = Inspector()
        self.inspector.committed.connect(self._on_committed)
        self.inspector.previewed.connect(self._on_previewed)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.inspector)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([300, 420, 380])
        layout.addWidget(splitter, stretch=1)

        self.timeline = Timeline()
        self.timeline.play_toggled.connect(self.toggle_play)
        self.timeline.stopped.connect(self.stop)
        self.timeline.seeked.connect(self.seek)
        self.timeline.range_changed.connect(self._on_range)
        self.timeline.speed_changed.connect(self.clock.set_speed)
        self.timeline.loop_changed.connect(lambda loop: setattr(self.clock, "loop", loop))
        self.timeline.stepped.connect(self.step)
        self.timeline.plan_changed.connect(self._on_plan_chosen)
        self.timeline.sampling_changed.connect(lambda _: self._rebuild_steps())
        self.timeline.samples_per_cycle.valueChanged.connect(lambda _: self._rebuild_steps())
        self.timeline.set_range(self.clock.start, self.clock.end)
        layout.addWidget(self.timeline)

        self.message = QLabel("")
        self.message.setMinimumHeight(18)
        layout.addWidget(self.message)
        self._build_shortcuts()

    def _build_toolbar(self) -> QToolBar:
        bar = QToolBar()
        self.new_action = self._action(bar, "Neu", self.new_design, "Ctrl+N")
        self.open_action = self._action(bar, "Öffnen …", self.open_design, "Ctrl+Shift+O")
        self.save_action = self._action(bar, "Speichern", self.save, QKeySequence.StandardKey.Save)
        self.save_as_action = self._action(bar, "Speichern unter …", self.save_as, "Ctrl+Shift+S")
        self.export_action = self._action(bar, "Als .lefx exportieren …", self.export, "Ctrl+E")
        bar.addSeparator()
        self.undo_action = self._action(bar, "↶ Rückgängig", self.undo, QKeySequence.StandardKey.Undo)
        self.redo_action = self._action(bar, "↷ Wiederholen", self.redo, None)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        bar.addSeparator()
        examples_button = QToolButton()
        examples_button.setText("Beispiele")
        examples_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(examples_button)
        for key, (title, _) in examples.EXAMPLES.items():
            menu.addAction(title, lambda k=key: self.load_example(k))
        examples_button.setMenu(menu)
        bar.addWidget(examples_button)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: 600; padding-right: 6px;")
        bar.addWidget(self.title)
        return bar

    def _action(self, bar: QToolBar, text: str, slot: Callable, shortcut) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        # Only while this tab is in front; the window's own menu keeps its keys.
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(slot)
        bar.addAction(action)
        self.addAction(action)
        return action

    def _build_preview(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 0, 4, 0)

        views = QHBoxLayout()
        self.view_buttons = QButtonGroup(self)
        for key in (COMPOSITE, ISOLATED, FOCUS):
            button = QToolButton()
            button.setText(VIEWS[key])
            button.setCheckable(True)
            button.setChecked(key == COMPOSITE)
            button.setProperty("view", key)
            self.view_buttons.addButton(button)
            views.addWidget(button)
        self.view_buttons.buttonClicked.connect(lambda button: self.set_view(button.property("view")))
        views.addStretch(1)
        layout.addLayout(views)

        self.ring = RingMonitor(self._led_count)
        layout.addWidget(self.ring, stretch=1)

        self.view_note = QLabel("")
        self.view_note.setWordWrap(True)
        self.view_note.setStyleSheet("color: #9ab;")
        layout.addWidget(self.view_note)
        legend = QLabel("● Farbe: gerendert   ● Schwarz: deckend schwarz   ◌ gestrichelt: "
                        "keine Ebene trägt bei (transparent; bei deckender Komposition sendet "
                        "das Gerät dort Schwarz)")
        legend.setWordWrap(True)
        legend.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(legend)

        options = QHBoxLayout()
        options.addWidget(QLabel("LEDs"))
        self.led_count_box = QSpinBox()
        self.led_count_box.setRange(1, 64)
        self.led_count_box.setValue(self._led_count)
        self.led_count_box.setToolTip("Ringgröße der Vorschau. Nicht Teil des Entwurfs; an das "
                                      "Gerät wird nur gesendet, wenn sie zur Ausgabe passt.")
        self.led_count_box.valueChanged.connect(self.set_led_count)
        options.addWidget(self.led_count_box)
        self.coverage_box = QCheckBox("Unbedeckte Positionen zeigen")
        self.coverage_box.setChecked(True)
        self.coverage_box.setToolTip("Zeigt Positionen, zu denen keine Ebene beiträgt, als ◌ statt "
                                     "als das Schwarz, das ein deckender Effekt dort ausgibt.")
        self.coverage_box.toggled.connect(lambda _: self._document_view_changed())
        options.addWidget(self.coverage_box)
        indices = QCheckBox("Indizes")
        indices.setChecked(True)
        indices.toggled.connect(self.ring.set_show_indices)
        options.addWidget(indices)
        options.addStretch(1)
        layout.addLayout(options)

        layout.addWidget(self._build_output())
        return panel

    def _build_output(self) -> QGroupBox:
        box = QGroupBox("Ausgabe")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.output_box = QComboBox()
        self.output_box.setToolTip("Dieselbe Ausgabe wie im Player; ein Wechsel gilt für das ganze Studio")
        self.output_box.currentTextChanged.connect(self._on_output_chosen)
        self.send_box = QCheckBox("An Ausgabe senden")
        self.send_box.setToolTip("Die Lab-Vorschau zusätzlich auf dem gewählten Gerät zeigen. "
                                 "Übernimmt dabei die Ausgabe vom Player.")
        self.send_box.toggled.connect(self._on_send_toggled)
        self.ring_source = QComboBox()
        self.ring_source.addItem("Ring zeigt Entwurf", False)
        self.ring_source.addItem("Ring zeigt Gerätesignal", True)
        self.ring_source.setToolTip("Gerätesignal: genau die Werte, die an das Gerät gehen, "
                                    "einschließlich globaler Helligkeit")
        self.ring_source.currentIndexChanged.connect(lambda _: self._render_now())
        row.addWidget(self.output_box, stretch=1)
        row.addWidget(self.send_box)
        row.addWidget(self.ring_source)
        layout.addLayout(row)
        self.output_state = QLabel("Nur Softwarevorschau")
        self.output_state.setWordWrap(True)
        layout.addWidget(self.output_state)
        self._sync_outputs()
        return box

    def _build_shortcuts(self) -> None:
        def shortcut(keys: str, slot: Callable, owner: QWidget | None = None) -> None:
            action = QAction(self)
            action.setShortcut(QKeySequence(keys))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(slot)
            (owner or self).addAction(action)

        shortcut("Space", self.toggle_play)
        shortcut(",", lambda: self.step(-1))
        shortcut(".", lambda: self.step(1))
        shortcut("Ctrl+L", lambda: self._on_requested("add_layer", {}))
        shortcut("Ctrl+D", lambda: self.tree.request_current("duplicate"))
        # Only in the tree: Delete in a field of the inspector must edit text.
        shortcut("Delete", lambda: self.tree.request_current("remove"), self.tree.tree)
        shortcut("F2", self.tree.rename_current, self.tree.tree)

    # -- the document -------------------------------------------------------

    def _adopt(self, editor: Editor, *, path: Path | None, saved: bool = True) -> None:
        """Start working on ``editor``'s document, with a fresh history."""
        if self._unsubscribe is not None:
            self._unsubscribe()
        self.editor = editor
        self._unsubscribe = editor.subscribe(self._on_document)
        self.path = path
        self._saved_key = content_key(editor.document) if saved else None
        self._selected = None
        self._on_document(editor.document)

    @property
    def document(self) -> dict:
        return self._document

    @property
    def dirty(self) -> bool:
        return content_key(self._document) != self._saved_key

    def _on_document(self, document: dict) -> None:
        self._document = document
        if self._selected is not None and locate(document, self._selected)[0] is None:
            self._selected = None
        self._transient = None
        self._document_view_changed()

    def _document_view_changed(self) -> None:
        self._rebuild_plan()
        self._refresh_views()
        self._rebuild_steps()
        self._render_now()

    def _focus_layer(self) -> str | None:
        item, kind = locate(self._document, self._selected)
        if kind == "layer":
            return item["id"]
        if kind == "animation":
            return item["target"]
        if item is None:
            return None
        for layer in self._document["layers"]:
            if _contains(layer["children"], item["id"]):
                return layer["id"]
        return None

    def _make_plan(self, document: dict) -> PreviewPlan:
        return PreviewPlan(self.compiler, document, self._view, self._focus_layer(),
                           reveal_coverage=self.coverage_box.isChecked())

    def _rebuild_plan(self) -> None:
        try:
            self._plan = self._make_plan(self._document)
        except Exception as exc:
            # The last good plan keeps rendering; the problem is said, not hidden.
            logger.exception("compiling the preview failed")
            self.report(f"Vorschau nicht aktualisiert: {exc}", error=True)
            return
        layer = next((item for item in self._document["layers"] if item["id"] == self._plan.layer), None)
        if self._view != COMPOSITE and layer is None:
            note = "Keine Ebene ausgewählt — es wird der Gesamteffekt gezeigt."
        elif self._view == ISOLATED:
            note = f"Isoliert: Ebene „{layer['name']}“" + ("" if layer["enabled"] else
                                                          " (im Gesamteffekt ausgeblendet)")
        elif self._view == FOCUS:
            note = (f"Hervorgehoben: Ebene „{layer['name']}“; die übrigen Ebenen nur zur "
                    "Orientierung abgedunkelt (reine Anzeige)")
        elif not self._document["layers"]:
            note = "Noch keine Ebene — „+ Ebene“ anlegen oder ein Beispiel laden."
        else:
            note = "Gesamteffekt: alle sichtbaren Ebenen zusammengesetzt"
        self.view_note.setText(note)

    def _refresh_views(self) -> None:
        self.tree.show_document(self._document, self._selected, self._led_count)
        self.inspector.show_object(self._document, self._selected, self._led_count)
        self.undo_action.setEnabled(self.editor is not None and self.editor.can_undo)
        self.redo_action.setEnabled(self.editor is not None and self.editor.can_redo)
        name = self.path.name if self.path is not None else "Unbenannter Entwurf"
        self.title.setText(f"{name}{'  •  ungespeichert' if self.dirty else ''}")

    # -- edits --------------------------------------------------------------

    @guarded
    def _on_selected(self, target: str | None) -> None:
        self._selected = target
        self.inspector.show_problem(None)
        self.inspector.show_object(self._document, target, self._led_count)
        item, kind = locate(self._document, target)
        if kind == "animation" and target in self._step_plans:
            self._step_key = target
            self._rebuild_steps()
        if self._view != COMPOSITE:
            self._rebuild_plan()
        self._render_now()

    def select(self, target: str | None) -> None:
        self._selected = target
        self.tree.select(target)
        self._on_selected(target)

    @guarded
    def _on_requested(self, name: str, args: dict) -> None:
        editor = self.editor
        target = args.get("target")
        if name == "add_layer":
            self.select(editor.add_layer(self._unique_layer_name()))
        elif name == "add_element":
            parent = self._selected if self.tree.current_kind() == "group" else self._ensure_layer()
            count = sum(1 for _ in _elements(self._document))
            block = BLOCKS[args["type"]]
            extra = {"color": PALETTE[count % len(PALETTE)]} if "color" in block.properties else {}
            self.select(editor.add_element(parent, args["type"], **extra))
        elif name == "add_animation":
            layer = self._ensure_layer()
            bound = {item["type"] for item in self._document["animations"] if item["target"] == layer}
            if args["type"] in bound:
                raise DesignError(f"„{BLOCKS[args['type']].label}“ ist an dieser Ebene schon gebunden; "
                                  "pro Ebene ist jeder Animationstyp nur einmal zulässig.")
            self.select(editor.add_animation(layer, args["type"]))
        elif name == "duplicate":
            self.select(editor.duplicate(target))
        elif name == "remove":
            parent = self._parent_of(target)
            editor.remove(target)
            self.select(parent)
        elif name in ("raise", "lower"):
            self._move(target, 1 if name == "raise" else -1)
        elif name == "rename":
            editor.rename(target, args["name"].strip())
        elif name == "visible":
            editor.configure_layer(target, enabled=args["enabled"])

    def _unique_layer_name(self) -> str:
        names = {layer["name"] for layer in self._document["layers"]}
        number = len(self._document["layers"]) + 1
        while f"Ebene {number}" in names:
            number += 1
        return f"Ebene {number}"

    def _ensure_layer(self) -> str:
        layer = self._focus_layer()
        if layer is None and self._document["layers"]:
            layer = self._document["layers"][-1]["id"]
        if layer is None:
            layer = self.editor.add_layer(self._unique_layer_name())
            self.report("Neue Ebene angelegt, weil noch keine vorhanden war.")
        return layer

    def _parent_of(self, target: str) -> str | None:
        item, kind = locate(self._document, target)
        if kind == "animation":
            return item["target"]
        if kind == "layer":
            return None
        for layer in self._document["layers"]:
            found = _parent_in(layer, target)
            if found is not None:
                return found
        return None

    def _move(self, target: str, delta: int) -> None:
        item, kind = locate(self._document, target)
        if kind == "layer":
            ids = [layer["id"] for layer in self._document["layers"]]
            index = ids.index(target) + delta
            if not 0 <= index < len(ids):
                self.report("Die Ebene liegt bereits " + ("ganz oben." if delta > 0 else "ganz unten."))
                return
            self.editor.move(target, None, index)
        elif kind in ("element", "group"):
            parent = self._parent_of(target)
            container, _ = locate(self._document, parent)
            ids = [child["id"] for child in container["children"]]
            index = ids.index(target) + delta
            if not 0 <= index < len(ids):
                self.report("Das Element liegt bereits " + ("ganz oben." if delta > 0 else "ganz unten."))
                return
            self.editor.move(target, parent, index)
        else:
            raise DesignError("Animationen haben keine Reihenfolge; sie wirken alle auf ihre Ebene.")

    @guarded
    def _on_committed(self, target: str | None, field: str, value: Any) -> None:
        self._transient = None
        try:
            if field.startswith("effect."):
                self.editor.metadata(**{field.split(".", 1)[1]: value})
            elif field == "@name":
                self.editor.rename(target, str(value).strip())
            elif field == "@enabled":
                self.editor.configure_layer(target, enabled=bool(value))
            elif field == "@blend":
                self.editor.configure_layer(target, blend=value)
            else:
                self.editor.set_property(target, field, value)
        except DesignError as exc:
            self.inspector.show_problem(str(exc))
            self.inspector.show_object(self._document, self._selected, self._led_count)
            self.report(str(exc), error=True)
            self._render_now()
            return
        self.inspector.show_problem(None)
        self._render_now()

    @guarded
    def _on_previewed(self, target: str | None, field: str, value: Any) -> None:
        """Show a value while it is still being chosen, without committing it."""
        if target is None or field.startswith("@"):
            return
        candidate = self.editor.document
        item, _ = locate(candidate, target)
        if item is None:
            return
        item["properties"][field] = value
        try:
            self._transient = self._make_plan(validate(candidate))
        except DesignError as exc:
            self.inspector.show_problem(str(exc))
            return
        self.inspector.show_problem(None)
        self._render_now()

    @guarded
    def undo(self) -> None:
        self.editor.undo()

    @guarded
    def redo(self) -> None:
        self.editor.redo()

    # -- the preview --------------------------------------------------------

    def set_view(self, view: str) -> None:
        self._view = view
        for button in self.view_buttons.buttons():
            button.setChecked(button.property("view") == view)
        self._rebuild_plan()
        self._render_now()

    def set_led_count(self, count: int) -> None:
        self._led_count = int(count)
        self.ring.set_led_count(self._led_count)
        if self.led_count_box.value() != self._led_count:
            self.led_count_box.setValue(self._led_count)
        if self.output.active and self.output.problem(self._led_count):
            self.output.stop()
            self.send_box.blockSignals(True)
            self.send_box.setChecked(False)
            self.send_box.blockSignals(False)
        self._refresh_views()
        self._rebuild_steps()
        self._refresh_output_state()
        self._render_now()

    def _render_now(self) -> None:
        plan = self._transient or self._plan
        if plan is None:
            return
        elapsed = self.clock.elapsed()
        try:
            frame = plan.frame(elapsed, self._led_count)
        except Exception as exc:
            logger.exception("rendering the preview failed")
            self.report(f"Vorschau-Fehler bei {elapsed:.3f} s: {exc}", error=True)
            return
        self.frame = frame
        if not (self.ring_source.currentData() and self.output.active):
            self.ring.set_colors(frame.colors)
        self.timeline.set_time(elapsed)
        self._update_step_info(elapsed)
        if self._active and self.output.active:
            try:
                self.output.push(frame.device)
            except Exception as exc:
                logger.exception("sending to the output failed")
                self.output.stop()
                self._set_send_box(False)
                self.report(f"Ausgabe beendet: {exc}", error=True)
            if not self.output.active:
                self._set_send_box(False)
                self._refresh_output_state()

    def on_device_frame(self, colors: tuple) -> None:
        """A frame off the device path (window signal); shown only if asked."""
        if self._active and self.output.active and self.ring_source.currentData():
            self.ring.set_colors(colors)

    # -- time ---------------------------------------------------------------

    def toggle_play(self) -> None:
        self.clock.toggle()
        self._sync_timer()
        self._render_now()

    def play(self) -> None:
        self.clock.play()
        self._sync_timer()

    def pause(self) -> None:
        self.clock.pause()
        self._sync_timer()
        self._render_now()

    def stop(self) -> None:
        self.clock.stop()
        self._sync_timer()
        self._render_now()

    def seek(self, position: float) -> None:
        self.clock.seek(position)
        self._render_now()

    def _sync_timer(self) -> None:
        running = self.clock.playing and self._active
        if running and not self.timer.isActive():
            self.timer.start()
        elif not running and self.timer.isActive():
            self.timer.stop()
        self.timeline.set_playing(self.clock.playing)

    def _tick(self) -> None:
        self._render_now()
        if not self.clock.playing:  # reached the end without looping
            self._sync_timer()

    def _on_range(self, span: float) -> None:
        self.clock.set_range(0.0, span)
        self.timeline.set_range(self.clock.start, self.clock.end)
        self._rebuild_steps()
        self._render_now()

    # -- steps --------------------------------------------------------------

    def _rebuild_steps(self) -> None:
        self._step_plans = steps.plans(self._document, self._led_count,
                                       self.timeline.samples_per_cycle.value())
        if self._step_key != UNIFORM and self._step_key not in self._step_plans:
            self._step_key = UNIFORM
        choices = [(UNIFORM, "Gleichmäßige Abtastpunkte")]
        choices += [(key, plan.title) for key, plan in self._step_plans.items()]
        self.timeline.set_plans(choices, self._step_key)
        self.timeline.set_sampling_mode(self._step_key == UNIFORM)
        plan = self.step_plan()
        self._step_summary = ""
        if plan.cyclic and self._plan is not None:
            try:
                count = steps.distinct_frames(lambda t: self._plan.frame(t, self._led_count).colors, plan)
                kind = "Schritte" if plan.natural else "Abtastpunkte"
                self._step_summary = (f"Zyklus: {plan.per_cycle} {kind} bei {self._led_count} LEDs, "
                                      f"{count} verschiedene Bilder")
            except Exception:
                logger.exception("counting distinct frames failed")
        marks = []
        if plan.period > 0:
            first = plan.after(self.clock.start - 1e-6)
            index = first
            while len(marks) < 2000:
                moment = plan.time(index)
                if moment > self.clock.end:
                    break
                marks.append(moment)
                index += 1
        self._marks = marks
        self._update_step_info(self.clock.elapsed())

    def step_plan(self) -> steps.StepPlan:
        if self._step_key == UNIFORM:
            return steps.uniform(self.timeline.sampling.value())
        return self._step_plans[self._step_key]

    def _on_plan_chosen(self, key: str) -> None:
        self._step_key = key or UNIFORM
        self._rebuild_steps()

    @guarded
    def step(self, delta: int) -> None:
        """Pause and go to the next or previous step point of the chosen plan."""
        self.clock.pause()
        self._sync_timer()
        plan = self.step_plan()
        now = self.clock.elapsed()
        index = plan.after(now) if delta > 0 else plan.before(now)
        moment = plan.time(index)
        if moment < self.clock.start - 1e-9 or moment > self.clock.end + 1e-9:
            self.report("Kein weiterer Schritt im Vorschauzeitraum.")
            return
        self.clock.seek(moment)
        self._render_now()

    def _update_step_info(self, elapsed: float) -> None:
        plan = self.step_plan()
        index = plan.nearest(elapsed)
        at_point = abs(plan.time(index) - elapsed) < 1e-6
        where = plan.label(index) if at_point else f"zwischen Punkten (nächster: {plan.label(index)})"
        text = where if not self._step_summary else f"{where}   ·   {self._step_summary}"
        if not plan.natural:
            text += "   ·   Abtastpunkte sind Zeitpunkte, keine Zustände"
        self.timeline.step_info.setText(text)
        self.timeline.ruler.set_marks(self._marks, plan.time(index) if at_point else None)

    # -- files --------------------------------------------------------------

    def confirm_discard(self) -> bool:
        """True when the current design may be replaced or the window closed."""
        if not self.dirty or not self.ask_before_discarding:
            return True
        answer = QMessageBox.question(
            self, "Ungespeicherter Entwurf",
            "Der Studio-Lab-Entwurf hat ungespeicherte Änderungen. Speichern?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def new_design(self) -> None:
        if self.confirm_discard():
            self._adopt(Editor(), path=None)
            self.report("Neuer, leerer Entwurf.")

    def load_example(self, key: str) -> None:
        if not self.confirm_discard():
            return
        title, build = examples.EXAMPLES[key]
        self._adopt(Editor(build()), path=None, saved=False)
        self.report(f"Beispiel geladen: {title}")

    def _directory(self) -> str:
        if self.path is not None:
            return str(self.path.parent)
        project = self.session.project
        return str(project.root) if project is not None else ""

    def open_design(self) -> None:
        if not self.confirm_discard():
            return
        chosen, _ = QFileDialog.getOpenFileName(self, "Entwurf öffnen", self._directory(), OPEN_FILTER)
        if chosen:
            self.open_path(Path(chosen))

    @guarded
    def open_path(self, path: Path) -> None:
        document = persistence.load(path)
        # A design read out of a package is a copy; saving goes to a new file.
        own = path.suffix.lower() != ".lefx"
        self._adopt(Editor(document), path=path if own else None)
        self.report(f"Geöffnet: {path}")

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        return self.save_to(self.path)

    def save_as(self) -> bool:
        default = str(Path(self._directory()) / f"{self._document['effect']['id']}.lefx-design.json")
        chosen, _ = QFileDialog.getSaveFileName(self, "Entwurf speichern", default, DESIGN_FILTER)
        if not chosen:
            return False
        return self.save_to(Path(chosen))

    def save_to(self, path: Path) -> bool:
        try:
            written = persistence.save(self._document, path)
        except (DesignError, OSError) as exc:
            self.report(f"Speichern fehlgeschlagen: {exc}", error=True)
            return False
        self.path = Path(written)
        self._saved_key = content_key(self._document)
        self._refresh_views()
        self.report(f"Gespeichert: {written}")
        return True

    def export(self) -> None:
        default = str(Path(self._directory()) / f"{self._document['effect']['id']}.lefx")
        chosen, _ = QFileDialog.getSaveFileName(self, "Als LEFX-Paket exportieren", default,
                                                "LEFX-Paket (*.lefx)")
        if chosen:
            self.export_to(Path(chosen))

    @guarded
    def export_to(self, path: Path) -> dict:
        report = export_package(self._document, path)
        check = verify_package(report["path"], self._document, led_count=self._led_count)
        if check["mismatches"]:
            self.report(f"Exportiert nach {report['path']}, aber {len(check['mismatches'])} von "
                        f"{check['compared']} Zeitpunkten weichen von der Vorschau ab!", error=True)
        else:
            self.report(f"Exportiert und geprüft: {report['path']} — der LEFX-Loader akzeptiert das "
                        f"Paket, {check['compared']} Zeitpunkte stimmen mit der Vorschau überein.")
        return {**report, "check": check}

    # -- output -------------------------------------------------------------

    def _sync_outputs(self) -> None:
        self.output_box.blockSignals(True)
        self.output_box.clear()
        for name in available_outputs():
            self.output_box.addItem(name)
        index = self.output_box.findText(self.session.output_name)
        self.output_box.setCurrentIndex(max(0, index))
        self.output_box.blockSignals(False)

    def _on_output_chosen(self, name: str) -> None:
        if not name or name == self.session.output_name:
            return
        if self.choose_output is not None:
            # The window owns the device choice, its busy check and its fallback.
            self.choose_output(name)
        self.refresh()

    def _on_send_toggled(self, on: bool) -> None:
        if on and self._active:
            self._start_output()
        elif not on:
            self.output.stop()
        self._refresh_output_state()
        self._render_now()

    def _start_output(self) -> None:
        if self.frame is None:
            return
        try:
            self.output.start(self.frame.device)
        except Exception as exc:
            self._set_send_box(False)
            self.report(f"Ausgabe nicht möglich: {exc}", error=True)
        self._refresh_output_state()

    def _set_send_box(self, on: bool) -> None:
        self.send_box.blockSignals(True)
        self.send_box.setChecked(on)
        self.send_box.blockSignals(False)

    def _refresh_output_state(self) -> None:
        problem = self.output.problem(self._led_count)
        if self.output.active:
            kind = "Gerät" if self.output.is_hardware else "ohne Hardware"
            text, color = f"Sendet an „{self.output.target}“ ({kind}). Player-Wiedergabe ist beendet.", "#4c9"
        elif problem and self.send_box.isChecked():
            text, color = problem, "#d76"
        elif self.send_box.isChecked():
            text, color = "Wird gesendet, sobald der Lab-Tab sichtbar ist.", "#9ab"
        else:
            status = self.session.sink_status()
            state = "bereit" if status.available else (status.detail or "nicht verfügbar")
            text, color = f"Nur Softwarevorschau · Ausgabe „{self.output.target}“: {state}", "#888"
            if problem:
                text += f" · {problem}"
        self.output_state.setText(text)
        self.output_state.setStyleSheet(f"color: {color};")

    # -- lifecycle ----------------------------------------------------------

    def refresh(self) -> None:
        """The window's output may have changed: follow it."""
        self._sync_outputs()
        if self._active and self.send_box.isChecked():
            self._start_output()
        self._refresh_output_state()

    def activate(self) -> None:
        """The tab came to the front."""
        self._active = True
        self._status_timer.start()
        self.refresh()
        self._sync_timer()
        self._render_now()

    def deactivate(self) -> None:
        """The tab went to the back: no timer, no output, the device is free."""
        self._active = False
        self._status_timer.stop()
        if self.clock.playing:
            self.clock.pause()
        self._sync_timer()
        self.output.stop()
        self._refresh_output_state()

    def shutdown(self) -> None:
        self.deactivate()
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    # -- messages -----------------------------------------------------------

    def report(self, text: str, *, error: bool = False) -> None:
        self.message.setText(text)
        self.message.setStyleSheet(f"color: {'#e07a5f' if error else '#8ab'};")
        self._message_timer.start(9000 if error else 5000)


def _contains(children: list[dict], target: str) -> bool:
    return any(child["id"] == target or (child.get("type") == "group" and _contains(child["children"], target))
               for child in children)


def _parent_in(container: dict, target: str) -> str | None:
    for child in container["children"]:
        if child["id"] == target:
            return container["id"]
        if child.get("type") == "group":
            found = _parent_in(child, target)
            if found is not None:
                return found
    return None


def _elements(document: dict):
    def visit(children):
        for child in children:
            if child.get("type") == "group":
                yield from visit(child["children"])
            else:
                yield child
    for layer in document["layers"]:
        yield from visit(layer["children"])


__all__ = ["LabPage", "content_key"]
