"""Writing a preset back into the source it came from.

The studio plays built packages, and a preset kept only there would last until
the next build. So the interesting part is the trip back: finding the source
directory a loaded definition came from, and leaving that source in a state the
build will still accept.

Qt-free — the dialog collects the words, this decides what happens to them.
"""

from __future__ import annotations

import shutil

import pytest
import yaml

from lefx.effect_creation import SourceError, import_effect_class, load_effect_source, validate_effect_source
from lefx.effect_creation.studio.authoring import (
    PresetDraft,
    check_draft,
    find_source_dir,
    read_presets,
    slugify,
    suggest_preset_id,
    write_preset,
    write_preset_checked,
)

from tests.architecture.scan import REPO_ROOT


@pytest.fixture
def source(tmp_path):
    """A throwaway copy of a real source, so writing to it costs nothing."""
    original = REPO_ROOT / "effects/core-set/sources/states/solid_fill"
    target = tmp_path / "effects/core-set/sources/states/solid_fill"
    target.parent.mkdir(parents=True)
    shutil.copytree(original, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


@pytest.fixture
def definition(source):
    return import_effect_class(load_effect_source(source)).definition


# -- naming -----------------------------------------------------------------


def test_a_label_becomes_a_usable_id():
    assert suggest_preset_id("solid_fill", "Ruhiges Blau") == "solid_fill_ruhiges_blau"
    assert suggest_preset_id("solid_fill", "  Warm  Amber ") == "solid_fill_warm_amber"


def test_an_id_is_prefixed_because_presets_share_one_namespace():
    """A preset called 'warm' collides with the second catalogue that has one."""
    assert suggest_preset_id("solid_fill", "warm").startswith("solid_fill_")


def test_an_already_prefixed_label_is_not_prefixed_twice():
    assert suggest_preset_id("solid_fill", "solid_fill_calm") == "solid_fill_calm"


def test_a_label_with_nothing_usable_in_it_falls_back_to_the_effect_id():
    assert suggest_preset_id("solid_fill", "!!!") == "solid_fill"


def test_slugify_keeps_only_what_an_id_may_contain():
    assert slugify("Ruhiges Blau (kalt)") == "ruhiges_blau_kalt"


# -- finding the way back ---------------------------------------------------


def test_a_definition_is_traced_to_the_source_it_was_built_from():
    found = find_source_dir("solid_fill", [REPO_ROOT / "effects"])
    assert found is not None
    assert found.name == "solid_fill"
    assert (found / "effect.py").is_file()


def test_a_directory_that_only_shares_a_name_is_not_mistaken_for_a_source(tmp_path):
    decoy = tmp_path / "effects/pretend/sources/states/solid_fill"
    decoy.mkdir(parents=True)
    (decoy / "readme.txt").write_text("not a source", encoding="utf-8")
    assert find_source_dir("solid_fill", [tmp_path / "effects"]) is None


def test_an_unknown_definition_has_no_source():
    assert find_source_dir("not_a_real_effect", [REPO_ROOT / "effects"]) is None


# -- checking before writing ------------------------------------------------


def test_a_draft_that_matches_the_schema_has_nothing_wrong_with_it(definition):
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="solid_fill_test", title="Test",
        description="", params={"color": "#123456", "brightness": 0.5},
    )
    assert check_draft(definition, draft) == []


def test_an_id_that_does_not_carry_the_effect_name_is_refused(definition):
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="warm", title="", description="",
        params={"color": "#123456"},
    )
    assert any("beginnen" in problem for problem in check_draft(definition, draft))


def test_values_outside_the_schema_are_caught_while_they_are_still_on_screen(definition):
    """Rather than at build time, somewhere else, later."""
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="solid_fill_bad", title="", description="",
        params={"brightness": 5.0},
    )
    assert any("Schema" in problem for problem in check_draft(definition, draft))


def test_an_empty_id_is_refused(definition):
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="", title="", description="", params={}
    )
    assert check_draft(definition, draft)


# -- writing ----------------------------------------------------------------


def test_a_preset_lands_in_the_source_and_the_source_still_validates(source, definition):
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="solid_fill_studio", title="Studio",
        description="Made while looking at it.",
        params={"color": "#204080", "brightness": 0.7},
    )
    written = write_preset_checked(definition, source, draft)

    assert written.is_file()
    stored = read_presets(source)["solid_fill_studio"]
    assert stored["params"]["color"] == "#204080"
    assert stored["title"] == "Studio"
    assert stored["description"].startswith("Made while")
    assert validate_effect_source(source).ok


def test_the_presets_that_were_already_there_survive(source, definition):
    before = set(read_presets(source))
    assert before, "the fixture should start with presets"

    write_preset_checked(
        definition,
        source,
        PresetDraft(effect_id="solid_fill", preset_id="solid_fill_new", title="New",
                    description="", params={"color": "#FFFFFF"}),
    )
    assert before < set(read_presets(source))


def test_an_existing_preset_is_not_overwritten_by_accident(source, definition):
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="solid_fill_calm_blue", title="Taken",
        description="", params={"color": "#000000"},
    )
    with pytest.raises(SourceError, match="already exists"):
        write_preset_checked(definition, source, draft)


def test_overwriting_is_possible_when_it_is_asked_for(source, definition):
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="solid_fill_calm_blue", title="Replaced",
        description="", params={"color": "#010203"},
    )
    write_preset_checked(definition, source, draft, overwrite=True)
    assert read_presets(source)["solid_fill_calm_blue"]["params"]["color"] == "#010203"


def test_a_write_that_would_break_the_source_is_rolled_back(source, definition, monkeypatch):
    """A source that stops validating is worse than a preset never written."""
    from lefx.effect_creation.studio import authoring

    original = (source / "presets.yaml").read_text(encoding="utf-8")

    # Slip past the pre-check to reach the validator, which is the backstop
    # this is about: something the draft check did not think of.
    monkeypatch.setattr(authoring, "check_draft", lambda *_: [])
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="solid_fill_broken", title="",
        description="", params={"brightness": "not a number"},
    )
    with pytest.raises(SourceError, match="no longer validate"):
        authoring.write_preset_checked(definition, source, draft)

    assert (source / "presets.yaml").read_text(encoding="utf-8") == original
    assert validate_effect_source(source).ok


def test_a_source_with_no_presets_yet_gets_a_file(tmp_path, source, definition):
    (source / "presets.yaml").unlink()
    assert read_presets(source) == {}

    written = write_preset_checked(
        definition,
        source,
        PresetDraft(effect_id="solid_fill", preset_id="solid_fill_first", title="First",
                    description="", params={"color": "#0A0B0C"}),
    )
    assert written.name == "presets.yaml"
    assert set(read_presets(source)) == {"solid_fill_first"}


def test_the_file_stays_a_document_that_loads(source, definition):
    write_preset_checked(
        definition,
        source,
        PresetDraft(effect_id="solid_fill", preset_id="solid_fill_x", title="Ümläute",
                    description="Mit Umlauten und : Doppelpunkt", params={"color": "#111111"}),
    )
    payload = yaml.safe_load((source / "presets.yaml").read_text(encoding="utf-8"))
    assert "presets" in payload
    assert payload["presets"]["solid_fill_x"]["title"] == "Ümläute"


def test_presets_come_out_in_a_stable_order(source, definition):
    """So a file written twice does not show up as a reordering in a diff."""
    for label in ("zebra", "alpha", "mike"):
        write_preset_checked(
            definition,
            source,
            PresetDraft(effect_id="solid_fill", preset_id=f"solid_fill_{label}",
                        title=label, description="", params={"color": "#222222"}),
        )
    written = list(read_presets(source))
    assert written == sorted(written)


def test_writing_the_raw_way_still_refuses_a_duplicate(source):
    draft = PresetDraft(
        effect_id="solid_fill", preset_id="solid_fill_calm_blue", title="", description="",
        params={"color": "#000000"},
    )
    with pytest.raises(SourceError):
        write_preset(source, draft)
