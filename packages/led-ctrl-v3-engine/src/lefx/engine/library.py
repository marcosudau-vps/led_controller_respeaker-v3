"""Which package files are loaded, and rebuilding the registry from them.

A reload builds a fresh registry and swaps it in only once every source has
loaded. A source that fails therefore changes nothing at all — there is no
half-registered state to reason about or clean up.

Discovery is explicit: the caller passes the directories to scan. The engine
reads no environment variables and knows no install layout, because where
packages live is a deployment question and this is not the deployment layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from .errors import PackageError, RegistrationError
from .packages import LoadedSource, PackageCache, load_source
from .registry import EffectRegistry

logger = logging.getLogger("lefx.engine.library")

PACKAGE_SUFFIXES = (".lefx", ".lefxset")


@dataclass(slots=True, frozen=True)
class SourceEntry:
    """One package file the library knows about."""

    path: Path
    enabled: bool = True
    autodiscovered: bool = False
    source_id: str | None = None
    kind: str | None = None
    effect_count: int = 0
    preset_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "source_id": self.source_id,
            "kind": self.kind,
            "enabled": self.enabled,
            "autodiscovered": self.autodiscovered,
            "effect_count": self.effect_count,
            "preset_count": self.preset_count,
            "error": self.error,
        }


def discover_packages(directories: Iterable[str | Path]) -> list[Path]:
    """Every ``.lefx`` and ``.lefxset`` below the given directories, sorted."""
    found: list[Path] = []
    for directory in directories:
        root = Path(directory).expanduser()
        if not root.is_dir():
            continue
        for suffix in PACKAGE_SUFFIXES:
            found.extend(sorted(root.rglob(f"*{suffix}")))
    unique: dict[Path, None] = {}
    for path in found:
        unique.setdefault(path.resolve(), None)
    return list(unique)


class EffectLibrary:
    """Owns the source list and the registry built from it."""

    def __init__(self, *, search_paths: Iterable[str | Path] = ()) -> None:
        self._entries: list[SourceEntry] = []
        self._suppressed: set[Path] = set()
        self._cache = PackageCache()
        self._registry = EffectRegistry()
        self._search_paths = [Path(path).expanduser() for path in search_paths]
        self.reload()

    @property
    def registry(self) -> EffectRegistry:
        return self._registry

    def sources(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]

    def add_source(self, path: str | Path, *, enabled: bool = True) -> SourceEntry:
        """Register a package file and reload. Rejected on the first problem."""
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise PackageError(f"No package file at {resolved}")
        if resolved.suffix not in PACKAGE_SUFFIXES:
            raise PackageError(
                f"{resolved.name} is not a LEFX source; expected one of: "
                f"{', '.join(PACKAGE_SUFFIXES)}"
            )
        self._suppressed.discard(resolved)
        existing = next((item for item in self._entries if item.path == resolved), None)
        if existing is None:
            self._entries.append(SourceEntry(path=resolved, enabled=enabled))
        else:
            self._entries[self._entries.index(existing)] = replace(existing, enabled=enabled)
        self.reload()
        return next(item for item in self._entries if item.path == resolved)

    def remove_source(self, source_id: str) -> None:
        """Drop a source and keep it out.

        Suppression is remembered rather than merely forgotten: a discovered
        file is still sitting in a search path, so without this the next reload
        would quietly bring it back.
        """
        matching = [item for item in self._entries if item.source_id == source_id]
        if not matching:
            raise PackageError(f"No loaded source with id {source_id!r}")
        self._suppressed.update(item.path for item in matching)
        self._entries = [item for item in self._entries if item.source_id != source_id]
        self.reload()

    def reload(self) -> None:
        """Rebuild everything. On failure the previous registry stays in place."""
        self._cache.clear()
        configured = {entry.path for entry in self._entries if not entry.autodiscovered}
        discovered = [
            path
            for path in discover_packages(self._search_paths)
            if path not in configured and path not in self._suppressed
        ]
        entries = [entry for entry in self._entries if not entry.autodiscovered]
        entries.extend(SourceEntry(path=path, autodiscovered=True) for path in discovered)

        registry = EffectRegistry()
        rebuilt: list[SourceEntry] = []
        for entry in entries:
            if not entry.enabled:
                rebuilt.append(replace(entry, effect_count=0, preset_count=0, error=None))
                continue
            try:
                loaded = load_source(entry.path, workdir=self._cache.workdir(entry.path.stem))
                _register(registry, loaded)
            except (PackageError, RegistrationError) as exc:
                # One bad file must not take the rest of the catalogue with it,
                # but it also must not appear half-loaded: its definitions are
                # simply absent and the reason is reported on the entry.
                logger.warning("failed to load effect source %s: %s", entry.path, exc)
                rebuilt.append(replace(entry, error=str(exc), effect_count=0, preset_count=0))
                continue
            rebuilt.append(
                replace(
                    entry,
                    source_id=loaded.source_id,
                    kind=loaded.kind,
                    effect_count=len(loaded.packages),
                    preset_count=loaded.preset_count,
                    error=None,
                )
            )

        self._entries = rebuilt
        self._registry = registry

    def close(self) -> None:
        self._cache.clear()


def _register(registry: EffectRegistry, loaded: LoadedSource) -> None:
    for package in loaded.packages:
        registry.register_effect(
            package.effect_class,
            source_id=package.source_id,
            package_id=package.package_id,
            package_version=package.package_version,
        )
    # Presets come second: every one of them references a definition, and
    # validating them needs that definition to be present already.
    for package in loaded.packages:
        for preset in package.presets:
            registry.register_preset(preset)


__all__ = ["EffectLibrary", "SourceEntry", "discover_packages"]
