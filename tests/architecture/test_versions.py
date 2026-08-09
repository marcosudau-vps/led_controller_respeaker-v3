"""One version across the workspace, and the pins that keep it that way.

Three distributions are released together as one system, so they carry one
version number. Nothing enforces that but this file: a package whose version
drifted would still build, still install, and still resolve — and would quietly
pair a new engine with an old SDK on somebody's machine.

The pins between them are the same rule stated a second way. The optional
packages depend on ``ledctrl-v3==<this version>``, not ``>=``, because they are
not independently useful libraries; they are one thing cut where it has to be
cut so that some of it can be left uninstalled.
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


def test_every_optional_distribution_is_reachable_through_an_extra():
    """Nothing publishable may be unreachable through ledctrl-v3.

    A distribution that is built and uploaded but that no extra installs is a
    package nobody can get to except by knowing it exists. ledctrl-v3 is not a
    metapackage any more — it carries the runtime itself — so what has to hold
    is about the extras, not about its dependencies.
    """
    extras = manifest("ledctrl-v3")["project"]["optional-dependencies"]
    named = {
        PIN.match(item.strip())["name"]
        for name, group in extras.items() if name != "all"
        for item in group
    }
    assert named == INTERNAL - {"ledctrl-v3"}

    # And "all" really is all of them, so that one extra is enough to get
    # everything rather than most of it.
    inside_all = {PIN.match(item.strip())["name"] for item in extras["all"]}
    assert inside_all == named


def test_the_runtime_distribution_declares_no_internal_dependency():
    """It is the bottom of the stack; there is nothing under it to depend on.

    An internal dependency here would be a cycle — the two optional packages
    already depend on this one — and pip would be entitled to complain.
    """
    declared = manifest("ledctrl-v3")["project"]["dependencies"]
    internal = [item for item in declared if PIN.match(item.strip())["name"] in INTERNAL]
    assert internal == []


def test_the_example_config_and_the_readme_do_not_pin_a_stale_version():
    """Documentation that shows a version has to show this one."""
    stale = []
    for path in (REPO_ROOT / "README.md", *PACKAGES_ROOT.glob("*/README.md")):
        for found in re.findall(r"==(\d+\.\d+\.\d+)", path.read_text(encoding="utf-8")):
            if found != workspace_version():
                stale.append(f"{path.relative_to(REPO_ROOT).as_posix()} names {found}")
    assert stale == []
