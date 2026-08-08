"""Build every distribution and prove the built artefacts actually install.

An editable workspace hides packaging mistakes rather than causing them: every
module is importable because the source tree is on the path, whatever the wheel
would have contained. A missing package directory, an entry point that names a
module that is not shipped, a runtime dependency declared only in the dev group
— none of it shows until something installs the artefact instead of the
checkout. So this builds every distribution, installs them into an empty
environment and asks the questions that only that environment can answer:

* do they all import,
* are the console scripts there and do they run,
* do the entry points resolve, so the service finds both devices,
* and does the simulator's service half work with no Qt installed at all.

That last one is the reason the ring window is an extra, and it is why the
studio — which brings Qt with it — is installed only afterwards, on top of the
environment that has already answered the question. Installing it first would
prove the opposite of what is wanted.

    uv run python scripts/check_release.py
    uv run python scripts/check_release.py --keep
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "build/dist-packages"

# Installed into an environment with no Qt in it, which is what proves the
# simulator's service half needs none. The studio is deliberately not here: it
# *is* a window and brings Qt with it, so it is installed afterwards, into the
# same environment, which is also the real upgrade path.
DISTRIBUTIONS = (
    "lefx-sdk",
    "lefx-engine",
    "lefx-authoring",
    "lefx-interfaces",
    "respeaker-led-device",
    "respeaker-led-simulator",
)

GUI_DISTRIBUTION = "lefx-studio"

ALL_DISTRIBUTIONS = (*DISTRIBUTIONS, GUI_DISTRIBUTION)

IMPORT_NAMES = (
    "lefx.sdk",
    "lefx.engine",
    "lefx.authoring",
    "lefx.interfaces",
    "respeaker_led.device",
    "respeaker_led.simulator",
)

# The half of the simulator a service process loads. None of it may need Qt.
GUI_FREE_MODULES = (
    "respeaker_led.simulator.registration",
    "respeaker_led.simulator.link",
    "respeaker_led.simulator.protocol",
    "respeaker_led.simulator.sink",
    "respeaker_led.simulator.provider",
    "respeaker_led.simulator.client",
)

EXPECTED_SINKS = {"respeaker", "simulator"}
EXPECTED_PROVIDERS = {"respeaker.doa", "simulator.doa"}


class CheckFailed(RuntimeError):
    pass


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, **kwargs)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)
    print(f"  ok  {message}")


def build_distributions() -> list[Path]:
    if DIST_DIR.exists():
        # A stale wheel of the same version would be installed in preference to
        # nothing, and the run would be checking the last build, not this one.
        shutil.rmtree(DIST_DIR)
    print(f"building {len(ALL_DISTRIBUTIONS)} distributions into {DIST_DIR.relative_to(REPO_ROOT)}")
    result = run(["uv", "build", "--all-packages", "--out-dir", str(DIST_DIR)], cwd=REPO_ROOT)
    if result.returncode != 0:
        raise CheckFailed(f"uv build failed:\n{result.stdout}\n{result.stderr}")

    wheels = sorted(DIST_DIR.glob("*.whl"))
    sdists = sorted(DIST_DIR.glob("*.tar.gz"))
    require(
        len(wheels) == len(ALL_DISTRIBUTIONS) and len(sdists) == len(ALL_DISTRIBUTIONS),
        f"built a wheel and an sdist for each of the {len(ALL_DISTRIBUTIONS)} distributions",
    )
    return wheels


def make_environment(root: Path) -> Path:
    result = run(["uv", "venv", str(root)], cwd=REPO_ROOT)
    if result.returncode != 0:
        raise CheckFailed(f"could not create the test environment:\n{result.stderr}")
    python = root / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
    if not python.exists():
        raise CheckFailed(f"no interpreter at {python}")

    # --find-links points at what was just built; third-party dependencies still
    # come from the index, because the point here is our packaging, not theirs.
    result = run(
        [
            "uv", "pip", "install",
            "--python", str(python),
            "--find-links", str(DIST_DIR),
            *DISTRIBUTIONS,
        ],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise CheckFailed(f"installing the built artefacts failed:\n{result.stderr}")
    return python


def script(python: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return python.parent / f"{name}{suffix}"


def check_imports(python: Path) -> None:
    for name in IMPORT_NAMES:
        result = run([str(python), "-c", f"import {name}"])
        detail = "" if result.returncode == 0 else f"\n{result.stderr}"
        require(result.returncode == 0, f"import {name}{detail}")


def check_versions(python: Path, distributions=DISTRIBUTIONS) -> None:
    code = (
        "import json;from importlib.metadata import version;"
        f"print(json.dumps({{name: version(name) for name in {list(distributions)!r}}}))"
    )
    result = run([str(python), "-c", code])
    require(result.returncode == 0, "every distribution reports its version")
    versions = json.loads(result.stdout)
    require(
        len(set(versions.values())) == 1,
        f"they all carry one version ({sorted(set(versions.values()))})",
    )


def check_simulator_without_qt(python: Path) -> None:
    installed = run([str(python), "-c", "import PySide6"])
    require(installed.returncode != 0, "the environment has no Qt, as an installation without the extra would not")

    code = "; ".join(f"import {name}" for name in GUI_FREE_MODULES)
    result = run([str(python), "-c", code + "; print('ok')"])
    require(result.returncode == 0, f"the simulator's service half imports without Qt\n{result.stderr}")

    # And the window says why rather than raising ImportError at the user.
    window = run([str(script(python, 'respeaker-led-simulator'))])
    require(
        window.returncode == 2 and "PySide6" in window.stderr,
        "the ring window explains that it needs the gui extra",
    )


def check_console_scripts(python: Path) -> None:
    for name in ("lefx", "lefx-pack", "respeaker-led-device", "respeaker-led-simulator"):
        require(script(python, name).exists(), f"console script {name} is installed")
    for name in ("lefx", "lefx-pack", "respeaker-led-device"):
        result = run([str(script(python, name)), "--help"])
        require(result.returncode == 0, f"{name} --help runs")


def check_entry_points(python: Path) -> None:
    """The devices have to be findable from metadata alone, with nothing imported."""
    result = run([str(script(python, "lefx")), "sinks"])
    require(result.returncode == 0, f"lefx sinks runs\n{result.stderr}")
    catalogue = json.loads(result.stdout)

    sinks = {item["name"] for item in catalogue["sinks"]}
    providers = {item["name"] for item in catalogue["input_providers"]}
    require(EXPECTED_SINKS <= sinks, f"both frame sinks are discovered ({sorted(sinks)})")
    require(
        EXPECTED_PROVIDERS <= providers,
        f"both DoA providers are discovered ({sorted(providers)})",
    )
    require(
        {item["capability"] for item in catalogue["input_providers"]} == {"doa"},
        "every installed provider offers the bare capability the engine asks for",
    )
    require(
        result.stderr.strip() == "",
        f"nothing warned while loading the entry points\n{result.stderr}",
    )


def check_the_service_starts(python: Path) -> None:
    """Build a service against the installed simulator, in that environment."""
    code = (
        "from lefx.interfaces import ControllerService\n"
        "service = ControllerService(sink='simulator', led_count=12, search_paths=[],\n"
        "                           sink_options={'port': 0})\n"
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
    result = run([str(python), "-c", code])
    require(
        result.returncode == 0 and "ok" in result.stdout,
        f"a service built from the installed packages renders to the simulator\n{result.stderr}",
    )


def check_the_studio_installs_on_top(python: Path) -> None:
    """The GUI application, added to an environment that already works.

    Deliberately last and deliberately into the same environment: this is the
    order a person would do it in, and it is the order that shows the studio
    brings its own Qt rather than needing one to have been there.
    """
    result = run(
        [
            "uv", "pip", "install",
            "--python", str(python),
            "--find-links", str(DIST_DIR),
            GUI_DISTRIBUTION,
        ],
        cwd=REPO_ROOT,
    )
    require(result.returncode == 0, f"{GUI_DISTRIBUTION} installs on top\n{result.stderr}")

    check_versions(python, ALL_DISTRIBUTIONS)

    imports = run([str(python), "-c", "import lefx.studio; print(lefx.studio.STUDIO_VERSION)"])
    require(imports.returncode == 0, f"import lefx.studio\n{imports.stderr}")

    headless = run(
        [str(python), "-c", "import lefx.studio; print(sorted(lefx.studio.available_outputs()))"]
    )
    require(
        headless.returncode == 0 and "simulator" in headless.stdout,
        f"the studio finds the installed outputs without a display\n{headless.stderr}",
    )

    require(script(python, "lefx-studio").exists(), "console script lefx-studio is installed")
    helped = run([str(script(python, "lefx-studio")), "--help"])
    require(helped.returncode == 0, f"lefx-studio --help runs\n{helped.stderr}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--keep", action="store_true", help="Leave the throwaway environment in place"
    )
    args = parser.parse_args(argv)

    try:
        build_distributions()
        root = Path(tempfile.mkdtemp(prefix="lefx-release-", dir=REPO_ROOT / "build"))
        print(f"installing into {root.relative_to(REPO_ROOT)}")
        try:
            python = make_environment(root)
            check_versions(python)
            check_imports(python)
            check_console_scripts(python)
            check_entry_points(python)
            check_simulator_without_qt(python)
            check_the_service_starts(python)
            check_the_studio_installs_on_top(python)
        finally:
            if not args.keep:
                shutil.rmtree(root, ignore_errors=True)
    except CheckFailed as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1

    print("\nall release checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
