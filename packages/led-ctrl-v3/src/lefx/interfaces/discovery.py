"""Finding devices and effect sets without importing them.

This is what makes the distribution boundary real rather than conventional. The
service never imports the hardware package, the simulator or a catalogue; it
reads the entry point groups ``lefx.frame_sinks``, ``lefx.input_providers`` and
``lefx.effect_sets`` and uses whatever is installed. Leaving a package out of an
installation leaves it out of the running system, with no code path to forget.

An entry point resolves to a factory. Failing to load one is reported and
skipped: a broken optional integration must not stop the service from starting.

Input providers are named ``<device>.<capability>`` — ``respeaker.doa``,
``simulator.doa``. The two halves do different jobs. The device half keeps the
names distinct while both packages are installed, which they routinely are; the
capability half is the only part a definition ever writes down. Choosing the
device chooses which providers run, and they are handed to the engine under the
bare capability, so the same ``provider_id="doa"`` resolves to the hardware or
to the simulator with nothing in the definition to change.

A provider registered without a device prefix belongs to no device and is always
available — a clock or a system sensor has no cable to be unplugged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, Callable, Mapping

from lefx.sdk import FrameSink, InputContext, OutputFrame, SinkStatus

from . import config

logger = logging.getLogger("lefx.interfaces.discovery")

SINK_GROUP = "lefx.frame_sinks"
PROVIDER_GROUP = "lefx.input_providers"
EFFECT_SET_GROUP = "lefx.effect_sets"

CAPABILITY_SEPARATOR = "."
"""Splits ``<device>.<capability>`` in an input provider's entry point name."""


def split_provider_name(name: str) -> tuple[str | None, str]:
    """Separate the device from the capability it provides.

    ``"respeaker.doa"`` becomes ``("respeaker", "doa")``; a bare ``"clock"``
    becomes ``(None, "clock")`` — no device, so no device to select it with.
    Only the first separator counts, so a capability may contain one.
    """
    device, separator, capability = name.partition(CAPABILITY_SEPARATOR)
    if not separator or not device or not capability:
        return None, name
    return device, capability


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


def create_providers(*, device: str | None = None, **options: Any) -> dict[str, Any]:
    """Build the selected device's input providers, keyed by capability.

    Providers belonging to another device are not built at all — building them
    would open a second device's connection for no reason. Providers with no
    device are always built.

    ``options`` reaches every factory unchanged, which is why factories are
    required to tolerate keywords they do not recognise.
    """
    built: dict[str, Any] = {}
    claimed: dict[str, str] = {}
    for name, discovered in sorted(available_providers().items()):
        owner, capability = split_provider_name(name)
        if owner is not None and owner != device:
            continue
        if capability in claimed:
            # Two providers offering one capability would otherwise resolve by
            # whichever the metadata happened to list first. Say who won.
            logger.warning(
                "input provider %r offers %r, which %r already provides; skipping it",
                name,
                capability,
                claimed[capability],
            )
            continue
        try:
            built[capability] = discovered.create(**options)
            claimed[capability] = name
        except Exception as exc:
            # A provider that cannot start is a missing data source, not a
            # reason for the service to refuse to run.
            logger.warning("could not create input provider %r: %s", name, exc)
    return built


def provider_callables(providers: Mapping[str, Any]) -> dict[str, Callable[[InputContext], Any]]:
    """Adapt provider objects to the callable the engine samples."""
    return {name: provider.sample for name, provider in providers.items()}


# -- effect sets ------------------------------------------------------------


def normalize_set_id(name: str) -> str:
    """The one form two spellings of a set both reduce to.

    ``core``, ``core-set``, ``Core_Set`` and ``core set`` are the same set. The
    id in a ``set.yaml`` carries the ``-set`` suffix and the entry point uses
    that id, but nobody writing ``INCLUDED_LEFXSET`` wants to type it, and
    telling them they must would be a rule with no purpose behind it.
    """
    reduced = name.strip().casefold().replace("_", "-").replace(" ", "-")
    return reduced[: -len("-set")] if reduced.endswith("-set") else reduced


def available_effect_sets() -> dict[str, Discovered]:
    """Every installed catalogue, keyed by the set id its entry point declares."""
    return _load(EFFECT_SET_GROUP)


def installed_effect_sets(included: list[str] | None = None) -> dict[str, Path]:
    """The archives of the installed sets that are switched on, by set id.

    ``included`` is a list of names in any of the forms ``normalize_set_id``
    accepts; ``None`` reads ``included_lefxset`` from the configuration, and an
    empty selection means every installed set. Empty-means-all rather than
    empty-means-none because the selection exists to *narrow* an installation,
    and a fresh install with no config file should play what it installed.

    A name that matches nothing installed is a warning, not an error: naming a
    set you have not installed yet is a mistake worth seeing, and not one worth
    refusing to start over.
    """
    if included is None:
        included = config.get("included_lefxset")
    wanted = {normalize_set_id(name) for name in included}

    found: dict[str, Path] = {}
    matched: set[str] = set()
    for set_id, discovered in sorted(available_effect_sets().items()):
        key = normalize_set_id(set_id)
        if wanted and key not in wanted:
            continue
        matched.add(key)
        try:
            path = Path(discovered.factory())
        except Exception as exc:
            logger.warning("effect set %r could not say where its archive is: %s", set_id, exc)
            continue
        if not path.is_file():
            # The distribution is installed but its archive is not there. In a
            # checkout that means build_effects.py has not run; in an
            # installation it means a broken wheel. Either way, silence here
            # would show up much later as an effect id nobody can resolve.
            logger.warning(
                "effect set %r is installed but %s is missing; it will not be loaded",
                set_id, path,
            )
            continue
        found[set_id] = path

    for name in sorted(wanted - matched):
        logger.warning(
            "included_lefxset names %r, which is not installed (installed: %s)",
            name, ", ".join(sorted(available_effect_sets())) or "none",
        )
    return found


def effect_set_search_paths(included: list[str] | None = None) -> list[Path]:
    """The directories the enabled sets live in, for the library to scan.

    Directories rather than files because that is what the engine's discovery
    takes, and because each catalogue distribution holds exactly one archive in
    a directory of its own — so the two are the same list said differently.
    """
    seen: dict[Path, None] = {}
    for path in installed_effect_sets(included).values():
        seen.setdefault(path.parent, None)
    return list(seen)


def describe() -> dict[str, Any]:
    """What is installed, for the status output and the sources listing."""
    enabled = installed_effect_sets()
    return {
        "effect_sets": [
            {
                "name": item.name,
                "distribution": item.distribution,
                "enabled": item.name in enabled,
                "archive": str(enabled[item.name]) if item.name in enabled else None,
            }
            for item in sorted(available_effect_sets().values(), key=lambda item: item.name)
        ],
        "sinks": [
            {"name": NullSink.name, "distribution": "led-ctrl-v3", "builtin": True},
            *(
                {"name": item.name, "distribution": item.distribution, "builtin": False}
                for item in sorted(available_sinks().values(), key=lambda item: item.name)
            ),
        ],
        "input_providers": [
            {
                "name": item.name,
                "device": split_provider_name(item.name)[0],
                "capability": split_provider_name(item.name)[1],
                "distribution": item.distribution,
            }
            for item in sorted(available_providers().values(), key=lambda item: item.name)
        ],
    }


__all__ = [
    "CAPABILITY_SEPARATOR",
    "EFFECT_SET_GROUP",
    "Discovered",
    "NullSink",
    "PROVIDER_GROUP",
    "SINK_GROUP",
    "available_effect_sets",
    "available_providers",
    "available_sinks",
    "create_providers",
    "create_sink",
    "describe",
    "effect_set_search_paths",
    "installed_effect_sets",
    "normalize_set_id",
    "provider_callables",
    "split_provider_name",
]
