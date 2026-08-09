"""Runtime input health and the shared polling helper.

The engine judges *reception*, not plausibility: whether a value arrived in
time, never whether it makes sense. A syntactically valid but nonsensical
reading is the source's problem or the definition's, not the engine's.

Nothing here ends an instance. A controlled overlay whose source has gone quiet
keeps running with null values, and the definition decides what that looks like.
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Any, Callable, Mapping

from lefx.sdk import DefinitionBase, InputContext

from .invocation import Invocation


class InputHealth(str, Enum):
    WAITING = "waiting"
    """Nothing has arrived yet since activation."""

    HEALTHY = "healthy"
    """A value arrived within the grace period."""

    FAILED = "failed"
    """The grace period has passed without a value."""


def _anchor(invocation: Invocation) -> float:
    """The point health is measured from.

    Activation seeds the clock so a brand new instance is not immediately
    considered failed; every success moves it forward.
    """
    if invocation.input_last_success_at is not None:
        return invocation.input_last_success_at
    return invocation.activated_at if invocation.activated_at is not None else invocation.created_at


def age_ms(invocation: Invocation, now: float) -> float:
    return max(0.0, (now - _anchor(invocation)) * 1000.0)


def evaluate_health(
    definition: DefinitionBase, invocation: Invocation, now: float
) -> InputHealth | None:
    """Reception state, or ``None`` for a form that has no runtime inputs."""
    policy = definition.input_sampling
    if policy is None or not definition.runtime_input_schema:
        return None
    if age_ms(invocation, now) >= policy.failure_after_ms:
        return InputHealth.FAILED
    if invocation.input_last_success_at is None:
        return InputHealth.WAITING
    return InputHealth.HEALTHY


def effective_inputs(
    definition: DefinitionBase, invocation: Invocation, now: float
) -> dict[str, Any]:
    """The values a render actually sees.

    Every declared key is present. During the grace period the last good values
    stay in place; once it lapses every declared field reads null, and the
    definition interprets that — the engine draws no error state of its own.
    """
    schema = definition.runtime_input_schema
    if not schema:
        return {}
    if evaluate_health(definition, invocation, now) is InputHealth.FAILED:
        return {name: None for name in schema}
    return {name: invocation.inputs.get(name) for name in schema}


def input_status(
    definition: DefinitionBase, invocation: Invocation, now: float
) -> dict[str, Any] | None:
    """Machine-readable reception state for the status endpoint."""
    policy = definition.input_sampling
    health = evaluate_health(definition, invocation, now)
    if policy is None or health is None:
        return None
    elapsed = age_ms(invocation, now)
    return {
        "mode": policy.mode.value,
        "provider_id": policy.provider_id,
        "status": health.value,
        "age_ms": int(round(elapsed)),
        "missed_heartbeats": int(elapsed // policy.heartbeat_interval_ms),
        "max_missed_heartbeats": policy.max_missed_heartbeats,
        "failure_after_ms": policy.failure_after_ms,
        "last_error": invocation.input_error,
    }


class PolledInputProvider:
    """Caches a reading so effect count and device access rate stay decoupled.

    Shared hardware is read on this provider's own schedule. Ten overlays
    watching the same source therefore produce one read per interval, not ten
    per frame.
    """

    def __init__(
        self,
        provider_id: str,
        reader: Callable[[], Mapping[str, Any] | None],
        *,
        max_hz: float,
    ) -> None:
        normalized = str(provider_id).strip()
        if not normalized:
            raise ValueError("provider_id must not be empty")
        if max_hz <= 0:
            raise ValueError("max_hz must be greater than zero")

        self.provider_id = normalized
        self.reader = reader
        self.max_hz = float(max_hz)
        self.interval_s = 1.0 / self.max_hz
        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] | None = None
        self._last_attempt_at: float | None = None
        self._last_success_at: float | None = None
        self._last_error: str | None = None
        self._poll_count = 0

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def refresh(self, now: float) -> bool:
        """Read the source if the interval has elapsed. Returns whether it tried."""
        with self._lock:
            if (
                self._last_attempt_at is not None
                and now - self._last_attempt_at < self.interval_s
            ):
                return False
            self._last_attempt_at = now
            self._poll_count += 1

        try:
            sampled = self.reader()
            if sampled is None:
                raise RuntimeError("input source returned no value")
            snapshot = dict(sampled)
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            return True

        with self._lock:
            self._snapshot = snapshot
            self._last_success_at = now
            self._last_error = None
        return True

    def sample(self, ctx: InputContext) -> Mapping[str, Any] | None:
        """Hand out the cached snapshot. Never touches the device itself."""
        del ctx
        with self._lock:
            if self._last_error is not None:
                raise RuntimeError(self._last_error)
            return None if self._snapshot is None else dict(self._snapshot)

    def status(self, now: float) -> dict[str, Any]:
        with self._lock:
            elapsed = (
                None
                if self._last_success_at is None
                else max(0, int(round((now - self._last_success_at) * 1000.0)))
            )
            return {
                "provider_id": self.provider_id,
                "max_hz": self.max_hz,
                "poll_count": self._poll_count,
                "age_ms": elapsed,
                "last_error": self._last_error,
                "available": self._snapshot is not None and self._last_error is None,
            }


__all__ = [
    "InputHealth",
    "PolledInputProvider",
    "age_ms",
    "effective_inputs",
    "evaluate_health",
    "input_status",
]
