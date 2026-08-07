"""Which invocation occupies which layer, and the event queue.

The store holds placement only. It carries no application state: there is no
base state name, no countdown, no direction. Those were application concepts
that had leaked into the engine and made it decide things it had no business
deciding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from .invocation import Invocation
from .layers import COMPOSITION_ORDER, LayerId


@dataclass(slots=True)
class LayerState:
    """One layer: at most one visible invocation, plus a queue on the event layer."""

    layer: LayerId
    active: Invocation | None = None
    queue: list[Invocation] = field(default_factory=list)

    def clear(self) -> list[str]:
        removed = [item.invocation_id for item in self.all_invocations()]
        self.active = None
        self.queue.clear()
        return removed

    def all_invocations(self) -> Iterator[Invocation]:
        if self.active is not None:
            yield self.active
        yield from self.queue


def _queue_order(invocation: Invocation) -> tuple[int, float]:
    """Higher priority first, then first come first served."""
    return (-invocation.effective_priority(), invocation.created_at)


@dataclass(slots=True)
class LayerStore:
    layers: dict[LayerId, LayerState] = field(
        default_factory=lambda: {layer: LayerState(layer=layer) for layer in LayerId}
    )

    def layer(self, layer_id: LayerId) -> LayerState:
        return self.layers[layer_id]

    def active(self, layer_id: LayerId) -> Invocation | None:
        return self.layers[layer_id].active

    def ordered_active(self) -> list[Invocation]:
        """Visible invocations from bottom to top."""
        return [
            self.layers[layer].active
            for layer in COMPOSITION_ORDER
            if self.layers[layer].active is not None
        ]  # type: ignore[misc]

    def find_channel(self, channel: str) -> Invocation | None:
        active = self.layers[LayerId.CONTROLLED_OVERLAY].active
        if active is not None and active.channel == channel:
            return active
        return None

    def set_active(self, invocation: Invocation, now: float) -> list[str]:
        """Place an invocation, replacing whatever held the layer before."""
        state = self.layers[invocation.layer]
        removed = state.clear()
        invocation.activate(now)
        state.active = invocation
        return removed

    def enqueue_event(self, invocation: Invocation, now: float) -> None:
        """Add an event, activating it immediately when the layer is free.

        A running event is never cut short by a newer one. Priority decides the
        order of what is waiting, not whether what is showing gets interrupted.
        """
        state = self.layers[LayerId.EVENT]
        if state.active is None:
            invocation.activate(now)
            state.active = invocation
            return
        key = _queue_order(invocation)
        position = len(state.queue)
        for index, queued in enumerate(state.queue):
            if key < _queue_order(queued):
                position = index
                break
        state.queue.insert(position, invocation)

    def clear_layer(self, layer_id: LayerId) -> list[str]:
        return self.layers[layer_id].clear()

    def clear_all(self) -> list[str]:
        removed: list[str] = []
        for state in self.layers.values():
            removed.extend(state.clear())
        return removed

    def advance(self, now: float) -> list[str]:
        """Retire everything whose time is up; promote the next event.

        Finite forms end because the engine says so. A package sends no
        completion signal and cannot end its own instance.
        """
        expired: list[str] = []
        for layer_id, state in self.layers.items():
            active = state.active
            if active is None or not active.is_expired(now):
                continue
            expired.append(active.invocation_id)
            state.active = None
            if layer_id is LayerId.EVENT and state.queue:
                promoted = state.queue.pop(0)
                promoted.activate(now)
                state.active = promoted
        return expired


__all__ = ["LayerState", "LayerStore"]
