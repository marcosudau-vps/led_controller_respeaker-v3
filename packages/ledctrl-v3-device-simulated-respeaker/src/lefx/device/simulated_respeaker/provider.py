"""The direction-of-arrival input half of the software device.

Same shape as the hardware provider, down to the value ranges: ``direction_deg``
is a float in ``[0, 360)`` and ``detection_state`` is one of the values
``direction_indicator`` declares. An effect cannot tell which of the two it is
reading from, and that is the whole point of the simulator being a device rather
than a preview mode.

With no window attached, :meth:`sample` returns ``None`` — the same answer an
unplugged reSpeaker gives, which the engine turns into ``waiting`` and then,
once the grace period lapses, ``failed``.
"""

from __future__ import annotations

import threading
from typing import Any, Mapping

from lefx.sdk import DoaCalibration, InputContext

from .link import SimulatorLink

DETECTION_STATES = ("none", "sound", "speech")
"""Mirrors the enum ``direction_indicator`` declares. A window that reports
anything else is reporting something no effect can use."""

DEFAULT_MAX_HZ = 30.0
"""The same ceiling the reSpeaker's provider uses.

Nothing here needs protecting from being read too often — the value is already
in memory. It is rate-limited anyway because an update cadence is part of what a
device is: an effect that only looks smooth against a source refreshing as fast
as it renders would look different on hardware, and then the simulator would
have stopped being a stand-in for it.
"""


class SimulatorDoaProvider:
    """Hands out the direction the ring window's controls are set to."""

    name = "simulator.doa"
    capability = "doa"

    def __init__(
        self,
        link: SimulatorLink,
        *,
        max_hz: float = DEFAULT_MAX_HZ,
        calibration: DoaCalibration | None = None,
    ) -> None:
        if max_hz <= 0:
            raise ValueError("max_hz must be greater than zero")
        self.link = link
        self.max_hz = float(max_hz)
        self.interval_s = 1.0 / self.max_hz
        # Carried for the same reason the hardware carries it, and applied at
        # the same point. A simulator whose readings needed no calibrating
        # would be a device with one fewer way to be wrong than the one it
        # stands in for, and the difference would show up first in whatever was
        # being debugged against it.
        self.calibration = calibration if calibration is not None else DoaCalibration()
        self._last_attempt_at: float | None = None
        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] | None = None
        self._last_success_at: float | None = None
        self._last_error: str | None = None
        self._refresh_count = 0
        self._closed = False

    def refresh(self, now: float) -> bool:
        """Take the window's current setting, if the interval has elapsed.

        Returns whether it tried — the same answer, on the same schedule, as the
        hardware provider gives.
        """
        with self._lock:
            if self._closed:
                return False
            if self._last_attempt_at is not None and now - self._last_attempt_at < self.interval_s:
                return False
            self._last_attempt_at = now
            self._refresh_count += 1

        reading = self.link.latest_inputs()
        if reading is None:
            with self._lock:
                self._snapshot = None
                self._last_error = self.link.detail()
            return True

        try:
            snapshot = self._validate(reading)
            snapshot["direction_deg"] = self.calibration.apply(snapshot["direction_deg"])
        except ValueError as exc:
            with self._lock:
                self._snapshot = None
                self._last_error = str(exc)
            return True

        with self._lock:
            self._snapshot = snapshot
            self._last_success_at = now
            self._last_error = None
        return True

    @staticmethod
    def _validate(reading: Mapping[str, Any]) -> dict[str, Any]:
        """Hold the window to the same contract the firmware is held to.

        The window is a separate process that could be any build; letting an
        out-of-range angle through here would make the simulator laxer than the
        hardware, and the two would stop being interchangeable.
        """
        direction = reading.get("direction_deg")
        if direction is not None:
            try:
                direction = float(direction)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid direction_deg: {reading.get('direction_deg')!r}") from None
            if not 0.0 <= direction < 360.0:
                raise ValueError(f"direction_deg is out of range: {direction!r}")

        state = reading.get("detection_state", "none")
        if state not in DETECTION_STATES:
            raise ValueError(f"Unknown detection_state: {state!r}")

        return {"direction_deg": direction, "detection_state": state}

    def sample(self, ctx: InputContext) -> Mapping[str, Any] | None:
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
                "refresh_count": self._refresh_count,
                "age_ms": age_ms,
                "last_error": self._last_error,
                "available": self._snapshot is not None,
                "calibration": self.calibration.to_dict(),
            }

    def close(self) -> None:
        """Idempotent. The link is shared with the sink, so it is not closed here."""
        with self._lock:
            self._closed = True
            self._snapshot = None


__all__ = ["DEFAULT_MAX_HZ", "DETECTION_STATES", "SimulatorDoaProvider"]
