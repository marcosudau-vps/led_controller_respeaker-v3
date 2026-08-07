"""What the entry points resolve to.

Mirrors the hardware package deliberately: two factories, one shared transport,
``**options`` tolerated everywhere. The service treats both devices through the
same code path, so anything asymmetric here would show up as the service having
to know which one it has.

Nothing in this import chain touches Qt. ``registration``, ``link``, ``sink``
and ``provider`` must stay importable in a service process that has no GUI
toolkit installed at all — PySide6 is an extra, and the window is a separate
program.
"""

from __future__ import annotations

import threading
from typing import Any

from lefx.sdk import FrameSink, InputProvider

from .link import SimulatorLink
from .provider import DEFAULT_MAX_HZ, SimulatorDoaProvider
from .sink import SimulatorFrameSink

_lock = threading.Lock()
_link: SimulatorLink | None = None


def shared_link(**options: Any) -> SimulatorLink:
    """The one loopback link, created on first use and left listening.

    Sink and provider share it the way they share a USB cable on the hardware:
    two listeners on one port is not a thing, and two links would leave the
    window able to reach only one of them.
    """
    global _link
    with _lock:
        if _link is None:
            _link = SimulatorLink(**options)
        link = _link
    link.start()
    return link


def reset_shared_link() -> None:
    """Drop the shared link, closing it first. For tests and restarts."""
    global _link
    with _lock:
        link, _link = _link, None
    if link is not None:
        link.close()


def _link_options(led_count: int, host: str | None, port: int | str | None) -> dict[str, Any]:
    """Only pass what was actually given, so the link keeps its own defaults.

    ``port`` may arrive as text from ``--sink-option port=8770``; the CLI does
    not know the type a sink wants for an option, so the conversion belongs here.
    """
    options: dict[str, Any] = {"led_count": int(led_count)}
    if host is not None:
        options["host"] = str(host)
    if port is not None:
        options["port"] = int(port)
    return options


def create_frame_sink(
    *, led_count: int = 12, host: str | None = None, port: int | str | None = None, **options: Any
) -> FrameSink:
    del options
    link = shared_link(**_link_options(led_count, host, port))
    return SimulatorFrameSink(link, led_count=led_count)


def create_doa_provider(
    *,
    led_count: int = 12,
    host: str | None = None,
    port: int | str | None = None,
    max_hz: float = DEFAULT_MAX_HZ,
    **options: Any,
) -> InputProvider:
    del options
    # The sink is built before the providers, so when both are the simulator's
    # this call finds the link the sink already configured and its own defaults
    # never come into play.
    link = shared_link(**_link_options(led_count, host, port))
    return SimulatorDoaProvider(link, max_hz=max_hz)


__all__ = ["create_doa_provider", "create_frame_sink", "reset_shared_link", "shared_link"]
