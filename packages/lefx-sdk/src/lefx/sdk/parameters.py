"""Parameter declarations and the rules for which options are allowed when.

Two things happen here that did not happen in earlier generations:

1. ``type`` is an enum, not a free string. A typo is a construction error, not a
   value that silently never matches.
2. Every declaration is checked in ``__post_init__``. An invalid parameter is
   not constructible, so no code path can hold one.

The matrix below is the single source of truth for which companion fields a type
accepts. ``minimum``/``maximum`` on a colour is not "ignored" — it is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, Mapping

from .errors import SchemaError, ValueNormalizationError
from .values import (
    format_color,
    parse_angle_degrees,
    parse_bool,
    parse_duration_ms,
    parse_ratio,
)


class _Missing:
    """Sentinel for "no default declared".

    ``None`` cannot serve this role: a nullable runtime input may legitimately
    default to ``None``, and the two cases must stay distinguishable.
    """

    _instance: "_Missing | None" = None

    def __new__(cls) -> "_Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Final = _Missing()


class ParamType(str, Enum):
    """The complete set of value types a declaration may use."""

    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    DURATION_MS = "duration_ms"
    ANGLE_DEG = "angle_deg"
    ENUM = "enum"
    COLOR = "color"
    COLOR_LIST = "color_list"
    GRADIENT = "gradient"
    COLOR_RANGE = "color_range"


@dataclass(slots=True, frozen=True)
class _TypeRules:
    """Which companion fields a parameter type accepts."""

    bounds: bool = False
    bounds_are_integers: bool = False
    enum_values: bool = False
    units: frozenset[str] | None = None  # ``None`` means "no unit allowed"


# The zulässigkeit matrix. Anything not listed as allowed is rejected.
_TYPE_RULES: Final[Mapping[ParamType, _TypeRules]] = {
    ParamType.BOOL: _TypeRules(),
    ParamType.INT: _TypeRules(bounds=True, bounds_are_integers=True, units=frozenset({"ms", "deg", "px", "count", "index", "ratio", "multiplier", "percent"})),
    ParamType.FLOAT: _TypeRules(bounds=True, units=frozenset({"ms", "deg", "px", "count", "ratio", "multiplier", "percent", "hz"})),
    ParamType.DURATION_MS: _TypeRules(bounds=True, bounds_are_integers=True, units=frozenset({"ms"})),
    ParamType.ANGLE_DEG: _TypeRules(units=frozenset({"deg"})),
    ParamType.ENUM: _TypeRules(enum_values=True),
    ParamType.COLOR: _TypeRules(),
    ParamType.COLOR_LIST: _TypeRules(bounds=True, bounds_are_integers=True, units=frozenset({"count"})),
    ParamType.GRADIENT: _TypeRules(),
    ParamType.COLOR_RANGE: _TypeRules(),
}


@dataclass(slots=True, frozen=True)
class _ReservedParam:
    """A parameter name whose meaning is fixed system-wide."""

    type: ParamType
    exact_minimum: float | None = None
    exact_maximum: float | None = None
    minimum_at_least: float | None = None
    minimum_above_zero: bool = False


# Reserved names carry the same meaning in every definition, so their type and
# range are not left to each author. This is what lets the CLI, the API and the
# documentation talk about "brightness" without qualification.
RESERVED_PARAMETERS: Final[Mapping[str, _ReservedParam]] = {
    "brightness": _ReservedParam(ParamType.FLOAT, exact_minimum=0.0, exact_maximum=1.0),
    "min_brightness": _ReservedParam(ParamType.FLOAT, exact_minimum=0.0, exact_maximum=1.0),
    "speed": _ReservedParam(ParamType.FLOAT, minimum_above_zero=True),
    "reverse": _ReservedParam(ParamType.BOOL),
    "progress": _ReservedParam(ParamType.FLOAT, exact_minimum=0.0, exact_maximum=100.0),
    "direction_deg": _ReservedParam(ParamType.ANGLE_DEG),
    "duration_ms": _ReservedParam(ParamType.DURATION_MS, minimum_at_least=1),
    "total_ms": _ReservedParam(ParamType.DURATION_MS, minimum_at_least=1),
    "remaining_ms": _ReservedParam(ParamType.DURATION_MS, minimum_at_least=0),
    "color": _ReservedParam(ParamType.COLOR),
    "secondary_color": _ReservedParam(ParamType.COLOR),
    "background_color": _ReservedParam(ParamType.COLOR),
    "colors": _ReservedParam(ParamType.COLOR_LIST),
    "gradient": _ReservedParam(ParamType.GRADIENT),
    "color_range": _ReservedParam(ParamType.COLOR_RANGE),
    "random_seed": _ReservedParam(ParamType.INT),
}


def _is_valid_name(value: str) -> bool:
    return (
        bool(value)
        and value.isidentifier()
        and not value.startswith("_")
        and value == value.lower()
    )


@dataclass(slots=True, frozen=True)
class ParamDefinition:
    """One declared field of a configuration or runtime input schema.

    ``required`` and ``default`` are mutually exclusive: a field that always
    falls back to a value is not required, and a field the caller must supply
    cannot have a fallback. Declaring both is a contradiction, not a preference.
    """

    name: str
    type: ParamType
    default: Any = MISSING
    required: bool = False
    description: str = ""
    minimum: float | int | None = None
    maximum: float | int | None = None
    enum_values: tuple[Any, ...] = ()
    unit: str | None = None
    nullable: bool = False
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self._check_name()
        self._check_type()
        rules = _TYPE_RULES[self.type]
        self._check_bounds(rules)
        self._check_enum_values(rules)
        self._check_unit(rules)
        self._check_aliases()
        self._check_reserved()
        self._check_required_and_default()
        self._canonicalize_default()

    @property
    def has_default(self) -> bool:
        return self.default is not MISSING

    # -- construction checks ------------------------------------------------

    def _check_name(self) -> None:
        if not _is_valid_name(self.name):
            raise SchemaError(
                f"Parameter name {self.name!r} must be lowercase snake_case "
                "and must not start with an underscore"
            )

    def _check_type(self) -> None:
        if not isinstance(self.type, ParamType):
            raise SchemaError(
                f"Parameter {self.name!r} declares type {self.type!r}; "
                f"expected one of: {', '.join(item.value for item in ParamType)}"
            )

    def _check_bounds(self, rules: _TypeRules) -> None:
        has_bounds = self.minimum is not None or self.maximum is not None
        if has_bounds and not rules.bounds:
            raise SchemaError(
                f"Parameter {self.name!r} of type {self.type.value!r} "
                "does not accept minimum or maximum"
            )
        if not has_bounds:
            return
        for label, bound in (("minimum", self.minimum), ("maximum", self.maximum)):
            if bound is None:
                continue
            if isinstance(bound, bool) or not isinstance(bound, (int, float)):
                raise SchemaError(f"Parameter {self.name!r} {label} must be numeric")
            if rules.bounds_are_integers and float(bound) != int(bound):
                raise SchemaError(
                    f"Parameter {self.name!r} of type {self.type.value!r} "
                    f"requires an integral {label}"
                )
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise SchemaError(
                f"Parameter {self.name!r} minimum {self.minimum} exceeds maximum {self.maximum}"
            )
        if self.type is ParamType.COLOR_LIST and self.minimum is not None and self.minimum < 0:
            raise SchemaError(f"Parameter {self.name!r} list length minimum must be >= 0")

    def _check_enum_values(self, rules: _TypeRules) -> None:
        if not rules.enum_values:
            if self.enum_values:
                raise SchemaError(
                    f"Parameter {self.name!r} of type {self.type.value!r} "
                    "does not accept enum_values"
                )
            return
        if not self.enum_values:
            raise SchemaError(f"Enum parameter {self.name!r} must declare enum_values")
        if len(set(self.enum_values)) != len(self.enum_values):
            raise SchemaError(f"Enum parameter {self.name!r} has duplicate enum_values")

    def _check_unit(self, rules: _TypeRules) -> None:
        if self.unit is None:
            return
        if rules.units is None:
            raise SchemaError(
                f"Parameter {self.name!r} of type {self.type.value!r} does not accept a unit"
            )
        if self.unit not in rules.units:
            allowed = ", ".join(sorted(rules.units))
            raise SchemaError(
                f"Parameter {self.name!r} declares unit {self.unit!r}; "
                f"type {self.type.value!r} allows: {allowed}"
            )

    def _check_aliases(self) -> None:
        seen: set[str] = set()
        for alias in self.aliases:
            if not isinstance(alias, str) or not _is_valid_name(alias):
                raise SchemaError(
                    f"Parameter {self.name!r} declares invalid alias {alias!r}"
                )
            if alias == self.name:
                raise SchemaError(
                    f"Parameter {self.name!r} declares an alias equal to its own name"
                )
            if alias in seen:
                raise SchemaError(f"Parameter {self.name!r} declares alias {alias!r} twice")
            seen.add(alias)

    def _check_reserved(self) -> None:
        reserved = RESERVED_PARAMETERS.get(self.name)
        if reserved is None:
            return
        if self.type is not reserved.type:
            raise SchemaError(
                f"Reserved parameter {self.name!r} must use type "
                f"{reserved.type.value!r}, not {self.type.value!r}"
            )
        if reserved.exact_minimum is not None and self.minimum != reserved.exact_minimum:
            raise SchemaError(
                f"Reserved parameter {self.name!r} must declare minimum "
                f"{reserved.exact_minimum}"
            )
        if reserved.exact_maximum is not None and self.maximum != reserved.exact_maximum:
            raise SchemaError(
                f"Reserved parameter {self.name!r} must declare maximum "
                f"{reserved.exact_maximum}"
            )
        if reserved.minimum_at_least is not None and (
            self.minimum is None or self.minimum < reserved.minimum_at_least
        ):
            raise SchemaError(
                f"Reserved parameter {self.name!r} must declare minimum "
                f">= {reserved.minimum_at_least}"
            )
        if reserved.minimum_above_zero and (self.minimum is None or self.minimum <= 0):
            raise SchemaError(
                f"Reserved parameter {self.name!r} must declare a minimum greater than zero"
            )

    def _check_required_and_default(self) -> None:
        if self.required and self.has_default:
            raise SchemaError(
                f"Parameter {self.name!r} is required and declares a default; "
                "a required field has no fallback"
            )

    def _canonicalize_default(self) -> None:
        """Store the default in the same canonical form a caller's value gets.

        Validating here means a broken default surfaces when the definition is
        written, not on the first activation that happens to omit the field.
        """
        if not self.has_default:
            return
        try:
            canonical = normalize_parameter_value(self, self.default)
        except (ValueError, TypeError) as exc:
            raise SchemaError(
                f"Parameter {self.name!r} has an invalid default {self.default!r}: {exc}"
            ) from exc
        object.__setattr__(self, "default", canonical)


def normalize_parameter_value(definition: ParamDefinition, value: Any) -> Any:
    """Bring one incoming value into the canonical form of its declared type."""
    if value is None:
        if definition.nullable:
            return None
        raise ValueError(f"{definition.name} must not be null")

    kind = definition.type
    if kind is ParamType.BOOL:
        normalized: Any = parse_bool(value)
    elif kind is ParamType.INT:
        normalized = _normalize_int(definition, value)
    elif kind is ParamType.FLOAT:
        normalized = _normalize_float(definition, value)
    elif kind is ParamType.DURATION_MS:
        normalized = parse_duration_ms(value, minimum=max(0, int(definition.minimum or 0)))
    elif kind is ParamType.ANGLE_DEG:
        normalized = parse_angle_degrees(value)
    elif kind is ParamType.ENUM:
        normalized = _normalize_enum(definition, value)
    elif kind is ParamType.COLOR:
        normalized = format_color(value)
    elif kind is ParamType.COLOR_LIST:
        normalized = _normalize_color_list(definition, value)
    elif kind is ParamType.GRADIENT:
        normalized = _normalize_gradient(definition, value)
    elif kind is ParamType.COLOR_RANGE:
        normalized = _normalize_color_range(definition, value)
    else:  # pragma: no cover - ParamType is exhaustive
        raise ValueError(f"Unsupported parameter type {kind!r} for {definition.name!r}")

    if isinstance(normalized, (int, float)) and not isinstance(normalized, bool):
        if definition.minimum is not None and normalized < definition.minimum:
            raise ValueError(f"{definition.name} must be >= {definition.minimum}")
        if definition.maximum is not None and normalized > definition.maximum:
            raise ValueError(f"{definition.name} must be <= {definition.maximum}")
    return normalized


def _normalize_int(definition: ParamDefinition, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{definition.name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{definition.name} must be an integer") from exc


def _normalize_float(definition: ParamDefinition, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{definition.name} must be numeric")
    if isinstance(value, str) and value.strip().endswith("%"):
        # A percentage is only unambiguous when the declared range says what it
        # is a percentage of: 0..1 means a ratio, 0..100 means percent points.
        if definition.minimum == 0.0 and definition.maximum == 1.0:
            return parse_ratio(value)
        if definition.minimum == 0.0 and definition.maximum == 100.0:
            try:
                return float(value.strip()[:-1])
            except ValueError as exc:
                raise ValueError(f"{definition.name} must be numeric or a percentage") from exc
        raise ValueError(
            f"{definition.name} does not accept a percentage; its range is not 0..1 or 0..100"
        )
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{definition.name} must be numeric") from exc


def _normalize_enum(definition: ParamDefinition, value: Any) -> Any:
    if value in definition.enum_values:
        return value
    if isinstance(value, str):
        matches = [
            candidate
            for candidate in definition.enum_values
            if isinstance(candidate, str) and candidate.casefold() == value.strip().casefold()
        ]
        if len(matches) == 1:
            return matches[0]
    expected = ", ".join(repr(item) for item in definition.enum_values)
    raise ValueError(f"{definition.name} must be one of: {expected}")


def _normalize_color_list(definition: ParamDefinition, value: Any) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{definition.name} must be a list of colors")
    normalized = [format_color(item) for item in value]
    if definition.minimum is not None and len(normalized) < definition.minimum:
        raise ValueError(
            f"{definition.name} must contain at least {int(definition.minimum)} colors"
        )
    if definition.maximum is not None and len(normalized) > definition.maximum:
        raise ValueError(
            f"{definition.name} must contain at most {int(definition.maximum)} colors"
        )
    return normalized


def _normalize_gradient(definition: ParamDefinition, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or not 2 <= len(value) <= 16:
        raise ValueError(f"{definition.name} must contain between 2 and 16 color stops")
    stops: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {"at", "color"}:
            raise ValueError(f"{definition.name}[{index}] must contain exactly 'at' and 'color'")
        try:
            at = float(item["at"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{definition.name}[{index}].at must be numeric") from exc
        if not 0.0 <= at <= 1.0:
            raise ValueError(f"{definition.name}[{index}].at must be between 0 and 1")
        stops.append({"at": at, "color": format_color(item["color"])})
    positions = [item["at"] for item in stops]
    if positions != sorted(positions) or positions[0] != 0.0 or positions[-1] != 1.0:
        raise ValueError(f"{definition.name} stops must be sorted and include positions 0 and 1")
    return stops


def _normalize_color_range(definition: ParamDefinition, value: Any) -> dict[str, list[float]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{definition.name} must be an HSV range object")
    if set(value) != {"hue", "saturation", "brightness"}:
        raise ValueError(f"{definition.name} must contain exactly hue, saturation and brightness")
    limits = {
        "hue": (0.0, 360.0),
        "saturation": (0.0, 1.0),
        "brightness": (0.0, 1.0),
    }
    normalized: dict[str, list[float]] = {}
    for name, (minimum, maximum) in limits.items():
        raw = value[name]
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ValueError(f"{definition.name}.{name} must be a [minimum, maximum] pair")
        try:
            low, high = float(raw[0]), float(raw[1])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{definition.name}.{name} bounds must be numeric") from exc
        if low > high or low < minimum or high > maximum:
            raise ValueError(
                f"{definition.name}.{name} must satisfy "
                f"{minimum} <= minimum <= maximum <= {maximum}"
            )
        normalized[name] = [low, high]
    return normalized


__all__ = [
    "MISSING",
    "RESERVED_PARAMETERS",
    "ParamDefinition",
    "ParamType",
    "SchemaError",
    "ValueNormalizationError",
    "normalize_parameter_value",
]
