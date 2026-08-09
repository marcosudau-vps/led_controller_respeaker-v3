"""The LED output half of the device.

Writes composed frames to the ring and reports whether it can. It never raises
at the port: a frame arrives thirty times a second, and a cable pulled between
two of them is an ordinary condition, not an exception the render loop should
have to catch. What went wrong is answered by :meth:`ReSpeakerFrameSink.status`.
"""

from __future__ import annotations

import logging

from lefx.sdk import OutputFrame, SinkStatus

from . import xvf
from .transport import UsbTransport

logger = logging.getLogger("lefx.device.respeaker.sink")


class ReSpeakerFrameSink:
    """Puts a frame on the reSpeaker's LED ring."""

    name = "respeaker"

    def __init__(self, transport: UsbTransport, *, led_count: int = xvf.RING_LED_COUNT) -> None:
        self.transport = transport
        self.led_count = int(led_count)
        self._ring_mode = False
        self._last_leds: tuple[int, ...] | None = None
        self._write_error: str | None = None
        self._closed = False

        # Configuration disagreeing with the hardware is a standing fault, not a
        # transient one: it is reported for as long as it holds, rather than
        # letting every single frame fail the firmware's length check.
        self._config_error: str | None = None
        if self.led_count != xvf.RING_LED_COUNT:
            self._config_error = (
                f"configured for {self.led_count} LEDs, but this device's ring "
                f"carries {xvf.RING_LED_COUNT}"
            )
            logger.error("%s", self._config_error)

    def apply_frame(self, frame: OutputFrame) -> None:
        leds = tuple(frame.leds)
        if len(leds) != xvf.RING_LED_COUNT:
            self._write_error = (
                f"frame has {len(leds)} LEDs, the ring takes {xvf.RING_LED_COUNT}"
            )
            return
        if not self.transport.is_connected:
            # The transport owns the explanation while the cable is out, so a
            # stale write error would only obscure it. The next connected frame
            # starts from a clean slate.
            self._forget()
            self._write_error = None
            return

        try:
            # A reconnected device has forgotten the ring mode along with
            # everything else, so re-assert it whenever the handle is new.
            # Read unconditionally: folding this into the condition below would
            # let short-circuiting skip the read on the very frame that sets the
            # mode, leaving the flag to fire again on the next one.
            new_session = self.transport.consume_session_dirty()
            if new_session or not self._ring_mode:
                self.transport.write("LED_EFFECT", [xvf.LED_EFFECT_RING_MODE])
                self._ring_mode = True
                self._last_leds = None
            if leds != self._last_leds:
                # USB writes are the expensive part of a frame. A ring that did
                # not change does not need to be sent again.
                self.transport.write("LED_RING_COLOR", list(leds))
                self._last_leds = leds
            self._write_error = None
        except Exception as exc:
            self._forget()
            self._write_error = str(exc)
            logger.debug("frame not delivered: %s", exc)

    def status(self) -> SinkStatus:
        if self._closed:
            return SinkStatus(available=False, detail="sink closed")
        if self._config_error is not None:
            return SinkStatus(available=False, detail=self._config_error)
        if not self.transport.is_connected:
            detail = self.transport.last_error or "reSpeaker not connected"
            return SinkStatus(available=False, detail=detail)
        if self._write_error is not None:
            return SinkStatus(available=False, detail=self._write_error)
        return SinkStatus(available=True, detail=None)

    def close(self) -> None:
        """Idempotent — shutdown paths overlap, and closing twice is not a fault."""
        if self._closed:
            return
        self._closed = True
        self._forget()
        self.transport.close()

    def _forget(self) -> None:
        """Drop what we believe about the device, so nothing is skipped later."""
        self._ring_mode = False
        self._last_leds = None


__all__ = ["ReSpeakerFrameSink"]
