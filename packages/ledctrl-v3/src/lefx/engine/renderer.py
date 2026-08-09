"""Composes layer frames into the single frame that reaches the hardware.

One rule governs the whole stack: a position holding ``None`` contributes
nothing and whatever was composed below stays; any colour, black included,
overwrites. That is the entire mechanism behind a direction marker sitting on
top of a state without erasing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from lefx.sdk import OutputFrame, scale_color

from .composer import LayerFrame


@dataclass(slots=True)
class OutputSettings:
    """Global output controls, applied after composition.

    These belong to the installation, not to any definition: dimming the ring
    must not change what an effect renders.
    """

    brightness: float = 1.0
    enabled: bool = True

    def with_brightness(self, level: float) -> None:
        self.brightness = max(0.0, min(1.0, float(level)))

    def with_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)


class SceneRenderer:
    def compose(
        self,
        frames: Iterable[LayerFrame],
        *,
        led_count: int,
        timestamp: float,
        settings: OutputSettings | None = None,
    ) -> OutputFrame:
        pixels = [0] * led_count
        for frame in frames:
            for index, value in enumerate(frame.pixels):
                if value is None:
                    # Nothing contributed here — keep what the layers below composed.
                    continue
                pixels[index] = value

        if settings is not None:
            if not settings.enabled:
                pixels = [0] * led_count
            elif settings.brightness < 1.0:
                pixels = [scale_color(value, settings.brightness) for value in pixels]

        return OutputFrame(leds=tuple(pixels), timestamp=timestamp)


__all__ = ["OutputSettings", "SceneRenderer"]
