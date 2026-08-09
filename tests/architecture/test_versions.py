"""One version across the workspace, and the pins that keep it that way.

Nine distributions are released together as one system, so they carry one
version number. Nothing enforces that but this file: a package whose version
drifted would still build, still install, and still resolve — and would quietly
pair a new engine with an old SDK on somebody's machine.

The pins between them are the same rule stated a second way. ``led-ctrl-v3-engine``
depends on ``led-ctrl-v3-sdk==3.0.0``, not ``>=``, because these are not independently
useful libraries; they are one thing cut into pieces that install separately.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from .scan import PACKAGES_ROOT, REPO_ROOT, distributions

ALL_DISTRIBUTIONS = distributions()

INTERNAL = set(ALL_DISTRIBUTIONS)

PIN = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*(?P<spec>.*)$")


def manifest(distribution: str) -> dict:
    path = PACKAGES_ROOT / distribution / "pyproject.toml"
    return tomllib.loads(path.read_bytes().decode("utf-8"))


def workspace_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_bytes().decode("utf-8")
    return tomllib.loads(text)["project"]["version"]


def requirements(distribution: str) -> list[str]:
    project = manifest(distribution)["project"]
    optional = project.get("optional-dependencies", {})
    return [*project.get("dependencies", []), *(item for group in optional.values() for item in group)]


def test_the_workspace_root_carries_a_version_at_all():
    """It is the one scripts/release.py reads and writes from."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", workspace_version())


@pytest.mark.parametrize("distribution", ALL_DISTRIBUTIONS)
def test_every_distribution_carries_the_workspace_version(distribution):
    assert manifest(distribution)["project"]["version"] == workspace_version()


@pytest.mark.parametrize("distribution", ALL_DISTRIBUTIONS)
def test_every_internal_dependency_is_pinned_to_that_exact_version(distribution):
    """``==`` rather than ``>=``, and to this release rather than to any.

    A range here would let pip pair pieces of two releases, which is the one
    failure mode a workspace never sees: everything resolves from the checkout,
    so the mismatch only ever happens on a machine that installed from an index.
    """
    expected = f"=={workspace_version()}"
    wrong = []
    for requirement in requirements(distribution):
        match = PIN.match(requirement.strip())
        assert match, requirement
        name, spec = match["name"], match["spec"].strip()
        if name not in INTERNAL:
            continue
        if spec != expected:
            wrong.append(f"{requirement!r} should pin {expected}")
    assert wrong == []


def test_the_metapackage_names_every_other_distribution_exactly_once():
    """Nothing publishable may be unreachable through led-ctrl-v3.

    A distribution that is built and uploaded but that no extra installs is a
    package nobody can get to except by knowing it exists.
    """
    project = manifest("led-ctrl-v3")["project"]
    named = {
        PIN.match(requirement.strip())["name"]
        for requirement in requirements("led-ctrl-v3")
    }
    assert named == INTERNAL - {"led-ctrl-v3"}

    # And "all" really is all of them, so that one extra is enough to get
    # everything rather than most of it.
    extras = project["optional-dependencies"]
    every = {
        PIN.match(item.strip())["name"]
        for name, group in extras.items() if name != "all"
        for item in group
    }
    inside_all = {PIN.match(item.strip())["name"] for item in extras["all"]}
    assert inside_all == every


def test_the_example_config_and_the_readme_do_not_pin_a_stale_version():
    """Documentation that shows a version has to show this one."""
    stale = []
    for path in (REPO_ROOT / "README.md", *PACKAGES_ROOT.glob("*/README.md")):
        for found in re.findall(r"==(\d+\.\d+\.\d+)", path.read_text(encoding="utf-8")):
            if found != workspace_version():
                stale.append(f"{path.relative_to(REPO_ROOT).as_posix()} names {found}")
    assert stale == []
