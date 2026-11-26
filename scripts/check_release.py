"""Build every distribution and prove the built artefacts actually install.

Install a fresh environment for each supported combination. Constraints
bind every internal distribution to the exact local wheel while the resolver
still has to follow its declared dependencies and extras.

    uv run python scripts/check_release.py
    uv run python scripts/check_release.py --keep
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from release_bundle import validate_distribution
from release_contract import (
    CONFIGURATOR, CORE, CURRENT, SIMULATOR, STUDIO, artifact_filenames, workspace_projects,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "build/dist-packages"

# Each request exercises the declared dependency graph in its own venv.
INSTALL_CASES = (
    ("core-only", CORE.name, (CORE,)),
    ("simulator-headless", SIMULATOR.name, (CORE, SIMULATOR)),
    *((project.extra, f"{CORE.name}[{project.extra}]", (CORE, project))
      for project in CURRENT if project.extra),
    ("configurator-direct", CONFIGURATOR.name, (CORE, CONFIGURATOR)),
    ("all", f"{CORE.name}[all]", CURRENT),
)


def effect_set_wheels() -> dict[str, list[str]]:
    """Which distribution has to contain which archives, read off the tree.

    A wheel built before scripts/build_effects.py ran installs cleanly, offers
    its entry points, and delivers nothing — the one failure the "artifacts"
    include in the pyproject cannot prevent. So the wheel gets opened, and this
    says what to look for.

    Derived rather than listed, because a list of catalogue names is exactly
    what went stale once: four places knew which catalogues exist, and renaming
    the distributions left one of them behind. The release then stopped at a
    guard reporting "0 wheels" for a package that no longer existed. The module
    path under src/lefx/sets/ is fixed by the import name and cannot drift; the
    distribution around it is whatever directory it happens to be in.
    """
    found: dict[str, list[str]] = {}
    for module_dir in sorted((REPO_ROOT / "packages").glob("*/src/lefx/sets/*")):
        if not module_dir.is_dir() or module_dir.name == "__pycache__":
            continue
        distribution = module_dir.parents[3].name
        set_name = module_dir.name.replace("_", "-")
        found.setdefault(distribution, []).append(
            f"lefx/sets/{module_dir.name}/{set_name}.lefxset"
        )
    return found


IMPORT_NAMES = (
    "lefx.sdk",
    "lefx.engine",
    "lefx.interfaces",
    "lefx.device.respeaker",
    "lefx.device.simulated_respeaker",
    "lefx.sets.core_set",
    "lefx.sets.smartspeaker_set",
)

# The half of the simulator a service process loads. None of it may need Qt.
GUI_FREE_MODULES = (
    "lefx.device.simulated_respeaker.registration",
    "lefx.device.simulated_respeaker.link",
    "lefx.device.simulated_respeaker.protocol",
    "lefx.device.simulated_respeaker.sink",
    "lefx.device.simulated_respeaker.provider",
    "lefx.device.simulated_respeaker.client",
)

EXPECTED_SINKS = {"respeaker", "simulator"}
EXPECTED_PROVIDERS = {"respeaker.doa", "simulator.doa"}
EXPECTED_EFFECT_SETS = {"core-set", "smartspeaker-set"}


class CheckFailed(RuntimeError):
    pass


def run(command: list[str], *, timeout=90, **kwargs) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME", "INCLUDED_LEFXSET"}
           and not key.startswith(("UV_", "PIP_", "LEFX_"))}
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONUTF8"] = "1"
    with tempfile.TemporaryDirectory(prefix="lefx-smoke-config-") as directory:
        config = Path(directory) / "config.yaml"
        config.write_text("{}\n", encoding="utf-8")
        env["LEFX_CONFIG"] = str(config)
        env["LEFX_STATE_ROOT"] = directory
        env.update(kwargs.pop("env", {}))
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                              env=env, timeout=timeout, **kwargs)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)
    print(f"  ok  {message}")


def build_distributions() -> list[Path]:
    if DIST_DIR.exists():
        # A stale wheel of the same version would be installed in preference to
        # nothing, and the run would be checking the last build, not this one.
        shutil.rmtree(DIST_DIR)
    projects = workspace_projects(REPO_ROOT)
    print(f"building {len(projects)} distributions into {DIST_DIR.relative_to(REPO_ROOT)}")
    result = run(["uv", "build", "--all-packages", "--out-dir", str(DIST_DIR)], cwd=REPO_ROOT, timeout=300)
    if result.returncode != 0:
        raise CheckFailed(f"uv build failed:\n{result.stdout}\n{result.stderr}")

    files = {path.name: path for path in DIST_DIR.iterdir() if path.name != ".gitignore"}
    require(set(files) == artifact_filenames(workspace_version(), projects),
            f"built exactly one wheel and one sdist for each of the {len(projects)} distributions")
    for path in files.values():
        validate_distribution(path, workspace_version(), projects)
    return [path for path in files.values() if path.suffix == ".whl"]


def make_environment(root: Path) -> Path:
    result = run(["uv", "--no-config", "venv", "--python", "3.12", str(root)], cwd=root.parent)
    if result.returncode != 0:
        raise CheckFailed(f"could not create the test environment:\n{result.stderr}")
    python = root / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
    if not python.exists():
        raise CheckFailed(f"no interpreter at {python}")

    return python


def workspace_version() -> str:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def install(python: Path, *requests: str) -> subprocess.CompletedProcess:
    version = workspace_version()
    constraints = python.parent.parent / "local-wheels.txt"
    constraints.write_text("".join(
        f"{project.name} @ {(DIST_DIR / project.wheel(version)).as_uri()}\n" for project in CURRENT
    ), encoding="utf-8")
    refresh = [argument for project in CURRENT for argument in ("--refresh-package", project.name)]
    return run(
        ["uv", "--no-config", "pip", "install", "--python", str(python),
         "--default-index", "https://pypi.org/simple", "--constraint", str(constraints),
         *refresh, *(f"{request}=={version}" for request in requests)],
        cwd=python.parent.parent, timeout=300,
    )


def script(python: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return python.parent / f"{name}{suffix}"


def check_imports(python: Path, projects) -> None:
    names = [name for name in IMPORT_NAMES
             if name != "lefx.device.simulated_respeaker" or SIMULATOR in projects]
    for name in names:
        result = run([str(python), "-c", f"import {name}"])
        detail = "" if result.returncode == 0 else f"\n{result.stderr}"
        require(result.returncode == 0, f"import {name}{detail}")


def check_the_catalogue_wheels_carry_a_catalogue(wheels: list[Path]) -> None:
    """Look inside the built wheel, before anything installs it."""
    import zipfile

    expected = effect_set_wheels()
    require(bool(expected), "there is at least one catalogue to check for")
    for distribution, members in expected.items():
        prefix = distribution.replace("-", "_")
        matching = [path for path in wheels if path.name.startswith(f"{prefix}-")]
        require(len(matching) == 1, f"exactly one wheel for {distribution}")
        with zipfile.ZipFile(matching[0]) as archive:
            names = set(archive.namelist())
        for member in members:
            require(
                member in names,
                f"{matching[0].name} contains {member} "
                "(run scripts/build_effects.py before building)",
            )


def check_versions(python: Path, projects) -> None:
    version = workspace_version()
    expected = {project.name: (DIST_DIR / project.wheel(version)).as_uri() for project in projects}
    code = (
        "import json; from importlib.metadata import distributions; "
        f"names={tuple(project.name for project in CURRENT)!r}; "
        "import re; "
        "print(json.dumps({name: [d.version, json.loads(d.read_text('direct_url.json') or '{}').get('url')] "
        "for d in distributions() if (name := re.sub(r'[-_.]+','-', d.name).lower()) in names}))"
    )
    result = run([str(python), "-I", "-c", code])
    require(result.returncode == 0, f"installed distributions report their origin\n{result.stderr}")
    actual = json.loads(result.stdout)
    require(set(actual) == set(expected), f"installed only the requested LEFX distributions ({sorted(actual)})")
    for project, url in expected.items():
        require(actual[project] == [version, url], f"{project} {version} installed from its local wheel")


def check_simulator_without_qt(python: Path) -> None:
    installed = run([str(python), "-c", "import PySide6"])
    require(installed.returncode != 0, "the environment has no Qt, as an installation without the extra would not")

    code = "; ".join(f"import {name}" for name in GUI_FREE_MODULES)
    result = run([str(python), "-c", code + "; print('ok')"])
    require(result.returncode == 0, f"the simulator's service half imports without Qt\n{result.stderr}")

    # And the window says why rather than raising ImportError at the user.
    window = run([str(script(python, 'lefx-simulator'))])
    require(
        window.returncode == 2 and "PySide6" in window.stderr,
        "the ring window explains that it needs the gui extra",
    )


def check_console_scripts(python: Path, *, simulator: bool, studio: bool) -> None:
    """The commands a runtime installation has. lefx-pack is not among them.

    It arrives with effect creation, and that it is *missing* here is the
    check: a default installation that could still build packages would mean
    the tooling had leaked into the runtime set.
    """
    entries = ("lefx", "lefx-respeaker", *(("lefx-simulator",) if simulator else ()))
    for name in entries:
        require(script(python, name).exists(), f"console script {name} is installed")
    for name in entries:
        result = run([str(script(python, name)), "--help"])
        require(result.returncode == 0, f"{name} --help runs")
    if studio:
        return
    require(
        not script(python, "lefx-pack").exists(),
        "lefx-pack is absent until effect creation is installed",
    )
    absent = run([str(python), "-c", "import lefx.effect_creation"])
    require(absent.returncode != 0, "lefx.effect_creation is not importable either")


def check_entry_points(python: Path, simulator: bool) -> None:
    """The devices have to be findable from metadata alone, with nothing imported."""
    result = run([str(script(python, "lefx")), "sinks"])
    require(result.returncode == 0, f"lefx sinks runs\n{result.stderr}")
    catalogue = json.loads(result.stdout)

    sinks = {item["name"] for item in catalogue["sinks"]}
    providers = {item["name"] for item in catalogue["input_providers"]}
    required_sinks = EXPECTED_SINKS if simulator else {"respeaker"}
    required_providers = EXPECTED_PROVIDERS if simulator else {"respeaker.doa"}
    require(required_sinks <= sinks and ("simulator" in sinks) == simulator,
            f"expected frame sinks are discovered ({sorted(sinks)})")
    require(required_providers == providers, f"expected DoA providers are discovered ({sorted(providers)})")
    require(
        {item["capability"] for item in catalogue["input_providers"]} == {"doa"},
        "every installed provider offers the bare capability the engine asks for",
    )

    sets = {item["name"] for item in catalogue["effect_sets"]}
    require(EXPECTED_EFFECT_SETS <= sets, f"both effect sets are discovered ({sorted(sets)})")
    require(
        all(item["enabled"] and item["archive"] for item in catalogue["effect_sets"]),
        "each installed set is enabled and points at an archive that is there",
    )
    require(
        result.stderr.strip() == "",
        f"nothing warned while loading the entry points\n{result.stderr}",
    )


def check_the_catalogue_loads(python: Path) -> None:
    """The sets arrived as effects, not merely as files.

    Installed rather than built: this is the only place the wheel's copy of the
    archive is opened by the loader that will open it in production.

    Run from an empty directory, because the service also scans ``effects/``
    beside the working directory. Anywhere with archives lying about — a
    checkout, a build directory, the parent of either — would load them too and
    fail on a duplicate id, reporting a packaging fault where there is only a
    stray file.
    """
    code = (
        "import json\n"
        "from lefx.interfaces import ControllerService\n"
        "service = ControllerService(led_count=12, state_file='background.json', autostart_providers=False)\n"
        "try:\n"
        "    sources = {e['source_id']: e for e in service.library.sources()}\n"
        "    broken = {n: e['error'] for n, e in sources.items() if e['error']}\n"
        "    assert not broken, broken\n"
        "    print(json.dumps({'count': len(service.library.registry),\n"
        "                      'sources': sorted(sources)}))\n"
        "finally:\n"
        "    service.stop()\n"
    )
    with tempfile.TemporaryDirectory(prefix="lefx-elsewhere-") as elsewhere:
        result = run([str(python), "-c", code], cwd=elsewhere)
    require(
        result.returncode == 0,
        f"the installed catalogue loads with no broken source\n{result.stdout}\n{result.stderr}",
    )
    loaded = json.loads(result.stdout)
    require(loaded["count"] > 0, f"the installed sets registered {loaded['count']} definitions")
    require(
        EXPECTED_EFFECT_SETS <= set(loaded["sources"]),
        f"both sets are among the loaded sources ({loaded['sources']})",
    )


def check_the_selection_narrows_the_catalogue(python: Path) -> None:
    """INCLUDED_LEFXSET, in the form it is documented in.

    Checked from a real environment rather than a unit test because what it
    selects on is entry point metadata, which only an installation has.
    """
    code = "from lefx.interfaces import discovery\nprint(sorted(discovery.installed_effect_sets()))\n"
    result = run([str(python), "-c", code], env={"INCLUDED_LEFXSET": "[core]"})
    require(
        result.returncode == 0 and result.stdout.strip() == "['core-set']",
        f"INCLUDED_LEFXSET=[core] leaves only the core set: "
        f"{result.stdout.strip()}\n{result.stderr}",
    )


def check_the_service_starts(python: Path) -> None:
    """Build a service against the installed simulator, in that environment."""
    code = (
        "from lefx.interfaces import ControllerService\n"
        "service = ControllerService(sink='simulator', led_count=12, search_paths=[],\n"
        "                           sink_options={'port': 0}, state_file='background.json')\n"
        "try:\n"
        "    assert service.sink_name == 'simulator', service.sink_name\n"
        "    assert set(service.providers) == {'doa'}, sorted(service.providers)\n"
        "    service.render_once(0.0)\n"
        "    status = service.status()\n"
        "    assert status['service']['sink'] == 'simulator'\n"
        "    print('ok')\n"
        "finally:\n"
        "    service.stop()\n"
    )
    with tempfile.TemporaryDirectory(prefix="lefx-simulator-") as directory:
        result = run([str(python), "-I", "-c", code], cwd=directory)
    require(
        result.returncode == 0 and "ok" in result.stdout,
        f"a service built from the installed packages renders to the simulator\n{result.stderr}",
    )


def check_effect_creation(python: Path, *, simulator: bool) -> None:
    code = ("import lefx.effect_creation.studio as studio; "
            "print(sorted(studio.available_outputs()))")
    result = run([str(python), "-I", "-c", code])
    require(result.returncode == 0 and ("simulator" in result.stdout) == simulator,
            f"Studio finds the installed outputs without a display\n{result.stderr}")
    for entry in ("lefx-pack", "lefx-studio"):
        result = run([str(script(python, entry)), "--help"])
        require(result.returncode == 0, f"{entry} --help runs\n{result.stderr}")


def check_configurator(python: Path) -> None:
    code = """
from lefx.configurator_widget import LefxCatalogueAdapter, PreviewRequest, PreviewSession
with LefxCatalogueAdapter.installed() as catalogue:
    assert {source["source_id"] for source in catalogue.sources()} == {"core-set", "smartspeaker-set"}
    assert any(entry.preset is not None for entry in catalogue.entries())
    session = PreviewSession(catalogue.registry)
    try:
        session.start(PreviewRequest("core-set::solid_fill", config={"color": "#123456", "brightness": 1}), 0)
        assert session.frame(0).leds == (0x123456,) * 12
    finally:
        session.close()
"""
    with tempfile.TemporaryDirectory(prefix="lefx-preview-") as directory:
        result = run([str(python), "-I", "-c", code], cwd=directory)
        require(result.returncode == 0, f"Configurator loads both sets and renders an isolated frame\n{result.stderr}")
        result = run([str(script(python, "lefx-configurator-widget")), "--smoke"], cwd=directory, timeout=60)
        require(result.returncode == 0, f"Configurator GUI entry point opens and closes\n{result.stderr}")


def check_install_case(root: Path, label: str, request: str, projects) -> None:
    print(f"installing {label}: {request}", flush=True)
    python = make_environment(root / label)
    result = install(python, request)
    require(result.returncode == 0, f"{request} installs\n{result.stderr}")
    result = run(["uv", "--no-config", "pip", "check", "--python", str(python)])
    require(result.returncode == 0, f"{label} has a consistent installed dependency graph\n{result.stderr}")
    check_versions(python, projects)
    check_imports(python, projects)
    qt = run([str(python), "-I", "-c", "from PySide6.QtWidgets import QApplication"])
    has_qt = label not in {"core-only", "simulator-headless"}
    require((qt.returncode == 0) == has_qt, f"{label} Qt availability is {has_qt}")
    simulator = SIMULATOR in projects
    if label in {"core-only", "simulator-headless", "all"}:
        check_entry_points(python, simulator)
        check_the_catalogue_loads(python)
    if label == "core-only":
        check_the_selection_narrows_the_catalogue(python)
    studio = STUDIO in projects
    check_console_scripts(python, simulator=simulator, studio=studio)
    if label == "simulator-headless":
        check_simulator_without_qt(python)
        check_the_service_starts(python)
    if studio:
        check_effect_creation(python, simulator=simulator)
    if CONFIGURATOR in projects:
        check_configurator(python)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="Leave the throwaway environments in place")
    args = parser.parse_args(argv)

    try:
        wheels = build_distributions()
        check_the_catalogue_wheels_carry_a_catalogue(wheels)
        root = Path(tempfile.mkdtemp(prefix="lefx-release-", dir=REPO_ROOT / "build"))
        try:
            for label, request, projects in INSTALL_CASES:
                check_install_case(root, label, request, projects)
        finally:
            if not args.keep:
                shutil.rmtree(root, ignore_errors=True)
    except (CheckFailed, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1

    print("\nall release checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
