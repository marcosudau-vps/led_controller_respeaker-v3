"""Finding a definition among a few dozen, and knowing how to run it.

Two jobs, both free of Qt so they can be checked without a display.

The first is searching. A catalogue of thirty-five grows, and scrolling a list
stops being how you find something long before it stops being how it is drawn.
Matching covers everything a person might remember about an effect — its id, its
title, what it does, where it came from, what it was tagged with.

The second is telling the window *how* a definition is played, which is the one
thing that differs between the four lifecycle forms and the one thing a caller
must not guess. A state is set and stays. A controlled overlay is set on a
channel and then fed values. A timed overlay runs itself out. An event is
emitted and never repeated on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from lefx.engine import Preset, RegisteredEffect
from lefx.sdk import (
    ControlledOverlayDefinition,
    DefinitionBase,
    DefinitionKind,
    EventDefinition,
    StateDefinition,
    TimedOverlayDefinition,
)

# The four lifecycle forms, which is what a person is choosing between. The
# coarser DefinitionType groups the two overlays together, and they are the two
# a browser most needs to keep apart: one is fed values while it runs and the
# other runs itself out.
KIND_LABELS: dict[DefinitionKind, str] = {
    DefinitionKind.STATE: "State",
    DefinitionKind.CONTROLLED_OVERLAY: "Controlled Overlay",
    DefinitionKind.TIMED_OVERLAY: "Timed Overlay",
    DefinitionKind.EVENT: "Event",
}


@dataclass(slots=True, frozen=True)
class Playback:
    """How a definition reaches the ring, and what it needs to get there."""

    verb: str
    """``state``, ``overlay`` or ``event`` — which command applies it."""

    needs_channel: bool
    """Whether it is addressed by channel once running."""

    accepts_runtime_inputs: bool
    """Whether it reads values that arrive while it runs."""

    repeatable: bool
    """Whether re-applying it continuously is meaningful.

    False for events. An event is a thing that happened; replaying it thirty
    times a second because a slider moved would be a different thing, and a
    misleading one to judge the effect by.
    """

    finite: bool
    """Whether it ends by itself."""


def playback_for(definition: DefinitionBase) -> Playback:
    if isinstance(definition, StateDefinition):
        return Playback(
            verb="state",
            needs_channel=False,
            accepts_runtime_inputs=False,
            repeatable=True,
            finite=False,
        )
    if isinstance(definition, ControlledOverlayDefinition):
        return Playback(
            verb="overlay",
            needs_channel=True,
            accepts_runtime_inputs=True,
            repeatable=True,
            finite=False,
        )
    if isinstance(definition, TimedOverlayDefinition):
        return Playback(
            verb="overlay",
            needs_channel=False,
            accepts_runtime_inputs=False,
            repeatable=True,
            finite=True,
        )
    if isinstance(definition, EventDefinition):
        return Playback(
            verb="event",
            needs_channel=False,
            accepts_runtime_inputs=False,
            repeatable=False,
            finite=True,
        )
    raise TypeError(f"Unknown definition form: {type(definition).__name__}")


def pulls_a_provider(definition: DefinitionBase) -> str | None:
    """The capability this definition reads from a device, if it reads one.

    A controlled overlay either pulls values from a provider or is pushed them
    by a caller. Which one decides whether the studio should offer input
    controls or get out of the way and let the device supply them.
    """
    policy = getattr(definition, "input_sampling", None)
    return None if policy is None else policy.provider_id


@dataclass(slots=True, frozen=True)
class Entry:
    """One row in the browser."""

    effect: RegisteredEffect

    @property
    def effect_id(self) -> str:
        return self.effect.effect_id

    @property
    def definition(self) -> DefinitionBase:
        return self.effect.definition

    @property
    def title(self) -> str:
        return self.definition.title or self.definition.id

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.definition.kind, "Definition")

    @property
    def haystack(self) -> str:
        definition = self.definition
        return " ".join(
            [
                definition.id,
                definition.title or "",
                definition.description or "",
                self.effect.source_id,
                self.kind_label,
                *definition.tags,
            ]
        ).casefold()

    def matches(self, query: str) -> bool:
        """Every word has to appear somewhere. Order and field do not matter.

        Requiring all of them is what makes a second word narrow a search
        instead of widening it, which is what typing one more word is for.
        """
        needles = query.casefold().split()
        if not needles:
            return True
        hay = self.haystack
        return all(needle in hay for needle in needles)


def entries(effects: Iterable[RegisteredEffect]) -> list[Entry]:
    return [Entry(effect) for effect in effects]


def filtered(
    items: Iterable[Entry],
    *,
    query: str = "",
    kind: DefinitionKind | None = None,
    source_id: str | None = None,
) -> list[Entry]:
    return [
        entry
        for entry in items
        if (kind is None or entry.definition.kind is kind)
        and (source_id is None or entry.effect.source_id == source_id)
        and entry.matches(query)
    ]


def starting_config(definition: DefinitionBase, preset: Preset | None = None) -> dict[str, Any]:
    """The values an editor opens with: the schema's defaults, then a preset's.

    Every declared parameter is present even when nothing supplies it, so the
    editor shows the whole surface of the definition rather than the part
    somebody happened to write down.
    """
    config: dict[str, Any] = {}
    for name, parameter in definition.parameter_schema.items():
        config[name] = parameter.default if parameter.has_default else None
    if preset is not None:
        config.update({key: value for key, value in preset.params.items() if key in config})
    return config


def starting_inputs(definition: DefinitionBase) -> dict[str, Any]:
    """The runtime inputs an editor opens with, or nothing for a form with none."""
    schema: Mapping[str, Any] = getattr(definition, "runtime_input_schema", {}) or {}
    return {
        name: (parameter.default if parameter.has_default else None)
        for name, parameter in schema.items()
    }


__all__ = [
    "KIND_LABELS",
    "Entry",
    "Playback",
    "entries",
    "filtered",
    "playback_for",
    "pulls_a_provider",
    "starting_config",
    "starting_inputs",
]
