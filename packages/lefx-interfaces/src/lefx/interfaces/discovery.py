"""Finding frame sinks and input providers without importing them.

This is what makes the distribution boundary real rather than conventional. The
service never imports the hardware package or the simulator; it reads the entry
point groups ``lefx.frame_sinks`` and ``lefx.input_providers`` and uses whatever
is installed. Leaving a package out of an installation leaves it out of the
running system, with no code path to forget.

An entry point resolves to a factory. Failing to load one is reported and
skipped: a broken optional integration must not stop the service from starting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any, Callable, Mapping

from lefx.sdk import FrameSink, InputContext, OutputFrame, SinkStatus

logger = logging.getLogger("lefx.interfaces.discovery")

SINK_GROUP = "lefx.frame_sinks"
PROVIDER_GROUP = "lefx.input_providers"


class NullSink:
    """Accepts frames and does nothing with them.

    Always available, so the engine has somewhere to render even when no output
    package is installed. Keeps the last frame so ``status`` and the API can
    still show what would have been displayed.
    """

    name = "null"

    def __init__(self) -> None:
        self.last_frame: OutputFrame | None = None

    def apply_frame(self, frame: OutputFrame) -> None:
        self.last_frame = frame

    def status(self) -> SinkStatus:
        return SinkStatus(available=True, detail="no output device; frames are discarded")

    def close(self) -> None:
        return None


@dataclass(slots=True, frozen=True)
class Discovered:
    """One registered factory, not yet called."""

    name: str
    factory: Callable[..., Any]
    distribution: str | None = None

    def create(self, **options: Any) -> Any:
        return self.factory(**options)


def _load(group: str) -> dict[str, Discovered]:
    found: dict[str, Discovered] = {}
    for entry in entry_points(group=group):
        try:
            factory = entry.load()
        except Exception as exc:
            logger.warning("could not load %s entry point %r: %s", group, entry.name, exc)
            continue
        found[entry.name] = Discovered(
            name=entry.name, factory=factory, distribution=_distribution_of(entry)
        )
    return found


def _distribution_of(entry: EntryPoint) -> str | None:
    dist = getattr(entry, "dist", None)
    return None if dist is None else getattr(dist, "name", None)


def available_sinks() -> dict[str, Discovered]:
    return _load(SINK_GROUP)


def available_providers() -> dict[str, Discovered]:
    return _load(PROVIDER_GROUP)


def create_sink(name: str, **options: Any) -> FrameSink:
    """Build the named sink, or the null sink when the name is ``null``."""
    if name == NullSink.name:
        return NullSink()
    found = available_sinks()
    if name not in found:
        known = ", ".join(sorted([NullSink.name, *found]))
        raise LookupError(
            f"No frame sink named {name!r}. Installed sinks: {known}. "
            "Install the package that provides it, or use 'null'."
        )
    return found[name].create(**options)


def create_providers(**options: Any) -> dict[str, Any]:
    """Build every installed input provider, skipping the ones that fail."""
    built: dict[str, Any] = {}
    for name, discovered in available_providers().items():
        try:
            built[name] = discovered.create(**options)
        except Exception as exc:
            # A provider that cannot start is a missing data source, not a
            # reason for the service to refuse to run.
            logger.warning("could not create input provider %r: %s", name, exc)
    return built


def provider_callables(providers: Mapping[str, Any]) -> dict[str, Callable[[InputContext], Any]]:
    """Adapt provider objects to the callable the engine samples."""
    return {name: provider.sample for name, provider in providers.items()}


def describe() -> dict[str, Any]:
    """What is installed, for the status output and the sources listing."""
    return {
        "sinks": [
            {"name": NullSink.name, "distribution": "lefx-interfaces", "builtin": True},
            *(
                {"name": item.name, "distribution": item.distribution, "builtin": False}
                for item in sorted(available_sinks().values(), key=lambda item: item.name)
            ),
        ],
        "input_providers": [
            {"name": item.name, "distribution": item.distribution}
            for item in sorted(available_providers().values(), key=lambda item: item.name)
        ],
    }


__all__ = [
    "Discovered",
    "NullSink",
    "PROVIDER_GROUP",
    "SINK_GROUP",
    "available_providers",
    "available_sinks",
    "create_providers",
    "create_sink",
    "describe",
    "provider_callables",
]
