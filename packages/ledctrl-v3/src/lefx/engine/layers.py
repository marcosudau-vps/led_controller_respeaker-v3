"""The layer stack and the fixed mapping from definition form to placement.

Callers never choose a layer. A definition's form decides it, which is what
prevents an event from becoming permanent or a state from floating above an
overlay. The only choice an author has is which of the two state slots a state
is designed for, and even that is declared rather than passed per activation.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Mapping

from lefx.sdk import DefinitionBase, DefinitionKind, StateSlot

from .errors import CommandError


class LayerId(str, Enum):
    """Composition stages, listed bottom to top."""

    BACKGROUND_STATE = "background_state"
    PRIMARY_STATE = "primary_state"
    TIMED_OVERLAY = "timed_overlay"
    CONTROLLED_OVERLAY = "controlled_overlay"
    EVENT = "event"


LAYER_PRIORITIES: Mapping[LayerId, int] = MappingProxyType(
    {
        LayerId.BACKGROUND_STATE: 100,
        LayerId.PRIMARY_STATE: 200,
        LayerId.TIMED_OVERLAY: 400,
        LayerId.CONTROLLED_OVERLAY: 500,
        LayerId.EVENT: 600,
    }
)

# Controlled overlays sit above timed ones on purpose: a running functional
# readout should stay visible, and anything that genuinely has to cover
# everything for a moment is an event.
COMPOSITION_ORDER: tuple[LayerId, ...] = tuple(
    sorted(LayerId, key=lambda layer: LAYER_PRIORITIES[layer])
)

_SLOT_LAYERS: Mapping[StateSlot, LayerId] = MappingProxyType(
    {
        StateSlot.BACKGROUND: LayerId.BACKGROUND_STATE,
        StateSlot.PRIMARY: LayerId.PRIMARY_STATE,
    }
)

_KIND_LAYERS: Mapping[DefinitionKind, LayerId] = MappingProxyType(
    {
        DefinitionKind.CONTROLLED_OVERLAY: LayerId.CONTROLLED_OVERLAY,
        DefinitionKind.TIMED_OVERLAY: LayerId.TIMED_OVERLAY,
        DefinitionKind.EVENT: LayerId.EVENT,
    }
)


def layer_for(definition: DefinitionBase, *, slot: StateSlot | None = None) -> LayerId:
    """The one layer this definition may occupy.

    ``slot`` applies to states only, defaults to the definition's first declared
    slot, and must be one the definition allows.
    """
    if definition.kind is not DefinitionKind.STATE:
        if slot is not None:
            raise CommandError(
                f"{definition.id!r} is a {definition.definition_type.value}; "
                "only states have a slot"
            )
        return _KIND_LAYERS[definition.kind]

    allowed = definition.slots  # type: ignore[attr-defined]
    chosen = allowed[0] if slot is None else slot
    if chosen not in allowed:
        permitted = ", ".join(item.value for item in allowed)
        raise CommandError(
            f"State {definition.id!r} does not allow the {chosen.value} slot; "
            f"it declares: {permitted}"
        )
    return _SLOT_LAYERS[chosen]


def slot_for(layer: LayerId) -> StateSlot | None:
    """The state slot a layer represents, or ``None`` for non-state layers."""
    for slot, mapped in _SLOT_LAYERS.items():
        if mapped is layer:
            return slot
    return None


def parse_state_slot(value: str | StateSlot) -> StateSlot:
    if isinstance(value, StateSlot):
        return value
    normalized = str(value or "").strip().lower()
    for slot in StateSlot:
        if slot.value == normalized:
            return slot
    permitted = ", ".join(slot.value for slot in StateSlot)
    raise CommandError(f"Unknown state slot {value!r}. Expected one of: {permitted}")


__all__ = [
    "COMPOSITION_ORDER",
    "LAYER_PRIORITIES",
    "LayerId",
    "layer_for",
    "parse_state_slot",
    "slot_for",
]
