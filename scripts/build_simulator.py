"""Build the ring window into a standalone executable.

The window is the one part of this system a person actually looks at, and it is
useful to be able to hand it to a machine that has no Python checkout — or to
keep it open while the checkout is being changed underneath. That is what this
produces.

It builds the *simulator*, not the service. The service is a Python application
with a CLI and an HTTP API; the window is a program you double-click.

    uv run --group build python scripts/build_simulator.py

Requires PyInstaller and the ``gui`` extra, neither of which is installed by
default — the service half deliberately carries no Qt. The script says so
plainly rather than failing somewhere inside a build.

One thing worth knowing about this build: PyInstaller resolves imports
statically, which is exactly why ``xvf_host`` was made an ordinary module in
this generation instead of being loaded from a file path at runtime. Anything
reached by path rather than by import is invisible here and will be missing from
the result.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = REPO_ROOT / "build"
DIST_DIR = BUILD_ROOT / "dist"
WORK_DIR = BUILD_ROOT / "pyinstaller"

NAME = "lefx-simulator"

LAUNCHER = '''"""Generated entry point. Absolute imports only — see build_simulator.py."""

from lefx.device.simulated_respeaker.app import main

raise SystemExit(main())
'''

HIDDEN_IMPORTS = (
    # main() imports these lazily so that a machine without Qt still gets a
    # readable error instead of a traceback. Lazy imports are reached by
    # PyInstaller's analysis in most cases, but naming them costs nothing and
    # removes the question.
    "lefx.device.simulated_respeaker.window",
    "lefx.device.simulated_respeaker.ring",
)

EXCLUDES = (
    # PySide6 ships far more than a ring and three controls need. Excluding the
    # large optional pieces is the difference between a download and a nuisance.
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    # Nothing in the window path uses these, and they pull in a lot.
    "matplotlib",
    "numpy",
    "PIL",
    "pytest",
    "tkinter",
)


def check_requirements() -> list[str]:
    """What is missing, in the words needed to install it."""
    missing: list[str] = []
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        missing.append(
            "PyInstaller is not installed:\n"
            "    uv sync --group build\n"
            "  (or: uv pip install pyinstaller)"
        )
    try:
        import PySide6  # noqa: F401
    except ImportError:
        missing.append(
            "PySide6 is not installed — it is the simulator's 'gui' extra:\n"
            '    uv pip install "PySide6>=6.0.0"'
        )
    try:
        import lefx.device.simulated_respeaker  # noqa: F401
    except ImportError:
        missing.append(
            "lefx.device.simulated_respeaker is not importable:\n"
            "    uv sync"
        )
    return missing


def build(*, onefile: bool, windowed: bool, clean: bool) -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    launcher = WORK_DIR / "simulator_entry.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--name",
        NAME,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(WORK_DIR / "work"),
        "--specpath",
        str(WORK_DIR),
        "--onefile" if onefile else "--onedir",
        # Console by default: the window reports a service it cannot reach
        # through the log, and swallowing that on a tool whose whole job is to
        # show you what is happening would be a poor trade for a tidier taskbar.
        "--windowed" if windowed else "--console",
    ]
    if clean:
        command.append("--clean")
    for name in HIDDEN_IMPORTS:
        command += ["--hidden-import", name]
    for name in EXCLUDES:
        command += ["--exclude-module", name]
    command.append(str(launcher))

    print("Building:", " ".join(command[3:]), "\n", flush=True)
    subprocess.run(command, check=True, cwd=REPO_ROOT)

    suffix = ".exe" if sys.platform.startswith("win") else ""
    return (
        DIST_DIR / f"{NAME}{suffix}"
        if onefile
        else DIST_DIR / NAME / f"{NAME}{suffix}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_simulator",
        description="Build the ring window into a standalone executable.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--onefile",
        dest="onefile",
        action="store_true",
        default=True,
        help="One self-extracting executable (default). Slower to start.",
    )
    mode.add_argument(
        "--onedir",
        dest="onefile",
        action="store_false",
        help="A folder with the executable beside its libraries. Starts faster.",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Hide the console window. Also hides connection errors.",
    )
    parser.add_argument(
        "--clean", action="store_true", help="Discard PyInstaller's caches first"
    )
    parser.add_argument(
        "--wipe", action="store_true", help="Remove previous build output first"
    )
    args = parser.parse_args(argv)

    missing = check_requirements()
    if missing:
        print("Cannot build:\n", file=sys.stderr)
        for item in missing:
            print(f"  - {item}\n", file=sys.stderr)
        return 2

    if args.wipe:
        for path in (DIST_DIR, WORK_DIR):
            shutil.rmtree(path, ignore_errors=True)

    try:
        artifact = build(onefile=args.onefile, windowed=args.windowed, clean=args.clean)
    except subprocess.CalledProcessError as exc:
        print(f"\nPyInstaller failed with exit code {exc.returncode}.", file=sys.stderr)
        return exc.returncode

    if not artifact.exists():
        print(f"\nBuild finished but {artifact} is missing.", file=sys.stderr)
        return 1

    size_mb = artifact.stat().st_size / (1024 * 1024)
    print(f"\nBuilt {artifact} ({size_mb:.1f} MB)")
    print(
        "\nRun it while a service is up:\n"
        f"    {artifact.name}\n"
        f"    {artifact.name} --port 8890\n"
        "\nThe window dials the service and reconnects on its own, so it can be\n"
        "started before the service and left open across restarts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
