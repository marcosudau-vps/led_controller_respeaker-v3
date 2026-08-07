"""Reading an editable effect source directory.

A source is what an author edits; a package is what a build produces. Keeping
the two words apart matters, because almost every confusing failure in the
predecessor came from treating a directory and an archive as the same thing.

Title, description, schemas and form live in the Python class, not in the YAML
manifest. The manifest carries only what the class cannot know about itself:
which source namespace it belongs to and where its entry point is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


class SourceError(ValueError):
    """A source directory does not satisfy the LEFX V3 layout or manifest rules."""


EFFECT_MANIFEST_STEMS = ("effect.yaml", "effect.yml", "effect.json")
SET_MANIFEST_STEMS = ("set.yaml", "set.yml", "set.json")

_EFFECT_REQUIRED = ("source_id",)
_EFFECT_ALLOWED = frozenset(
    _EFFECT_REQUIRED
    + (
        "package_id",
        "entry_file",
        "entry_class",
        "author",
        "vendor",
        "license",
        "compatible_hardware",
        "package_version",
        "min_sdk_version",
    )
)

_SET_REQUIRED = ("set_id", "source_id")
_SET_ALLOWED = frozenset(
    _SET_REQUIRED
    + (
        "title",
        "description",
        "version",
        "min_sdk_version",
        "effects",
        "tags",
        "author",
        "vendor",
        "license",
    )
)

# Names that carried meaning in older generations and must not be silently
# accepted now, because accepting them would mean ignoring what they said.
_RETIRED_KEYS = frozenset({"commands", "widgets", "common", "type", "overlay_mode", "title", "description"})


def _read_manifest(directory: Path, stems: tuple[str, ...], label: str) -> tuple[Path, Any]:
    found = [directory / stem for stem in stems if (directory / stem).is_file()]
    if not found:
        raise SourceError(
            f"{label} {directory} has no manifest; expected one of: {', '.join(stems)}"
        )
    if len(found) > 1:
        names = ", ".join(path.name for path in found)
        raise SourceError(f"{label} {directory} has several manifests: {names}")

    path = found[0]
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SourceError(f"{path} is malformed: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise SourceError(f"{path} must contain an object")
    return path, dict(payload)


def _check_keys(
    payload: Mapping[str, Any], required: tuple[str, ...], allowed: frozenset[str], path: Path
) -> None:
    missing = [key for key in required if not str(payload.get(key, "")).strip()]
    if missing:
        raise SourceError(f"{path} is missing: {', '.join(missing)}")
    unknown = set(payload) - allowed
    if not unknown:
        return
    retired = sorted(unknown & _RETIRED_KEYS)
    if retired:
        raise SourceError(
            f"{path} declares {', '.join(retired)}, which V3 does not use. "
            "The definition class is the single source of truth for the contract."
        )
    raise SourceError(f"{path} has unknown keys: {', '.join(sorted(unknown))}")


@dataclass(slots=True, frozen=True)
class EffectSource:
    """One editable definition directory."""

    root: Path
    manifest_path: Path
    source_id: str
    entry_file: str
    entry_class: str | None
    package_id: str | None
    author: str | None = None
    vendor: str | None = None
    license_id: str | None = None
    package_version: int = 1
    min_sdk_version: str = "3.0.0"
    compatible_hardware: tuple[str, ...] = ()

    @property
    def entry_path(self) -> Path:
        return self.root / self.entry_file

    @property
    def entry_module(self) -> str:
        return Path(self.entry_file).stem

    @property
    def presets_path(self) -> Path | None:
        for name in ("presets.yaml", "presets.yml", "presets.json"):
            candidate = self.root / name
            if candidate.is_file():
                return candidate
        return None

    def presets(self) -> dict[str, Any]:
        path = self.presets_path
        if path is None:
            return {}
        text = path.read_text(encoding="utf-8")
        try:
            payload = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise SourceError(f"{path} is malformed: {exc}") from exc
        if payload is None:
            return {}
        if not isinstance(payload, Mapping) or not isinstance(payload.get("presets"), Mapping):
            raise SourceError(f"{path} must contain a 'presets' object")
        return dict(payload["presets"])


def load_effect_source(directory: str | Path) -> EffectSource:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise SourceError(f"No source directory at {root}")

    path, payload = _read_manifest(root, EFFECT_MANIFEST_STEMS, "Effect source")
    _check_keys(payload, _EFFECT_REQUIRED, _EFFECT_ALLOWED, path)

    entry_file = str(payload.get("entry_file") or "effect.py")
    if not (root / entry_file).is_file():
        raise SourceError(f"{path} points at {entry_file}, which does not exist")

    hardware = payload.get("compatible_hardware", ())
    if isinstance(hardware, str):
        hardware = (hardware,)

    return EffectSource(
        root=root,
        manifest_path=path,
        source_id=str(payload["source_id"]).strip(),
        entry_file=entry_file,
        entry_class=(str(payload["entry_class"]).strip() if payload.get("entry_class") else None),
        package_id=(str(payload["package_id"]).strip() if payload.get("package_id") else None),
        author=payload.get("author"),
        vendor=payload.get("vendor"),
        license_id=payload.get("license"),
        package_version=int(payload.get("package_version", 1)),
        min_sdk_version=str(payload.get("min_sdk_version", "3.0.0")),
        compatible_hardware=tuple(str(item) for item in hardware),
    )


@dataclass(slots=True, frozen=True)
class EffectSetSource:
    """A directory collecting prebuilt packages into one distributable set."""

    root: Path
    manifest_path: Path
    set_id: str
    source_id: str
    title: str
    description: str = ""
    version: int = 1
    min_sdk_version: str = "3.0.0"
    tags: tuple[str, ...] = ()
    author: str | None = None
    vendor: str | None = None
    license_id: str | None = None
    members: tuple[str, ...] = ()

    @property
    def effects_dir(self) -> Path:
        return self.root / "effects"


def load_effect_set_source(directory: str | Path) -> EffectSetSource:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise SourceError(f"No set source directory at {root}")

    path, payload = _read_manifest(root, SET_MANIFEST_STEMS, "Set source")
    _check_keys(payload, _SET_REQUIRED, _SET_ALLOWED, path)

    effects_dir = root / "effects"
    if not effects_dir.is_dir():
        raise SourceError(f"{root} has no effects/ directory")

    declared = payload.get("effects")
    if declared is None:
        members = tuple(sorted(item.name for item in effects_dir.glob("*.lefx")))
    else:
        if not isinstance(declared, list) or not declared:
            raise SourceError(f"{path} 'effects' must be a non-empty list")
        members = tuple(str(item) for item in declared)
    if not members:
        raise SourceError(f"{effects_dir} contains no built .lefx packages")

    for member in members:
        if not (effects_dir / member).is_file():
            raise SourceError(f"{path} lists {member!r}, which is not in {effects_dir}")

    return EffectSetSource(
        root=root,
        manifest_path=path,
        set_id=str(payload["set_id"]).strip(),
        source_id=str(payload["source_id"]).strip(),
        title=str(payload.get("title") or payload["set_id"]),
        description=str(payload.get("description", "")),
        version=int(payload.get("version", 1)),
        min_sdk_version=str(payload.get("min_sdk_version", "3.0.0")),
        tags=tuple(str(item) for item in payload.get("tags", ())),
        author=payload.get("author"),
        vendor=payload.get("vendor"),
        license_id=payload.get("license"),
        members=members,
    )


__all__ = [
    "EffectSetSource",
    "EffectSource",
    "SourceError",
    "load_effect_set_source",
    "load_effect_source",
]
