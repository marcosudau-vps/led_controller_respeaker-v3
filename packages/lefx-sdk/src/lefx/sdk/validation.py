"""Schema-level validation of incoming payloads.

Single values are normalized in :mod:`lefx.sdk.parameters`. This module works on
whole payloads: it resolves aliases, rejects unknown fields with suggestions,
and collects every problem before raising, so one round trip reports everything
that is wrong rather than the first thing.
"""

from __future__ import annotations

import difflib
from typing import Any, Mapping

from .definitions import DefinitionBase
from .errors import ParameterValidationError, ValidationIssue, ValueNormalizationError
from .parameters import ParamDefinition, normalize_parameter_value


def resolve_configuration(
    definition: DefinitionBase,
    *,
    preset: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge defaults, an optional preset and explicit values into canonical config.

    Precedence is defaults, then preset, then explicit values. Because every
    configuration field declares a default, the result always contains every
    declared key — a renderer never has to guess a fallback.
    """
    merged: dict[str, Any] = {
        name: param.default for name, param in definition.parameter_schema.items()
    }
    supplied: dict[str, Any] = {}
    supplied.update(dict(preset or {}))
    supplied.update(dict(overrides or {}))

    normalized_supplied = normalize_values(
        definition.parameter_schema,
        supplied,
        field_prefix="config",
    )
    merged.update(normalized_supplied)
    return merged


def initial_runtime_inputs(definition: DefinitionBase) -> dict[str, Any]:
    """The starting runtime input map of a fresh instance.

    Required inputs begin as ``None`` because no value has arrived yet; the
    rest begin at their declared default. Every declared key is present, which
    is what lets a renderer index ``ctx.inputs`` directly.
    """
    values: dict[str, Any] = {}
    for name, param in definition.runtime_input_schema.items():
        values[name] = None if param.required else param.default
    return values


def normalize_runtime_inputs(
    definition: DefinitionBase,
    values: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Normalize a partial runtime input update.

    Only supplied fields are returned. An empty update is valid and means "still
    alive" — the caller treats it as a heartbeat. A single unknown or invalid
    field rejects the whole update, so an instance never ends up half applied.
    """
    return normalize_values(
        definition.runtime_input_schema,
        values,
        field_prefix="inputs",
    )


def normalize_values(
    schema: Mapping[str, ParamDefinition],
    values: Mapping[str, Any] | None,
    *,
    field_prefix: str,
) -> dict[str, Any]:
    """Resolve aliases, reject unknown fields and normalize what remains."""
    raw = dict(values or {})
    issues: list[ValidationIssue] = []

    alias_map = {
        alias: name for name, param in schema.items() for alias in param.aliases
    }
    for alias, name in alias_map.items():
        if alias not in raw:
            continue
        if name in raw:
            issues.append(
                ValidationIssue(
                    code="conflicting_fields",
                    field=f"{field_prefix}.{alias}",
                    value=raw[alias],
                    message=f"Fields {name!r} and its alias {alias!r} cannot be used together",
                )
            )
            raw.pop(alias)
            continue
        raw[name] = raw.pop(alias)

    accepted = sorted(set(schema) | set(alias_map))
    for name in sorted(set(raw) - set(schema)):
        suggestions = tuple(difflib.get_close_matches(name, accepted, n=3, cutoff=0.55))
        issues.append(
            ValidationIssue(
                code="unknown_field",
                field=f"{field_prefix}.{name}",
                value=raw[name],
                message=f"Unknown field {name!r}",
                suggestions=suggestions,
            )
        )

    normalized: dict[str, Any] = {}
    for name, param in schema.items():
        if name not in raw:
            continue
        try:
            normalized[name] = normalize_parameter_value(param, raw[name])
        except (ValueError, TypeError) as exc:
            code = exc.code if isinstance(exc, ValueNormalizationError) else "invalid_value"
            suggestions = (
                exc.suggestions if isinstance(exc, ValueNormalizationError) else ()
            )
            issues.append(
                ValidationIssue(
                    code=code,
                    field=f"{field_prefix}.{name}",
                    value=raw[name],
                    message=str(exc),
                    suggestions=tuple(suggestions),
                )
            )

    if issues:
        raise ParameterValidationError(issues)
    return normalized


__all__ = [
    "initial_runtime_inputs",
    "normalize_runtime_inputs",
    "normalize_values",
    "resolve_configuration",
]
