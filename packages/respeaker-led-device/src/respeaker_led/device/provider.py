"""The direction-of-arrival input half of the device.

Reading is split in two on purpose. :meth:`ReSpeakerDoaProvider.refresh` is
called once per rendered frame and is the only thing that touches USB, at a rate
of its own choosing; :meth:`ReSpeakerDoaProvider.sample` hands out the cached
snapshot and never blocks. Ten overlays watching the direction therefore cost
one device read per interval, not ten per frame.

An inactive VAD is a valid, healthy reading — the microphones heard nothing.
Only an unreachable or malformed device counts as a failure.
"""

from __future__ import annotations

import logging
import math
import threading
from typing import Any, Mapping

from lefx.sdk import InputContext

from .transport import UsbTransport

logger = logging.getLogger("respeaker_led.device.provider")

DEFAULT_MAX_HZ = 30.0
"""Ceiling on device reads per second, independent of the render rate."""


def decode_doa(payload: Any) -> dict[str, Any]:
    """Turn a raw ``DOA_VALUE`` payload into the declared runtime inputs.

    Two ``uint16``: the angle in whole degrees, and the voice activity flag.
    Kept a free function so the wire format can be tested without a device.
    """
    if not isinstance(payload, (tuple, list)) or len(payload) != 2:
        raise ValueError(f"Unexpected DOA_VALUE payload: {payload!r}")

    raw_direction = payload[0]
    if isinstance(raw_direction, bool) or not isinstance(raw_direction, (int, float)):
        raise ValueError(f"Invalid DOA_VALUE direction: {raw_direction!r}")
    direction = float(raw_direction)
    if not math.isfinite(direction) or not 0.0 <= direction < 360.0:
        raise ValueError(f"DOA_VALUE direction is out of range: {raw_direction!r}")

    raw_vad = payload[1]
    if isinstance(raw_vad, bool):
        active = raw_vad
    elif isinstance(raw_vad, int) and raw_vad in {0, 1}:
        active = bool(raw_vad)
    else:
        raise ValueError(f"Invalid DOA_VALUE VAD flag: {raw_vad!r}")

    return {
        "direction_deg": direction,
        # The firmware distinguishes sound from silence, not speech from sound.
        # Claiming "speech" here would report more than the device measured.
        "detection_state": "sound" if active else "none",
    }


class ReSpeakerDoaProvider:
    """Caches the device's direction reading on its own schedule."""

    name = "respeaker.doa"
    capability = "doa"

    def __init__(self, transport: UsbTransport, *, max_hz: float = DEFAULT_MAX_HZ) -> None:
        if max_hz <= 0:
            raise ValueError("max_hz must be greater than zero")
        self.transport = transport
        self.max_hz = float(max_hz)
        self.interval_s = 1.0 / self.max_hz

        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] | None = None
        self._last_attempt_at: float | None = None
        self._last_success_at: float | None = None
        self._last_error: str | None = None
        self._poll_count = 0
        self._closed = False

    def refresh(self, now: float) -> bool:
        """Read the device if the interval has elapsed. Returns whether it tried."""
        with self._lock:
            if self._closed:
                return False
            if self._last_attempt_at is not None and now - self._last_attempt_at < self.interval_s:
                return False
            self._last_attempt_at = now
            self._poll_count += 1

        try:
            snapshot = decode_doa(self.transport.read("DOA_VALUE"))
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                # A disconnected device has no current direction. Keeping the
                # last one would let the ring point somewhere on stale data.
                self._snapshot = None
            return True

        with self._lock:
            self._snapshot = snapshot
            self._last_success_at = now
            self._last_error = None
        return True

    def sample(self, ctx: InputContext) -> Mapping[str, Any] | None:
        """Hand out the cached snapshot. Never touches the device itself.

        ``None`` means "no reading available" — the same answer the simulator
        gives with no window attached, and what the engine turns into ``waiting``
        and then ``failed``. Why there is none is in :meth:`status`.
        """
        del ctx
        with self._lock:
            return None if self._snapshot is None else dict(self._snapshot)

    def status(self, now: float) -> dict[str, Any]:
        with self._lock:
            age_ms = (
                None
                if self._last_success_at is None
                else max(0, int(round((now - self._last_success_at) * 1000.0)))
            )
            return {
                "provider_id": self.capability,
                "device": self.name,
                "max_hz": self.max_hz,
                "poll_count": self._poll_count,
                "age_ms": age_ms,
                "last_error": self._last_error,
                "available": self._snapshot is not None,
            }

    def close(self) -> None:
        """Idempotent. The transport is shared, so closing it is not our call."""
        with self._lock:
            self._closed = True
            self._snapshot = None


__all__ = ["DEFAULT_MAX_HZ", "ReSpeakerDoaProvider", "decode_doa"]
