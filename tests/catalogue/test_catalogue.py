"""The first-party catalogue, exercised the way the engine will run it.

Every source is imported once and then rendered at several ring sizes and at
several points in its life. The point is not that the pictures look right — that
needs eyes — but that no definition quietly breaks the contract it declared.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lefx.authoring import import_effect_class, load_effect_source, validate_effect_source
from lefx.engine import check_frame
from lefx.sdk import (
    CompositionMode,
    ControlledOverlayDefinition,
    DefinitionKind,
    EventDefinition,
    RenderContext,
    StateDefinition,
    TimedOverlayDefinition,
    initial_runtime_inputs,
    resolve_configuration,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_ROOT = REPO_ROOT / "effects"

LED_COUNTS = (1, 5, 12, 24)
MOMENTS = (0.0, 0.001, 0.37, 1.0, 2.5, 9.9, 60.0)

EXPECTED = {
    "core-set": 12,
    "smartspeaker-set": 23,
}


def source_dirs() -> list[Path]:
    return sorted((CATALOGUE_ROOT).rglob("sources/**/effect.yaml"))


def source_ids() -> list[str]:
    return [f"{path.parents[3].name}/{path.parent.name}" for path in source_dirs()]


ALL_SOURCES = source_dirs()
ALL_IDS = source_ids()


@pytest.fixture(scope="module")
def loaded() -> dict[str, tuple[Path, type]]:
    """Import every source once; importing is the expensive part."""
    result: dict[str, tuple[Path, type]] = {}
    for manifest, label in zip(ALL_SOURCES, ALL_IDS):
        source = load_effect_source(manifest.parent)
        result[label] = (manifest.parent, import_effect_class(source))
    return result


# -- the catalogue as a whole -----------------------------------------------


def test_both_sets_are_present_and_complete():
    counts: dict[str, int] = {}
    for label in ALL_IDS:
        counts[label.split("/")[0]] = counts.get(label.split("/")[0], 0) + 1
    assert counts == EXPECTED


def test_every_lifecycle_form_and_colour_model_is_covered(loaded):
    """The core set is reference material; a gap in it is a gap in the examples."""
    core = {
        label.split("/")[1]: effect_class.get_definition()
        for label, (_, effect_class) in loaded.items()
        if label.startswith("core-set/")
    }
    kinds = {definition.kind for definition in core.values()}
    models = {definition.color_model for definition in core.values()}
    assert kinds == set(DefinitionKind)
    assert len(models) == 6, sorted(model.value for model in models)


def test_definition_ids_are_globally_unique(loaded):
    ids = [effect_class.get_definition().id for _, effect_class in loaded.values()]
    assert len(set(ids)) == len(ids)


def test_every_directory_is_named_after_its_definition(loaded):
    for label, (directory, effect_class) in loaded.items():
        assert directory.name == effect_class.get_definition().id, label


def test_every_definition_sits_in_the_folder_for_its_type(loaded):
    groups = {"state": "states", "overlay": "overlays", "event": "events"}
    for label, (directory, effect_class) in loaded.items():
        definition = effect_class.get_definition()
        assert directory.parent.name == groups[definition.definition_type.value], label


# -- per-source validation --------------------------------------------------


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_every_source_validates(manifest):
    report = validate_effect_source(manifest.parent)
    assert report.ok, report.errors
    assert not report.warnings, report.warnings


# -- rendering --------------------------------------------------------------


def render_at(effect_class, *, led_count: int, elapsed: float, params=None, inputs=None):
    definition = effect_class.get_definition()
    context = RenderContext(
        now=elapsed,
        started_at=0.0,
        led_count=led_count,
        definition=definition,
        params=params or resolve_configuration(definition),
        inputs=inputs if inputs is not None else initial_runtime_inputs(definition),
    )
    frame = effect_class().render(context)
    check_frame(frame, definition, led_count)
    return frame


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_every_definition_renders_at_every_ring_size_and_moment(loaded, manifest):
    label = f"{manifest.parents[3].name}/{manifest.parent.name}"
    _, effect_class = loaded[label]
    for led_count in LED_COUNTS:
        for elapsed in MOMENTS:
            render_at(effect_class, led_count=led_count, elapsed=elapsed)


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_declared_composition_matches_what_is_rendered(loaded, manifest):
    """An opaque definition must fill every position; check_frame enforces it.

    The reverse direction needs stating too: a definition that calls itself
    transparent but never yields is not wrong, only misleading — so this only
    asserts the promise that has teeth.
    """
    label = f"{manifest.parents[3].name}/{manifest.parent.name}"
    _, effect_class = loaded[label]
    definition = effect_class.get_definition()
    frame = render_at(effect_class, led_count=12, elapsed=0.5)
    if definition.composition is CompositionMode.OPAQUE:
        assert all(value is not None for value in frame), definition.id


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_every_preset_resolves_and_renders(loaded, manifest):
    label = f"{manifest.parents[3].name}/{manifest.parent.name}"
    directory, effect_class = loaded[label]
    definition = effect_class.get_definition()
    presets = load_effect_source(directory).presets()
    if not definition.parameter_schema:
        # Nothing to curate: a definition with no configuration has no preset
        # to offer, and an empty one would only be noise in the catalogue.
        assert not presets, f"{label} has no parameters but ships a preset"
        return
    assert presets, f"{label} ships no preset"
    for preset_id, entry in presets.items():
        params = resolve_configuration(definition, preset=entry.get("params", {}))
        assert preset_id.startswith(definition.id), preset_id
        render_at(effect_class, led_count=12, elapsed=0.5, params=params)


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_directional_definitions_render_both_ways(loaded, manifest):
    label = f"{manifest.parents[3].name}/{manifest.parent.name}"
    _, effect_class = loaded[label]
    definition = effect_class.get_definition()
    if not definition.directional:
        return
    for reverse in (False, True):
        params = resolve_configuration(definition, overrides={"reverse": reverse})
        render_at(effect_class, led_count=12, elapsed=0.4, params=params)


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_numeric_parameters_render_at_both_extremes(loaded, manifest):
    """A minimum and a maximum that nobody ever renders are not really bounds."""
    label = f"{manifest.parents[3].name}/{manifest.parent.name}"
    _, effect_class = loaded[label]
    definition = effect_class.get_definition()
    for name, param in definition.parameter_schema.items():
        for bound in (param.minimum, param.maximum):
            if bound is None or param.type.value in {"color_list"}:
                continue
            params = resolve_configuration(definition, overrides={name: bound})
            render_at(effect_class, led_count=12, elapsed=0.5, params=params)


# -- runtime inputs ---------------------------------------------------------


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_controlled_overlays_handle_null_and_both_extremes(loaded, manifest):
    label = f"{manifest.parents[3].name}/{manifest.parent.name}"
    _, effect_class = loaded[label]
    definition = effect_class.get_definition()
    if not isinstance(definition, ControlledOverlayDefinition):
        return

    for name, param in definition.runtime_input_schema.items():
        candidates: list[object] = []
        if param.nullable:
            # Null is what a renderer sees before the first value and after the
            # source goes quiet. Every controlled overlay must survive it.
            candidates.append(None)
        if param.minimum is not None:
            candidates.append(param.minimum)
        if param.maximum is not None:
            candidates.append(param.maximum)
        if param.enum_values:
            candidates.extend(param.enum_values)
        if param.type.value == "angle_deg":
            candidates.extend([0.0, 179.9, 359.9])

        for value in candidates:
            inputs = initial_runtime_inputs(definition)
            inputs[name] = value
            render_at(effect_class, led_count=12, elapsed=0.5, inputs=inputs)


# -- lifecycle shape --------------------------------------------------------


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_finite_forms_declare_a_duration_and_states_do_not(loaded, manifest):
    label = f"{manifest.parents[3].name}/{manifest.parent.name}"
    _, effect_class = loaded[label]
    definition = effect_class.get_definition()

    if isinstance(definition, (TimedOverlayDefinition, EventDefinition)):
        assert definition.duration_field.value in definition.parameter_schema
    if isinstance(definition, StateDefinition):
        assert "duration_ms" not in definition.parameter_schema
        assert "total_ms" not in definition.parameter_schema
        assert definition.runtime_input_schema == {}


@pytest.mark.parametrize("manifest", ALL_SOURCES, ids=ALL_IDS)
def test_finite_forms_render_from_start_to_past_their_end(loaded, manifest):
    label = f"{manifest.parents[3].name}/{manifest.parent.name}"
    _, effect_class = loaded[label]
    definition = effect_class.get_definition()
    if not isinstance(definition, (TimedOverlayDefinition, EventDefinition)):
        return

    params = resolve_configuration(definition)
    total = params[definition.duration_field.value] / 1000.0
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5):
        render_at(effect_class, led_count=12, elapsed=total * fraction, params=params)


# -- packaging --------------------------------------------------------------


def test_both_sets_build_and_load_back(tmp_path):
    """The whole chain: sources in, one verified archive per set out."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from build_effects import build_set
    finally:
        sys.path.pop(0)

    from lefx.engine import load_source

    for set_name, expected in EXPECTED.items():
        result = build_set(CATALOGUE_ROOT / set_name, output_root=tmp_path)
        assert result["ok"]
        assert result["effect_count"] == expected
        loaded_set = load_source(result["path"])
        assert len(loaded_set.packages) == expected
        assert all(package.source_id == set_name for package in loaded_set.packages)
