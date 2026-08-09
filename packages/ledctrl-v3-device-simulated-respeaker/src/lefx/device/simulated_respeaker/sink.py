"""The output half of the software device.

Same port, same obligations as the hardware sink: it never raises, and it says
whether it can deliver. What differs is only the reason it cannot — a closed
window instead of an unplugged cable — and that difference lives in the detail
string, where the rest of the system reads it as text rather than branching on it.

Unlike USB, a local socket write is cheap, so there is no change detection here.
Sending every frame keeps the window honest about the render rate.
"""

from __future__ import annotations

import logging

from lefx.sdk import OutputFrame, SinkStatus

from .link import SimulatorLink

logger = logging.getLogger("lefx.device.simulated_respeaker.sink")


class SimulatorFrameSink:
    """Sends composed frames to the ring window."""

    name = "simulator"

    def __init__(self, link: SimulatorLink, *, led_count: int = 12) -> None:
        self.link = link
        self.led_count = int(led_count)
        self._error: str | None = None
        self._closed = False

    def apply_frame(self, frame: OutputFrame) -> None:
        if self._closed:
            return
        leds = tuple(frame.leds)
        if len(leds) != self.led_count:
            # The window was told the ring size when it connected; a frame of a
            # different length would draw wrongly rather than not at all.
            self._error = f"frame has {len(leds)} LEDs, this ring has {self.led_count}"
            return
        try:
            self.link.send_frame(leds, frame.timestamp)
            self._error = None
        except Exception as exc:
            # Same rule as the hardware: a frame arrives thirty times a second,
            # and a display that went away between two of them is not an
            # exception for the render loop to handle.
            self._error = str(exc)
            logger.debug("frame not delivered: %s", exc)

    def status(self) -> SinkStatus:
        if self._closed:
            return SinkStatus(available=False, detail="sink closed")
        if self._error is not None:
            return SinkStatus(available=False, detail=self._error)
        detail = self.link.detail()
        return SinkStatus(available=detail is None, detail=detail)

    def close(self) -> None:
        """Idempotent."""
        if self._closed:
            return
        self._closed = True
        self.link.close()


__all__ = ["SimulatorFrameSink"]
