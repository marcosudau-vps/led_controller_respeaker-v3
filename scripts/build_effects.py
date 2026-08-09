"""Build every effect set in ``effects/`` into the distribution that ships it.

Each set directory holds editable sources under ``sources/``. The archive built
from them lands inside the distribution that ships it, which is the one place a
built set ever lives: the same directory in a checkout, in the editable
workspace and in an installed wheel. That is what makes ``uv sync`` enough to
have a catalogue and ``uv build`` enough to ship one.

Built artefacts are reproducible output and are not committed.

    uv run python scripts/build_effects.py
    uv run python scripts/build_effects.py --set core-set
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from lefx.effect_creation import SourceError, pack_effect, pack_effect_set, validate_effect_source

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_ROOT = REPO_ROOT / "effects"
PACKAGES_ROOT = REPO_ROOT / "packages"


def distribution_dir(set_name: str) -> Path | None:
    """The ``src/lefx/sets/<module>`` directory shipping this set, if one exists.

    Looked up by module path rather than assembled from a distribution name.
    The module path is fixed by the import name; the distribution name is a
    packaging decision that has already changed once.
    """
    module = set_name.replace("-", "_")
    for candidate in sorted(PACKAGES_ROOT.glob(f"*/src/lefx/sets/{module}")):
        if candidate.is_dir():
            return candidate
    return None


def source_dirs(set_root: Path) -> list[Path]:
    return sorted(
        manifest.parent
        for manifest in (set_root / "sources").rglob("effect.yaml")
    )


def build_set(set_root: Path, *, output_root: Path | None = None) -> dict:
    """Validate, pack and assemble one set. ``output_root`` overrides the target."""
    if output_root is None:
        target_dir = distribution_dir(set_root.name)
        if target_dir is None:
            module = set_root.name.replace("-", "_")
            raise SourceError(
                f"no distribution ships {set_root.name}: nothing under packages/ has a "
                f"src/lefx/sets/{module}/ directory. Add the package, or pass --output "
                "to build somewhere else."
            )
    else:
        target_dir = Path(output_root)

    staging = set_root / "effects"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    packages = []
    for source in source_dirs(set_root):
        report = validate_effect_source(source)
        if not report.ok:
            raise SourceError(
                f"{source.name} did not validate:\n  " + "\n  ".join(report.errors)
            )
        for warning in report.warnings:
            print(f"  warning: {source.name}: {warning}", file=sys.stderr)
        packages.append(pack_effect(source, staging / f"{report.identifier}.lefx"))

    target_dir.mkdir(parents=True, exist_ok=True)
    result = pack_effect_set(set_root, target_dir / f"{set_root.name}.lefxset")
    result["packages"] = [package["effect_id"] for package in packages]

    # The set archive now carries every one of these, and the staging directory
    # sits inside a directory the service scans for packages. Left behind, each
    # member would be found a second time as a package of its own and rejected
    # for an id the set has already registered — a catalogue that builds
    # correctly and then reports thirty-five broken sources at every start.
    # Staging is intermediate output; it goes at the end for the same reason it
    # goes at the beginning.
    shutil.rmtree(staging)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the first-party effect sets.")
    parser.add_argument("--set", dest="only", help="Build one set instead of all of them")
    parser.add_argument(
        "--output",
        default=None,
        help="Build into this directory instead of into each set's own distribution",
    )
    args = parser.parse_args(argv)

    roots = sorted(path for path in CATALOGUE_ROOT.iterdir() if (path / "set.yaml").is_file())
    if args.only:
        roots = [path for path in roots if path.name == args.only]
        if not roots:
            print(f"No set named {args.only!r} under {CATALOGUE_ROOT}", file=sys.stderr)
            return 1

    results = []
    for root in roots:
        print(f"building {root.name}", file=sys.stderr)
        try:
            results.append(build_set(root, output_root=args.output))
        except SourceError as exc:
            print(json.dumps({"ok": False, "set": root.name, "error": str(exc)}, indent=2))
            return 1

    print(json.dumps({"ok": True, "sets": results}, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
