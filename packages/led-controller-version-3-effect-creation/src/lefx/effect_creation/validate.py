"""Source validation and the smoke render.

The build is a quality gate, not a zip step. A source that reaches the packer
has already been proven to import cleanly on its own, to declare exactly one
definition, to keep its presets inside its own schema, and to render a frame
that satisfies the contract it declared — at more than one ring size, because a
package that only works at twelve LEDs has hardcoded something it should not.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lefx.engine import check_frame
from lefx.sdk import (
    BaseEffect,
    DefinitionBase,
    ParameterValidationError,
    RenderContext,
    initial_runtime_inputs,
    resolve_configuration,
)

from .imports import ImportViolation, check_imports, find_effect_classes
from .source import EffectSetSource, EffectSource, SourceError

SMOKE_LED_COUNTS: tuple[int, ...] = (5, 12, 24)

_module_counter = 0


@dataclass(slots=True)
class ValidationReport:
    ok: bool
    kind: str
    identifier: str
    source_id: str
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "id": self.identifier,
            "source_id": self.source_id,
            "details": self.details,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def import_effect_class(source: EffectSource) -> type[BaseEffect]:
    """Import the source in isolation and return its single definition class."""
    declared = find_effect_classes(source.entry_path)
    if not declared:
        raise SourceError(
            f"{source.entry_path} defines no BaseEffect subclass; a source ships "
            "exactly one definition"
        )
    if source.entry_class is None and len(declared) > 1:
        raise SourceError(
            f"{source.entry_path} defines several definitions ({', '.join(declared)}); "
            "a source ships exactly one, or the manifest must name entry_class"
        )
    wanted = source.entry_class or declared[0]
    if wanted not in declared:
        raise SourceError(
            f"{source.manifest_path} names entry_class {wanted!r}, which "
            f"{source.entry_path.name} does not define"
        )

    global _module_counter
    _module_counter += 1
    alias = f"_lefx_src_{source.root.name}_{_module_counter}"

    init_path = source.root / "__init__.py"
    created_init = not init_path.exists()
    if created_init:
        init_path.write_text("", encoding="utf-8")
    try:
        spec = importlib.util.spec_from_file_location(
            alias, init_path, submodule_search_locations=[str(source.root)]
        )
        if spec is None or spec.loader is None:
            raise SourceError(f"Cannot import {source.root}")
        package = importlib.util.module_from_spec(spec)
        sys.modules[alias] = package
        spec.loader.exec_module(package)
        module = importlib.import_module(f"{alias}.{source.entry_module}")
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError(f"Importing {source.entry_path} failed: {exc}") from exc
    finally:
        sys.modules.pop(alias, None)
        if created_init:
            init_path.unlink(missing_ok=True)

    effect_class = getattr(module, wanted, None)
    if not isinstance(effect_class, type) or not issubclass(effect_class, BaseEffect):
        raise SourceError(f"{wanted} in {source.entry_path.name} is not a BaseEffect subclass")
    if not isinstance(getattr(effect_class, "definition", None), DefinitionBase):
        raise SourceError(f"{wanted} declares no LEFX V3 definition")
    return effect_class


def smoke_render(
    effect_class: type[BaseEffect], *, led_counts: tuple[int, ...] = SMOKE_LED_COUNTS
) -> None:
    """Render one frame per ring size and hold it to the declared contract.

    This catches integration mistakes, not visual ones. It does not replace
    deliberate animation or boundary tests.
    """
    definition = effect_class.get_definition()
    params = resolve_configuration(definition)
    inputs = initial_runtime_inputs(definition)
    for led_count in led_counts:
        instance = effect_class()
        context = RenderContext(
            now=1.0,
            started_at=0.0,
            led_count=led_count,
            definition=definition,
            params=params,
            inputs=inputs,
        )
        try:
            frame = instance.render(context)
        except Exception as exc:
            raise SourceError(
                f"{definition.id!r} failed to render at {led_count} LEDs: {exc}"
            ) from exc
        check_frame(frame, definition, led_count)


def validate_effect_source(directory: str | Path) -> ValidationReport:
    """Everything a source must satisfy before it may be packed."""
    from .source import load_effect_source

    source = load_effect_source(directory)
    report = ValidationReport(
        ok=False, kind="effect", identifier="", source_id=source.source_id
    )

    violations: list[ImportViolation] = check_imports(source.root)
    if violations:
        report.errors.extend(str(item) for item in violations)
        return report

    try:
        effect_class = import_effect_class(source)
    except SourceError as exc:
        report.errors.append(str(exc))
        return report

    definition = effect_class.get_definition()
    report.identifier = definition.id

    if source.root.name != definition.id:
        report.warnings.append(
            f"directory is {source.root.name!r} but the definition is {definition.id!r}; "
            "keeping them equal makes the catalogue navigable"
        )

    presets = source.presets()
    for preset_id, entry in presets.items():
        if not isinstance(entry, dict):
            report.errors.append(f"preset {preset_id!r} is not an object")
            continue
        unknown = set(entry) - {"title", "description", "tags", "params"}
        if unknown:
            report.errors.append(
                f"preset {preset_id!r} has unknown keys: {', '.join(sorted(unknown))}. "
                "A preset carries configuration only."
            )
            continue
        try:
            resolve_configuration(definition, preset=entry.get("params", {}))
        except ParameterValidationError as exc:
            report.errors.append(f"preset {preset_id!r} does not satisfy the schema: {exc}")

    try:
        smoke_render(effect_class)
    except SourceError as exc:
        report.errors.append(str(exc))
    except Exception as exc:
        report.errors.append(f"smoke render failed: {exc}")

    report.details = {
        "kind": definition.kind.value,
        "type": definition.definition_type.value,
        "package_id": source.package_id or f"{source.source_id}.{definition.id}",
        "entry_class": effect_class.__name__,
        "entry_module": source.entry_module,
        "preset_count": len(presets),
        "led_counts": list(SMOKE_LED_COUNTS),
    }
    report.ok = not report.errors
    return report


def validate_effect_set_source(directory: str | Path) -> ValidationReport:
    """A set is checked as a whole: members, namespace and id collisions."""
    from lefx.engine import load_source as load_package

    from .source import load_effect_set_source

    source: EffectSetSource = load_effect_set_source(directory)
    report = ValidationReport(
        ok=False, kind="set", identifier=source.set_id, source_id=source.source_id
    )

    seen: dict[str, str] = {}
    effect_count = 0
    preset_count = 0
    for member in source.members:
        path = source.effects_dir / member
        try:
            loaded = load_package(path)
        except Exception as exc:
            report.errors.append(f"{member}: {exc}")
            continue
        if loaded.source_id != source.source_id:
            report.errors.append(
                f"{member} declares source {loaded.source_id!r} but the set is "
                f"{source.source_id!r}; every member shares the set's namespace"
            )
        for package in loaded.packages:
            effect_count += 1
            preset_count += len(package.presets)
            for identifier in (package.effect_id, *(p.preset_id for p in package.presets)):
                previous = seen.get(identifier)
                if previous is not None:
                    report.errors.append(
                        f"{identifier!r} is declared by both {previous} and {member}"
                    )
                seen[identifier] = member

    report.details = {
        "title": source.title,
        "members": list(source.members),
        "effect_count": effect_count,
        "preset_count": preset_count,
    }
    report.ok = not report.errors
    return report


__all__ = [
    "SMOKE_LED_COUNTS",
    "ValidationReport",
    "import_effect_class",
    "smoke_render",
    "validate_effect_set_source",
    "validate_effect_source",
]
