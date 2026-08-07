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

from lefx.sdk import FrameSink, InputProvider

from . import xvf
from .provider import DEFAULT_MAX_HZ, ReSpeakerDoaProvider
from .sink import ReSpeakerFrameSink
from .transport import UsbTransport

_lock = threading.Lock()
_transport: UsbTransport | None = None


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


def create_frame_sink(*, led_count: int = xvf.RING_LED_COUNT, **options: Any) -> FrameSink:
    del options
    return ReSpeakerFrameSink(shared_transport(), led_count=led_count)


def create_doa_provider(
    *, max_hz: float = DEFAULT_MAX_HZ, **options: Any
) -> InputProvider:
    del options
    return ReSpeakerDoaProvider(shared_transport(), max_hz=max_hz)


__all__ = [
    "create_doa_provider",
    "create_frame_sink",
    "reset_shared_transport",
    "shared_transport",
]
