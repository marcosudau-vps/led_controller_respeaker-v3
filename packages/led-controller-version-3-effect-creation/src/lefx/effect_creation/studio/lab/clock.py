"""Preview time that does not depend on how often anyone looks at it.

The timeline asks for "now" whenever it repaints, which is as often as the GUI
manages. The answer is computed from a monotonic clock and an anchor, never by
adding a frame interval, so a slow repaint shows a later moment rather than a
slower effect, and pausing, seeking or changing the speed costs no drift.
"""

from __future__ import annotations

import time
from typing import Callable


class PreviewClock:
    """Play, pause, stop and seek over ``[start, end]`` at a chosen speed."""

    def __init__(
        self, *, start: float = 0.0, end: float = 10.0, now: Callable[[], float] = time.monotonic
    ) -> None:
        self._now = now
        self.start = float(start)
        self.end = max(self.start + 0.001, float(end))
        self.speed = 1.0
        self.loop = True
        self._position = self.start
        self._anchor: float | None = None

    @property
    def playing(self) -> bool:
        return self._anchor is not None

    def elapsed(self) -> float:
        """The preview time right now. Reaching the end loops or pauses there."""
        if self._anchor is None:
            return self._position
        moment = self._now()
        position = self._position + (moment - self._anchor) * self.speed
        if position >= self.end:
            if self.loop:
                position = self.start + (position - self.start) % (self.end - self.start)
            else:
                position, moment = self.end, None
        self._position, self._anchor = position, moment
        return position

    def play(self) -> None:
        if self.playing:
            return
        if self._position >= self.end:
            self._position = self.start
        self._anchor = self._now()

    def pause(self) -> None:
        self._position = self.elapsed()
        self._anchor = None

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def stop(self) -> None:
        self._anchor = None
        self._position = self.start

    def seek(self, position: float) -> None:
        self._position = min(self.end, max(self.start, float(position)))
        if self._anchor is not None:
            self._anchor = self._now()

    def set_speed(self, speed: float) -> None:
        self._position = self.elapsed()
        if self._anchor is not None:
            self._anchor = self._now()
        self.speed = max(0.01, float(speed))

    def set_range(self, start: float, end: float) -> None:
        position = self.elapsed()
        self.start = max(0.0, float(start))
        self.end = max(self.start + 0.001, float(end))
        self.seek(position)


__all__ = ["PreviewClock"]
