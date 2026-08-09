"""What the entry points resolve to.

Two factories, one per direction, declared separately in ``pyproject.toml`` as
``lefx.frame_sinks: respeaker`` and ``lefx.input_providers: respeaker.doa``.
The service calls whichever it needs and never imports this package by name.

Both share a single transport. Output and input are independent objects — the
point of registering them separately — but there is one USB endpoint, and two
transports would take turns losing to each other over it.

Every factory takes ``**options`` and ignores what it does not know: the service
passes the same keywords to every installed factory, so tolerating unfamiliar
ones is part of the contract rather than politeness.
"""

from __future__ import annotations

import threading
from typing import Any

from lefx.sdk import FrameSink, InputProvider, resolve_calibration

from . import xvf
from .provider import DEFAULT_MAX_HZ, ReSpeakerDoaProvider
from .sink import ReSpeakerFrameSink
from .transport import UsbTransport

DEVICE_NAME = "respeaker"
"""The key this device's calibration is stored under."""

_lock = threading.Lock()
_transport: UsbTransport | None = None


def as_bool(value: Any) -> bool:
    """Coerce a sink option to a flag.

    ``--sink-option force_claim=true`` arrives as text: the CLI cannot know what
    type a given sink wants for a given option, so the conversion belongs to the
    side that declared the option.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on", "ja", "an"}


def as_int(value: Any) -> int:
    """Coerce a sink option to a whole number, accepting ``0x2886`` as written.

    Base zero rather than ten, because the two options that use this are a USB
    vendor and product id, and every datasheet, every device manager entry and
    every line of documentation writes those in hex.
    """
    if isinstance(value, bool):
        raise ValueError("expected a number, got a flag")
    if isinstance(value, int):
        return value
    return int(str(value).strip(), 0)


def shared_transport(**options: Any) -> UsbTransport:
    """The one managed USB connection, created on first use and kept running.

    ``options`` configures the transport the first time only; later callers get
    the connection that already exists rather than a second one configured
    differently.
    """
    global _transport
    with _lock:
        if _transport is None:
            _transport = UsbTransport(**options)
        transport = _transport
    # Outside the lock: start() takes the transport's own locks, and it also
    # revives a transport that a previous shutdown stopped.
    transport.start()
    return transport


def reset_shared_transport() -> None:
    """Drop the shared transport, stopping it first. For tests and restarts."""
    global _transport
    with _lock:
        transport, _transport = _transport, None
    if transport is not None:
        transport.close()


def _transport_options(
    force_claim: Any,
    claim_unrelated: Any,
    vendor_id: Any = None,
    product_id: Any = None,
    usb_timeout_ms: Any = None,
) -> dict[str, Any]:
    """Only what the caller actually asked for.

    Force-claiming terminates another program, so it is never inferred from a
    default. It has to be spelled out, every time, by whoever is running this.

    Device identity and transfer timeout travel as a prepared ``finder`` rather
    than as three more transport parameters. The transport's job is keeping a
    connection alive, not knowing which device it is or how patient to be with
    it; both of those belong to whoever opens the handle, and that is the finder.
    Left unspecified, no finder is passed at all and the transport keeps its own
    default — so an ordinary installation is unaffected by any of this.
    """
    options: dict[str, Any] = {}
    if force_claim is not None:
        options["force_claim"] = as_bool(force_claim)
    if claim_unrelated is not None:
        options["claim_unrelated"] = as_bool(claim_unrelated)

    if vendor_id is None and product_id is None and usb_timeout_ms is None:
        return options

    vid = xvf.VENDOR_ID if vendor_id is None else as_int(vendor_id)
    pid = xvf.PRODUCT_ID if product_id is None else as_int(product_id)
    timeout = None if usb_timeout_ms is None else as_int(usb_timeout_ms)
    options["finder"] = lambda: xvf.find(vid, pid, timeout_ms=timeout)
    return options


def create_frame_sink(
    *,
    led_count: int = xvf.RING_LED_COUNT,
    force_claim: Any = None,
    claim_unrelated: Any = None,
    vendor_id: Any = None,
    product_id: Any = None,
    usb_timeout_ms: Any = None,
    **options: Any,
) -> FrameSink:
    del options
    transport = shared_transport(
        **_transport_options(
            force_claim, claim_unrelated, vendor_id, product_id, usb_timeout_ms
        )
    )
    return ReSpeakerFrameSink(transport, led_count=led_count)


def create_doa_provider(
    *,
    max_hz: float = DEFAULT_MAX_HZ,
    force_claim: Any = None,
    claim_unrelated: Any = None,
    vendor_id: Any = None,
    product_id: Any = None,
    usb_timeout_ms: Any = None,
    angle_offset_deg: Any = None,
    reverse: Any = None,
    calibration_file: Any = None,
    **options: Any,
) -> InputProvider:
    del options
    transport = shared_transport(
        **_transport_options(
            force_claim, claim_unrelated, vendor_id, product_id, usb_timeout_ms
        )
    )
    return ReSpeakerDoaProvider(
        transport,
        max_hz=max_hz,
        calibration=resolve_calibration(
            DEVICE_NAME,
            angle_offset_deg=angle_offset_deg,
            reverse=reverse,
            path=calibration_file,
        ),
    )


__all__ = [
    "DEVICE_NAME",
    "as_bool",
    "as_int",
    "create_doa_provider",
    "create_frame_sink",
    "reset_shared_transport",
    "shared_transport",
]
