"""Build the studio into a standalone executable.

The studio is the one part of this system that is useful on a machine without a
checkout of it — you point it at a project, and it plays, tunes, calibrates and
authors. That only works frozen if two things survive the bundling, and neither
of them is obvious, because both work perfectly in a source tree and fail only
in the executable.

**Entry point metadata.** The devices are found through
``importlib.metadata.entry_points()``, which reads the ``.dist-info``
directories of installed distributions. PyInstaller does not collect those
unless told to, so a frozen studio would come up with no reSpeaker and no
simulator in the output list and no error to explain it. ``--copy-metadata``
for every distribution that declares an entry point fixes it, and
``check_recipe`` below asserts the list is complete rather than remembered.

**The effect author's standard library.** Effect packages are imported at
runtime from ZIPs, and they may import anything on the authoring whitelist —
``colorsys``, ``statistics``, ``fractions``. PyInstaller bundles what it sees
imported, and it cannot see inside a ``.lefx`` that does not exist yet. So the
whole whitelist is named as a hidden import; otherwise a catalogue that loads
in the checkout fails in the executable, one effect at a time.

    uv run --group build python scripts/build_studio.py
    uv run --group build python scripts/build_studio.py --onedir

Requires PyInstaller and PySide6, neither installed by default.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from importlib.metadata import distributions
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = REPO_ROOT / "build"
DIST_DIR = BUILD_ROOT / "dist"
WORK_DIR = BUILD_ROOT / "pyinstaller"

NAME = "lefx-studio"

LAUNCHER = '''"""Generated entry point. Absolute imports only — see build_studio.py."""

from lefx.studio.app import main

raise SystemExit(main())
'''

ENTRY_POINT_GROUPS = ("lefx.frame_sinks", "lefx.input_providers")

# Distributions whose metadata has to travel even though nothing imports them
# by name. The four lefx ones are here because ``importlib.metadata.version``
# is asked for them, and the device packages because they *are* the entry
# points — see check_recipe.
ALWAYS_COPY_METADATA = (
    "lefx-sdk",
    "lefx-engine",
    "lefx-authoring",
    "lefx-interfaces",
    "lefx-studio",
)

EXCLUDES = (
    # PySide6 ships far more than this window needs.
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtNfc", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtPositioning", "PySide6.QtQml",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtTextToSpeech", "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets",
    "matplotlib", "numpy", "PIL", "pytest", "tkinter",
)


def entry_point_distributions() -> list[str]:
    """Every installed distribution that registers a sink or a provider.

    Discovered rather than listed, so a third device package installed
    alongside is carried into the bundle without this file being edited.
    """
    found: set[str] = set()
    for distribution in distributions():
        name = distribution.metadata["Name"]
        if not name:
            continue
        for entry in distribution.entry_points:
            if entry.group in ENTRY_POINT_GROUPS:
                found.add(name)
    return sorted(found)


def author_stdlib() -> list[str]:
    """What an effect package is allowed to import, and therefore might."""
    from lefx.authoring import ALLOWED_STDLIB

    return sorted(name for name in ALLOWED_STDLIB if name != "__future__")


def hidden_imports() -> list[str]:
    """Modules nothing imports statically but something imports at runtime."""
    names = [
        # Reached only through entry points, by string.
        "lefx.device.respeaker.registration",
        "lefx.device.simulated_respeaker.registration",
        # The studio's own Qt pages are imported inside main().
        "lefx.studio.window",
        "lefx.studio.calibration_page",
        "lefx.studio.source_editor",
        "lefx.studio.preset_dialog",
        # What a loaded effect may import. See the module docstring.
        *author_stdlib(),
    ]
    return sorted(dict.fromkeys(names))


def metadata_to_copy() -> list[str]:
    return sorted({*ALWAYS_COPY_METADATA, *entry_point_distributions()})


def check_recipe() -> list[str]:
    """What this build would get wrong, before spending four minutes on it.

    Both failure modes are silent in the finished executable — a missing device
    just is not offered, a missing stdlib module breaks one effect — so they are
    worth catching here rather than in a bug report.
    """
    problems: list[str] = []

    declared = set(metadata_to_copy())
    for name in entry_point_distributions():
        if name not in declared:
            problems.append(f"{name} registers an entry point but its metadata is not copied")

    hidden = set(hidden_imports())
    for name in author_stdlib():
        if name not in hidden:
            problems.append(f"effects may import {name}, but it is not a hidden import")

    if not entry_point_distributions():
        problems.append(
            "no device package is installed, so the executable would offer no output"
        )
    return problems


def check_requirements() -> list[str]:
    missing: list[str] = []
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        missing.append("PyInstaller is not installed:\n    uv sync --group build")
    try:
        import PySide6  # noqa: F401
    except ImportError:
        missing.append('PySide6 is not installed:\n    uv pip install "PySide6>=6.0.0"')
    try:
        import lefx.studio  # noqa: F401
    except ImportError:
        missing.append("lefx.studio is not importable:\n    uv sync")
    return missing


def build(*, onefile: bool, windowed: bool, clean: bool) -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    launcher = WORK_DIR / "studio_entry.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", NAME,
        "--distpath", str(DIST_DIR),
        "--workpath", str(WORK_DIR / "work"),
        "--specpath", str(WORK_DIR),
        "--onefile" if onefile else "--onedir",
        # Console by default: the studio logs which project it opened and why a
        # device is unavailable, and hiding that on a tool for debugging effects
        # would be a poor trade for a tidier taskbar.
        "--windowed" if windowed else "--console",
    ]
    if clean:
        command.append("--clean")
    for name in metadata_to_copy():
        command += ["--copy-metadata", name]
    for name in hidden_imports():
        command += ["--hidden-import", name]
    for name in EXCLUDES:
        command += ["--exclude-module", name]
    command.append(str(launcher))

    print("Building:", " ".join(command[3:]), "\n", flush=True)
    subprocess.run(command, check=True, cwd=REPO_ROOT)

    suffix = ".exe" if sys.platform.startswith("win") else ""
    return DIST_DIR / f"{NAME}{suffix}" if onefile else DIST_DIR / NAME / f"{NAME}{suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_studio", description=__doc__.splitlines()[0]
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--onefile", dest="onefile", action="store_true", default=True,
                      help="One self-extracting executable (default). Slower to start.")
    mode.add_argument("--onedir", dest="onefile", action="store_false",
                      help="A folder beside its libraries. Starts faster.")
    parser.add_argument("--windowed", action="store_true", help="Hide the console window.")
    parser.add_argument("--clean", action="store_true", help="Discard PyInstaller's caches.")
    parser.add_argument("--wipe", action="store_true", help="Remove previous output first.")
    parser.add_argument("--check", action="store_true",
                        help="Only verify the recipe; build nothing.")
    args = parser.parse_args(argv)

    missing = check_requirements()
    if missing:
        print("Cannot build:\n", file=sys.stderr)
        for item in missing:
            print(f"  - {item}\n", file=sys.stderr)
        return 2

    problems = check_recipe()
    if problems:
        print("The build recipe is incomplete:\n", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"metadata:       {', '.join(metadata_to_copy())}")
    print(f"hidden imports: {len(hidden_imports())}")
    if args.check:
        print("\nRecipe looks complete.")
        return 0

    if args.wipe:
        shutil.rmtree(DIST_DIR / NAME, ignore_errors=True)

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
        "\nPoint it at a checkout:\n"
        f"    {artifact.name} --project C:\\pfad\\zum\\repo\n"
        "\nWithout --project it reopens the last one, or uses the working\n"
        "directory. Projekt / Projekt öffnen switches at any time."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
