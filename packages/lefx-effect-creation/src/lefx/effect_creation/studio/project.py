"""Which checkout the studio is working on.

Run from a source tree, everything the studio needs is findable relative to the
working directory, and that is what the rest of the system assumes: the service
looks beside the cwd for a catalogue, a calibration lands in the cwd. That
assumption is exactly what a standalone build breaks. An executable is started
from wherever it happens to sit — a Start menu, a desktop, a folder of tools —
and "beside the working directory" then means somewhere nobody chose.

So the studio stops inferring and is told: one root, and every path derived from
it. That is not a concession to the frozen build. It is better in the checkout
too, because it makes "which project am I editing" a thing on screen rather than
a property of how the terminal happened to be opened, and it lets one studio
switch between two catalogues without being restarted.

No Qt: where files are is not a question about widgets.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("lefx.effect_creation.studio.project")

CATALOGUE_DIR = "effects"
CALIBRATION_FILE = "doa_calibration.json"
STATE_FILE = "build/studio-state.json"

SET_PACKAGE_DIR = "packages"
"""Where a built set lands: inside the distribution that ships it.

There used to be a ``build/effects`` for this, and it was a third place a
``.lefxset`` could be. Now each set has exactly one home — the package tree of
``lefxset-<name>`` — and that home is the same directory in a checkout, in an
editable workspace and in an installed wheel. A set that is built is a set that
is installed; there is no step in between that can be forgotten.
"""

RECENT_FILE = Path.home() / ".lefx" / "studio.json"
"""Where the last project is remembered.

In the user's home rather than beside the executable: a tool that wrote next to
itself would need to live somewhere writable, and would forget everything the
first time it was copied elsewhere.
"""


@dataclass(slots=True, frozen=True)
class Project:
    """A checkout the studio can read effects from and write sources into."""

    root: Path

    @classmethod
    def at(cls, path: str | Path | None = None) -> "Project":
        """A project at the given path, or at the working directory."""
        return cls(root=Path(path if path is not None else Path.cwd()).expanduser().resolve())

    # -- what lives where ---------------------------------------------------

    @property
    def catalogue_root(self) -> Path:
        """Where effect *sources* live, one directory per set."""
        return self.root / CATALOGUE_DIR

    def build_target(self, set_name: str) -> Path:
        """Where the named set's archive belongs, built or not."""
        return (
            self.root / SET_PACKAGE_DIR / f"lefxset-{set_name}"
            / "src" / "lefx" / "sets" / set_name.replace("-", "_") / f"{set_name}.lefxset"
        )

    @property
    def built_set_dirs(self) -> list[Path]:
        """The directories holding this project's built archives.

        Globbed off the project rather than read from the installed entry
        points on purpose. The studio is pointed at *a checkout* — possibly not
        the one it was built from — and has to show that checkout's catalogue,
        not whichever one happened to be installed alongside the executable.
        """
        found = self.root.glob(f"{SET_PACKAGE_DIR}/lefxset-*/src/lefx/sets/*")
        return sorted(path for path in found if path.is_dir() and path.name != "__pycache__")

    @property
    def package_search_paths(self) -> list[Path]:
        """What the embedded service scans, in the order the service uses.

        The built catalogue first, then the source tree — the same two places
        ``lefx serve`` looks, so the studio shows what the service would load.
        """
        return [*self.built_set_dirs, self.catalogue_root]

    @property
    def calibration_file(self) -> Path:
        return self.root / CALIBRATION_FILE

    @property
    def state_file(self) -> Path:
        """Where the embedded service persists a background state.

        Inside ``build/`` because it is scratch: a studio session should not
        leave a state behind that the next real service picks up.
        """
        return self.root / STATE_FILE

    @property
    def source_roots(self) -> list[Path]:
        return [self.catalogue_root]

    def sets(self) -> list[Path]:
        """Every effect set in the project, found by its manifest."""
        if not self.catalogue_root.is_dir():
            return []
        found = {
            manifest.parent
            for stem in ("set.yaml", "set.yml", "set.json")
            for manifest in self.catalogue_root.glob(f"*/{stem}")
        }
        return sorted(found)

    def sources_in(self, set_root: str | Path) -> list[Path]:
        """The effect sources of one set, in the order a build takes them."""
        root = Path(set_root)
        return sorted(
            {
                manifest.parent
                for stem in ("effect.yaml", "effect.yml", "effect.json")
                for manifest in (root / "sources").rglob(stem)
            }
        )

    # -- whether it is one --------------------------------------------------

    @property
    def looks_like_a_project(self) -> bool:
        """Whether there is anything here for the studio to work on.

        A directory with neither sources nor a built catalogue is not wrong —
        it is where a first effect gets written — but the window should say so
        rather than present an empty list as if it were a finding.
        """
        return self.catalogue_root.is_dir() or bool(self.built_set_dirs)

    @property
    def label(self) -> str:
        return self.root.name or str(self.root)

    def describe(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "catalogue": str(self.catalogue_root),
            "build": [str(path) for path in self.built_set_dirs],
            "sets": [path.name for path in self.sets()],
            "is_project": self.looks_like_a_project,
        }

    # -- building -----------------------------------------------------------

    def build_catalogue(self) -> list[dict[str, Any]]:
        """Build every set in the project, the way the build script does.

        Carried here rather than shelled out to ``scripts/build_effects.py``,
        because a standalone studio has no ``scripts/`` — and because a tool
        that can write a source should be able to build it without asking for a
        terminal. The staging directory is removed afterwards for the same
        reason the script removes it: it sits inside a directory the service
        scans, and every member left there is found a second time.
        """
        import shutil

        from lefx.effect_creation import build_effect_set

        results: list[dict[str, Any]] = []
        for set_root in self.sets():
            target = self.build_target(set_root.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            staging = set_root / "effects"
            if staging.exists():
                shutil.rmtree(staging)
            try:
                results.append(
                    build_effect_set(set_root, self.sources_in(set_root), target)
                )
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        return results


# -- remembering the last one ----------------------------------------------


def remember(project: Project, *, path: Path = RECENT_FILE) -> None:
    """Record the project, so double-clicking the tool reopens it."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"recent": str(project.root)}, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        # Not being able to remember is a smaller problem than refusing to run.
        logger.warning("could not record the recent project: %s", exc)


def recalled(*, path: Path = RECENT_FILE) -> Project | None:
    """The last project, if there was one and it is still there."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    recent = payload.get("recent")
    if not recent:
        return None
    project = Project.at(recent)
    return project if project.root.is_dir() else None


def resolve(explicit: str | Path | None = None, *, path: Path = RECENT_FILE) -> Project:
    """Which project to open: what was asked for, what was last used, or here.

    In that order. An explicit ``--project`` always wins; a frozen build started
    by double-clicking has no useful working directory and falls back to what it
    was last pointed at; a checkout started from its own root gets that root
    without anybody having to say so.
    """
    if explicit is not None:
        return Project.at(explicit)

    here = Project.at()
    if here.looks_like_a_project:
        return here

    remembered = recalled(path=path)
    if remembered is not None:
        return remembered
    return here


def under_a_frozen_build() -> bool:
    """Whether this is running as a standalone executable.

    Only used to decide how loudly to ask for a project: a checkout can guess
    from the working directory, a bundle should not pretend to.
    """
    import sys

    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def iter_paths(project: Project) -> Iterable[tuple[str, Path]]:
    """For the window's status line and for tests to assert against."""
    yield "Wurzel", project.root
    yield "Quellen", project.catalogue_root
    for path in project.built_set_dirs:
        yield f"Gebaut ({path.name})", path
    yield "Kalibrierung", project.calibration_file


__all__ = [
    "CALIBRATION_FILE",
    "CATALOGUE_DIR",
    "SET_PACKAGE_DIR",
    "RECENT_FILE",
    "STATE_FILE",
    "Project",
    "iter_paths",
    "recalled",
    "remember",
    "resolve",
    "under_a_frozen_build",
]
