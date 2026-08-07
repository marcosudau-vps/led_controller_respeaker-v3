"""What a definition receives when it renders or samples.

Both contexts are deliberately narrow. Earlier generations handed the renderer
the whole runtime invocation and the layer it happened to sit on, which invited
effects to branch on placement — the one thing the layer model exists to
prevent. A definition needs the clock, the ring size and its values; that is
what it gets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .definitions import DefinitionBase


@dataclass(slots=True, frozen=True)
class RenderContext:
    """Everything a definition needs to produce one frame.

    ``params`` and ``inputs`` are complete: every key the definition declared is
    present and already canonical. ``inputs`` values may be ``None`` while a
    source has not delivered yet or has gone stale.
    """

    now: float
    """Monotonic engine time. Never wall-clock — animations must survive a clock change."""

    started_at: float
    """Monotonic time at which this instance became active."""

    led_count: int
    """Number of positions the returned frame must have."""

    definition: DefinitionBase

    params: Mapping[str, Any]
    """Stable configuration, canonical and complete."""

    inputs: Mapping[str, Any]
    """Mutable runtime inputs; empty for every form but the controlled overlay."""

    @property
    def elapsed(self) -> float:
        """Seconds since activation — the basis for every time-based animation.

        Using this rather than a frame counter keeps a definition's timing
        independent of the render rate.
        """
        return self.now - self.started_at

    def transparent_frame(self) -> list[int | None]:
        """A frame that changes nothing; the neutral result for a transparent form."""
        return [None] * self.led_count

    def blank_frame(self) -> list[int | None]:
        """A frame of black; opaque and therefore hiding everything below."""
        return [0] * self.led_count


@dataclass(slots=True, frozen=True)
class InputContext:
    """What a pull source receives when the engine asks it for values."""

    now: float
    led_count: int
    config: Mapping[str, Any]
    previous_inputs: Mapping[str, Any]


__all__ = ["InputContext", "RenderContext"]
