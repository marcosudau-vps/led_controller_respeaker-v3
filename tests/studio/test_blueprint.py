"""Designing a definition, and the guarantee that a bad one cannot be written.

The editor's promise is not "invalid input is rejected on save" but "invalid
input never becomes a file". That rests on one move: the blueprint constructs
the *real* definition — which validates itself in ``__post_init__`` — and the
source text is printed from something that already exists. So the tests here
mostly ask two questions:

* does every combination the schema forbids come back as a problem, before
  anything is written;
* does everything that is written validate, pack, and load.

The second one is asked against all four lifecycle forms, because the studio's
whole claim is that it can produce any of them.
"""

from __future__ import annotations

import pytest

from lefx.authoring import (
    SourceError,
    import_effect_class,
    load_effect_source,
    validate_effect_source,
)
from lefx.sdk import (
    RESERVED_PARAMETERS,
    ColorModel,
    CompositionMode,
    DefinitionKind,
    DurationField,
    InputMode,
    ParamDefinition,
    ParamType,
    SchemaError,
    StateSlot,
)
from lefx.studio.blueprint import (
    DEFINITION_CLASSES,
    DURATION_LIMIT_MS,
    TYPE_SUPPORT,
    EffectBlueprint,
    ParameterBlueprint,
    build_package,
    default_for,
    reserved_blueprint,
    starting_blueprint,
)


def ready(kind: DefinitionKind, effect_id: str = "studio_demo") -> EffectBlueprint:
    blueprint = starting_blueprint(kind, effect_id=effect_id, source_id="demo-set")
    blueprint.title = "Studio Demo"
    blueprint.description = "Vom Studio entworfen, um geprüft zu werden."
    return blueprint


# -- the type matrix, checked against the SDK rather than restated ----------


@pytest.mark.parametrize("kind", list(ParamType))
def test_the_editors_type_matrix_agrees_with_the_schema(kind):
    """The form greys out fields a type does not accept, from a table of its own.

    A table that drifted from the SDK's would grey out the wrong things — so it
    is not compared to the SDK's source but probed against its behaviour.
    """
    support = TYPE_SUPPORT[kind]
    # A default that sits inside the bounds being probed, so a rejection means
    # "this type has no bounds" and not "1000 is more than 10".
    probe_defaults = {ParamType.INT: 1, ParamType.FLOAT: 1.0, ParamType.DURATION_MS: 1}
    base = {
        "name": "probe",
        "type": kind,
        "default": probe_defaults.get(kind, default_for(kind)),
    }
    if kind is ParamType.ENUM:
        base["enum_values"] = ("first", "second")

    accepts_bounds = _accepts(base, minimum=0, maximum=10)
    assert accepts_bounds == support.bounds, f"{kind.value}: bounds"

    if support.unit_allowed:
        for unit in support.units:
            assert _accepts(base, unit=unit), f"{kind.value}: unit {unit}"
        assert not _accepts(base, unit="furlong"), f"{kind.value}: bogus unit accepted"
    else:
        assert not _accepts(base, unit="ms"), f"{kind.value}: unit accepted"

    if not support.enum_values:
        assert not _accepts(base, enum_values=("a",)), f"{kind.value}: enum_values accepted"


def _accepts(base: dict, **extra) -> bool:
    try:
        ParamDefinition(**{**base, **extra})
    except (SchemaError, ValueError, TypeError):
        return False
    return True


def test_every_lifecycle_form_can_be_produced():
    """A form added to the SDK must not silently become one the editor cannot make."""
    assert set(DEFINITION_CLASSES) == set(DefinitionKind)


# -- reserved names ---------------------------------------------------------


@pytest.mark.parametrize("name", sorted(RESERVED_PARAMETERS))
def test_a_reserved_name_comes_pre_filled_and_valid(name):
    """These carry one meaning system-wide, so the editor does not ask.

    ``brightness`` is a float from zero to one wherever it appears; offering the
    choice would only offer the chance to get it wrong.
    """
    blueprint = reserved_blueprint(name)
    assert blueprint.problem() is None, blueprint.problem()
    assert blueprint.build().type is RESERVED_PARAMETERS[name].type


def test_a_reserved_name_keeps_the_range_the_system_fixed():
    brightness = reserved_blueprint("brightness").build()
    assert (brightness.minimum, brightness.maximum) == (0.0, 1.0)
    assert reserved_blueprint("speed").build().minimum > 0


# -- what a blueprint refuses ----------------------------------------------


@pytest.mark.parametrize("kind", list(DefinitionKind))
def test_a_starting_blueprint_needs_only_a_name_to_be_valid(kind):
    """The editor opens on something that already runs, not on an error list."""
    assert ready(kind).problems() == []


def test_a_nameless_definition_is_not_valid():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.effect_id = ""
    assert any("Id" in problem for problem in blueprint.problems())


@pytest.mark.parametrize("bad_id", ["Mein Effekt", "9lives", "mein-effekt", "class", "_privat"])
def test_an_id_that_is_not_an_identifier_is_refused(bad_id):
    blueprint = ready(DefinitionKind.STATE)
    blueprint.effect_id = bad_id
    assert blueprint.problems()


def test_a_definition_without_a_description_is_refused():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.description = "  "
    assert blueprint.problems()


def test_a_coloured_definition_without_brightness_is_caught_before_writing():
    """No single field is wrong here; the combination is. Which is why the
    check is a real constructor and not a list of field validators."""
    blueprint = ready(DefinitionKind.STATE)
    blueprint.parameters = [p for p in blueprint.parameters if p.name != "brightness"]
    assert "brightness" in blueprint.required_parameters()
    assert blueprint.problems()


def test_an_animated_definition_must_declare_speed():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.animated = True
    assert "speed" in blueprint.required_parameters()
    assert blueprint.problems()

    blueprint.add_missing_parameters()
    assert blueprint.problems() == []


def test_a_directional_definition_must_declare_reverse():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.directional = True
    assert blueprint.required_parameters() == ["reverse"]
    blueprint.add_missing_parameters()
    assert blueprint.problems() == []


def test_a_colourless_definition_may_not_carry_colour_fields():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.color_model = ColorModel.NONE
    assert set(blueprint.forbidden_parameters()) >= {"color", "brightness"}
    assert blueprint.problems()


def test_a_state_may_not_declare_a_duration():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.parameters.append(reserved_blueprint("duration_ms"))
    assert "duration_ms" in blueprint.forbidden_parameters()
    assert blueprint.problems()


def test_a_finite_form_needs_the_length_it_names():
    blueprint = ready(DefinitionKind.EVENT)
    blueprint.parameters = [p for p in blueprint.parameters if p.name != "duration_ms"]
    assert blueprint.required_parameters() == ["duration_ms"]
    assert blueprint.problems()


def test_switching_the_length_field_changes_what_is_required():
    blueprint = ready(DefinitionKind.TIMED_OVERLAY)
    blueprint.duration_field = DurationField.TOTAL_MS
    assert blueprint.required_parameters() == ["total_ms"]
    assert "duration_ms" in blueprint.forbidden_parameters()


def test_a_restorable_state_must_allow_the_background_slot():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.restorable = True
    blueprint.slots = (StateSlot.PRIMARY,)
    assert blueprint.problems()

    blueprint.slots = (StateSlot.PRIMARY, StateSlot.BACKGROUND)
    assert blueprint.problems() == []


def test_a_pulling_overlay_without_runtime_inputs_is_refused():
    blueprint = ready(DefinitionKind.CONTROLLED_OVERLAY)
    blueprint.sampling_mode = InputMode.PULL
    blueprint.provider_id = "doa"
    blueprint.runtime_inputs = []
    assert blueprint.problems()


def test_a_runtime_input_cannot_shadow_a_configuration_field():
    blueprint = ready(DefinitionKind.CONTROLLED_OVERLAY)
    blueprint.runtime_inputs.append(reserved_blueprint("brightness"))
    assert blueprint.problems()


def test_a_duplicate_parameter_is_reported_as_one():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.parameters.append(reserved_blueprint("color"))
    assert any("doppelt" in problem for problem in blueprint.problems())


def test_an_empty_render_body_is_not_a_definition():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.render_body = "   "
    assert any("render()" in problem for problem in blueprint.problems())


def test_a_parameter_whose_bounds_contradict_is_refused():
    parameter = ParameterBlueprint(
        name="speed", type=ParamType.FLOAT, default=1.0, minimum=4.0, maximum=1.0
    )
    assert parameter.problem() is not None


def test_a_parameter_default_outside_its_own_bounds_is_refused():
    parameter = ParameterBlueprint(
        name="ratio", type=ParamType.FLOAT, default=9.0, minimum=0.0, maximum=1.0
    )
    assert parameter.problem() is not None


def test_an_enum_without_values_is_refused():
    parameter = ParameterBlueprint(name="mode", type=ParamType.ENUM, default="a")
    assert parameter.problem() is not None


# -- the bounds the editor itself offers ------------------------------------


def test_the_forms_own_limits_are_generous_but_finite():
    """The schema would take a duration of four hours; a form that offered one
    would invite a typo nobody notices. Ten minutes is two orders of magnitude
    above anything in the catalogue."""
    assert DURATION_LIMIT_MS == 600_000
    longest = max(
        parameter.maximum or 0
        for parameter in [reserved_blueprint("duration_ms"), reserved_blueprint("total_ms")]
    )
    assert longest == DURATION_LIMIT_MS
    assert reserved_blueprint("duration_ms").build().minimum >= 1


# -- from blueprint to file to package --------------------------------------


@pytest.mark.parametrize("kind", list(DefinitionKind))
def test_a_blueprint_becomes_a_source_that_validates(kind, tmp_path):
    root = ready(kind, effect_id=f"studio_{kind.value}").write(tmp_path)

    assert (root / "effect.py").is_file()
    assert (root / "effect.yaml").is_file()
    report = validate_effect_source(root)
    assert report.ok, report.errors
    assert not report.warnings, report.warnings


@pytest.mark.parametrize("kind", list(DefinitionKind))
def test_the_written_source_loads_back_as_the_definition_it_described(kind, tmp_path):
    blueprint = ready(kind, effect_id=f"studio_{kind.value}")
    blueprint.tags = ("studio", "demo")
    root = blueprint.write(tmp_path)

    definition = import_effect_class(load_effect_source(root)).definition
    assert definition.id == blueprint.effect_id
    assert definition.kind is kind
    assert definition.title == blueprint.title
    assert definition.tags == ("studio", "demo")
    assert set(definition.parameter_schema) == {p.name for p in blueprint.parameters}


@pytest.mark.parametrize("kind", list(DefinitionKind))
def test_a_written_source_packs_into_a_single_lefx(kind, tmp_path):
    """The end of the road the user asked for: one file, buildable from the GUI."""
    root = ready(kind, effect_id=f"studio_{kind.value}").write(tmp_path)
    target = tmp_path / f"studio_{kind.value}.lefx"

    report = build_package(root, target)

    assert target.is_file()
    assert target.suffix == ".lefx"
    assert report["effect_id"] == f"studio_{kind.value}"
    assert report["size_bytes"] > 0


def test_a_packed_effect_loads_into_a_registry_like_any_other(tmp_path):
    from lefx.engine import load_source

    root = ready(DefinitionKind.STATE, effect_id="studio_state").write(tmp_path)
    build_package(root, tmp_path / "studio_state.lefx")

    loaded = load_source(tmp_path / "studio_state.lefx")
    assert [package.effect_id for package in loaded.packages] == ["studio_state"]


def test_an_invalid_blueprint_writes_nothing_at_all(tmp_path):
    blueprint = ready(DefinitionKind.STATE)
    blueprint.title = ""
    with pytest.raises(SourceError):
        blueprint.write(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_an_existing_source_is_not_overwritten_by_accident(tmp_path):
    blueprint = ready(DefinitionKind.STATE)
    blueprint.write(tmp_path)
    with pytest.raises(SourceError, match="existiert bereits"):
        blueprint.write(tmp_path)
    blueprint.write(tmp_path, force=True)


# -- what the generated source looks like -----------------------------------


def test_the_generated_source_imports_only_what_it_uses():
    """These files are written to be read next to the catalogue."""
    blueprint = ready(DefinitionKind.STATE)
    code = blueprint.source_code()
    imports = code.split(")")[0]

    assert "StateDefinition" in imports
    assert "parse_color" in imports and "scale_color" in imports
    assert "position_for_angle" not in imports
    assert "DurationField" not in imports


def test_the_generated_source_uses_the_house_quoting():
    code = ready(DefinitionKind.STATE).source_code()
    assert 'id="studio_demo"' in code
    assert "'" not in code.split("def render")[0].replace("'''", "")


def test_a_helper_used_in_the_body_is_imported():
    blueprint = ready(DefinitionKind.STATE)
    blueprint.render_body = (
        "        frame = ctx.blank_frame()\n"
        '        frame[position_for_angle(90.0, ctx.led_count)] = parse_color("#FFFFFF")\n'
        "        return frame"
    )
    assert "position_for_angle" in blueprint.source_code()
    assert blueprint.problems() == []


def test_the_generated_source_is_importable_python(tmp_path):
    root = ready(DefinitionKind.CONTROLLED_OVERLAY, effect_id="studio_overlay").write(tmp_path)
    effect_class = import_effect_class(load_effect_source(root))
    assert effect_class.__name__ == "StudioOverlay"


def test_a_body_that_does_not_run_is_caught_when_it_is_written(tmp_path):
    """The source validator renders at several ring sizes; a body that throws
    is found there rather than the first time the effect is used."""
    blueprint = ready(DefinitionKind.STATE)
    blueprint.render_body = "        return [1] * (ctx.led_count + 1)"
    with pytest.raises(SourceError):
        blueprint.write(tmp_path)


def test_the_manifest_points_at_the_class_that_was_generated(tmp_path):
    root = ready(DefinitionKind.EVENT, effect_id="studio_event").write(tmp_path)
    manifest = (root / "effect.yaml").read_text(encoding="utf-8")
    assert "entry_class: StudioEvent" in manifest
    assert "source_id: demo-set" in manifest


def test_a_definition_lands_in_the_folder_its_form_belongs_to():
    assert ready(DefinitionKind.STATE).folder == "states"
    assert ready(DefinitionKind.CONTROLLED_OVERLAY).folder == "overlays"
    assert ready(DefinitionKind.TIMED_OVERLAY).folder == "overlays"
    assert ready(DefinitionKind.EVENT).folder == "events"


def test_a_composed_definition_survives_every_colour_model(tmp_path):
    """Each model demands its own config fields; the editor fills them in."""
    for model in ColorModel:
        blueprint = ready(DefinitionKind.STATE, effect_id=f"studio_{model.value}")
        blueprint.color_model = model
        blueprint.parameters = []
        blueprint.add_missing_parameters()
        blueprint.composition = CompositionMode.OPAQUE
        blueprint.render_body = "        return ctx.blank_frame()"
        assert blueprint.problems() == [], (model, blueprint.problems())
        blueprint.write(tmp_path)
