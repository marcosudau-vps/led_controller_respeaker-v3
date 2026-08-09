"""The ``lefx-studio`` console script.

Starts the window and hands it a session. Everything else is in the modules the
window pulls in; this file exists to have one obvious place where the process
begins and ends.
"""

from __future__ import annotations

import argparse
import logging
import sys

from pathlib import Path

from .project import Project, iter_paths, remember, resolve, under_a_frozen_build
from .session import NULL_OUTPUT, StudioSession, available_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lefx-studio",
        description="Play, tune, calibrate and author LEFX effects.",
    )
    parser.add_argument(
        "--output",
        default=NULL_OUTPUT,
        help=(
            "Which device to open at start. The studio can switch later; "
            f"installed right now: {', '.join(available_outputs())}"
        ),
    )
    parser.add_argument("--led-count", type=int, default=12)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument(
        "--project",
        default=None,
        metavar="PATH",
        help=(
            "The checkout to work on. Everything is derived from it: where effects "
            "are read from, where a calibration is kept, where a new source is "
            "written. Defaults to the working directory, or the last one used."
        ),
    )
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        dest="sources",
        metavar="PATH",
        help="Override where effect packages are looked for, repeatable",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help=(
            "Report what this build can reach and exit, without opening a window. "
            "The way to find out whether a standalone build is complete."
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def self_check(project: Project) -> int:
    """Everything a frozen build can silently get wrong, asked out loud.

    Two failures are invisible in a bundle: a device whose metadata was not
    carried is simply not offered, and an effect that imports a standard library
    module the bundle does not contain fails alone, at load time, on somebody
    else's machine. Both are checked here by doing the thing rather than
    inspecting the recipe — the outputs are discovered, the catalogue is loaded,
    and every definition in it is rendered once.
    """
    from lefx.sdk import RenderContext, initial_runtime_inputs, resolve_configuration

    print(f"frozen build : {under_a_frozen_build()}")
    for label, path in iter_paths(project):
        marker = "ok " if Path(path).exists() else "-- "
        print(f"{label:<13}: {marker}{path}")

    outputs = available_outputs()
    print(f"outputs      : {', '.join(outputs)}")
    if outputs == [NULL_OUTPUT]:
        print("             ! no device package reachable — entry point metadata is missing")

    session = StudioSession(project=project)
    failures: list[str] = []
    try:
        session.open(NULL_OUTPUT)
        effects = session.registry.list_effects()
        print(f"catalogue    : {len(effects)} Definitionen, "
              f"{len(session.registry.list_presets())} Presets")
        for entry in effects:
            definition = entry.definition
            try:
                # Rendering is what pulls an effect's own imports in. A bundle
                # missing one of them fails here rather than in front of a user.
                entry.effect_class().render(
                    RenderContext(
                        now=1.0, started_at=0.0, led_count=12, definition=definition,
                        params=resolve_configuration(definition),
                        inputs=initial_runtime_inputs(definition),
                    )
                )
            except Exception as exc:
                failures.append(f"{definition.id}: {exc}")
        for source in session.service.library.sources():
            if source["error"]:
                failures.append(f"{source['path']}: {source['error']}")
    finally:
        session.close()

    if failures:
        print(f"\n{len(failures)} Problem(e):")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("rendering    : alle Definitionen gerendert")
    print("\nDieser Build ist vollständig.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    project = resolve(args.project)
    logging.getLogger("lefx.effect_creation.studio").info("project: %s", project.root)
    if args.self_check:
        return self_check(project)

    from PySide6.QtWidgets import QApplication

    from .window import StudioWindow
    if under_a_frozen_build() and not project.looks_like_a_project:
        # A bundle started by double-clicking has no meaningful working
        # directory, so guessing one would silently point the tool at the
        # desktop. Say so instead; the window offers a picker.
        logging.getLogger("lefx.effect_creation.studio").warning(
            "no catalogue at %s — choose one with Projekt / Projekt öffnen", project.root
        )

    session = StudioSession(
        led_count=args.led_count,
        fps=args.fps,
        search_paths=args.sources,
        project=project,
    )
    remember(project)

    application = QApplication(sys.argv[:1])
    application.setApplicationName("LEFX Studio")
    window = StudioWindow(session, initial_output=args.output)
    window.setWindowTitle(f"LEFX Studio — {project.label}")
    window.show()
    try:
        return int(application.exec())
    finally:
        # exec() returns on the last window closing, but a crash on the way out
        # would otherwise leave a USB endpoint held by a process that is gone.
        session.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
