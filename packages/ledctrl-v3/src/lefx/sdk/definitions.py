"""Type-specific effect definitions.

Earlier generations used one flat definition class with optional fields and a
separate validation function. That made contradictory contracts constructible —
a state with runtime inputs, an event without a duration — and left "which
option is allowed when" as a chain of conditionals nobody could read as a whole.

V3 answers the question structurally instead. There are four definition classes,
one per lifecycle form, and a field that does not apply to a form simply does
not exist on it. A state **cannot** declare runtime inputs; there is no
attribute to declare them on.

What used to live in ``layer_rules`` and ``capabilities`` is gone, because all
of it followed from the type: only events queue, only finite forms have a
duration, transparency is already stated by ``composition``. The two genuine
choices that remain are the state's slots and whether a finite form lets a
caller override its duration.

Two invariants make effect code straightforward:

* every configuration parameter declares a default, so resolved configuration
  always contains every declared key;
* every runtime input is either required-and-nullable or has a default, so the
  engine can always present every declared key.

Together they mean a renderer reads ``ctx.params["color"]`` rather than
``params.get("color", 0x00C066)`` — which is how re-implemented parsing crept
into packages before.

``None`` carries one meaning throughout: nothing here, leave what is below
untouched. It means that in a frame and it means that in a nullable colour
parameter. Black is a colour and hides what is below it; the two are not
interchangeable, and no code path may substitute one for the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Mapping

from .errors import SchemaError
from .parameters import ParamDefinition, ParamType


class DefinitionKind(str, Enum):
    """The single discriminator for a definition's lifecycle form."""

    STATE = "state"
    CONTROLLED_OVERLAY = "controlled_overlay"
    TIMED_OVERLAY = "timed_overlay"
    EVENT = "event"


class DefinitionType(str, Enum):
    """The user-facing grouping used by listings and the control surface."""

    STATE = "state"
    OVERLAY = "overlay"
    EVENT = "event"


class OverlayMode(str, Enum):
    CONTROLLED = "controlled"
    TIMED = "timed"


class StateSlot(str, Enum):
    """The two places a state may occupy."""

    BACKGROUND = "background"
    PRIMARY = "primary"


class DurationField(str, Enum):
    """Which parameter a finite form uses to express its length."""

    DURATION_MS = "duration_ms"
    TOTAL_MS = "total_ms"


class ColorModel(str, Enum):
    NONE = "none"
    MONO = "mono"
    DUAL = "dual"
    PALETTE = "palette"
    GRADIENT = "gradient"
    RANDOM_RANGE = "random_range"


class CompositionMode(str, Enum):
    OPAQUE = "opaque"
    TRANSPARENT = "transparent"


class InputMode(str, Enum):
    PUSH = "push"
    PULL = "pull"


_COLOR_MODEL_FIELDS: Mapping[ColorModel, frozenset[str]] = {
    ColorModel.NONE: frozenset(),
    ColorModel.MONO: frozenset({"color"}),
    ColorModel.DUAL: frozenset({"color", "secondary_color"}),
    ColorModel.PALETTE: frozenset({"colors"}),
    ColorModel.GRADIENT: frozenset({"gradient"}),
    ColorModel.RANDOM_RANGE: frozenset({"color_range", "random_seed"}),
}

_ALL_COLOR_FIELDS: frozenset[str] = frozenset(
    name for names in _COLOR_MODEL_FIELDS.values() for name in names
)


@dataclass(slots=True, frozen=True)
class InputSamplingPolicy:
    """How a controlled overlay obtains its runtime inputs, and when it is stale.

    ``failure_after_ms`` is derived rather than configured so that the grace
    period can never contradict the heartbeat settings it is built from.
    """

    mode: InputMode = InputMode.PUSH
    provider_id: str | None = None
    interval_ms: int = 0
    heartbeat_interval_ms: int = 1000
    max_missed_heartbeats: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.mode, InputMode):
            raise SchemaError(f"Input sampling mode {self.mode!r} is not a valid InputMode")
        if self.provider_id is not None:
            if self.mode is not InputMode.PULL:
                raise SchemaError("provider_id is only allowed with pull sampling")
            if not self.provider_id.strip():
                raise SchemaError("provider_id must not be empty")
        if self.interval_ms < 0:
            raise SchemaError("interval_ms must be >= 0")
        if self.heartbeat_interval_ms < 100:
            raise SchemaError("heartbeat_interval_ms must be >= 100")
        if self.max_missed_heartbeats < 1:
            raise SchemaError("max_missed_heartbeats must be >= 1")

    @property
    def failure_after_ms(self) -> int:
        return self.heartbeat_interval_ms * self.max_missed_heartbeats


def _is_valid_id(value: str) -> bool:
    return (
        bool(value)
        and value.isidentifier()
        and not value.startswith("_")
        and value == value.lower()
    )


@dataclass(slots=True, frozen=True, kw_only=True)
class DefinitionBase:
    """Fields every definition has, regardless of lifecycle form."""

    kind: ClassVar[DefinitionKind]

    id: str
    title: str
    description: str
    parameter_schema: Mapping[str, ParamDefinition] = field(default_factory=dict)
    color_model: ColorModel = ColorModel.NONE
    composition: CompositionMode = CompositionMode.OPAQUE
    animated: bool = False
    directional: bool = False
    tags: tuple[str, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        self._check_identity()
        self._freeze_schemas()
        self._check_schema(self.parameter_schema, label="config")
        self._check_configuration_is_total()
        self._check_color_model()
        self._check_visual_flags()
        self._check_alias_collisions()
        self._check_form()

    # -- vocabulary ---------------------------------------------------------

    @property
    def definition_type(self) -> DefinitionType:
        if self.kind is DefinitionKind.STATE:
            return DefinitionType.STATE
        if self.kind is DefinitionKind.EVENT:
            return DefinitionType.EVENT
        return DefinitionType.OVERLAY

    @property
    def overlay_mode(self) -> OverlayMode | None:
        if self.kind is DefinitionKind.CONTROLLED_OVERLAY:
            return OverlayMode.CONTROLLED
        if self.kind is DefinitionKind.TIMED_OVERLAY:
            return OverlayMode.TIMED
        return None

    @property
    def runtime_input_schema(self) -> Mapping[str, ParamDefinition]:
        """Empty for every form except the controlled overlay, which overrides it."""
        return MappingProxyType({})

    @property
    def input_sampling(self) -> InputSamplingPolicy | None:
        return None

    # -- construction checks ------------------------------------------------

    def _check_identity(self) -> None:
        if not _is_valid_id(self.id):
            raise SchemaError(
                f"Definition id {self.id!r} must be lowercase snake_case "
                "and must not start with an underscore"
            )
        if not self.title.strip():
            raise SchemaError(f"Definition {self.id!r} must declare a title")
        if not self.description.strip():
            raise SchemaError(f"Definition {self.id!r} must declare a description")
        if self.version < 1:
            raise SchemaError(f"Definition {self.id!r} version must be >= 1")
        for tag in self.tags:
            if not isinstance(tag, str) or not tag.strip():
                raise SchemaError(f"Definition {self.id!r} declares an empty tag")
        if not isinstance(self.color_model, ColorModel):
            raise SchemaError(f"Definition {self.id!r} declares an invalid color_model")
        if not isinstance(self.composition, CompositionMode):
            raise SchemaError(f"Definition {self.id!r} declares an invalid composition")

    def _freeze_schemas(self) -> None:
        object.__setattr__(self, "parameter_schema", MappingProxyType(dict(self.parameter_schema)))

    def _check_schema(self, schema: Mapping[str, ParamDefinition], *, label: str) -> None:
        for key, param in schema.items():
            if not isinstance(param, ParamDefinition):
                raise SchemaError(f"Definition {self.id!r} {label} {key!r} is not a ParamDefinition")
            if key != param.name:
                raise SchemaError(
                    f"Definition {self.id!r} {label} schema key/name mismatch: "
                    f"{key!r} != {param.name!r}"
                )

    def _check_configuration_is_total(self) -> None:
        """Configuration must always resolve completely.

        A configuration field that is neither required nor defaulted would be
        absent from resolved configuration, forcing every renderer to invent a
        fallback — which is exactly how packages ended up re-implementing value
        parsing. Requiring a default keeps that decision in the schema.

        A nullable configuration field is explicitly allowed, and ``None`` there
        carries the same meaning it has in a frame: leave the position alone.
        That is how a definition offers "paint the background black" and "let
        the layer below show through" as one parameter rather than two.
        """
        for name, param in self.parameter_schema.items():
            if param.required:
                raise SchemaError(
                    f"Definition {self.id!r} config {name!r} is required; configuration "
                    "fields must declare a default instead so they always resolve"
                )
            if not param.has_default:
                raise SchemaError(
                    f"Definition {self.id!r} config {name!r} must declare a default"
                )

    def _check_color_model(self) -> None:
        names = set(self.parameter_schema)
        required = _COLOR_MODEL_FIELDS[self.color_model]
        missing = required - names
        if missing:
            raise SchemaError(
                f"Definition {self.id!r} color model {self.color_model.value!r} "
                f"requires config fields: {', '.join(sorted(missing))}"
            )
        if self.color_model is ColorModel.NONE:
            present = names & _ALL_COLOR_FIELDS
            if present:
                raise SchemaError(
                    f"Definition {self.id!r} uses color model 'none' but declares "
                    f"color configuration: {', '.join(sorted(present))}"
                )
            if "brightness" in names:
                raise SchemaError(
                    f"Definition {self.id!r} uses color model 'none' and must not "
                    "declare brightness"
                )
            return
        if "brightness" not in names:
            raise SchemaError(
                f"Definition {self.id!r} is colored and must declare config.brightness"
            )
        # Reserved-name rules already pin each colour field to its type, so the
        # model only has to check presence.

    def _check_visual_flags(self) -> None:
        names = self.parameter_schema
        if self.animated and "speed" not in names:
            raise SchemaError(f"Animated definition {self.id!r} must declare config.speed")
        if not self.animated and "speed" in names:
            raise SchemaError(
                f"Definition {self.id!r} declares config.speed but is not marked animated"
            )
        if self.directional and "reverse" not in names:
            raise SchemaError(f"Directional definition {self.id!r} must declare config.reverse")
        if not self.directional and "reverse" in names:
            raise SchemaError(
                f"Definition {self.id!r} declares config.reverse but is not marked directional"
            )

    def _check_alias_collisions(self) -> None:
        """Aliases live in one namespace across config and runtime inputs.

        A config alias that shadows a runtime input name would make the same
        word mean two different things depending on which payload it arrived in.
        """
        canonical = set(self.parameter_schema) | set(self.runtime_input_schema)
        owners: dict[str, str] = {}
        for schema in (self.parameter_schema, self.runtime_input_schema):
            for name, param in schema.items():
                for alias in param.aliases:
                    if alias in canonical:
                        raise SchemaError(
                            f"Definition {self.id!r} alias {alias!r} on {name!r} "
                            "collides with a canonical field name"
                        )
                    owner = owners.get(alias)
                    if owner is not None:
                        raise SchemaError(
                            f"Definition {self.id!r} alias {alias!r} is shared by "
                            f"{owner!r} and {name!r}"
                        )
                    owners[alias] = name

    def _check_form(self) -> None:
        """Hook for form-specific rules; the base form has none."""


@dataclass(slots=True, frozen=True, kw_only=True)
class StateDefinition(DefinitionBase):
    """A persistent visual ground state.

    Runs until replaced or cleared, has no duration and no runtime inputs.
    ``slots`` declares which of the two state places the definition is designed
    for; only a background state can be restored on service start.
    """

    kind: ClassVar[DefinitionKind] = DefinitionKind.STATE

    slots: tuple[StateSlot, ...] = (StateSlot.PRIMARY,)
    restorable: bool = False

    def _check_form(self) -> None:
        if not self.slots:
            raise SchemaError(f"State {self.id!r} must declare at least one slot")
        for slot in self.slots:
            if not isinstance(slot, StateSlot):
                raise SchemaError(f"State {self.id!r} declares an invalid slot {slot!r}")
        if len(set(self.slots)) != len(self.slots):
            raise SchemaError(f"State {self.id!r} declares a slot twice")
        if self.restorable and StateSlot.BACKGROUND not in self.slots:
            raise SchemaError(
                f"State {self.id!r} is marked restorable but does not allow the "
                "background slot; only the background state is persisted"
            )
        for finite in ("duration_ms", "total_ms"):
            if finite in self.parameter_schema:
                raise SchemaError(
                    f"State {self.id!r} declares config.{finite}; states are indefinite"
                )


@dataclass(slots=True, frozen=True, kw_only=True)
class ControlledOverlayDefinition(DefinitionBase):
    """An indefinite overlay addressed by channel and fed with mutable inputs.

    This is the only form that may declare runtime inputs, and therefore the
    only one with an input sampling policy.
    """

    kind: ClassVar[DefinitionKind] = DefinitionKind.CONTROLLED_OVERLAY

    runtime_inputs: Mapping[str, ParamDefinition] = field(default_factory=dict)
    sampling: InputSamplingPolicy = field(default_factory=InputSamplingPolicy)

    @property
    def runtime_input_schema(self) -> Mapping[str, ParamDefinition]:
        return self.runtime_inputs

    @property
    def input_sampling(self) -> InputSamplingPolicy:
        return self.sampling

    def _check_form(self) -> None:
        object.__setattr__(self, "runtime_inputs", MappingProxyType(dict(self.runtime_inputs)))
        self._check_schema(self.runtime_inputs, label="runtime input")

        overlap = set(self.runtime_inputs) & set(self.parameter_schema)
        if overlap:
            raise SchemaError(
                f"Controlled overlay {self.id!r} declares {', '.join(sorted(overlap))} "
                "as both configuration and runtime input; a runtime value must not "
                "be able to shadow stable configuration"
            )

        for name, param in self.runtime_inputs.items():
            if param.required and not param.nullable:
                raise SchemaError(
                    f"Controlled overlay {self.id!r} runtime input {name!r} is required "
                    "and must be nullable: no value has arrived yet when the instance "
                    "starts, and the value becomes null again when the source fails"
                )
            if not param.required and not param.has_default:
                raise SchemaError(
                    f"Controlled overlay {self.id!r} runtime input {name!r} must be "
                    "required or declare a default so every declared key is always present"
                )

        if not isinstance(self.sampling, InputSamplingPolicy):
            raise SchemaError(f"Controlled overlay {self.id!r} declares an invalid sampling policy")
        if self.sampling.mode is InputMode.PULL and not self.runtime_inputs:
            raise SchemaError(
                f"Controlled overlay {self.id!r} uses pull sampling but declares no runtime inputs"
            )


@dataclass(slots=True, frozen=True, kw_only=True)
class _FiniteDefinition(DefinitionBase):
    """Shared rules for the two forms the engine ends automatically."""

    duration_field: DurationField = DurationField.DURATION_MS
    supports_duration_override: bool = False

    def _check_finite_duration(self) -> None:
        if not isinstance(self.duration_field, DurationField):
            raise SchemaError(f"Definition {self.id!r} declares an invalid duration_field")
        name = self.duration_field.value
        param = self.parameter_schema.get(name)
        if param is None:
            raise SchemaError(
                f"Definition {self.id!r} declares duration_field {name!r} "
                f"but has no config.{name}"
            )
        if param.type is not ParamType.DURATION_MS:
            raise SchemaError(
                f"Definition {self.id!r} config.{name} must use type 'duration_ms'"
            )
        other = "total_ms" if name == "duration_ms" else "duration_ms"
        if other in self.parameter_schema:
            raise SchemaError(
                f"Definition {self.id!r} declares both duration_ms and total_ms; "
                "a finite form has exactly one length"
            )


@dataclass(slots=True, frozen=True, kw_only=True)
class TimedOverlayDefinition(_FiniteDefinition):
    """A finite overlay above a state, activated once and removed on expiry.

    Has no channel and no runtime inputs: start and end are fixed at activation.
    """

    kind: ClassVar[DefinitionKind] = DefinitionKind.TIMED_OVERLAY

    def _check_form(self) -> None:
        self._check_finite_duration()


@dataclass(slots=True, frozen=True, kw_only=True)
class EventDefinition(_FiniteDefinition):
    """A one-shot prioritized signal that passes through the event queue."""

    kind: ClassVar[DefinitionKind] = DefinitionKind.EVENT

    default_priority: int | None = None

    def _check_form(self) -> None:
        self._check_finite_duration()
        if self.default_priority is not None and isinstance(self.default_priority, bool):
            raise SchemaError(f"Event {self.id!r} default_priority must be an integer")


AnyDefinition = (
    StateDefinition | ControlledOverlayDefinition | TimedOverlayDefinition | EventDefinition
)


DEFINITION_CLASSES: Mapping[DefinitionKind, type[DefinitionBase]] = MappingProxyType(
    {
        DefinitionKind.STATE: StateDefinition,
        DefinitionKind.CONTROLLED_OVERLAY: ControlledOverlayDefinition,
        DefinitionKind.TIMED_OVERLAY: TimedOverlayDefinition,
        DefinitionKind.EVENT: EventDefinition,
    }
)


def resolved_default_configuration(definition: DefinitionBase) -> dict[str, Any]:
    """Every configuration key with its declared default, already canonical."""
    return {name: param.default for name, param in definition.parameter_schema.items()}


__all__ = [
    "AnyDefinition",
    "ColorModel",
    "CompositionMode",
    "ControlledOverlayDefinition",
    "DEFINITION_CLASSES",
    "DefinitionBase",
    "DefinitionKind",
    "DefinitionType",
    "DurationField",
    "EventDefinition",
    "InputMode",
    "InputSamplingPolicy",
    "OverlayMode",
    "StateDefinition",
    "StateSlot",
    "TimedOverlayDefinition",
    "resolved_default_configuration",
]
