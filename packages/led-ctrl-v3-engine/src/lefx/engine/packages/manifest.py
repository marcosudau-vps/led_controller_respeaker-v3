"""Serializing a definition into a package manifest, and checking it back.

The Python class is the source of truth for the contract. The manifest is a
serialized copy that lets tooling read a package without executing it — and,
more importantly, lets the loader prove that the metadata shipped in the archive
still describes the class inside it.

The check is a whole-structure comparison rather than a field walk: the
definition is re-serialized after import and the two dictionaries must be equal.
A field added later is therefore covered automatically instead of being
silently unchecked.
"""

from __future__ import annotations

from typing import Any, Mapping

from lefx.sdk import (
    MISSING,
    ControlledOverlayDefinition,
    DefinitionBase,
    DefinitionKind,
    EventDefinition,
    ParamDefinition,
    StateDefinition,
)

from ..errors import PackageError

PACKAGE_FORMAT = "lefx/3"
SET_FORMAT = "lefxset/3"

MANIFEST_NAME = "manifest.json"
SET_MANIFEST_NAME = "set-manifest.json"
PRESETS_NAME = "effect-presets.json"
HASHES_NAME = "hashes.json"
PAYLOAD_DIR = "payload"


def serialize_param(param: ParamDefinition) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": param.name,
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
    # "no default" and "defaults to null" are different states, so the key is
    # present only when a default was actually declared.
    if param.has_default:
        payload["default"] = param.default
    return payload


def serialize_schema(schema: Mapping[str, ParamDefinition]) -> dict[str, Any]:
    return {name: serialize_param(param) for name, param in schema.items()}


def serialize_definition(definition: DefinitionBase) -> dict[str, Any]:
    """The complete contract of one definition as plain JSON-compatible data."""
    payload: dict[str, Any] = {
        "kind": definition.kind.value,
        "definition_type": definition.definition_type.value,
        "overlay_mode": None
        if definition.overlay_mode is None
        else definition.overlay_mode.value,
        "id": definition.id,
        "title": definition.title,
        "description": definition.description,
        "version": definition.version,
        "tags": list(definition.tags),
        "visual": {
            "color_model": definition.color_model.value,
            "composition": definition.composition.value,
            "animated": definition.animated,
            "directional": definition.directional,
        },
        "parameter_schema": serialize_schema(definition.parameter_schema),
        "runtime_input_schema": serialize_schema(definition.runtime_input_schema),
        "input_sampling": None,
        "form": {},
    }

    if isinstance(definition, StateDefinition):
        payload["form"] = {
            "slots": [slot.value for slot in definition.slots],
            "restorable": definition.restorable,
        }
    elif isinstance(definition, ControlledOverlayDefinition):
        policy = definition.sampling
        payload["input_sampling"] = {
            "mode": policy.mode.value,
            "provider_id": policy.provider_id,
            "interval_ms": policy.interval_ms,
            "heartbeat_interval_ms": policy.heartbeat_interval_ms,
            "max_missed_heartbeats": policy.max_missed_heartbeats,
            "failure_after_ms": policy.failure_after_ms,
        }
    else:
        payload["form"] = {
            "duration_field": definition.duration_field.value,  # type: ignore[attr-defined]
            "supports_duration_override": definition.supports_duration_override,  # type: ignore[attr-defined]
        }
        if isinstance(definition, EventDefinition):
            payload["form"]["default_priority"] = definition.default_priority

    return payload


def build_package_manifest(
    definition: DefinitionBase,
    *,
    source_id: str,
    package_id: str,
    entry_module: str,
    entry_class: str,
    package_version: int = 1,
    min_sdk_version: str = "3.0.0",
    author: str | None = None,
    vendor: str | None = None,
    license_id: str | None = None,
    built_at: str | None = None,
    compatible_hardware: tuple[str, ...] = (),
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "format": PACKAGE_FORMAT,
        "source_id": source_id,
        "package_id": package_id,
        "effect_id": definition.id,
        "qualified_id": f"{source_id}::{definition.id}",
        "package_version": package_version,
        "min_sdk_version": min_sdk_version,
        "runtime": "python",
        "entry_module": entry_module,
        "entry_class": entry_class,
        "definition": serialize_definition(definition),
    }
    optional = {
        "author": author,
        "vendor": vendor,
        "license": license_id,
        "built_at": built_at,
    }
    manifest.update({key: value for key, value in optional.items() if value is not None})
    if compatible_hardware:
        manifest["compatible_hardware"] = list(compatible_hardware)
    return manifest


_REQUIRED_PACKAGE_KEYS = (
    "format",
    "source_id",
    "package_id",
    "effect_id",
    "package_version",
    "entry_module",
    "entry_class",
    "definition",
)

_ALLOWED_PACKAGE_KEYS = frozenset(
    _REQUIRED_PACKAGE_KEYS
    + (
        "qualified_id",
        "min_sdk_version",
        "runtime",
        "author",
        "vendor",
        "license",
        "built_at",
        "compatible_hardware",
    )
)


def parse_package_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the envelope. Unknown keys are refused, never ignored."""
    if not isinstance(payload, Mapping):
        raise PackageError("Package manifest must be an object")
    if payload.get("format") != PACKAGE_FORMAT:
        raise PackageError(
            f"Unsupported package format {payload.get('format')!r}; expected "
            f"{PACKAGE_FORMAT!r}. V1 and V2 packages are not read by this runtime."
        )
    missing = [key for key in _REQUIRED_PACKAGE_KEYS if key not in payload]
    if missing:
        raise PackageError(f"Package manifest is missing: {', '.join(missing)}")
    unknown = set(payload) - _ALLOWED_PACKAGE_KEYS
    if unknown:
        raise PackageError(f"Package manifest has unknown keys: {', '.join(sorted(unknown))}")
    if not isinstance(payload["definition"], Mapping):
        raise PackageError("Package manifest 'definition' must be an object")
    return dict(payload)


_REQUIRED_SET_KEYS = ("format", "set_id", "source_id", "effects")
_ALLOWED_SET_KEYS = frozenset(
    _REQUIRED_SET_KEYS
    + (
        "title",
        "description",
        "version",
        "min_sdk_version",
        "tags",
        "author",
        "vendor",
        "license",
        "built_at",
    )
)


def parse_set_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise PackageError("Set manifest must be an object")
    if payload.get("format") != SET_FORMAT:
        raise PackageError(
            f"Unsupported set format {payload.get('format')!r}; expected {SET_FORMAT!r}"
        )
    missing = [key for key in _REQUIRED_SET_KEYS if key not in payload]
    if missing:
        raise PackageError(f"Set manifest is missing: {', '.join(missing)}")
    unknown = set(payload) - _ALLOWED_SET_KEYS
    if unknown:
        raise PackageError(f"Set manifest has unknown keys: {', '.join(sorted(unknown))}")
    if not isinstance(payload["effects"], list) or not payload["effects"]:
        raise PackageError("Set manifest must list at least one member")
    return dict(payload)


def check_manifest_matches_definition(
    manifest: Mapping[str, Any], definition: DefinitionBase
) -> None:
    """Refuse a package whose metadata drifted from the class it ships."""
    declared = manifest["definition"]
    actual = serialize_definition(definition)
    if declared == actual:
        return
    differences = _describe_differences(declared, actual)
    raise PackageError(
        f"Package manifest does not match the definition in {manifest['effect_id']!r}: "
        + "; ".join(differences)
    )


def _describe_differences(declared: Any, actual: Any, path: str = "") -> list[str]:
    if isinstance(declared, Mapping) and isinstance(actual, Mapping):
        notes: list[str] = []
        for key in sorted(set(declared) | set(actual)):
            child = f"{path}.{key}" if path else str(key)
            if key not in declared:
                notes.append(f"{child} only in class")
            elif key not in actual:
                notes.append(f"{child} only in manifest")
            else:
                notes.extend(_describe_differences(declared[key], actual[key], child))
        return notes
    if declared != actual:
        return [f"{path or 'definition'}: manifest {declared!r} != class {actual!r}"]
    return []


def param_from_payload(payload: Mapping[str, Any]) -> ParamDefinition:
    """Rebuild a declaration from manifest data, for tooling that inspects packages."""
    from lefx.sdk import ParamType

    return ParamDefinition(
        name=payload["name"],
        type=ParamType(payload["type"]),
        default=payload["default"] if "default" in payload else MISSING,
        required=bool(payload.get("required", False)),
        description=payload.get("description", ""),
        minimum=payload.get("minimum"),
        maximum=payload.get("maximum"),
        enum_values=tuple(payload.get("enum_values", ())),
        unit=payload.get("unit"),
        nullable=bool(payload.get("nullable", False)),
        aliases=tuple(payload.get("aliases", ())),
    )


def definition_kind_of(manifest: Mapping[str, Any]) -> DefinitionKind:
    return DefinitionKind(manifest["definition"]["kind"])


__all__ = [
    "HASHES_NAME",
    "MANIFEST_NAME",
    "PACKAGE_FORMAT",
    "PAYLOAD_DIR",
    "PRESETS_NAME",
    "SET_FORMAT",
    "SET_MANIFEST_NAME",
    "build_package_manifest",
    "check_manifest_matches_definition",
    "definition_kind_of",
    "param_from_payload",
    "parse_package_manifest",
    "parse_set_manifest",
    "serialize_definition",
    "serialize_param",
    "serialize_schema",
]
