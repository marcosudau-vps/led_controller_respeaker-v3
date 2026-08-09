"""Scaffolding, source validation, the import boundary and the build."""

from __future__ import annotations

import json
import zipfile

import pytest

from lefx.effect_creation import (
    SourceError,
    check_imports,
    init_effect_set_source,
    init_effect_source,
    load_effect_source,
    pack_effect,
    pack_effect_set,
    validate_effect_set_source,
    validate_effect_source,
)
from lefx.effect_creation.cli import main as cli_main
from lefx.engine import PackageError, load_source

KINDS = ("state", "controlled_overlay", "timed_overlay", "event")


def scaffold(tmp_path, kind="state", effect_id="sample_effect", source_id="test-set"):
    root = tmp_path / effect_id
    init_effect_source(root, effect_id=effect_id, source_id=source_id, kind=kind)
    return root


# -- scaffolding ------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_every_scaffold_validates_as_generated(tmp_path, kind):
    """A starting point that does not work is worse than none."""
    report = validate_effect_source(scaffold(tmp_path, kind=kind))
    assert report.ok, report.errors
    assert report.details["kind"] == kind
    assert report.details["preset_count"] == 1


@pytest.mark.parametrize("kind", KINDS)
def test_every_scaffold_packs_and_loads_back(tmp_path, kind):
    root = scaffold(tmp_path, kind=kind)
    result = pack_effect(root, tmp_path / "out.lefx")
    assert result["ok"]
    assert load_source(result["path"]).packages[0].effect_id == "sample_effect"


def test_an_unknown_kind_is_refused():
    with pytest.raises(SourceError, match="Unknown definition kind"):
        init_effect_source("unused", effect_id="x", source_id="y", kind="widget")


def test_scaffolding_refuses_to_overwrite_by_accident(tmp_path):
    root = scaffold(tmp_path)
    with pytest.raises(SourceError, match="not empty"):
        init_effect_source(root, effect_id="sample_effect", source_id="test-set")
    init_effect_source(root, effect_id="sample_effect", source_id="test-set", force=True)


# -- source manifests -------------------------------------------------------


def test_the_manifest_carries_placement_only(tmp_path):
    source = load_effect_source(scaffold(tmp_path))
    assert source.source_id == "test-set"
    assert source.entry_module == "effect"
    assert source.entry_class == "SampleEffect"


def test_contract_fields_in_the_manifest_are_refused(tmp_path):
    root = scaffold(tmp_path)
    (root / "effect.yaml").write_text(
        "source_id: test-set\ntype: state\ntitle: Sample\n", encoding="utf-8"
    )
    with pytest.raises(SourceError, match="which V3 does not use"):
        load_effect_source(root)


def test_an_unknown_manifest_key_is_refused(tmp_path):
    root = scaffold(tmp_path)
    (root / "effect.yaml").write_text("source_id: test-set\nspeed: 2\n", encoding="utf-8")
    with pytest.raises(SourceError, match="unknown keys: speed"):
        load_effect_source(root)


def test_two_manifests_are_refused(tmp_path):
    root = scaffold(tmp_path)
    (root / "effect.json").write_text('{"source_id": "test-set"}', encoding="utf-8")
    with pytest.raises(SourceError, match="several manifests"):
        load_effect_source(root)


def test_a_json_manifest_works_too(tmp_path):
    root = scaffold(tmp_path)
    (root / "effect.yaml").unlink()
    (root / "effect.json").write_text(
        json.dumps({"source_id": "test-set", "entry_class": "SampleEffect"}), encoding="utf-8"
    )
    assert validate_effect_source(root).ok


# -- the import boundary ----------------------------------------------------


def test_the_sdk_and_a_stdlib_subset_are_available(tmp_path):
    root = scaffold(tmp_path)
    (root / "geometry.py").write_text(
        "import math\nfrom lefx.sdk import parse_color\n", encoding="utf-8"
    )
    assert check_imports(root) == []


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("import os", "not in the allowed"),
        ("import socket", "not in the allowed"),
        ("from lefx.engine import EffectRuntime", "only lefx.sdk is available"),
        ("import lefx.device.respeaker", "only lefx.sdk is available"),
        ("from lefx.interfaces import ControllerService", "only lefx.sdk is available"),
    ],
)
def test_reaching_outside_the_package_is_refused(tmp_path, statement, expected):
    root = scaffold(tmp_path)
    (root / "effect.py").write_text(
        statement + "\n" + (root / "effect.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    report = validate_effect_source(root)
    assert not report.ok
    assert any(expected in error for error in report.errors)


def test_relative_imports_inside_the_source_are_fine(tmp_path):
    root = scaffold(tmp_path)
    (root / "geometry.py").write_text("STEP = 3\n", encoding="utf-8")
    text = (root / "effect.py").read_text(encoding="utf-8")
    (root / "effect.py").write_text("from .geometry import STEP\n" + text, encoding="utf-8")
    assert validate_effect_source(root).ok


def test_a_generic_shared_module_is_refused(tmp_path):
    """The shape that makes packages stop being independently installable."""
    root = scaffold(tmp_path)
    (root / "common.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    report = validate_effect_source(root)
    assert not report.ok
    assert any("generic shared modules" in error for error in report.errors)


# -- definition rules -------------------------------------------------------


def test_a_source_must_declare_exactly_one_definition(tmp_path):
    root = scaffold(tmp_path)
    (root / "effect.yaml").write_text("source_id: test-set\n", encoding="utf-8")
    text = (root / "effect.py").read_text(encoding="utf-8")
    (root / "effect.py").write_text(
        text + "\n\nclass Second(BaseEffect):\n    definition = SampleEffect.definition\n\n"
        "    def render(self, ctx):\n        return ctx.blank_frame()\n",
        encoding="utf-8",
    )
    report = validate_effect_source(root)
    assert not report.ok
    assert any("exactly one" in error for error in report.errors)


def test_a_source_with_no_definition_is_refused(tmp_path):
    root = scaffold(tmp_path)
    (root / "effect.py").write_text("VALUE = 1\n", encoding="utf-8")
    report = validate_effect_source(root)
    assert any("no BaseEffect subclass" in error for error in report.errors)


def test_a_directory_name_that_disagrees_is_a_warning_not_an_error(tmp_path):
    root = tmp_path / "different_name"
    init_effect_source(root, effect_id="sample_effect", source_id="test-set")
    report = validate_effect_source(root)
    assert report.ok
    assert any("directory is" in warning for warning in report.warnings)


# -- the smoke render -------------------------------------------------------


def test_a_frame_of_the_wrong_length_fails_the_build(tmp_path):
    root = scaffold(tmp_path)
    text = (root / "effect.py").read_text(encoding="utf-8")
    text = text.replace(
        "return [color] * ctx.led_count", "return [color] * 12  # hardcoded ring size"
    )
    (root / "effect.py").write_text(text, encoding="utf-8")
    report = validate_effect_source(root)
    assert not report.ok
    assert any("positions, expected 5" in error for error in report.errors)


def test_an_opaque_definition_returning_none_fails_the_build(tmp_path):
    root = scaffold(tmp_path)
    text = (root / "effect.py").read_text(encoding="utf-8")
    text = text.replace("return [color] * ctx.led_count", "return [None] * ctx.led_count")
    (root / "effect.py").write_text(text, encoding="utf-8")
    report = validate_effect_source(root)
    assert any("declared opaque but returned None" in error for error in report.errors)


def test_a_render_that_raises_is_reported_with_its_ring_size(tmp_path):
    root = scaffold(tmp_path)
    text = (root / "effect.py").read_text(encoding="utf-8")
    text = text.replace("return [color] * ctx.led_count", "raise RuntimeError('boom')")
    (root / "effect.py").write_text(text, encoding="utf-8")
    report = validate_effect_source(root)
    assert any("failed to render at 5 LEDs" in error for error in report.errors)


# -- presets ----------------------------------------------------------------


def test_a_preset_outside_the_schema_fails_validation(tmp_path):
    root = scaffold(tmp_path)
    (root / "presets.yaml").write_text(
        "presets:\n  bad:\n    params:\n      color: not-a-color\n", encoding="utf-8"
    )
    report = validate_effect_source(root)
    assert any("does not satisfy the schema" in error for error in report.errors)


def test_a_preset_may_not_carry_runtime_inputs(tmp_path):
    root = scaffold(tmp_path, kind="controlled_overlay")
    (root / "presets.yaml").write_text(
        "presets:\n  bad:\n    params: {}\n    inputs:\n      direction_deg: 90\n",
        encoding="utf-8",
    )
    report = validate_effect_source(root)
    assert any("carries configuration only" in error for error in report.errors)


def test_presets_travel_into_the_built_package(tmp_path):
    root = scaffold(tmp_path)
    result = pack_effect(root, tmp_path / "out.lefx")
    assert result["preset_count"] == 1
    loaded = load_source(result["path"])
    assert loaded.packages[0].presets[0].preset_id == "sample_effect_default"


# -- building ---------------------------------------------------------------


def test_a_failing_source_is_not_packed(tmp_path):
    root = scaffold(tmp_path)
    (root / "common.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(SourceError, match="did not validate"):
        pack_effect(root, tmp_path / "out.lefx")
    assert not (tmp_path / "out.lefx").exists()


def test_the_archive_contains_only_payload_and_metadata(tmp_path):
    root = scaffold(tmp_path)
    (root / "assets").mkdir()
    (root / "assets" / "curve.json").write_text("[]", encoding="utf-8")
    result = pack_effect(root, tmp_path / "out.lefx")

    with zipfile.ZipFile(result["path"]) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "hashes.json" in names
    assert "effect-presets.json" in names
    assert "payload/effect.py" in names
    assert "payload/assets/curve.json" in names
    # Source manifests are build inputs, not payload.
    assert "payload/effect.yaml" not in names
    assert "payload/presets.yaml" not in names


def test_local_modules_and_assets_ship_with_the_package(tmp_path):
    root = scaffold(tmp_path)
    (root / "geometry.py").write_text("STEP = 3\n", encoding="utf-8")
    text = (root / "effect.py").read_text(encoding="utf-8")
    (root / "effect.py").write_text("from .geometry import STEP\n" + text, encoding="utf-8")

    result = pack_effect(root, tmp_path / "out.lefx")
    loaded = load_source(result["path"])
    assert loaded.packages[0].effect_id == "sample_effect"


# -- sets -------------------------------------------------------------------


def build_set(tmp_path, ids=("first_effect", "second_effect")):
    set_root = tmp_path / "my-set"
    init_effect_set_source(set_root, set_id="my-set", source_id="my-set")
    for effect_id in ids:
        source = tmp_path / "sources" / effect_id
        init_effect_source(source, effect_id=effect_id, source_id="my-set")
        pack_effect(source, set_root / "effects" / f"{effect_id}.lefx")
    return set_root


def test_a_set_builds_from_prebuilt_packages(tmp_path):
    set_root = build_set(tmp_path)
    report = validate_effect_set_source(set_root)
    assert report.ok, report.errors

    result = pack_effect_set(set_root, tmp_path / "my-set.lefxset")
    assert result["effect_count"] == 2
    assert result["preset_count"] == 2

    loaded = load_source(result["path"])
    assert sorted(package.effect_id for package in loaded.packages) == [
        "first_effect",
        "second_effect",
    ]


def test_a_member_from_another_namespace_fails_the_set(tmp_path):
    set_root = build_set(tmp_path, ids=("first_effect",))
    stray = tmp_path / "sources" / "stray"
    init_effect_source(stray, effect_id="stray_effect", source_id="somewhere-else")
    pack_effect(stray, set_root / "effects" / "stray.lefx")

    report = validate_effect_set_source(set_root)
    assert not report.ok
    assert any("shares the set's namespace" in error for error in report.errors)


def test_an_empty_set_is_refused(tmp_path):
    set_root = tmp_path / "empty-set"
    init_effect_set_source(set_root, set_id="empty-set", source_id="empty-set")
    with pytest.raises(SourceError, match="no built .lefx packages"):
        validate_effect_set_source(set_root)


# -- the command line -------------------------------------------------------


def test_the_cli_runs_the_whole_chain(tmp_path, capsys):
    source = tmp_path / "cli_effect"
    assert cli_main(
        ["init", str(source), "--effect-id", "cli_effect", "--source-id", "cli-set"]
    ) == 0
    capsys.readouterr()

    assert cli_main(["validate", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

    output = tmp_path / "cli_effect.lefx"
    assert cli_main(["build", str(source), str(output)]) == 0
    capsys.readouterr()

    assert cli_main(["verify", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["effects"] == ["cli_effect"]

    assert cli_main(["inspect", str(output)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["packages"][0]["form"] == "state"
    assert payload["packages"][0]["config"] == ["brightness", "color"]


def test_the_cli_reports_a_failure_on_stderr_and_exits_nonzero(tmp_path, capsys):
    assert cli_main(["verify", str(tmp_path / "missing.lefx")]) == 1
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_the_cli_reports_an_invalid_source_without_raising(tmp_path, capsys):
    root = scaffold(tmp_path)
    (root / "common.py").write_text("X = 1\n", encoding="utf-8")
    assert cli_main(["validate", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
