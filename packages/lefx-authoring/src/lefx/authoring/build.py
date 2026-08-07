"""Building ``.lefx`` and ``.lefxset`` archives.

Packing happens only after validation, and the result is verified by loading it
back. A build that produces an archive the loader rejects has failed, whatever
the packer thought.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lefx.engine import build_package_manifest, load_source
from lefx.engine.packages import (
    HASHES_NAME,
    MANIFEST_NAME,
    PAYLOAD_DIR,
    PRESETS_NAME,
    SET_FORMAT,
    SET_MANIFEST_NAME,
    sha256_of,
)

from .source import EffectSetSource, EffectSource, SourceError, load_effect_set_source, load_effect_source
from .validate import import_effect_class, validate_effect_set_source, validate_effect_source

# Everything else in a source directory is authoring material, not payload.
EXCLUDED_NAMES = frozenset(
    {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
)
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo"})


def _payload_files(source: EffectSource) -> list[Path]:
    manifest_names = {source.manifest_path.name}
    preset_path = source.presets_path
    if preset_path is not None:
        manifest_names.add(preset_path.name)

    files: list[Path] = []
    for path in sorted(source.root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source.root)
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        if len(relative.parts) == 1 and relative.name in manifest_names:
            continue
        files.append(path)
    return files


def _write_archive(path: Path, members: dict[str, bytes]) -> Path:
    hashes = {"files": {name: sha256_of(data) for name, data in members.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            archive.writestr(name, data)
        archive.writestr(HASHES_NAME, json.dumps(hashes, indent=2, sort_keys=True))
    return path


def pack_effect(
    directory: str | Path, output: str | Path, *, skip_validation: bool = False
) -> dict[str, Any]:
    """Validate a source and write the ``.lefx`` archive."""
    source = load_effect_source(directory)

    if not skip_validation:
        report = validate_effect_source(source.root)
        if not report.ok:
            raise SourceError(
                f"{source.root} did not validate:\n  " + "\n  ".join(report.errors)
            )

    effect_class = import_effect_class(source)
    definition = effect_class.get_definition()
    package_id = source.package_id or f"{source.source_id}.{definition.id}"

    manifest = build_package_manifest(
        definition,
        source_id=source.source_id,
        package_id=package_id,
        entry_module=source.entry_module,
        entry_class=effect_class.__name__,
        package_version=source.package_version,
        min_sdk_version=source.min_sdk_version,
        author=source.author,
        vendor=source.vendor,
        license_id=source.license_id,
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        compatible_hardware=source.compatible_hardware,
    )

    members: dict[str, bytes] = {
        MANIFEST_NAME: json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
        f"{PAYLOAD_DIR}/__init__.py": b"",
    }
    for path in _payload_files(source):
        relative = path.relative_to(source.root).as_posix()
        if relative == "__init__.py":
            continue
        members[f"{PAYLOAD_DIR}/{relative}"] = path.read_bytes()

    presets = source.presets()
    if presets:
        members[PRESETS_NAME] = json.dumps(
            {"presets": presets}, indent=2, sort_keys=True
        ).encode("utf-8")

    target = Path(output).expanduser().resolve()
    _write_archive(target, members)

    verified = load_source(target)
    return {
        "ok": True,
        "kind": "package",
        "path": str(target),
        "source_id": source.source_id,
        "package_id": package_id,
        "effect_id": definition.id,
        "type": definition.definition_type.value,
        "preset_count": len(verified.packages[0].presets),
        "size_bytes": target.stat().st_size,
    }


def pack_effect_set(
    directory: str | Path, output: str | Path, *, skip_validation: bool = False
) -> dict[str, Any]:
    """Bundle prebuilt packages into a ``.lefxset`` archive."""
    source: EffectSetSource = load_effect_set_source(directory)

    if not skip_validation:
        report = validate_effect_set_source(source.root)
        if not report.ok:
            raise SourceError(
                f"{source.root} did not validate:\n  " + "\n  ".join(report.errors)
            )

    manifest: dict[str, Any] = {
        "format": SET_FORMAT,
        "set_id": source.set_id,
        "source_id": source.source_id,
        "title": source.title,
        "version": source.version,
        "min_sdk_version": source.min_sdk_version,
        "effects": list(source.members),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for key, value in (
        ("description", source.description),
        ("author", source.author),
        ("vendor", source.vendor),
        ("license", source.license_id),
    ):
        if value:
            manifest[key] = value
    if source.tags:
        manifest["tags"] = list(source.tags)

    members: dict[str, bytes] = {
        SET_MANIFEST_NAME: json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    }
    for member in source.members:
        members[f"effects/{member}"] = (source.effects_dir / member).read_bytes()

    target = Path(output).expanduser().resolve()
    _write_archive(target, members)

    verified = load_source(target)
    return {
        "ok": True,
        "kind": "set",
        "path": str(target),
        "set_id": source.set_id,
        "source_id": source.source_id,
        "effect_count": len(verified.packages),
        "preset_count": verified.preset_count,
        "size_bytes": target.stat().st_size,
    }


def build_effect_set(
    set_directory: str | Path,
    source_directories: Iterable[str | Path],
    output: str | Path,
    *,
    stage: str | Path | None = None,
) -> dict[str, Any]:
    """Build every source, place the packages, then bundle the set.

    The normal path for a first-party catalogue: sources in, one verified set
    out, with each package validated on its own along the way.
    """
    set_root = Path(set_directory).expanduser().resolve()
    effects_dir = Path(stage) if stage is not None else set_root / "effects"
    effects_dir.mkdir(parents=True, exist_ok=True)

    built: list[dict[str, Any]] = []
    for directory in source_directories:
        source = load_effect_source(directory)
        effect_class = import_effect_class(source)
        name = f"{effect_class.get_definition().id}.lefx"
        built.append(pack_effect(source.root, effects_dir / name))

    result = pack_effect_set(set_root, output)
    result["packages"] = built
    return result


__all__ = ["build_effect_set", "pack_effect", "pack_effect_set"]
