"""Read-only catalogue snapshots backed by LEFX's typed definitions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from lefx.engine.errors import EngineError
from lefx.engine.library import EffectLibrary
from lefx.engine.registry import EffectRegistry, ResolvedTarget
from lefx.interfaces.discovery import installed_effect_sets
from lefx.sdk import DefinitionBase, DefinitionKind, resolve_configuration


@dataclass(frozen=True)
class CatalogueEntry:
    qualified_id: str
    short_id: str
    source_id: str
    package_id: str | None
    package_version: int | None
    title: str
    description: str
    tags: tuple[str, ...]
    definition: DefinitionBase
    preset: Mapping[str, Any] | None = None

    @property
    def form(self) -> DefinitionKind:
        return self.definition.kind

    @property
    def label(self) -> str:
        kind = "Preset" if self.preset is not None else "Effekt"
        return f"{self.title} · {kind} · {self.qualified_id}"

    def resolve_config(self, overrides=None) -> dict:
        return deepcopy(resolve_configuration(
            self.definition, preset=self.preset, overrides=overrides
        ))


class CatalogueProvider(Protocol):
    def entries(self) -> tuple[CatalogueEntry, ...]: ...
    def resolve(self, target: str) -> CatalogueEntry: ...


class MemoryCatalogue:
    """Provider for embedders and tests with an existing sequence of entries."""

    def __init__(self, entries=()):
        self._entries = tuple(entries)

    def entries(self) -> tuple[CatalogueEntry, ...]:
        return self._entries

    def resolve(self, target: str) -> CatalogueEntry:
        name = target.strip()
        exact = [entry for entry in self._entries if name == entry.qualified_id]
        matches = exact or [
            entry for entry in self._entries
            if name in (entry.short_id, entry.package_id if entry.preset is None else None,
                        f"{entry.source_id}.{entry.short_id}")
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            candidates = ", ".join(sorted(entry.qualified_id for entry in matches))
            raise ValueError(f"Mehrdeutiges Ziel {name!r}: {candidates}")
        raise ValueError(f"Unbekanntes Ziel {name!r}. Prüfe die Katalogquellen.")


def _entry(resolved: ResolvedTarget) -> CatalogueEntry:
    registered, preset = resolved.effect, resolved.preset
    definition = registered.definition
    return CatalogueEntry(
        preset.qualified_id if preset else registered.qualified_id,
        resolved.target_id, preset.source_id if preset else registered.source_id,
        registered.package_id, registered.package_version,
        (preset.title or preset.preset_id) if preset else definition.title,
        preset.description if preset else definition.description,
        preset.tags if preset else definition.tags, definition,
        deepcopy(dict(preset.params)) if preset else None,
    )


class LefxCatalogueAdapter:
    """Wrap an EffectRegistry, or a library whose registry can be refreshed."""

    def __init__(self, source: EffectRegistry | EffectLibrary, *, owns_library=False):
        self._source = source
        self._owns_library = owns_library

    @classmethod
    def installed(cls, included=("core-set", "smartspeaker-set"),
                  *, extra_sources=()) -> LefxCatalogueAdapter:
        archives = installed_effect_sets(list(included))
        library = EffectLibrary()
        try:
            for path in (*archives.values(), *extra_sources):
                library.add_source(Path(path))
        except Exception:
            library.close()
            raise
        return cls(library, owns_library=True)

    @property
    def registry(self) -> EffectRegistry:
        return self._source.registry if isinstance(self._source, EffectLibrary) else self._source

    def entries(self) -> tuple[CatalogueEntry, ...]:
        registry = self.registry
        definitions = [_entry(ResolvedTarget(effect)) for effect in registry.list_effects()]
        presets = [_entry(ResolvedTarget(registry.get(preset.effect_id), preset))
                   for preset in registry.list_presets()]
        return tuple(definitions + presets)

    def resolve(self, target: str) -> CatalogueEntry:
        try:
            return _entry(self.registry.resolve(target))
        except EngineError as exc:
            raise ValueError(str(exc)) from exc

    def sources(self) -> list[dict]:
        return self._source.sources() if isinstance(self._source, EffectLibrary) else []

    def refresh(self) -> None:
        if isinstance(self._source, EffectLibrary):
            self._source.reload()

    def close(self) -> None:
        if self._owns_library:
            self._source.close()

    def __enter__(self) -> LefxCatalogueAdapter:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
