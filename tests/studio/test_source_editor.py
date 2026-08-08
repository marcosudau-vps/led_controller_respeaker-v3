"""The editor page, driven the way a person drives it.

The blueprint tests cover what may be written. These cover the claim the *form*
makes: that a field a type does not have is switched off rather than left to be
filled in wrongly, that Save is unavailable while anything is wrong, and that
the button chain from "new definition" to a ``.lefx`` on disk actually runs.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6", reason="the source editor needs Qt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from lefx.authoring import import_effect_class, load_effect_source  # noqa: E402
from lefx.sdk import (  # noqa: E402
    ColorModel,
    DefinitionKind,
    DurationField,
    InputMode,
    ParamType,
    StateSlot,
)
from lefx.studio.blueprint import ParameterBlueprint, build_package  # noqa: E402
from lefx.studio.session import StudioSession  # noqa: E402
from lefx.studio.source_editor import ParameterEditorRow, SourceEditorPage  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("LEFX_STATE_ROOT", str(tmp_path))
    session = StudioSession(
        led_count=12, fps=60.0, search_paths=[], state_file=tmp_path / "background.json"
    )
    session.open("null")
    built = SourceEditorPage(session)
    try:
        yield built
    finally:
        session.close()


def describe(page, kind: DefinitionKind, effect_id: str) -> None:
    """Fill in the three fields a starting blueprint is missing."""
    page.kind_box.setCurrentIndex(page.kind_box.findData(kind))
    page.effect_id.setText(effect_id)
    page.title.setText("Studio Demo")
    page.description.setPlainText("Vom Studio entworfen.")
    page._on_edited()  # noqa: SLF001 — what typing triggers


# -- the form only offers what the type has ---------------------------------


def test_a_type_without_bounds_has_its_bound_fields_switched_off(qt_app):
    row = ParameterEditorRow(ParameterBlueprint(name="tint", type=ParamType.COLOR))
    assert row.bounds_host.isEnabled() is False
    assert row.enum_values.isEnabled() is False
    assert row.unit.isEnabled() is False


def test_a_numeric_type_offers_bounds_and_its_own_units(qt_app):
    row = ParameterEditorRow(ParameterBlueprint(name="ratio", type=ParamType.FLOAT, default=0.0))
    assert row.bounds_host.isEnabled() is True
    assert row.unit.isEnabled() is True
    units = {row.unit.itemText(index) for index in range(row.unit.count())}
    assert {"ms", "deg", "hz"} <= units
    assert "furlong" not in units


def test_an_enum_offers_its_values_and_nothing_else(qt_app):
    row = ParameterEditorRow(ParameterBlueprint(name="mode", type=ParamType.ENUM, default="a"))
    assert row.enum_values.isEnabled() is True
    assert row.bounds_host.isEnabled() is False


def test_changing_the_type_reshapes_the_row(qt_app):
    row = ParameterEditorRow(ParameterBlueprint(name="value", type=ParamType.COLOR))
    assert row.bounds_host.isEnabled() is False

    row.type_box.setCurrentIndex(row.type_box.findData(ParamType.INT))
    assert row.blueprint.type is ParamType.INT
    assert row.bounds_host.isEnabled() is True
    # And the default was replaced with one of the right shape.
    assert isinstance(row.blueprint.default, int)


def test_a_duration_box_cannot_be_set_to_four_hours(qt_app):
    """Bounded generously but finitely: the schema would take it, a form should
    not make it a typo away."""
    row = ParameterEditorRow(ParameterBlueprint(name="duration_ms", type=ParamType.DURATION_MS))
    row.maximum.setValue(14_400_000)
    assert row.maximum.value() <= 600_000


def test_typing_a_reserved_name_adopts_its_fixed_declaration(qt_app):
    """Rather than letting a wrong type be entered and rejected afterwards."""
    row = ParameterEditorRow(ParameterBlueprint(name="", type=ParamType.COLOR))
    row.name.setText("brightness")
    row._on_name_edited("brightness")  # noqa: SLF001

    assert row.blueprint.type is ParamType.FLOAT
    assert (row.blueprint.minimum, row.blueprint.maximum) == (0.0, 1.0)
    assert row.type_box.isEnabled() is False
    assert row.reserved_note.isVisible() or row.reserved_note.text()


def test_configuration_fields_cannot_be_marked_required(qt_app):
    """A config field must always resolve, so it always has a default instead."""
    row = ParameterEditorRow(ParameterBlueprint(name="tint", type=ParamType.COLOR), runtime=False)
    assert row.required.isEnabled() is False
    assert row.nullable.isEnabled() is False


def test_runtime_inputs_may_be_nullable_and_required(qt_app):
    row = ParameterEditorRow(ParameterBlueprint(name="level", type=ParamType.FLOAT), runtime=True)
    assert row.required.isEnabled() is True
    assert row.nullable.isEnabled() is True


# -- the page as a whole ----------------------------------------------------


@pytest.mark.parametrize("kind", list(DefinitionKind))
def test_the_page_opens_on_something_valid_once_it_is_named(page, kind):
    describe(page, kind, f"studio_{kind.value}")
    assert page.save_button.isEnabled() is True
    assert page.preview_source.toPlainText().startswith("from lefx.sdk import")


def test_save_is_unavailable_while_anything_is_wrong(page):
    describe(page, DefinitionKind.STATE, "studio_state")
    assert page.save_button.isEnabled() is True

    page.effect_id.setText("Nicht Gültig")
    page._on_edited()  # noqa: SLF001
    assert page.save_button.isEnabled() is False
    assert page.status.text()

    page.effect_id.setText("studio_state")
    page._on_edited()  # noqa: SLF001
    assert page.save_button.isEnabled() is True


def test_the_form_only_shows_the_fields_the_chosen_form_has(page):
    describe(page, DefinitionKind.STATE, "studio_state")
    assert page.slots_host.isVisible() or not page.isVisible()
    assert page.blueprint.kind is DefinitionKind.STATE

    describe(page, DefinitionKind.EVENT, "studio_event")
    assert page.blueprint.kind is DefinitionKind.EVENT
    assert page.blueprint.finite is True

    describe(page, DefinitionKind.CONTROLLED_OVERLAY, "studio_overlay")
    assert page.blueprint.runtime_inputs


def test_switching_the_form_starts_from_something_valid_again(page):
    """The mandatory and forbidden fields change with the form, so it is begun
    again rather than patched into a shape that would need untangling."""
    describe(page, DefinitionKind.STATE, "studio_thing")
    assert "duration_ms" not in {p.name for p in page.blueprint.parameters}

    describe(page, DefinitionKind.TIMED_OVERLAY, "studio_thing")
    assert "duration_ms" in {p.name for p in page.blueprint.parameters}
    assert page.save_button.isEnabled() is True


def test_a_missing_mandatory_field_can_be_filled_in_with_one_click(page):
    describe(page, DefinitionKind.STATE, "studio_state")
    page.animated.setChecked(True)

    assert page.fill_button.isEnabled() is True
    assert page.save_button.isEnabled() is False
    assert "speed" in page.status.text()

    page._fill_required()  # noqa: SLF001
    assert page.save_button.isEnabled() is True
    assert "speed" in {p.name for p in page.blueprint.parameters}


def test_a_colour_model_brings_its_own_required_fields(page):
    describe(page, DefinitionKind.STATE, "studio_state")
    page.color_model.setCurrentIndex(page.color_model.findData(ColorModel.PALETTE))
    page._on_structure_changed()  # noqa: SLF001

    assert "colors" in page.blueprint.required_parameters()
    page._fill_required()  # noqa: SLF001
    assert page.blueprint.problems() == []


def test_the_length_field_follows_the_choice(page):
    describe(page, DefinitionKind.TIMED_OVERLAY, "studio_timed")
    page.duration_field.setCurrentIndex(page.duration_field.findData(DurationField.TOTAL_MS))
    page._on_structure_changed()  # noqa: SLF001

    assert page.blueprint.duration_field is DurationField.TOTAL_MS
    assert "total_ms" in page.blueprint.required_parameters()
    assert page.save_button.isEnabled() is False


def test_the_capability_field_only_matters_when_inputs_are_pulled(page):
    describe(page, DefinitionKind.CONTROLLED_OVERLAY, "studio_overlay")
    page.sampling_mode.setCurrentIndex(page.sampling_mode.findData(InputMode.PUSH))
    page._on_edited()  # noqa: SLF001
    assert page.provider_id.isEnabled() is False

    page.sampling_mode.setCurrentIndex(page.sampling_mode.findData(InputMode.PULL))
    page._on_edited()  # noqa: SLF001
    assert page.provider_id.isEnabled() is True

    page.provider_id.setText("doa")
    page._on_edited()  # noqa: SLF001
    assert page.blueprint.definition().input_sampling.provider_id == "doa"


def test_a_state_can_be_made_restorable_only_with_a_background_slot(page):
    describe(page, DefinitionKind.STATE, "studio_state")
    assert page.restorable.isEnabled() is False

    page.slot_background.setChecked(True)
    page._on_edited()  # noqa: SLF001
    assert page.restorable.isEnabled() is True

    page.restorable.setChecked(True)
    page._on_edited()  # noqa: SLF001
    assert page.blueprint.definition().restorable is True
    assert StateSlot.BACKGROUND in page.blueprint.definition().slots


def test_a_render_body_that_does_not_compile_stops_the_preview(page):
    describe(page, DefinitionKind.STATE, "studio_state")
    page.code.setPlainText("        this is not python")
    page._on_edited()  # noqa: SLF001

    page._preview()  # noqa: SLF001 — what the Preview button calls
    assert "render()" in page.status.text() or page.save_button.isEnabled() is False


# -- all the way to a file --------------------------------------------------


@pytest.mark.parametrize("kind", list(DefinitionKind))
def test_the_button_chain_produces_a_lefx_on_disk(page, kind, tmp_path, monkeypatch):
    """New definition → write → pack, with the dialogs answered for it.

    This is the road the user asked for, walked end to end: what comes out is a
    single ``.lefx`` that loads like any other package.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    target_dir = tmp_path / "sources"
    target_dir.mkdir()
    package = tmp_path / f"studio_{kind.value}.lefx"

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(target_dir))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(package), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    describe(page, kind, f"studio_{kind.value}")
    page._write()  # noqa: SLF001
    assert page.written is not None and page.written.is_dir()
    assert page.pack_button.isEnabled() is True

    page._pack()  # noqa: SLF001
    assert package.is_file()

    definition = import_effect_class(load_effect_source(page.written)).definition
    assert definition.kind is kind


def test_writing_refuses_when_the_target_already_holds_that_effect(page, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    target_dir = tmp_path / "sources"
    target_dir.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(target_dir))
    complaints: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _p, _t, message: complaints.append(message))

    describe(page, DefinitionKind.STATE, "studio_state")
    page._write()  # noqa: SLF001
    page._write()  # noqa: SLF001

    assert complaints and "existiert bereits" in complaints[0]


def test_the_packed_effect_can_be_loaded_by_the_engine(page, tmp_path, monkeypatch):
    from lefx.engine import load_source
    from PySide6.QtWidgets import QFileDialog

    target_dir = tmp_path / "sources"
    target_dir.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(target_dir))

    describe(page, DefinitionKind.STATE, "studio_state")
    page._write()  # noqa: SLF001
    build_package(page.written, tmp_path / "studio_state.lefx")

    loaded = load_source(tmp_path / "studio_state.lefx")
    assert [package.effect_id for package in loaded.packages] == ["studio_state"]


def test_a_new_definition_can_be_previewed_on_the_attached_device(page):
    """Rendered by the real engine on the real sink, before it is a file."""
    describe(page, DefinitionKind.STATE, "studio_state")
    page._preview()  # noqa: SLF001

    status = page.session.status()
    running = [entry["effect_id"] for entry in status["layers"].values() if entry]
    assert "studio_state" in running


def test_a_body_that_throws_is_caught_while_it_is_still_on_screen(page):
    """Not at save time, in a dialog that closes over it.

    The same smoke render the source validator performs runs on every edit, so
    Save is simply off while the definition would not render.
    """
    describe(page, DefinitionKind.STATE, "studio_state")
    assert page.save_button.isEnabled() is True

    page.code.setPlainText("        return [1] * (ctx.led_count + 1)")
    page._on_edited()  # noqa: SLF001
    assert page.save_button.isEnabled() is False
    assert "studio_state" in page.status.text()

    page.code.setPlainText("        return ctx.blank_frame()")
    page._on_edited()  # noqa: SLF001
    assert page.save_button.isEnabled() is True


def test_a_body_that_is_not_python_says_which_line(page):
    describe(page, DefinitionKind.STATE, "studio_state")
    page.code.setPlainText("        return [")
    page._on_edited()  # noqa: SLF001

    assert page.save_button.isEnabled() is False
    assert "Python" in page.status.text()
