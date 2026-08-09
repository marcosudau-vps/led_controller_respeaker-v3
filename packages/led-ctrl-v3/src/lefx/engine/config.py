"""Runtime settings of one engine instance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class EngineConfig:
    """Ring size and render rate.

    ``led_count`` is a setting rather than a constant. Definitions read it from
    the render context and size their frames accordingly, which is why the same
    package runs on a twelve-LED ring and on a five-LED one.
    """

    led_count: int = 12
    fps: float = 30.0

    def __post_init__(self) -> None:
        if self.led_count < 1:
            raise ValueError("led_count must be at least 1")
        if self.fps <= 0:
            raise ValueError("fps must be greater than zero")


__all__ = ["EngineConfig"]
