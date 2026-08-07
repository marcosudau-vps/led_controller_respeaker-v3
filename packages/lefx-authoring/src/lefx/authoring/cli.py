"""The ``lefx-pack`` command line.

Every subcommand prints JSON and returns a non-zero status on failure, so it is
as usable from a build script as it is by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lefx.engine import EngineError, load_source

from .build import pack_effect, pack_effect_set
from .scaffold import init_effect_set_source, init_effect_source
from .source import SourceError
from .validate import validate_effect_set_source, validate_effect_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lefx-pack",
        description="Create, validate, build and inspect LEFX V3 sources and packages.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a new effect source")
    init.add_argument("directory")
    init.add_argument("--effect-id", required=True)
    init.add_argument("--source-id", required=True)
    init.add_argument(
        "--kind",
        default="state",
        help="state, controlled_overlay, timed_overlay or event",
    )
    init.add_argument("--title")
    init.add_argument("--class-name")
    init.add_argument("--force", action="store_true")

    init_set = sub.add_parser("init-set", help="Create a new set source")
    init_set.add_argument("directory")
    init_set.add_argument("--set-id", required=True)
    init_set.add_argument("--source-id", required=True)
    init_set.add_argument("--title")
    init_set.add_argument("--force", action="store_true")

    validate = sub.add_parser("validate", help="Validate an effect source")
    validate.add_argument("directory")

    validate_set = sub.add_parser("validate-set", help="Validate a set source")
    validate_set.add_argument("directory")

    build = sub.add_parser("build", help="Build a .lefx from an effect source")
    build.add_argument("directory")
    build.add_argument("output")

    build_set = sub.add_parser("build-set", help="Build a .lefxset from a set source")
    build_set.add_argument("directory")
    build_set.add_argument("output")

    verify = sub.add_parser("verify", help="Load a built package and report what it contains")
    verify.add_argument("path")

    inspect = sub.add_parser("inspect", help="Show the metadata of a built package")
    inspect.add_argument("path")

    return parser


def _verify(path: str) -> dict[str, Any]:
    loaded = load_source(path)
    return {
        "ok": True,
        "kind": loaded.kind,
        "path": str(loaded.path),
        "source_id": loaded.source_id,
        "effects": [package.effect_id for package in loaded.packages],
        "preset_count": loaded.preset_count,
    }


def _inspect(path: str) -> dict[str, Any]:
    loaded = load_source(path)
    return {
        "ok": True,
        "kind": loaded.kind,
        "path": str(loaded.path),
        "source_id": loaded.source_id,
        "set": loaded.set_manifest,
        "packages": [
            {
                "package_id": package.package_id,
                "effect_id": package.effect_id,
                "type": package.definition.definition_type.value,
                "form": package.definition.kind.value,
                "title": package.definition.title,
                "description": package.definition.description,
                "version": package.definition.version,
                "tags": list(package.definition.tags),
                "config": sorted(package.definition.parameter_schema),
                "runtime_inputs": sorted(package.definition.runtime_input_schema),
                "presets": [preset.preset_id for preset in package.presets],
            }
            for package in loaded.packages
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            result = init_effect_source(
                args.directory,
                effect_id=args.effect_id,
                source_id=args.source_id,
                kind=args.kind,
                title=args.title,
                class_name=args.class_name,
                force=args.force,
            )
        elif args.command == "init-set":
            result = init_effect_set_source(
                args.directory,
                set_id=args.set_id,
                source_id=args.source_id,
                title=args.title,
                force=args.force,
            )
        elif args.command == "validate":
            result = validate_effect_source(args.directory).to_dict()
        elif args.command == "validate-set":
            result = validate_effect_set_source(args.directory).to_dict()
        elif args.command == "build":
            result = pack_effect(args.directory, args.output)
        elif args.command == "build-set":
            result = pack_effect_set(args.directory, args.output)
        elif args.command == "verify":
            result = _verify(args.path)
        elif args.command == "inspect":
            result = _inspect(args.path)
        else:  # pragma: no cover - argparse rejects anything else
            raise SourceError(f"Unsupported command {args.command!r}")
    except (SourceError, EngineError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
