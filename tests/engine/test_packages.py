"""The lefx/3 archive format, verified without help from the builder.

These archives are assembled by hand on purpose. If the loader only ever saw
output from our own builder, the two could drift together and still agree.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from lefx.engine import (
    EffectLibrary,
    PackageError,
    build_package_manifest,
    load_source,
    serialize_definition,
)
from lefx.engine.packages import sha256_of

from .sample_effects import SolidState

EFFECT_SOURCE = '''
from lefx.sdk import (
    BaseEffect, ColorModel, ParamDefinition, ParamType, RenderContext,
    StateDefinition, StateSlot, parse_color,
)


class SolidState(BaseEffect):
    definition = StateDefinition(
        id="solid_state",
        title="Solid State",
        description="Fills the ring with one colour.",
        parameter_schema={
            "color": ParamDefinition(name="color", type=ParamType.COLOR, default="blue"),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT,
                default=1.0, minimum=0.0, maximum=1.0,
            ),
        },
        color_model=ColorModel.MONO,
        slots=(StateSlot.PRIMARY, StateSlot.BACKGROUND),
        restorable=True,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        return [parse_color(ctx.params["color"])] * ctx.led_count
'''


def build_lefx(
    path: Path,
    *,
    manifest: dict | None = None,
    source: str = EFFECT_SOURCE,
    presets: dict | None = None,
    tamper: bool = False,
) -> Path:
    payload = build_package_manifest(
        SolidState.definition,
        source_id="core-set",
        package_id="core-set.solid_state",
        entry_module="effect",
        entry_class="SolidState",
    )
    if manifest is not None:
        payload.update(manifest)

    members: dict[str, bytes] = {
        "manifest.json": json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
        "payload/__init__.py": b"",
        "payload/effect.py": source.encode("utf-8"),
    }
    if presets is not None:
        members["effect-presets.json"] = json.dumps({"presets": presets}).encode("utf-8")

    hashes = {"files": {name: sha256_of(data) for name, data in members.items()}}
    if tamper:
        members["payload/effect.py"] = (source + "\n# altered after the build\n").encode("utf-8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
        archive.writestr("hashes.json", json.dumps(hashes, indent=2, sort_keys=True))
    return path


def build_lefxset(path: Path, members: dict[str, Path], *, set_id: str = "core-set") -> Path:
    manifest = {
        "format": "lefxset/3",
        "set_id": set_id,
        "source_id": "core-set",
        "title": "Core Set",
        "version": 1,
        "effects": sorted(members),
    }
    entries: dict[str, bytes] = {
        "set-manifest.json": json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    }
    for name, member_path in members.items():
        entries[f"effects/{name}"] = member_path.read_bytes()

    hashes = {"files": {name: sha256_of(data) for name, data in entries.items()}}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        archive.writestr("hashes.json", json.dumps(hashes, indent=2, sort_keys=True))
    return path


# -- manifests --------------------------------------------------------------


def test_a_definition_serializes_to_a_form_that_round_trips_its_contract():
    payload = serialize_definition(SolidState.definition)
    assert payload["kind"] == "state"
    assert payload["form"] == {"slots": ["primary", "background"], "restorable": True}
    assert payload["parameter_schema"]["color"]["default"] == "#0000FF"
    assert payload["visual"]["color_model"] == "mono"
    assert payload["runtime_input_schema"] == {}
    assert payload["input_sampling"] is None


def test_a_declared_default_is_distinguishable_from_no_default():
    from lefx.sdk import ParamDefinition, ParamType

    with_default = serialize_definition(SolidState.definition)["parameter_schema"]["color"]
    assert "default" in with_default

    from lefx.engine.packages import serialize_param

    bare = serialize_param(
        ParamDefinition(name="direction_deg", type=ParamType.ANGLE_DEG, required=True, nullable=True)
    )
    assert "default" not in bare


# -- loading ----------------------------------------------------------------


def test_a_well_formed_package_loads_and_carries_its_definition(tmp_path):
    source = load_source(build_lefx(tmp_path / "solid.lefx"))
    assert source.kind == "package"
    assert source.source_id == "core-set"
    package = source.packages[0]
    assert package.effect_id == "solid_state"
    assert package.definition.id == "solid_state"
    assert package.effect_class.get_definition().title == "Solid State"


def test_a_loaded_package_actually_renders(tmp_path):
    from lefx.engine import EffectRuntime, EngineConfig, build_registry

    source = load_source(build_lefx(tmp_path / "solid.lefx"))
    registry = build_registry([source.packages[0].effect_class], source_id="core-set")
    engine = EffectRuntime(registry, config=EngineConfig(led_count=3))
    engine.set_state("solid_state", {"color": "rot"}, now=0.0)
    assert engine.render_once(now=0.0).leds == (0xFF0000,) * 3


def test_an_altered_payload_is_refused(tmp_path):
    with pytest.raises(PackageError, match="altered after it was built"):
        load_source(build_lefx(tmp_path / "solid.lefx", tamper=True))


def test_an_unrecorded_file_is_refused(tmp_path):
    path = build_lefx(tmp_path / "solid.lefx")
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("payload/sneaky.py", "print('hello')")
    with pytest.raises(PackageError, match="not part of the build"):
        load_source(path)


def test_an_older_format_is_refused_rather_than_guessed(tmp_path):
    with pytest.raises(PackageError, match="V1 and V2 packages are not read"):
        load_source(build_lefx(tmp_path / "solid.lefx", manifest={"format": "lefx/2"}))


def test_an_unknown_manifest_key_is_refused(tmp_path):
    with pytest.raises(PackageError, match="unknown keys: commands"):
        load_source(build_lefx(tmp_path / "solid.lefx", manifest={"commands": []}))


def test_a_manifest_that_drifted_from_its_class_is_refused(tmp_path):
    drifted = build_package_manifest(
        SolidState.definition,
        source_id="core-set",
        package_id="core-set.solid_state",
        entry_module="effect",
        entry_class="SolidState",
    )
    drifted["definition"]["visual"]["composition"] = "transparent"
    with pytest.raises(PackageError, match="visual.composition"):
        load_source(build_lefx(tmp_path / "solid.lefx", manifest={"definition": drifted["definition"]}))


def test_a_missing_entry_class_is_reported_clearly(tmp_path):
    with pytest.raises(PackageError, match="entry class 'Missing'"):
        load_source(build_lefx(tmp_path / "solid.lefx", manifest={"entry_class": "Missing"}))


def test_an_unsupported_file_extension_is_refused(tmp_path):
    stray = tmp_path / "solid.zip"
    build_lefx(stray)
    with pytest.raises(PackageError, match="not a LEFX source"):
        load_source(stray)


# -- presets ----------------------------------------------------------------


def test_presets_travel_with_their_package(tmp_path):
    source = load_source(
        build_lefx(
            tmp_path / "solid.lefx",
            presets={
                "solid_calm": {
                    "title": "Solid Calm",
                    "params": {"color": "#4A7BFF", "brightness": 0.45},
                }
            },
        )
    )
    preset = source.packages[0].presets[0]
    assert preset.preset_id == "solid_calm"
    assert preset.effect_id == "solid_state"
    assert preset.source_id == "core-set"


def test_a_preset_with_unknown_keys_is_refused(tmp_path):
    with pytest.raises(PackageError, match="unknown keys: inputs"):
        load_source(
            build_lefx(
                tmp_path / "solid.lefx",
                presets={"bad": {"params": {}, "inputs": {"direction_deg": 1}}},
            )
        )


# -- sets -------------------------------------------------------------------


def test_a_set_loads_every_member(tmp_path):
    member = build_lefx(tmp_path / "solid.lefx")
    bundle = build_lefxset(tmp_path / "core.lefxset", {"solid.lefx": member})
    source = load_source(bundle)
    assert source.kind == "set"
    assert [package.effect_id for package in source.packages] == ["solid_state"]


def test_a_member_from_another_source_namespace_is_refused(tmp_path):
    member = build_lefx(tmp_path / "solid.lefx", manifest={"source_id": "other"})
    bundle = build_lefxset(tmp_path / "core.lefxset", {"solid.lefx": member})
    with pytest.raises(PackageError, match="every member shares"):
        load_source(bundle)


def test_a_set_that_lists_a_missing_member_is_refused(tmp_path):
    member = build_lefx(tmp_path / "solid.lefx")
    bundle = build_lefxset(tmp_path / "core.lefxset", {"solid.lefx": member})
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("set-manifest.json"))
    manifest["effects"].append("ghost.lefx")

    entries = {"set-manifest.json": json.dumps(manifest, sort_keys=True).encode("utf-8")}
    with zipfile.ZipFile(bundle) as archive:
        entries["effects/solid.lefx"] = archive.read("effects/solid.lefx")
    hashes = {"files": {name: sha256_of(data) for name, data in entries.items()}}
    with zipfile.ZipFile(bundle, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        archive.writestr("hashes.json", json.dumps(hashes, sort_keys=True))

    with pytest.raises(PackageError, match="not in the archive"):
        load_source(bundle)


# -- the library ------------------------------------------------------------


def test_the_library_discovers_packages_below_its_search_paths(tmp_path):
    nested = tmp_path / "packages"
    nested.mkdir(parents=True, exist_ok=True)
    build_lefx(nested / "solid.lefx")
    library = EffectLibrary(search_paths=[tmp_path])
    assert "solid_state" in library.registry.effects
    assert library.sources()[0]["autodiscovered"] is True
    library.close()


def test_a_broken_source_reports_itself_without_taking_the_others_down(tmp_path):
    good = tmp_path / "good"
    good.mkdir()
    build_lefx(good / "solid.lefx")
    (good / "broken.lefx").write_bytes(b"not a zip at all")

    library = EffectLibrary(search_paths=[good])
    assert "solid_state" in library.registry.effects
    broken = [entry for entry in library.sources() if entry["error"]]
    assert len(broken) == 1
    assert broken[0]["path"].endswith("broken.lefx")
    library.close()


def test_removing_a_source_rebuilds_without_it(tmp_path):
    build_lefx(tmp_path / "solid.lefx")
    library = EffectLibrary(search_paths=[tmp_path])
    assert len(library.registry) == 1
    library.remove_source("core-set")
    assert len(library.registry) == 0
    library.close()


def test_an_added_source_is_registered_immediately(tmp_path):
    path = build_lefx(tmp_path / "solid.lefx")
    library = EffectLibrary()
    assert len(library.registry) == 0
    entry = library.add_source(path)
    assert entry.source_id == "core-set"
    assert entry.effect_count == 1
    assert len(library.registry) == 1
    library.close()
