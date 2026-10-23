"""The headless visual core as the Studio Lab uses it, without a window.

What the Lab promises rests on these: edits go through the editor and its
validation, the preview is the compiled design and nothing else, a preview view
never edits the design, and the exported package renders what the preview
showed.
"""

from __future__ import annotations

import pytest

from lefx.effect_creation.visual import Editor, new_document, validate
from lefx.effect_creation.visual import persistence, steps
from lefx.effect_creation.visual.blocks import BLOCKS, DesignError
from lefx.effect_creation.visual.compiler import compile_design, export_package, verify_package
from lefx.effect_creation.visual.preview import (
    COMPOSITE,
    FOCUS,
    ISOLATED,
    PreviewCompiler,
    PreviewPlan,
    snapshot,
)

RED, BLUE = 0xFF0000, 0x0000FF


def counter_rotating() -> tuple[Editor, str, str]:
    """The acceptance case: two five- and three-LED segments, opposite turns."""
    editor = Editor()
    first = editor.add_layer("A")
    editor.add_element(first, "segment", length=5 / 12, color="#FF0000")
    editor.add_animation(first, "rotation", rate=0.5)
    second = editor.add_layer("B")
    editor.add_element(second, "segment", position=0.5, length=3 / 12, color="#0000FF")
    editor.add_animation(second, "rotation", rate=0.5, reverse=True)
    return editor, first, second


# -- editing ----------------------------------------------------------------


def test_layers_are_added_and_removed_with_what_they_own():
    editor, first, second = counter_rotating()
    assert [layer["name"] for layer in editor.document["layers"]] == ["A", "B"]
    editor.remove(first)
    document = editor.document
    assert [layer["id"] for layer in document["layers"]] == [second]
    assert all(item["target"] == second for item in document["animations"])


def test_one_animation_type_per_layer_is_enforced_and_leaves_the_design_intact():
    editor, first, _ = counter_rotating()
    before = editor.document
    with pytest.raises(DesignError, match="nur einmal"):
        editor.add_animation(first, "rotation")
    assert editor.document == before
    editor.add_animation(first, "pulse")  # another type is fine


def test_a_rejected_property_value_changes_nothing():
    editor, first, _ = counter_rotating()
    segment = editor.document["layers"][0]["children"][0]["id"]
    before = editor.document
    with pytest.raises(DesignError):
        editor.set_property(segment, "length", 1.5)
    with pytest.raises(DesignError):
        editor.set_property(segment, "color", "red")
    assert editor.document == before


def test_property_changes_undo_and_redo():
    editor, _, _ = counter_rotating()
    segment = editor.document["layers"][0]["children"][0]["id"]
    editor.set_property(segment, "color", "#00FF00")
    assert editor.document["layers"][0]["children"][0]["properties"]["color"] == "#00FF00"
    editor.undo()
    assert editor.document["layers"][0]["children"][0]["properties"]["color"] == "#FF0000"
    editor.redo()
    assert editor.document["layers"][0]["children"][0]["properties"]["color"] == "#00FF00"


def test_layer_order_and_visibility_change_what_is_rendered():
    editor, first, second = counter_rotating()
    editor.set_property(editor.document["layers"][1]["children"][0]["id"], "position", 0.0)
    # Both segments start at LED 0; the later layer lies on top.
    assert compile_design(editor.document).render(0.0)[0] == BLUE
    editor.move(second, None, 0)
    assert compile_design(editor.document).render(0.0)[0] == RED
    editor.configure_layer(first, enabled=False)
    assert compile_design(editor.document).render(0.0)[0] == BLUE


def test_every_block_is_reachable_through_the_editor():
    editor = Editor()
    layer = editor.add_layer()
    for name, block in BLOCKS.items():
        if block.category == "element":
            editor.add_element(layer, name)
        else:
            editor.add_animation(layer, name)
    compiled = compile_design(editor.document)
    assert len(compiled.render(1.5, 12)) == 12


# -- preview ----------------------------------------------------------------


def test_the_design_recompiles_after_a_change():
    editor, first, _ = counter_rotating()
    compiler = PreviewCompiler()
    before = PreviewPlan(compiler, editor.document).frame(0.0, 12).colors
    editor.set_property(editor.document["layers"][0]["children"][0]["id"], "color", "#00FF00")
    after = PreviewPlan(compiler, editor.document).frame(0.0, 12).colors
    assert compiler.compilations == 2
    assert before[0] == RED and after[0] == 0x00FF00


def test_frames_are_not_compiled_per_moment():
    editor, _, _ = counter_rotating()
    compiler = PreviewCompiler()
    plan = PreviewPlan(compiler, editor.document, reveal_coverage=False)
    for index in range(200):
        plan.frame(index / 60, 12)
    assert compiler.compilations == 1


def test_the_preview_at_fixed_moments():
    editor, _, _ = counter_rotating()
    plan = PreviewPlan(PreviewCompiler(), editor.document, reveal_coverage=False)
    assert plan.frame(0.0, 12).colors == (RED,) * 5 + (0, BLUE, BLUE, BLUE, 0, 0, 0)
    # Half a turn per second: after one second A has gone round by six LEDs,
    # B by six the other way, so they have swapped halves.
    assert plan.frame(1.0, 12).colors == (BLUE,) * 3 + (0, 0, 0) + (RED,) * 5 + (0,)


def test_coverage_is_revealed_without_changing_what_the_device_gets():
    editor, _, _ = counter_rotating()
    compiler = PreviewCompiler()
    revealed = PreviewPlan(compiler, editor.document, reveal_coverage=True).frame(0.0, 12)
    plain = PreviewPlan(compiler, editor.document, reveal_coverage=False).frame(0.0, 12)
    assert None in revealed.colors and None not in plain.colors
    assert revealed.device == plain.device == plain.colors


def test_an_isolated_view_shows_one_layer_and_leaves_the_design_alone():
    editor, first, second = counter_rotating()
    editor.configure_layer(second, enabled=False)
    document = editor.document
    isolated = PreviewPlan(PreviewCompiler(), document, ISOLATED, second).frame(0.0, 12)
    assert isolated.colors == (None,) * 6 + (BLUE,) * 3 + (None,) * 3
    assert editor.document == document  # nothing was switched on in the design


def test_the_focus_view_dims_the_other_layers_for_orientation_only():
    editor, first, second = counter_rotating()
    focus = PreviewPlan(PreviewCompiler(), editor.document, FOCUS, second).frame(0.0, 12)
    assert focus.colors[6:9] == (BLUE,) * 3
    assert 0 < focus.colors[0] < RED and focus.colors[0] & 0x00FFFF == 0


def test_an_unknown_layer_falls_back_to_the_whole_effect():
    editor, _, _ = counter_rotating()
    plan = PreviewPlan(PreviewCompiler(), editor.document, ISOLATED, "nope")
    assert plan.view == COMPOSITE


def test_a_snapshot_is_a_copy():
    editor, first, _ = counter_rotating()
    document = editor.document
    copy = snapshot(document, solo=first, reveal_coverage=True)
    assert copy["effect"]["composition"] == "transparent"
    assert document["effect"]["composition"] == "opaque"
    assert validate(copy) == copy


# -- steps ------------------------------------------------------------------


def test_a_rotation_steps_through_led_offsets_not_through_time():
    rotation = {"type": "rotation", "properties": {"rate": 0.5, "reverse": False, "phase": 0.0}}
    plan = steps.plan_for(rotation, 12)
    assert plan.natural and plan.per_cycle == 12
    assert plan.time(1) == pytest.approx(1 / 6)
    assert plan.after(0.0) == 1 and plan.before(plan.time(3)) == 2
    reverse = steps.plan_for({**rotation, "properties": {**rotation["properties"], "reverse": True}}, 12)
    assert reverse.label(1).startswith("Versatz 11")


def test_led_count_and_number_of_different_pictures_are_kept_apart():
    """Twelve offsets, two pictures: the A/B case from the brief."""
    editor = Editor()
    layer = editor.add_layer()
    for index in range(0, 12, 2):
        editor.add_element(layer, "point", position=index / 12, color="#FFAA00")
    editor.add_animation(layer, "rotation", rate=1 / 12)
    document = editor.document
    plan = steps.plans(document, 12)[document["animations"][0]["id"]]
    compiled = compile_design(document)
    assert plan.per_cycle == 12
    assert steps.distinct_frames(lambda t: compiled.render(t, 12), plan) == 2


def test_continuous_animations_offer_samples_not_states():
    pulse = {"type": "pulse", "properties": {"frequency": 2.0, "phase": 0.0, "minimum": -20.0, "maximum": 0.0}}
    plan = steps.plan_for(pulse, 12, sample_count=5)
    assert not plan.natural and plan.per_cycle == 5
    assert plan.time(5) == pytest.approx(0.5)
    blink = {"type": "blink", "properties": {"frequency": 1.0, "phase": 0.0, "duty": 0.25,
                                              "minimum": 0.0, "maximum": 1.0}}
    assert steps.plan_for(blink, 12).labels == ("an", "aus")
    assert steps.uniform(0.25).time(4) == pytest.approx(1.0)


# -- persistence and export -------------------------------------------------


def test_a_saved_design_comes_back_as_it_was(tmp_path):
    editor, _, _ = counter_rotating()
    path = persistence.save(editor.document, tmp_path / "design.lefx-design.json")
    assert persistence.load(path) == editor.document


def test_the_exported_package_is_accepted_and_renders_the_preview(tmp_path):
    editor, _, _ = counter_rotating()
    editor.metadata(id="lab_export", title="Lab-Export")
    report = export_package(editor.document, tmp_path / "lab_export.lefx")
    check = verify_package(report["path"], editor.document)
    assert check["mismatches"] == [] and check["compared"] >= 5
    # And the editable design comes back out of the package.
    assert persistence.load(report["path"]) == editor.document


def test_the_export_check_notices_a_different_design(tmp_path):
    editor, _, _ = counter_rotating()
    report = export_package(editor.document, tmp_path / "x.lefx")
    editor.set_property(editor.document["layers"][0]["children"][0]["id"], "color", "#00FF00")
    assert verify_package(report["path"], editor.document)["mismatches"]


def test_a_new_document_is_valid_and_empty():
    document = new_document()
    assert validate(document)["layers"] == []
    assert compile_design(document).render(0.0) == [0] * 12
