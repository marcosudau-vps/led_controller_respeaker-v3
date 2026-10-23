"""The Studio Lab tab, driven through its widgets without anyone looking.

The five flows of the brief — a simple project, an animated layer, several
layers, edit/undo/save/load, export — are each walked through here with the
page's own buttons, menus, fields and ruler, against the real window and the
real compiled preview. Qt offscreen; no hardware.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6", reason="the studio window needs Qt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lefx.effect_creation.visual import persistence  # noqa: E402
from lefx.effect_creation.visual.compiler import compile_design  # noqa: E402
from lefx.effect_creation.studio.lab.output import FEED_ID  # noqa: E402
from lefx.effect_creation.studio.session import StudioSession  # noqa: E402
from lefx.effect_creation.studio.window import StudioWindow  # noqa: E402

RED, BLUE = 0xFF0000, 0x0000FF


class FakeTime:
    def __init__(self) -> None:
        self.now = 50.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qt_app, tmp_path):
    session = StudioSession(search_paths=[], state_file=tmp_path / "background.json")
    window = StudioWindow(session)
    window.lab.ask_before_discarding = False
    window.tabs.setCurrentWidget(window.lab)
    qt_app.processEvents()
    try:
        yield window
    finally:
        window.close()
        session.close()


@pytest.fixture
def lab(window):
    page = window.lab
    page.clock._now = FakeTime()
    return page


def choose(menu, label: str) -> None:
    menu.aboutToShow.emit()
    action = next(action for action in menu.actions() if action.text().startswith(label))
    assert action.isEnabled(), f"{label} is disabled"
    action.trigger()


def segment(lab, *, leds: int, color: str) -> str:
    choose(lab.tree.element_menu, "Segment")
    target = lab.tree.current_id()
    lab.inspector.field("length").leds.setValue(leds)
    field = lab.inspector.field("color")
    field.text.setText(color)
    field.text.editingFinished.emit()
    return target


def preview_at(lab, moment: float) -> tuple:
    """What the stored design renders at ``moment`` — the export's answer."""
    return tuple(compile_design(lab.document).render(moment, lab.ring.led_count))


# -- the tab ----------------------------------------------------------------


def test_the_lab_is_one_more_tab_and_the_old_ones_stay(window):
    labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert labels == ["Player", "Kalibrierung", "Neuer Effekt", "Studio Lab (experimentell)"]


# -- flow A: a simple project -----------------------------------------------


def test_flow_a_layer_segment_properties_and_the_ring(lab):
    lab.new_design()
    lab.tree.add_layer_button.click()
    segment(lab, leds=5, color="#FF0000")

    document = lab.document
    assert len(document["layers"]) == 1
    properties = document["layers"][0]["children"][0]["properties"]
    assert properties["length"] == pytest.approx(5 / 12) and properties["color"] == "#FF0000"
    # Five LEDs lit from the top; the rest uncovered, shown as transparent.
    assert lab.ring.colors == (RED,) * 5 + (None,) * 7
    lab.coverage_box.setChecked(False)
    assert lab.ring.colors == (RED,) * 5 + (0,) * 7


# -- flow B: an animated layer ----------------------------------------------


def test_flow_b_rotation_play_pause_and_seek(lab):
    lab.tree.add_layer_button.click()
    segment(lab, leds=5, color="#FF0000")
    choose(lab.tree.animation_menu, "Rotation")
    lab.inspector.field("rate").spin.setValue(0.5)
    assert lab.document["animations"][0]["properties"]["rate"] == 0.5

    lab.timeline.play_button.click()
    assert lab.timer.isActive() and lab.clock.playing
    lab.clock._now.now += 1.0
    lab._tick()
    assert lab.frame.elapsed == pytest.approx(1.0)
    assert lab.ring.colors[6:11] == (RED,) * 5  # half a turn on

    lab.timeline.play_button.click()
    assert not lab.timer.isActive()
    lab.clock._now.now += 3.0
    lab._tick()
    assert lab.frame.elapsed == pytest.approx(1.0)  # paused means paused

    ruler = lab.timeline.ruler
    QTest.mouseClick(ruler, Qt.MouseButton.LeftButton, pos=QPoint(ruler.width() // 4, 20))
    moment = ruler.time_at(ruler.width() // 4)
    assert lab.clock.elapsed() == pytest.approx(moment)
    assert tuple(lab.frame.device) == preview_at(lab, moment)

    # A parameter change shows at once, at the same moment.
    lab.inspector.field("reverse").box.setChecked(True)
    assert lab.document["animations"][0]["properties"]["reverse"] is True
    assert tuple(lab.frame.device) == preview_at(lab, moment)


def test_a_second_animation_of_the_same_type_is_refused_without_a_crash(lab):
    lab.tree.add_layer_button.click()
    choose(lab.tree.animation_menu, "Rotation")
    before = lab.document
    lab.tree.animation_menu.aboutToShow.emit()
    rotation = next(a for a in lab.tree.animation_menu.actions() if a.text().startswith("Rotation"))
    assert not rotation.isEnabled() and "vorhanden" in rotation.text()
    lab.tree.requested.emit("add_animation", {"type": "rotation"})
    assert lab.document == before
    assert "nur einmal" in lab.message.text()


# -- flow C: several layers -------------------------------------------------


def test_flow_c_two_layers_order_visibility_and_views(lab, qt_app):
    lab.tree.add_layer_button.click()
    first_layer = lab.tree.current_id()
    segment(lab, leds=5, color="#FF0000")
    choose(lab.tree.animation_menu, "Rotation")
    lab.tree.add_layer_button.click()
    second_layer = lab.tree.current_id()
    segment(lab, leds=3, color="#0000FF")
    choose(lab.tree.animation_menu, "Rotation")
    lab.inspector.field("reverse").box.setChecked(True)

    # Both segments start at LED 0: the upper layer wins there.
    assert lab.ring.colors[0] == BLUE
    lab.select(second_layer)
    lab.tree.lower_button.click()
    assert [layer["id"] for layer in lab.document["layers"]] == [second_layer, first_layer]
    assert lab.ring.colors[0] == RED

    # Hiding the upper layer through its tree checkbox.
    lab.select(first_layer)
    item = lab.tree.tree.currentItem()
    item.setCheckState(0, Qt.CheckState.Unchecked)
    qt_app.processEvents()
    assert next(layer for layer in lab.document["layers"] if layer["id"] == first_layer)["enabled"] is False
    assert lab.ring.colors[0] == BLUE

    # Isolated view of the hidden layer shows it alone; the design is unchanged.
    before = lab.document
    button = next(b for b in lab.view_buttons.buttons() if b.property("view") == "isolated")
    button.click()
    assert lab.ring.colors[:5] == (RED,) * 5 and lab.ring.colors[5:] == (None,) * 7
    assert "ausgeblendet" in lab.view_note.text()
    assert lab.document == before
    lab.set_view("composite")
    assert lab.ring.colors[0] == BLUE


# -- flow D: edit, undo, redo, save, load -----------------------------------


def test_flow_d_undo_redo_save_and_load(lab, tmp_path):
    lab.tree.add_layer_button.click()
    target = segment(lab, leds=5, color="#FF0000")
    lab.inspector.field("color").text.setText("#00FF00")
    lab.inspector.field("color").text.editingFinished.emit()
    lab.undo_action.trigger()
    assert lab.document["layers"][0]["children"][0]["properties"]["color"] == "#FF0000"
    lab.redo_action.trigger()
    assert lab.document["layers"][0]["children"][0]["properties"]["color"] == "#00FF00"

    assert lab.dirty
    path = tmp_path / "entwurf.lefx-design.json"
    assert lab.save_to(path)
    assert not lab.dirty and "entwurf" in lab.title.text()
    saved = lab.document

    lab.new_design()
    assert lab.document["layers"] == []
    lab.open_path(path)
    assert lab.document == saved
    lab.select(target)
    assert lab.inspector.field("color").text.text() == "#00FF00"


# -- flow E: export ---------------------------------------------------------


def test_flow_e_export_validate_reload_and_compare(lab, tmp_path):
    lab.load_example("counter_rotation")
    report = lab.export_to(tmp_path / "gegenlaeufig.lefx")
    assert report["ok"] and report["check"]["mismatches"] == []
    assert "geprüft" in lab.message.text()
    exported = lab.document

    lab.new_design()
    lab.open_path(tmp_path / "gegenlaeufig.lefx")
    assert lab.document == exported
    assert lab.path is None  # a copy out of a package is saved somewhere new
    for moment in (0.0, 0.7, 2.25, 3.9):
        lab.seek(moment)
        assert tuple(lab.frame.device) == preview_at(lab, moment)


# -- editing comfort and robustness -----------------------------------------


def test_dragging_a_slider_previews_without_committing(lab):
    lab.tree.add_layer_button.click()
    segment(lab, leds=2, color="#FF0000")
    before = lab.document
    field = lab.inspector.field("position")
    field.slider.sliderMoved.emit(500)  # half way round, not yet released
    assert lab.document == before
    assert lab.ring.colors[6:8] == (RED, RED)
    field.slider.setValue(500)
    field.slider.sliderReleased.emit()
    assert lab.document["layers"][0]["children"][0]["properties"]["position"] == pytest.approx(0.5)


def test_an_invalid_value_is_explained_next_to_the_field(lab):
    lab.tree.add_layer_button.click()
    choose(lab.tree.animation_menu, "Blinken")
    before = lab.document
    lab.inspector.field("minimum").spin.setValue(0.9)
    lab.inspector.field("maximum").spin.setValue(0.1)
    assert lab.document["animations"][0]["properties"]["maximum"] == 1.0
    assert lab.inspector.problem.isVisibleTo(lab.inspector)
    assert "Minimum" in lab.inspector.problem.text()
    assert lab.document["animations"][0]["properties"]["minimum"] == 0.9
    assert before != lab.document  # the valid half of the edit stayed


def test_rename_duplicate_and_remove_through_the_tree(lab, qt_app):
    lab.tree.add_layer_button.click()
    layer = lab.tree.current_id()
    segment(lab, leds=3, color="#FF0000")
    lab.select(layer)
    item = lab.tree.tree.currentItem()
    item.setText(0, "Sternschnuppe A")
    qt_app.processEvents()
    assert lab.document["layers"][0]["name"] == "Sternschnuppe A"

    lab.tree.duplicate_button.click()
    assert [l["name"] for l in lab.document["layers"]] == ["Sternschnuppe A", "Sternschnuppe A (Kopie)"]
    copy = lab.tree.current_id()
    lab.tree.remove_button.click()
    assert [l["id"] for l in lab.document["layers"]] == [layer]
    assert lab.tree.current_id() is None and copy != layer


def test_steps_follow_the_selected_animation(lab):
    lab.load_example("alternating")
    rotation = lab.document["animations"][0]["id"]
    lab.select(rotation)
    assert lab.step_plan().natural and lab.step_plan().per_cycle == 12
    assert "2 verschiedene Bilder" in lab.timeline.step_info.text()
    lab.timeline.next_step.click()
    first = lab.clock.elapsed()
    lab.timeline.next_step.click()
    assert lab.clock.elapsed() == pytest.approx(2 * first)
    assert "Versatz" in lab.timeline.step_info.text()
    lab.timeline.previous_step.click()
    assert lab.clock.elapsed() == pytest.approx(first)


def test_the_preview_ring_size_is_independent_of_the_design(lab):
    lab.load_example("counter_rotation")
    before = lab.document
    lab.led_count_box.setValue(24)
    assert len(lab.ring.colors) == 24 and lab.document == before


# -- the output and the tab's life ------------------------------------------


def test_sending_follows_the_studio_output_and_stops_with_the_tab(window, lab):
    lab.load_example("two_points")
    lab.send_box.setChecked(True)
    service = window.session.service
    assert lab.output.active
    assert service.runtime.status()["layers"]["primary_state"]["effect_id"] == FEED_ID
    assert "Sendet" in lab.output_state.text()

    lab.timeline.play_button.click()
    window.tabs.setCurrentIndex(0)  # the Player
    assert not lab.timer.isActive() and not lab.clock.playing
    assert not lab.output.active
    assert service.runtime.status()["layers"]["primary_state"] is None

    window.tabs.setCurrentWidget(lab)
    assert lab.output.active  # the box is still ticked


def test_a_mismatching_ring_size_is_not_sent(lab):
    lab.load_example("two_points")
    lab.send_box.setChecked(True)
    lab.led_count_box.setValue(16)
    assert not lab.output.active and not lab.send_box.isChecked()
    lab.send_box.setChecked(True)
    assert not lab.output.active
    assert "16 LEDs" in lab.message.text()


def test_the_ring_draws_transparent_positions(lab):
    lab.load_example("two_points")
    lab.ring.resize(300, 300)
    assert None in lab.ring.colors
    assert not lab.ring.grab().isNull()


def test_closing_the_window_releases_everything(qt_app, tmp_path):
    session = StudioSession(search_paths=[], state_file=tmp_path / "background.json")
    window = StudioWindow(session)
    window.tabs.setCurrentWidget(window.lab)
    window.lab.load_example("two_points")
    window.lab.ask_before_discarding = False
    window.lab.send_box.setChecked(True)
    window.lab.toggle_play()
    window.close()
    assert not window.lab.timer.isActive()
    assert not window.lab.output.active
    assert session.service is None
    assert window.lab._unsubscribe is None


def test_unsaved_work_can_veto_closing(qt_app, tmp_path):
    session = StudioSession(search_paths=[], state_file=tmp_path / "background.json")
    window = StudioWindow(session)
    window.lab.load_example("two_points")
    window.lab.confirm_discard = lambda: False
    window.show()
    window.close()
    assert window.isVisible() and session.service is not None
    window.lab.confirm_discard = lambda: True
    window.close()
    assert session.service is None


def test_typing_into_a_field_does_not_trigger_the_step_keys(window, lab, qt_app):
    """"," steps back and "." forward — but not while a number is being typed,
    where either may be the decimal separator."""
    window.show()
    lab.tree.add_layer_button.click()
    segment(lab, leds=2, color="#FF0000")
    lab.seek(2.0)
    spin = lab.inspector.field("brightness").spin
    spin.setFocus()
    spin.lineEdit().selectAll()
    QTest.keyClicks(spin, "0,5")
    QTest.keyClicks(spin, "0.5")
    qt_app.processEvents()
    assert lab.clock.elapsed() == pytest.approx(2.0)
    lab.tree.tree.setFocus()
    QTest.keyClick(lab.tree.tree, Qt.Key.Key_Period)
    assert lab.clock.elapsed() == pytest.approx(2.25)


# -- review R01: what the Lab says matches what the device gets --------------


@pytest.fixture
def device_window(qt_app, tmp_path, monkeypatch):
    """The real window on a fake hardware output that records every frame.

    Only the sink is replaced. Everything above it — the embedded service with
    its own render thread, the engine, the TappedSink, the window's menus — is
    the real thing, so these tests see what a reSpeaker would be sent.
    """
    from lefx.effect_creation.studio import session as studio_session
    from lefx.sdk import SinkStatus

    sinks: list = []

    class RecordingSink:
        name = "fake-respeaker"

        def __init__(self) -> None:
            self.frames: list[tuple[int, ...]] = []
            self.closed = False

        def apply_frame(self, frame) -> None:
            self.frames.append(tuple(frame.leds))

        def status(self):
            return SinkStatus(available=True, detail=None)

        def close(self) -> None:
            self.closed = True

    def create_sink(name, **options):
        sinks.append(RecordingSink())
        return sinks[-1]

    monkeypatch.setenv("LEFX_STATE_ROOT", str(tmp_path))  # no other service "holds" it
    monkeypatch.setattr(studio_session.discovery, "create_sink", create_sink)
    session = StudioSession(search_paths=[], state_file=tmp_path / "background.json")
    window = StudioWindow(session, initial_output="fake-respeaker")
    window.lab.ask_before_discarding = False
    window.tabs.setCurrentWidget(window.lab)
    window.lab.clock._now = FakeTime()
    qt_app.processEvents()
    try:
        yield window, sinks
    finally:
        window.close()
        session.close()


def trigger(window, menu: str, label: str) -> None:
    """Run a menu entry the way a click does: through its QAction."""
    for entry in window.menuBar().actions():
        if entry.text().replace("&", "") == menu:
            for action in entry.menu().actions():
                if action.text() == label:
                    action.trigger()
                    return
    raise AssertionError(f"no menu entry {menu} → {label}")


def start_sending(window) -> tuple[int, ...]:
    lab = window.lab
    lab.load_example("two_points")
    lab.send_box.setChecked(True)
    assert lab.output.active and not lab.clock.playing  # sending, preview paused
    return tuple(lab.frame.device)


def test_reloading_the_catalogue_keeps_a_paused_lab_on_the_device(device_window):
    """LAB-001-R01-F01: Katalog → Quellen neu laden, preview paused, the device keeps the Lab image.

    And what the page says is true: it shows "Sendet" because the engine is
    in fact rendering the feed, not because a flag was never reset.
    """
    from tests.studio.test_lab_output import settle

    window, sinks = device_window
    shown = start_sending(window)

    trigger(window, "Katalog", "Quellen neu laden")
    settle(window.session)

    service = window.session.service
    assert service.status()["service"]["last_error"] is None
    assert sinks[-1].frames[-1] == shown
    assert service.runtime.status()["layers"]["primary_state"]["effect_id"] == FEED_ID
    assert window.lab.output.active and window.lab.send_box.isChecked()
    assert "Sendet" in window.lab.output_state.text()


def test_clearing_everything_ends_the_lab_send_and_says_so(device_window):
    """LAB-001-R01-F02: Ausgabe → Alles löschen unticks the box and stops claiming to send.

    The resume rule is visible too: nothing comes back by itself; ticking the
    box again takes the device over once more, at once.
    """
    from tests.studio.test_lab_output import settle

    window, sinks = device_window
    lab = window.lab
    shown = start_sending(window)

    trigger(window, "Ausgabe", "Alles löschen")
    settle(window.session)

    assert not lab.output.active
    assert not lab.send_box.isChecked()
    assert "Sendet" not in lab.output_state.text()
    assert "Alles löschen" in lab.message.text()
    assert sinks[-1].frames[-1] == (0,) * 12

    lab.send_box.setChecked(True)  # the explicit resume
    settle(window.session)
    assert lab.output.active and "Sendet" in lab.output_state.text()
    assert sinks[-1].frames[-1] == shown


def test_a_failed_export_check_keeps_the_previous_package(lab, tmp_path, monkeypatch):
    """LAB-001-R01-F03: the Lab reports success only after the check, and keeps the old file otherwise."""
    from lefx.effect_creation.studio.lab import page as page_module
    from lefx.effect_creation.visual import compiler

    lab.load_example("counter_rotation")
    target = tmp_path / "kept.lefx"
    assert lab.export_to(target)["check"]["mismatches"] == []
    before = target.read_bytes()

    lab.load_example("two_points")  # a different design is on the page now

    def disagree(path, document, **kwargs):
        return {"effect_id": "x", "compared": 8, "mismatches": [0.5]}

    monkeypatch.setattr(compiler, "verify_package", disagree)
    # The page imported its own name for it before the fix; cover that too, so
    # this test reproduces the finding against the unchanged code as well.
    monkeypatch.setattr(page_module, "verify_package", disagree, raising=False)

    assert lab.export_to(target) is None  # refused, not reported as done
    assert target.read_bytes() == before
    assert "Exportiert" not in lab.message.text()
    assert "nicht verändert" in lab.message.text()
