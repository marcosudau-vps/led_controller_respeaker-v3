"""Explicit project and artifact contracts shared by release checks and the mirror."""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEV_REPO = "marcosudau-vps/led_controller_respeaker-v3"
MIRROR_REPO = "marcosudau-vps/led-ctrl-v3"


def canonical_name(name: str) -> str:
    """Normalize a project name according to the Python packaging specification."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Distribution:
    directory: str
    environment: str
    extra: str | None = None
    dependency_extra: str = ""

    @property
    def name(self) -> str:
        return canonical_name(self.directory)

    @property
    def stem(self) -> str:
        return self.name.replace("-", "_")

    def wheel(self, version: str) -> str:
        return f"{self.stem}-{version}-py3-none-any.whl"

    def sdist(self, version: str) -> str:
        return f"{self.stem}-{version}.tar.gz"


CORE = Distribution("led-controller-version-3", "pypi")
STUDIO = Distribution("led-controller-version-3-effect-creation", "pypi-effect-creation", "effect-creation")
SIMULATOR = Distribution(
    "led-controller-version-3-device-simulated-respeaker", "pypi-simulator", "simulated-respeaker", "[gui]"
)
CONFIGURATOR = Distribution("lefx_config_widget", "pypi-configurator", "configurator")
CURRENT = (CORE, STUDIO, SIMULATOR, CONFIGURATOR)

# This released tag predates the integration. An ordinary CI build may still
# use 3.0.4 as the development version, with the current four-project contract.
HISTORIC_VERSION = "3.0.4"
HISTORIC_COMMIT = "5aabd0639aad6c12cdba2bf1b427691d6026b771"
HISTORIC_MIRROR = "f6bd3823170820b123a061d2609c8008bfae708a"
HISTORIC_RUN = "45854688359"
HISTORIC = (CORE, STUDIO, SIMULATOR)


def version_key(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError(f"Invalid release version: {version}")
    return tuple(map(int, version.split(".")))


def require_commit(commit: str) -> None:
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full Git commit SHA is required")


def release_projects(version: str, commit: str) -> tuple[Distribution, ...]:
    """Select a contract using the caller's independently verified release identity."""
    require_commit(commit)
    if (version, commit) == (HISTORIC_VERSION, HISTORIC_COMMIT):
        return HISTORIC
    if version_key(version) <= version_key(HISTORIC_VERSION) or commit == HISTORIC_COMMIT:
        raise ValueError(f"No release contract for v{version} at {commit}")
    return CURRENT


def require_release_identity(version: str, commit: str, *, mirror=None, run_id=None) -> None:
    release_projects(version, commit)
    if mirror is not None:
        require_commit(mirror)
    if commit == HISTORIC_COMMIT and (
        (mirror is not None and mirror != HISTORIC_MIRROR)
        or (run_id is not None and run_id != HISTORIC_RUN)
    ):
        raise ValueError("Historical release identity does not match the original mirror or release run")


def build_projects(version: str, commit: str) -> tuple[Distribution, ...]:
    """CI can also build the four-project workspace at development version 3.0.4."""
    require_commit(commit)
    if version == HISTORIC_VERSION and commit != HISTORIC_COMMIT:
        return CURRENT
    return release_projects(version, commit)


def artifact_filenames(version: str, projects=CURRENT) -> set[str]:
    version_key(version)
    return {name for project in projects for name in (project.wheel(version), project.sdist(version))}


def workspace_projects(root: Path) -> tuple[Distribution, ...]:
    """Check the explicit publication list against the checked-out workspace."""
    packages = root / "packages"
    actual = {p.parent.name for p in packages.glob("*/pyproject.toml")}
    expected = {p.directory for p in CURRENT}
    if actual != expected:
        raise ValueError(f"Workspace changed: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    for project in CURRENT:
        metadata = tomllib.loads((packages / project.directory / "pyproject.toml").read_text(encoding="utf-8"))
        if canonical_name(metadata["project"]["name"]) != project.name:
            raise ValueError(f"Project metadata does not match the release contract: {project.directory}")
    return CURRENT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    projects = release_projects(args.version, args.commit)
    print(json.dumps({"include": [
        {"distribution": project.stem, "environment": project.environment} for project in projects
    ]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
