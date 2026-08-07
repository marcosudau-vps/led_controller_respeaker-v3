"""The two ports between the engine and the outside world.

Both live in the SDK rather than in the engine so that a hardware integration
can be written against the contract without installing the runtime, and so that
the engine never has to know which implementation exists. Implementations are
discovered through the entry point groups ``lefx.frame_sinks`` and
``lefx.input_providers``.

That a single device serves both directions over one transport — as the
reSpeaker does with USB — is a detail of that integration. Keeping the ports
separate means a failing DoA read cannot take the LED output down with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from .context import InputContext


@dataclass(slots=True, frozen=True)
class OutputFrame:
    """A fully composed frame ready for output. One opaque colour per LED."""

    leds: tuple[int, ...]
    timestamp: float


@dataclass(slots=True, frozen=True)
class SinkStatus:
    """Whether a sink can currently deliver, and why not if it cannot.

    Every sink answers this, so the service reports connection state uniformly
    instead of type-checking its way to an answer.
    """

    available: bool
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "detail": self.detail}


@runtime_checkable
class FrameSink(Protocol):
    """Receives composed frames. The engine's only way out."""

    def apply_frame(self, frame: OutputFrame) -> None:
        """Deliver one frame. Must not raise on a transient device problem."""
        ...

    def status(self) -> SinkStatus:
        """Report current deliverability without attempting a write."""
        ...

    def close(self) -> None:
        """Release the underlying resource. Called once on shutdown."""
        ...


@runtime_checkable
class InputProvider(Protocol):
    """Supplies runtime input values for pull-sampled controlled overlays."""

    def sample(self, ctx: InputContext) -> Mapping[str, Any] | None:
        """Return current values, or ``None`` when nothing new is available.

        Must not block. A provider that talks to shared hardware caches its own
        snapshot on its own schedule, so the number of active effect instances
        never multiplies the number of device reads.
        """
        ...


__all__ = ["FrameSink", "InputProvider", "OutputFrame", "SinkStatus"]
