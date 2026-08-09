"""What V1 was, and must not become again.

The generation before this one carried two systems at once: a documented layered
path and, underneath it, a set of named application states wired directly into
the engine — a background state, a countdown, an offline state the service set
by hand when the USB connection dropped. The whole reason this repository exists
is that removing them from a running system turned out to be harder than
starting again without them.

Nothing stops them coming back one convenience at a time, so the names are
listed here and the listing is checked.

Two things this must not do. It must not fail on prose: a comment explaining
that there is deliberately no offline state names the term, and rewording it
would be the wrong way to make a test pass. And it must not fail on the current
catalogue: ``countdown_ring`` is a V3 timed overlay with a duration and no
special standing anywhere — the V1 concept was ``CountdownState``, a state the
engine knew by name, and that distinction is the point rather than an exemption.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .scan import REPO_ROOT, code_strings_and_names, parse

# Names that carried V1 semantics. Matched against identifiers and string values
# in the code, whole word or dotted attribute — never against comments.
FORBIDDEN_NAMES = frozenset(
    {
        # Named application states the engine itself knew.
        "base_state",
        "BaseState",
        "BASE_STATE_NAMES",
        "CountdownState",
        "countdown_state",
        "EVENT_NAMES",
        "LEGACY_SCENE_NAMES",
        # The scene indirection the composer no longer builds.
        "Scene",
        "Visual",
        "LayerVisual",
        "main_layer_valid",
        # Schema fields that V3 derives from the definition type instead.
        "layer_rules",
        "EffectCapabilities",
        # Command surfaces that were replaced rather than kept alongside.
        "ControllerCommandNormalizer",
        "set_progress",
        "set_direction",
        "stt_adapter",
    }
)

# Substrings, for the things that are not identifiers.
FORBIDDEN_FRAGMENTS = ("api/v1", "LEGACY_", "lefx/1", "lefx/2", "lefxset/1", "lefxset/2")

# What the rule is about: code that runs, and the definitions and metadata that
# run with it. Planning documents record what was removed and say the names out
# loud; tests name them to check them. Neither is a regression.
PRODUCTION_TREES = (
    REPO_ROOT / "packages",
    REPO_ROOT / "effects",
    REPO_ROOT / "scripts",
)

PYTHON_SKIP_PARTS = frozenset({"__pycache__", "build", "dist", ".venv"})
TEXT_SUFFIXES = (".yaml", ".yml", ".json", ".toml")


def production_python() -> list[Path]:
    found: list[Path] = []
    for tree in PRODUCTION_TREES:
        for path in tree.rglob("*.py"):
            if PYTHON_SKIP_PARTS.isdisjoint(path.parts):
                found.append(path)
    return sorted(found)


def production_metadata() -> list[Path]:
    found: list[Path] = []
    for tree in PRODUCTION_TREES:
        for suffix in TEXT_SUFFIXES:
            for path in tree.rglob(f"*{suffix}"):
                if PYTHON_SKIP_PARTS.isdisjoint(path.parts):
                    found.append(path)
    return sorted(found)


PYTHON_FILES = production_python()
METADATA_FILES = production_metadata()


def label(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def test_the_scan_actually_covers_the_running_code():
    """A rule over an empty file list passes forever. Establish it is not."""
    covered = {label(path) for path in PYTHON_FILES}
    assert "packages/led-ctrl-v3/src/lefx/engine/runtime.py" in covered
    assert "packages/led-ctrl-v3/src/lefx/interfaces/service.py" in covered
    assert "effects/core-set/sources/overlays/direction_indicator/effect.py" in covered
    assert len(METADATA_FILES) > 30


@pytest.mark.parametrize("path", PYTHON_FILES, ids=label)
def test_no_v1_name_is_used_in_production_code(path):
    used = code_strings_and_names(parse(path))
    # A dotted value such as "runtime.set_direction" hides the name inside a
    # string; split on the separators a name can be reached through.
    reachable = {part for value in used for part in value.replace(".", " ").split()} | used
    assert reachable & FORBIDDEN_NAMES == set()


@pytest.mark.parametrize("path", PYTHON_FILES + METADATA_FILES, ids=label)
def test_no_v1_surface_is_named_in_production_files(path):
    """The fragments, over the whole file including comments.

    These are unambiguous: no honest comment in a V3 tree contains ``api/v1``,
    and if one did it would be describing a route that must not exist.
    """
    text = path.read_text(encoding="utf-8")
    assert [fragment for fragment in FORBIDDEN_FRAGMENTS if fragment in text] == []


def test_the_only_api_surface_is_v3():
    from lefx.interfaces import API_PREFIX

    assert API_PREFIX == "/api/v3"


def test_the_package_stamps_are_generation_three():
    from lefx.engine.packages.manifest import PACKAGE_FORMAT, SET_FORMAT

    assert PACKAGE_FORMAT == "lefx/3"
    assert SET_FORMAT == "lefxset/3"


def test_countdown_ring_is_an_ordinary_timed_overlay_not_a_state():
    """The catalogue keeps the word; V3 does not keep the concept.

    The V1 countdown was a state the engine resolved by name, with its own
    handling. This is a definition like any other: finite, declared duration, no
    standing anywhere in the engine.
    """
    from lefx.effect_creation import import_effect_class, load_effect_source
    from lefx.sdk import TimedOverlayDefinition

    source = REPO_ROOT / "effects/smartspeaker-set/sources/overlays/countdown_ring"
    definition = import_effect_class(load_effect_source(source)).definition
    assert isinstance(definition, TimedOverlayDefinition)
    assert definition.duration_field is not None
