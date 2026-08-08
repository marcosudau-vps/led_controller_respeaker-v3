"""How a device's measured direction relates to its LED ring.

A microphone array and an LED ring are two things screwed to one board, and
nothing guarantees that the array's zero points at LED zero. On the reSpeaker it
does not: the cable enters between the twelfth LED and the first, and the array
is rotated against the ring by whatever the layout happened to be. The number is
a property of the hardware, measured once.

That is why it lives here and is applied by the device rather than by an effect.
An effect asks for the capability ``doa`` and gets a bearing on the ring it is
drawing on; it does not ask which way round the board was assembled. Were the
offset an effect parameter, every definition that reads a direction and every
preset built from one would carry a copy of the same physical fact, and a second
device would need a second copy of each.

Both device packages need this and neither may import the other, so the shared
value belongs to the SDK — the same reason :class:`SinkStatus` does.

The effect's own ``angle_offset_deg`` stays what it always was: a deliberate
rotation of the picture, applied on top of a bearing that is already correct.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ENV_CALIBRATION_PATH = "LEFX_DOA_CALIBRATION"
DEFAULT_CALIBRATION_FILE = "doa_calibration.json"


@dataclass(slots=True, frozen=True)
class DoaCalibration:
    """The rotation between a device's measured zero and its LED zero."""

    angle_offset_deg: float = 0.0
    reverse: bool = False
    """Whether the array counts angles the other way round the ring."""

    def __post_init__(self) -> None:
        if not isinstance(self.reverse, bool):
            raise ValueError(f"reverse must be a boolean, got {self.reverse!r}")
        try:
            offset = float(self.angle_offset_deg)
        except (TypeError, ValueError):
            raise ValueError(
                f"angle_offset_deg must be a number, got {self.angle_offset_deg!r}"
            ) from None
        if offset != offset or offset in (float("inf"), float("-inf")):
            raise ValueError(f"angle_offset_deg must be finite, got {offset!r}")
        # Normalised on construction so two calibrations that mean the same
        # rotation compare equal and report the same number.
        object.__setattr__(self, "angle_offset_deg", offset % 360.0)

    @property
    def identity(self) -> bool:
        """Whether this changes nothing — an uncalibrated device."""
        return self.angle_offset_deg == 0.0 and not self.reverse

    def apply(self, direction_deg: float | None) -> float | None:
        """Turn a measured bearing into one expressed on the ring.

        Mirroring comes first and the offset second. The other order would
        mirror the mounting rotation along with the measurement, which is a
        different device and not this one.

        ``None`` stays ``None``: nothing measured cannot be rotated.
        """
        if direction_deg is None:
            return None
        measured = float(direction_deg) % 360.0
        if self.reverse:
            measured = (-measured) % 360.0
        return (measured + self.angle_offset_deg) % 360.0

    def to_dict(self) -> dict[str, Any]:
        return {"angle_offset_deg": self.angle_offset_deg, "reverse": self.reverse}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "DoaCalibration":
        unknown = set(payload) - {"angle_offset_deg", "reverse"}
        if unknown:
            raise ValueError(f"Unknown calibration keys: {sorted(unknown)}")
        return cls(
            angle_offset_deg=payload.get("angle_offset_deg", 0.0),
            reverse=bool(payload.get("reverse", False)),
        )


def calibration_path(path: str | Path | None = None) -> Path:
    """Where calibrations are kept: the argument, the environment, or the cwd."""
    if path is not None:
        return Path(path).expanduser()
    configured = os.environ.get(ENV_CALIBRATION_PATH)
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / DEFAULT_CALIBRATION_FILE


def load_calibration(device: str, *, path: str | Path | None = None) -> DoaCalibration:
    """The calibration recorded for one device, or the identity if there is none.

    Entries are keyed by device, because the file describes devices and there
    can be more than one — a reSpeaker on a desk and a simulator standing in
    for it do not share a mounting angle.

    A missing file means an uncalibrated device and is not an error. A file that
    exists and cannot be read *is* one: quietly falling back to the identity
    would leave every direction wrong by the offset that was supposed to fix
    it, and it would look exactly like a device that had never been calibrated.
    """
    target = calibration_path(path)
    if not target.is_file():
        return DoaCalibration()

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read the calibration at {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{target} must contain an object keyed by device name")

    entry = payload.get(device)
    if entry is None:
        return DoaCalibration()
    if not isinstance(entry, Mapping):
        raise ValueError(f"{target}: entry for {device!r} must be an object")
    try:
        return DoaCalibration.from_mapping(entry)
    except ValueError as exc:
        raise ValueError(f"{target}: entry for {device!r} is invalid: {exc}") from exc


def as_flag(value: Any) -> bool:
    """Coerce a command-line style value to a flag.

    ``--sink-option reverse=true`` arrives as text. The caller passing it cannot
    know what type a given option wants, so the conversion belongs beside the
    type that wants it.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on", "ja", "an"}


def resolve_calibration(
    device: str,
    *,
    angle_offset_deg: Any = None,
    reverse: Any = None,
    path: str | Path | None = None,
) -> DoaCalibration:
    """The calibration to use: the recorded one, with explicit options on top.

    Options override individually rather than wholesale, so overriding the
    offset for one run does not silently discard a recorded ``reverse``.
    """
    recorded = load_calibration(device, path=path)
    if angle_offset_deg is None and reverse is None:
        return recorded
    return DoaCalibration(
        angle_offset_deg=(
            recorded.angle_offset_deg if angle_offset_deg is None else float(angle_offset_deg)
        ),
        reverse=recorded.reverse if reverse is None else as_flag(reverse),
    )


def save_calibration(
    device: str, calibration: DoaCalibration, *, path: str | Path | None = None
) -> Path:
    """Record one device's calibration, leaving the other devices' alone."""
    target = calibration_path(path)
    payload: dict[str, Any] = {}
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read the calibration at {target}: {exc}") from exc
        if not isinstance(existing, dict):
            raise ValueError(f"{target} must contain an object keyed by device name")
        payload = existing

    payload[device] = calibration.to_dict()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


__all__ = [
    "DEFAULT_CALIBRATION_FILE",
    "ENV_CALIBRATION_PATH",
    "DoaCalibration",
    "as_flag",
    "calibration_path",
    "load_calibration",
    "resolve_calibration",
    "save_calibration",
]
