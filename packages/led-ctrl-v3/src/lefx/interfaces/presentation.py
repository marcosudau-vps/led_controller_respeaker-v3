"""Turning engine objects into the payloads the API and CLI return.

Serialization lives here rather than on the service, which in the predecessor
had grown a set of private ``_serialize_*`` methods and become a presentation
layer alongside everything else it did.
"""

from __future__ import annotations

from typing import Any

from lefx.engine import Preset, RegisteredEffect, ResolvedTarget
from lefx.sdk import ControlledOverlayDefinition, DefinitionBase, ParamDefinition, StateDefinition


def parameter(param: ParamDefinition) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": param.type.value,
        "required": param.required,
        "description": param.description,
        "minimum": param.minimum,
        "maximum": param.maximum,
        "enum_values": list(param.enum_values),
        "unit": param.unit,
        "nullable": param.nullable,
        "aliases": list(param.aliases),
    }
    if param.has_default:
        payload["default"] = param.default
    return payload


def definition(effect: RegisteredEffect) -> dict[str, Any]:
    """The full contract of one definition."""
    declared = effect.definition
    payload: dict[str, Any] = {
        "id": declared.id,
        "qualified_id": effect.qualified_id,
        "package_id": effect.package_id,
        "source_id": effect.source_id,
        "type": declared.definition_type.value,
        "form": declared.kind.value,
        "overlay_mode": None if declared.overlay_mode is None else declared.overlay_mode.value,
        "title": declared.title,
        "description": declared.description,
        "version": declared.version,
        "tags": list(declared.tags),
        "visual": {
            "color_model": declared.color_model.value,
            "composition": declared.composition.value,
            "animated": declared.animated,
            "directional": declared.directional,
        },
        "config": {name: parameter(param) for name, param in declared.parameter_schema.items()},
        "runtime_inputs": {
            name: parameter(param) for name, param in declared.runtime_input_schema.items()
        },
        "input_sampling": _sampling(declared),
        "placement": _placement(declared),
    }
    return payload


def _sampling(declared: DefinitionBase) -> dict[str, Any] | None:
    policy = declared.input_sampling
    if policy is None or not declared.runtime_input_schema:
        return None
    return {
        "mode": policy.mode.value,
        "provider_id": policy.provider_id,
        "interval_ms": policy.interval_ms,
        "heartbeat_interval_ms": policy.heartbeat_interval_ms,
        "max_missed_heartbeats": policy.max_missed_heartbeats,
        "failure_after_ms": policy.failure_after_ms,
    }


def _placement(declared: DefinitionBase) -> dict[str, Any]:
    """Where this form runs — derived from the type, never chosen by a caller."""
    if isinstance(declared, StateDefinition):
        return {
            "slots": [slot.value for slot in declared.slots],
            "restorable": declared.restorable,
        }
    if isinstance(declared, ControlledOverlayDefinition):
        return {"requires_channel": True}
    return {
        "duration_field": declared.duration_field.value,  # type: ignore[attr-defined]
        "supports_duration_override": declared.supports_duration_override,  # type: ignore[attr-defined]
        "default_priority": getattr(declared, "default_priority", None),
    }


def preset(item: Preset) -> dict[str, Any]:
    return item.to_dict()


def resolved(target: str, item: ResolvedTarget) -> dict[str, Any]:
    payload = definition(item.effect)
    payload["resolved_from"] = target
    payload["resolved_kind"] = item.kind
    if item.preset is not None:
        payload["preset"] = item.preset.to_dict()
    return payload


def summary(effect: RegisteredEffect) -> dict[str, Any]:
    """The short form used by listings without ``--details``."""
    return {
        "id": effect.effect_id,
        "title": effect.definition.title,
        "type": effect.definition.definition_type.value,
        "form": effect.definition.kind.value,
        "source_id": effect.source_id,
    }


__all__ = ["definition", "parameter", "preset", "resolved", "summary"]
