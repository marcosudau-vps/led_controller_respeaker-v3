"""Reading .lefx and .lefxset archives.

Three things are checked before a definition is allowed anywhere near the
registry: the archive contents still hash to what the build recorded, the
manifest still describes the class inside, and the class is the one the manifest
names. Any of them failing rejects the whole source — nothing is registered
partially.

A package carries executable Python. Hashes prove that the bytes were not
altered after the build; they say nothing about who wrote them. There is no
sandbox and no signature check, so only load packages you trust.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import threading
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, Mapping

from lefx.sdk import BaseEffect, DefinitionBase

from ..errors import PackageError
from ..registry import Preset
from .manifest import (
    HASHES_NAME,
    MANIFEST_NAME,
    PAYLOAD_DIR,
    PRESETS_NAME,
    SET_MANIFEST_NAME,
    check_manifest_matches_definition,
    parse_package_manifest,
    parse_set_manifest,
)

_import_lock = threading.Lock()
_module_counter = 0


@dataclass(slots=True, frozen=True)
class LoadedPackage:
    """One verified definition, ready to be registered."""

    manifest: Mapping[str, Any]
    definition: DefinitionBase
    effect_class: type[BaseEffect]
    presets: tuple[Preset, ...] = ()

    @property
    def source_id(self) -> str:
        return self.manifest["source_id"]

    @property
    def package_id(self) -> str:
        return self.manifest["package_id"]

    @property
    def effect_id(self) -> str:
        return self.manifest["effect_id"]

    @property
    def package_version(self) -> int:
        return int(self.manifest["package_version"])


@dataclass(slots=True, frozen=True)
class LoadedSource:
    """Everything one file contributed — a single package or a whole set."""

    path: Path
    kind: str
    source_id: str
    packages: tuple[LoadedPackage, ...] = ()
    set_manifest: Mapping[str, Any] | None = None

    @property
    def preset_count(self) -> int:
        return sum(len(package.presets) for package in self.packages)


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(archive: zipfile.ZipFile, name: str, label: str) -> Any:
    try:
        raw = archive.read(name)
    except KeyError as exc:
        raise PackageError(f"{label} is missing {name}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError(f"{label} has malformed {name}: {exc}") from exc


def _verify_hashes(archive: zipfile.ZipFile, label: str) -> None:
    """Every member the build recorded must still hash to the recorded value."""
    payload = _read_json(archive, HASHES_NAME, label)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("files"), Mapping):
        raise PackageError(f"{label} has a malformed {HASHES_NAME}")
    recorded: Mapping[str, str] = payload["files"]
    if not recorded:
        raise PackageError(f"{label} records no file hashes")

    present = {name for name in archive.namelist() if not name.endswith("/")}
    for name, expected in recorded.items():
        if name not in present:
            raise PackageError(f"{label} is missing recorded file {name}")
        actual = sha256_of(archive.read(name))
        if actual != expected:
            raise PackageError(
                f"{label} file {name} does not match its recorded hash; "
                "the package was altered after it was built"
            )
    unrecorded = present - set(recorded) - {HASHES_NAME}
    if unrecorded:
        raise PackageError(
            f"{label} contains files that were not part of the build: "
            f"{', '.join(sorted(unrecorded))}"
        )


def _next_module_name(effect_id: str) -> str:
    global _module_counter
    with _import_lock:
        _module_counter += 1
        return f"_lefx_pkg_{effect_id}_{_module_counter}"


def _import_entry_module(root: Path, module_name: str, package_alias: str) -> ModuleType:
    """Import the payload as its own top-level package.

    The payload directory becomes a package of its own so that relative imports
    inside a source keep working, while nothing about the host application's
    module layout leaks into it.
    """
    init_path = root / "__init__.py"
    if not init_path.is_file():
        init_path.write_text("", encoding="utf-8")

    spec = importlib.util.spec_from_file_location(
        package_alias, init_path, submodule_search_locations=[str(root)]
    )
    if spec is None or spec.loader is None:
        raise PackageError(f"Cannot import payload at {root}")
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_alias] = package
    try:
        spec.loader.exec_module(package)
        return importlib.import_module(f"{package_alias}.{module_name}")
    except Exception as exc:
        sys.modules.pop(package_alias, None)
        raise PackageError(f"Failed to import {module_name} from {root}: {exc}") from exc


def _effect_class_from(module: ModuleType, entry_class: str, label: str) -> type[BaseEffect]:
    candidate = getattr(module, entry_class, None)
    if candidate is None:
        raise PackageError(f"{label} declares entry class {entry_class!r}, which is missing")
    if not isinstance(candidate, type) or not issubclass(candidate, BaseEffect):
        raise PackageError(f"{label} entry class {entry_class!r} is not a BaseEffect subclass")
    definition = getattr(candidate, "definition", None)
    if not isinstance(definition, DefinitionBase):
        raise PackageError(f"{label} entry class {entry_class!r} declares no definition")
    return candidate


def _presets_from(payload: Any, manifest: Mapping[str, Any], label: str) -> tuple[Preset, ...]:
    if payload is None:
        return ()
    if not isinstance(payload, Mapping) or not isinstance(payload.get("presets"), Mapping):
        raise PackageError(f"{label} has a malformed {PRESETS_NAME}")
    presets: list[Preset] = []
    for preset_id, entry in payload["presets"].items():
        if not isinstance(entry, Mapping):
            raise PackageError(f"{label} preset {preset_id!r} is not an object")
        unknown = set(entry) - {"title", "description", "tags", "params"}
        if unknown:
            raise PackageError(
                f"{label} preset {preset_id!r} has unknown keys: {', '.join(sorted(unknown))}"
            )
        presets.append(
            Preset(
                preset_id=preset_id,
                source_id=manifest["source_id"],
                effect_id=manifest["effect_id"],
                params=dict(entry.get("params", {})),
                title=entry.get("title", ""),
                description=entry.get("description", ""),
                tags=tuple(entry.get("tags", ())),
            )
        )
    return tuple(presets)


def _load_package_archive(
    archive: zipfile.ZipFile, *, label: str, workdir: Path
) -> LoadedPackage:
    _verify_hashes(archive, label)
    manifest = parse_package_manifest(_read_json(archive, MANIFEST_NAME, label))

    presets_payload = None
    if PRESETS_NAME in archive.namelist():
        presets_payload = _read_json(archive, PRESETS_NAME, label)
    presets = _presets_from(presets_payload, manifest, label)

    root = workdir / manifest["effect_id"]
    root.mkdir(parents=True, exist_ok=True)
    for name in archive.namelist():
        if not name.startswith(f"{PAYLOAD_DIR}/") or name.endswith("/"):
            continue
        target = root / Path(name).relative_to(PAYLOAD_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))

    alias = _next_module_name(manifest["effect_id"])
    module = _import_entry_module(root, manifest["entry_module"], alias)
    effect_class = _effect_class_from(module, manifest["entry_class"], label)
    definition = effect_class.get_definition()

    if definition.id != manifest["effect_id"]:
        raise PackageError(
            f"{label} declares effect_id {manifest['effect_id']!r} but ships "
            f"definition {definition.id!r}"
        )
    check_manifest_matches_definition(manifest, definition)

    return LoadedPackage(
        manifest=manifest,
        definition=definition,
        effect_class=effect_class,
        presets=presets,
    )


def load_source(path: str | Path, *, workdir: Path | None = None) -> LoadedSource:
    """Load a ``.lefx`` or ``.lefxset`` file and verify everything it contains."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise PackageError(f"No package file at {resolved}")

    owns_workdir = workdir is None
    target = Path(workdir) if workdir is not None else Path(
        tempfile.mkdtemp(prefix="lefx-package-")
    )
    try:
        if resolved.suffix == ".lefx":
            with _open_archive(resolved) as archive:
                package = _load_package_archive(
                    archive, label=resolved.name, workdir=target
                )
            return LoadedSource(
                path=resolved,
                kind="package",
                source_id=package.source_id,
                packages=(package,),
            )
        if resolved.suffix == ".lefxset":
            return _load_set(resolved, target)
        raise PackageError(
            f"{resolved.name} is not a LEFX source; expected a .lefx or .lefxset file"
        )
    except Exception:
        if owns_workdir:
            shutil.rmtree(target, ignore_errors=True)
        raise


def _open_archive(path: Path) -> zipfile.ZipFile:
    """Open an archive, reporting a non-archive as a package problem.

    A file that is not a zip at all is just another malformed package, and the
    library treats every package problem the same way.
    """
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise PackageError(f"{path.name} is not a readable LEFX archive: {exc}") from exc
    except OSError as exc:
        raise PackageError(f"Cannot read {path}: {exc}") from exc


def _load_set(path: Path, workdir: Path) -> LoadedSource:
    label = path.name
    with _open_archive(path) as archive:
        _verify_hashes(archive, label)
        manifest = parse_set_manifest(_read_json(archive, SET_MANIFEST_NAME, label))
        packages: list[LoadedPackage] = []
        for member in manifest["effects"]:
            name = f"effects/{member}"
            if name not in archive.namelist():
                raise PackageError(f"{label} lists {member!r}, which is not in the archive")
            try:
                inner_archive = zipfile.ZipFile(_member_stream(archive, name))
            except zipfile.BadZipFile as exc:
                raise PackageError(f"{label} member {member!r} is not a readable archive") from exc
            with inner_archive as inner:
                package = _load_package_archive(
                    inner, label=f"{label}:{member}", workdir=workdir
                )
            if package.source_id != manifest["source_id"]:
                raise PackageError(
                    f"{label} member {member!r} declares source {package.source_id!r} "
                    f"but the set is {manifest['source_id']!r}; every member shares "
                    "the set's source namespace"
                )
            packages.append(package)

    _check_unique_ids(packages, label)
    return LoadedSource(
        path=path,
        kind="set",
        source_id=manifest["source_id"],
        packages=tuple(packages),
        set_manifest=manifest,
    )


def _member_stream(archive: zipfile.ZipFile, name: str) -> BytesIO:
    return BytesIO(archive.read(name))


def _check_unique_ids(packages: list[LoadedPackage], label: str) -> None:
    """Definition and preset ids share one namespace, inside a set as well."""
    seen: dict[str, str] = {}
    for package in packages:
        for identifier, what in _identifiers(package):
            previous = seen.get(identifier)
            if previous is not None:
                raise PackageError(
                    f"{label} declares {identifier!r} twice ({previous} and {what})"
                )
            seen[identifier] = what


def _identifiers(package: LoadedPackage) -> Iterator[tuple[str, str]]:
    yield package.effect_id, f"definition in {package.package_id}"
    for preset in package.presets:
        yield preset.preset_id, f"preset in {package.package_id}"


@dataclass(slots=True)
class PackageCache:
    """Holds the extracted payloads of everything currently loaded."""

    root: Path = field(
        default_factory=lambda: Path(tempfile.mkdtemp(prefix="lefx-packages-"))
    )

    def workdir(self, name: str) -> Path:
        target = self.root / name
        target.mkdir(parents=True, exist_ok=True)
        return target

    def clear(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


__all__ = [
    "LoadedPackage",
    "LoadedSource",
    "PackageCache",
    "load_source",
    "sha256_of",
]
