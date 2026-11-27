import os
from json import dumps, loads
from pathlib import Path
from runpy import run_path

import pytest

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QComboBox, QDialog, QLineEdit, QMessageBox, QPushButton,
)

from lefx.sdk import DefinitionKind, ParamDefinition, ParamType, StateSlot
from lefx.config_widget import (
    EffectCatalogueWidget, EffectEditor, EventSpec, HostCapabilities, LedCallEditor,
    LedFeedbackConfigurator, LedFeedbackDialog, LedVerb, ParameterForm,
)
from lefx.config_widget.testlab import STT_SAMPLE, TestLab as LabWindow
from lefx.config_widget.widgets import AngleEditor, ColorListEditor, GradientEditor


def button(widget, text):
    return next(item for item in widget.findChildren(QPushButton)
                if item.text() == text and not item.isHidden())


def named(widget, cls, label):
    return next(item for item in widget.findChildren(cls)
                if item.accessibleName() == label and not item.isHidden())


def choose_mode(row, mode):
    row.mode.setCurrentIndex(row.mode.findData(mode))


def type_text(field, value):
    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, value)


def capture(widget, file):
    destination = os.environ.get("LEFX_GUI_EVIDENCE")
    widget.repaint()
    QCoreApplication.processEvents()
    if destination:
        path = Path(destination) / file
        assert widget.grab().save(str(path))


def close_widget(widget):
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_catalogue_filter_and_keyboard(qapp, catalogue):
    view = EffectCatalogueWidget(catalogue, forms=(DefinitionKind.STATE, DefinitionKind.EVENT))
    view.show()
    spy = QSignalSpy(view.target_selected)
    view.kind_filter.setCurrentIndex(view.kind_filter.findData(False))
    type_text(view.search, "pulse_signal")
    assert view.results.count() == 1
    QTest.keyClick(view.search, Qt.Key.Key_Return)
    assert spy.count() == 1 and spy.at(0)[0] == "core-set::pulse_signal"
    type_text(view.search, "synchronverarbeitung")
    assert view.results.count() == 0
    view.search.clear()
    view.kind_filter.setCurrentIndex(view.kind_filter.findData(True))
    assert view.results.count() > 0
    assert all("Preset" in view.results.item(i).text() for i in range(view.results.count()))
    close_widget(view)


def test_schema_types_defaults_required_and_aliases(qapp):
    p = ParamDefinition
    t = ParamType
    schema = {param.name: param for param in (
        p("flag", t.BOOL, default=False),
        p("counter", t.INT, default=2, minimum=-10, unit="count"),
        p("speed", t.FLOAT, default=2.5, minimum=.01, unit="multiplier", aliases=("rate",)),
        p("duration_ms", t.DURATION_MS, default=800, minimum=1, maximum=4000),
        p("direction_deg", t.ANGLE_DEG, default=45.123456789, unit="deg"),
        p("choice", t.ENUM, default=3, enum_values=("smooth", 3, True)),
        p("color", t.COLOR, default=None, nullable=True),
        p("colors", t.COLOR_LIST, default=["#00FF00", "#00FF00"], minimum=2, maximum=4),
        p("gradient", t.GRADIENT, default=[{"at": 0, "color": "#000000"}, {"at": 1, "color": "#FFF000"}]),
        p("color_range", t.COLOR_RANGE, default={"hue": [0, 360], "saturation": [0, 1], "brightness": [0, 1]}),
        p("required_probe", t.FLOAT, required=True, nullable=True),
        p("optional_probe", t.INT),
    )}
    form = ParameterForm(schema, inherited={"flag": True}, values={"rate": 2, "color": None})
    form.show()
    assert {spec.type for spec in schema.values()} == set(t)
    assert form.value() == {"rate": 2, "color": None}
    assert form.rows["flag"].mode.currentText() == "Preset"
    assert form.rows["optional_probe"].notice.isVisible()
    assert str(form.validate()[0]).startswith("config.required_probe")
    choose_mode(form.rows["required_probe"], "override")
    type_text(named(form.rows["required_probe"], QLineEdit, "required_probe"), "1.23")
    choose_mode(form.rows["choice"], "override")
    choice = named(form.rows["choice"], QComboBox, "choice")
    choice.setFocus()
    QTest.keyClick(choice, Qt.Key.Key_End)
    assert form.value()["choice"] is True
    assert form.value()["color"] is None and not form.validate()
    assert form.rows["direction_deg"].findChild(AngleEditor).value() == 45.123456789
    assert form.rows["colors"].findChild(ColorListEditor).value() == ["#00FF00", "#00FF00"]
    assert not form.rows["gradient"].findChild(GradientEditor).error()
    form.set_value({"speed": 3.0, "rate": 1.5, "unknown": {"x": None}})
    assert form.rows["speed"].mode.isEnabled() is False
    assert form.value()["unknown"] == {"x": None}
    assert {error.field for error in form.validate()} == {"config.rate", "config.unknown"}
    close_widget(form)


def test_real_effect_editor_cancellation_and_override(qapp, catalogue):
    entry = next(item for item in catalogue.entries() if item.definition.id == "gradient_ring" and item.preset)
    editor = EffectEditor(entry, config={"brightness": 0.67})
    editor.show()
    row = editor.form.rows["gradient"]
    inherited = row.findChild(GradientEditor).value()
    assert editor.value() == {"brightness": .67} and not editor.validate()
    choose_mode(row, "override")
    gradient = row.findChildren(GradientEditor)[-1]
    composition = gradient.create_detail()
    composition.add_stop()
    assert gradient.value() == inherited
    assert gradient.commit_detail(composition)
    assert len(editor.value()["gradient"]) == len(inherited) + 1
    assert editor.resolved_config()["brightness"] == .67
    assert entry.resolve_config()["gradient"] == inherited
    choose_mode(row, "inherit")
    assert "gradient" not in editor.value() and not editor.validate()
    close_widget(editor)
    composition.deleteLater()


def test_call_slot_target_filters_and_confirmed_type_change(qapp, catalogue):
    event = EventSpec("app", "Anwendung", verbs=frozenset({LedVerb.SET_STATE, LedVerb.CLEAR_STATE}))
    editor = LedCallEditor(catalogue, value={"set_state": "ready_state", "config": {"speed": 2}},
                           event=event, capabilities=HostCapabilities(slots=(StateSlot.PRIMARY,)))
    editor.show()
    assert named(editor, QComboBox, "Slot").count() == 2
    assert editor.verb_combo.count() == 2
    button(editor, "Ziel auswählen…").click()
    assert editor.target_picker.results.count() > 0
    assert all(catalogue.resolve(editor.target_picker.results.item(i).data(Qt.ItemDataRole.UserRole)).form
               is DefinitionKind.STATE for i in range(editor.target_picker.results.count()))
    button(editor, "‹ Zurück zum Aufruf").click()
    assert editor.value()["set_state"] == "ready_state"

    def answer(result):
        modal = qapp.activeModalWidget()
        assert isinstance(modal, QMessageBox)
        modal.button(result).click()

    combo = editor.verb_combo
    QTimer.singleShot(20, lambda: answer(QMessageBox.StandardButton.No))
    combo.activated.emit(combo.findData("clear_state"))
    assert editor.value()["config"] == {"speed": 2}
    QTimer.singleShot(20, lambda: answer(QMessageBox.StandardButton.Yes))
    combo.activated.emit(combo.findData("clear_state"))
    assert editor.value() == {"clear_state": "primary"}
    assert not editor.validate()
    close_widget(editor)


def test_mapping_order_draft_validation_acceptance_and_opaque_rules(qapp, catalogue):
    events = [EventSpec("one", "Eins"), EventSpec("two", "Zwei"), EventSpec("future", "Neue Regel")]
    original = {"one": [{"clear_state": "primary"}, {"emit_event": "success_event"}],
                "two": None, "future": {"future_verb": {"unknown": True}},
                "other": "unsichtbar"}
    widget = LedFeedbackConfigurator(events, catalogue, rules=original)
    widget.show()
    spy = QSignalSpy(widget.applied)
    assert widget.export() == original and widget.warnings()
    widget.mapping.open_event("future")
    assert not widget.mapping.add.isEnabled() and not widget.mapping.remove.isEnabled()
    widget.mapping.open_event("one")
    widget.mapping.calls.setCurrentRow(1)
    widget.mapping.up.click()
    assert next(iter(widget.value()["one"][0])) == "emit_event"
    widget.mapping.edit_call()
    field = named(widget.mapping.call_editor, QLineEdit, "Priorität")
    type_text(field, "ungueltig")
    widget.request_back()
    assert widget.is_dirty() and widget.validate()
    assert not widget.apply() and spy.count() == 0
    widget.mapping.open_event("two")
    assert widget.value()["two"] is None
    widget.mapping.open_event("one")
    widget.mapping.edit_call()
    type_text(named(widget.mapping.call_editor, QLineEdit, "Priorität"), "-17")
    widget.mapping.commit_open_call()
    assert widget.apply() and spy.count() == 1
    snapshot = spy.at(0)[0]
    assert snapshot["one"][0]["priority"] == -17
    snapshot["one"].clear()
    assert len(widget.value()["one"]) == 2 and "priority" not in original["one"][1]
    widget.mapping.down.click()
    assert widget.is_dirty()
    widget.cancel()
    assert not widget.is_dirty() and widget.value()["one"][0]["priority"] == -17
    close_widget(widget)


def test_dialog_discard_and_accept(qapp, catalogue):
    rules = {"event": {"clear_state": "primary"}}
    dialog = LedFeedbackDialog([EventSpec("event", "Ereignis")], catalogue, rules=rules)
    dialog.show()
    dialog.configurator.mapping.open_event("event")
    dialog.configurator.mapping.edit_call()
    combo = named(dialog.configurator.mapping.call_editor, QComboBox, "Slot")
    combo.activated.emit(combo.findData("background"))
    dialog.reject()
    assert dialog.result_rules is None and dialog.configurator.value() == rules
    dialog.show()
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted and dialog.result_rules == rules
    close_widget(dialog)


def test_stacked_host_keeps_draft_until_explicit_action(qapp, catalogue):
    example = Path(__file__).resolve().parents[1] / "examples/stacked_host.py"
    host_type = run_path(str(example))["SettingsHost"]
    host = host_type(catalogue)
    host.show()
    button(host.currentWidget(), "LED-Effekte konfigurieren").click()
    widget = host.configurator
    assert host.currentWidget() is widget
    mapping = widget.mapping
    mapping.open_event("sync.done")
    mapping.edit_call()
    type_text(named(mapping.call_editor, QLineEdit, "Priorität"), "21")
    widget.back_button.click()
    assert host.currentWidget() is not widget
    assert widget.value()["sync.done"]["priority"] == 21
    assert "priority" not in host.saved_rules["sync.done"]
    button(host.currentWidget(), "LED-Effekte konfigurieren").click()
    assert widget.is_dirty() and widget.apply()
    assert host.saved_rules["sync.done"]["priority"] == 21
    close_widget(host)


def test_add_remove_and_discard_one_call(qapp, catalogue):
    event = EventSpec("close", "Schließen", verbs=frozenset({LedVerb.CLEAR_STATE}))
    view = LedFeedbackConfigurator([event], catalogue)
    view.show()
    mapping = view.mapping
    mapping.open_event("close")
    mapping.add.click()
    assert mapping.call_editor.value() == {"clear_state": "primary"}
    button(mapping.stack.currentWidget(), "Aufrufänderungen verwerfen").click()
    assert view.value() == {}
    mapping.add.click()
    button(mapping.stack.currentWidget(), "Aufruf übernehmen").click()
    assert view.value() == {"close": {"clear_state": "primary"}}
    view.apply()

    def confirm_removal():
        modal = qapp.activeModalWidget()
        yes = modal.button(QMessageBox.StandardButton.Yes)
        yes.click()

    QTimer.singleShot(20, confirm_removal)
    mapping.remove.click()
    assert view.value() == {"close": []}
    view.cancel()
    assert view.value() == {"close": {"clear_state": "primary"}}
    close_widget(view)


@pytest.mark.parametrize("open_call", [False, True])
@pytest.mark.parametrize("load", ["set_value", "set_draft"])
def test_host_load_is_silent_and_preserves_apply_cancel(qapp, catalogue, open_call, load):
    initial = {"e": {"emit_event": "success_event"}}
    loaded = {"e": {"emit_event": "success_event", "priority": 4}}
    widget = LedFeedbackConfigurator([EventSpec("e", "Ereignis")], catalogue, rules=initial)
    widget.show()
    if open_call:
        widget.mapping.open_event("e")
        widget.mapping.edit_call()
    draft = QSignalSpy(widget.draft_changed)
    mapping_draft = QSignalSpy(widget.mapping.draft_changed)
    applied = QSignalSpy(widget.applied)
    cancelled = QSignalSpy(widget.cancelled)

    getattr(widget, load)(loaded)
    assert draft.count() == mapping_draft.count() == applied.count() == cancelled.count() == 0
    assert widget.mapping.call_editor is None and widget.value() == loaded
    assert widget.is_dirty() is (load == "set_draft")
    loaded["e"]["priority"] = 99
    assert widget.value()["e"]["priority"] == 4

    widget.cancel()
    assert widget.value()["e"].get("priority") == (None if load == "set_draft" else 4)
    assert cancelled.count() == 1 and applied.count() == 0
    widget.mapping.open_event("e")
    widget.mapping.edit_call()
    notifications = draft.count()
    type_text(named(widget.mapping.call_editor, QLineEdit, "Priorität"), "7")
    assert draft.count() > notifications and widget.is_dirty()
    assert widget.apply()
    assert applied.count() == 1 and cancelled.count() == 1
    assert widget.value()["e"]["priority"] == 7 and not widget.is_dirty()
    applied.at(0)[0]["e"]["priority"] = 42
    assert widget.value()["e"]["priority"] == 7

    widget.mapping.open_event("e")
    widget.mapping.edit_call()
    type_text(named(widget.mapping.call_editor, QLineEdit, "Priorität"), "8")
    notifications = draft.count()
    widget.cancel()
    assert draft.count() == notifications + 1
    assert applied.count() == 1 and cancelled.count() == 2
    assert widget.mapping.call_editor is None and widget.value()["e"]["priority"] == 7
    close_widget(widget)


def test_testlab_import_export_keeps_non_led_fields(qapp):
    window = LabWindow()
    window.show()
    window.tabs.setCurrentIndex(3)
    payload = {
        "schema_version": 2,
        "events": {"test.alarm": {"led": {"emit_event": "pulse_signal"},
                                  "sound": {"cue": "complete"}, "app": {"action": "indicator.success"}}},
    }
    window.json.setPlainText(dumps(payload))
    button(window.exchange, "JSON als Entwurf importieren").click()
    assert window.tabs.currentIndex() == 1
    window.tabs.setCurrentIndex(3)
    button(window.exchange, "Entwurf anzeigen").click()
    assert loads(window.json.toPlainText()) == payload
    assert "gültig" in window.message.text()
    close_widget(window)


def test_testlab_desktop_workflow(qapp):
    window = LabWindow()
    window.resize(960, 720)
    window.show()
    window.theme.setCurrentIndex(1)
    light = qapp.palette().window().color()
    assert light.lightness() > 200
    QTest.qWait(60)
    print(f"QPA={qapp.platformName()} wide={window.width()}x{window.height()}")
    browser = window.browser
    type_text(browser.picker.search, "solid_fill")
    QTest.keyClick(browser.picker.search, Qt.Key.Key_Return)
    browser.preview.start_button.click()
    for _ in range(100):
        if browser.preview.ring.value()[0] is not None:
            break
        QTest.qWait(15)
    assert all(color is not None for color in browser.preview.ring.value())
    assert len({color.name() for color in browser.preview.ring.value()}) == 1
    capture(window, "01-katalog-und-preview.png")
    worker = browser.preview._worker
    window.tabs.setCurrentIndex(1)
    assert not browser.preview._poll.isActive() and not browser.preview._debounce.isActive()
    assert worker.wait(2)
    window.resize(680, 540)
    QTest.qWait(40)
    print(f"compact={window.width()}x{window.height()} keyboard=search+Enter+Tab")
    assert window.width() <= 710 and window.height() <= 570
    mapping = window.configurator.mapping
    mapping.open_event("task.finished")
    assert mapping.calls.count() == 2
    capture(window, "02-ereignis-aufreihenfolge.png")
    window.read_only.click()
    assert not mapping.remove.isEnabled()
    window.read_only.click()
    saved = window.configurator.value()
    pending = {**saved, "task.pending": {"clear_state": "primary"}}
    window.configurator.set_draft(pending)
    window.show_stt.click()
    assert window._document.with_led_rules(window.configurator.export()) == STT_SAMPLE
    window.sources.activated.emit(1)
    assert window.configurator.validate()
    window.sources.activated.emit(0)
    assert not window.configurator.validate()
    window.show_stt.click()
    assert window.configurator.value() == pending and window.configurator.is_dirty()
    window.configurator.cancel()
    assert window.configurator.value() == saved
    window.sources.activated.emit(3)
    assert any("Mehrdeutiges Ziel" in issue.message for issue in window.configurator.validate())
    window.sources.activated.emit(0)
    window.tabs.setCurrentIndex(2)
    window.theme.setCurrentIndex(2)
    gallery = window.gallery
    gradient = gallery.findChild(GradientEditor)
    gradient.open_detail()
    modal = gradient.findChild(QDialog)
    QTest.qWait(30)
    capture(modal, "03-gradient-dunkel.png")
    detail = modal.findChild(GradientEditor)
    detail.add_stop()
    draft = gradient.value()
    modal.reject()
    assert gradient.value() == draft
    capture(window, "04-galerie-dunkel.png")
    assert qapp.palette().window().color().lightness() < 80
    window.tabs.setCurrentIndex(0)
    browser.open_target("level_meter")
    assert "progress" in str(browser.inputs.validate()[0])
    browser.preview.start_button.click()
    assert "inputs.progress" in browser.preview.state.text()
    capture(window, "05-fehlende-testwerte.png")
    editable = browser.inputs.rows["progress"]
    choose_mode(editable, "override")
    field = named(editable, QLineEdit, "progress")
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_Tab)
    assert qapp.focusWidget() is not field
    type_text(field, "75")
    assert not browser.inputs.validate()
    browser.preview.start_button.click()
    for _ in range(100):
        if browser.preview.ring.value()[0] is not None:
            break
        QTest.qWait(15)
    assert any(color is not None and color.name() != "#000000" for color in browser.preview.ring.value())
    window.theme.setCurrentIndex(0)
    close_widget(window)
    print("Desktop geprüft: echte Frames, Preset-/Quellenauswahl, Mapping, Read-only, kompakte Größe, "
          "STT-Roundtrip, Mehrdeutigkeit, Hell und Dunkel, Gradienten-Abbruch und fehlende Testwerte.")
