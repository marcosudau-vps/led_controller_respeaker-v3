"""The base class every effect package implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Mapping

from .context import InputContext, RenderContext
from .definitions import DefinitionBase


class BaseEffect(ABC):
    """One effect implementation, bound to exactly one definition.

    The engine creates one instance per activation, so an implementation may
    hold Python state for the run it is part of. It must not hold external
    resources: V3 has no start, stop, reset or finished hook, and an instance is
    dropped without notice when the engine ends it.
    """

    definition: ClassVar[DefinitionBase]

    @classmethod
    def get_definition(cls) -> DefinitionBase:
        return cls.definition

    def sample_inputs(self, ctx: InputContext) -> Mapping[str, Any] | None:
        """Provide runtime inputs for a pull-sampled controlled overlay.

        Only called when the definition declares pull sampling without a
        provider id. Must not block: it runs inside the render loop.
        """
        del ctx
        return None

    @abstractmethod
    def render(self, ctx: RenderContext) -> list[int | None]:
        """Return exactly ``ctx.led_count`` entries.

        Each entry is either an RGB integer or ``None``, and the difference
        between ``None`` and black is the whole point of the layer model:

        ``None``
            Contribute nothing at this position. Whatever the layers below
            composed stays visible — a direction marker over a state leaves
            eleven of twelve positions ``None`` so the state shows through.

        ``0x000000``
            Black is a colour. It overwrites what is below and switches the LED
            off. Use it to hide the layer below, never as a stand-in for "no
            contribution".

        Only a transparent definition may return ``None``; an opaque one fills
        every position. ``ctx.transparent_frame()`` and ``ctx.blank_frame()``
        give the two neutral starting points.

        Must be deterministic for a given context and fast: it runs once per
        frame per active layer, and it performs no I/O.
        """
        raise NotImplementedError


__all__ = ["BaseEffect"]
