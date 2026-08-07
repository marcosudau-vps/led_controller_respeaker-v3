"""One activation of a definition.

The definition is the immutable contract; the invocation is what is actually
running. Keeping them apart is what lets the same definition be activated
several times over without its metadata and its runtime state mixing.

Nothing is smuggled through ``params`` here. Earlier generations hid activation
time, channel and origin in dunder-prefixed keys that then had to be stripped
before every render; those are ordinary fields now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lefx.sdk import DefinitionBase, DefinitionKind, DurationField

from .errors import CommandError
from .layers import LAYER_PRIORITIES, LayerId


@dataclass(slots=True)
class Invocation:
    """A definition, its resolved values, and where it stands in its lifecycle."""

    invocation_id: str
    definition: DefinitionBase
    layer: LayerId
    params: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)

    created_at: float = 0.0
    """When the invocation was accepted — for an event, when it entered the queue."""

    activated_at: float | None = None
    """When it became visible. A queued event has not been activated yet."""

    duration_ms: int | None = None
    """Length for finite forms; ``None`` for states and controlled overlays."""

    priority: int | None = None
    channel: str | None = None
    preset_id: str | None = None
    source: str | None = None

    input_last_attempt_at: float | None = None
    input_last_success_at: float | None = None
    input_error: str | None = None

    @property
    def effect_id(self) -> str:
        return self.definition.id

    @property
    def is_active(self) -> bool:
        return self.activated_at is not None

    def effective_priority(self) -> int:
        """Queue order for events; falls back to the definition, then the layer."""
        if self.priority is not None:
            return int(self.priority)
        declared = getattr(self.definition, "default_priority", None)
        if declared is not None:
            return int(declared)
        return LAYER_PRIORITIES[self.layer]

    def activate(self, now: float) -> None:
        """Start the clock.

        A queued event only begins to age once it is on screen, so its declared
        duration is the time it is actually visible rather than the time since
        it was requested.
        """
        self.activated_at = now
        if self.input_last_success_at is None and self.inputs_seeded:
            self.input_last_success_at = now

    @property
    def inputs_seeded(self) -> bool:
        """Whether activation already carried a usable runtime value.

        A non-empty initial input counts as a successful reception, so an
        instance that was handed data up front does not start out ``waiting``.
        """
        return any(value is not None for value in self.inputs.values())

    def expires_at(self) -> float | None:
        if self.duration_ms is None or self.activated_at is None:
            return None
        return self.activated_at + (self.duration_ms / 1000.0)

    def is_expired(self, now: float) -> bool:
        deadline = self.expires_at()
        return deadline is not None and now >= deadline

    def remaining_ms(self, now: float) -> int | None:
        deadline = self.expires_at()
        if deadline is None:
            return None
        return max(0, int(round((deadline - now) * 1000.0)))


def duration_from_config(
    definition: DefinitionBase,
    params: dict[str, Any],
    *,
    override_ms: int | None = None,
) -> int | None:
    """The length a finite form will run for.

    States and controlled overlays are indefinite and return ``None``. An
    override is only honoured when the definition allows one, so a caller cannot
    stretch a signal that was designed to be brief.
    """
    if definition.kind in {DefinitionKind.STATE, DefinitionKind.CONTROLLED_OVERLAY}:
        return None
    field_name: DurationField = definition.duration_field  # type: ignore[attr-defined]
    configured = params[field_name.value]
    if override_ms is None:
        return int(configured)
    if not definition.supports_duration_override:  # type: ignore[attr-defined]
        raise CommandError(
            f"{definition.id!r} does not support a duration override; "
            f"set config.{field_name.value} instead"
        )
    return int(override_ms)


__all__ = ["Invocation", "duration_from_config"]
