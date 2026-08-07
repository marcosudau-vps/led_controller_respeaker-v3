"""Templates for new sources.

Every scaffold validates and packs as generated. Starting from something that
already works means the first error an author sees comes from their own change,
not from the starting point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lefx.sdk import DefinitionKind

from .source import SourceError

_KIND_ALIASES = {
    "state": DefinitionKind.STATE,
    "overlay": DefinitionKind.CONTROLLED_OVERLAY,
    "controlled": DefinitionKind.CONTROLLED_OVERLAY,
    "controlled_overlay": DefinitionKind.CONTROLLED_OVERLAY,
    "timed": DefinitionKind.TIMED_OVERLAY,
    "timed_overlay": DefinitionKind.TIMED_OVERLAY,
    "event": DefinitionKind.EVENT,
}


def parse_kind(value: str) -> DefinitionKind:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized not in _KIND_ALIASES:
        options = ", ".join(sorted({"state", "controlled_overlay", "timed_overlay", "event"}))
        raise SourceError(f"Unknown definition kind {value!r}. Expected one of: {options}")
    return _KIND_ALIASES[normalized]


def _class_name(effect_id: str) -> str:
    return "".join(part.capitalize() for part in effect_id.split("_")) or "Effect"


_MANIFEST = """\
# The class in effect.py is the source of truth for the contract. This manifest
# only says where the definition belongs and where to find it.
source_id: {source_id}
entry_file: effect.py
entry_class: {class_name}
"""

_PRESETS = """\
presets:
  {effect_id}_default:
    title: {title} (Default)
    description: A starting point; every value stays overridable.
    params:
      color: "{color}"
"""

_STATE = '''\
from lefx.sdk import (
    BaseEffect,
    ColorModel,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    StateSlot,
    parse_color,
    scale_color,
)


class {class_name}(BaseEffect):
    """A persistent ground state: runs until it is replaced or cleared."""

    definition = StateDefinition(
        id="{effect_id}",
        title="{title}",
        description="Describe what this state shows and when it applies.",
        parameter_schema={{
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="{color}",
                description="Ring colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Brightness factor.",
            ),
        }},
        color_model=ColorModel.MONO,
        slots=(StateSlot.PRIMARY,),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        # ctx.params always holds every declared key, already canonical.
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        return [color] * ctx.led_count
'''

_CONTROLLED = '''\
from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    ParamDefinition,
    ParamType,
    RenderContext,
    parse_color,
    position_for_angle,
    scale_color,
)


class {class_name}(BaseEffect):
    """A controlled overlay: runs until its channel is cleared, fed at runtime."""

    definition = ControlledOverlayDefinition(
        id="{effect_id}",
        title="{title}",
        description="Describe what this overlay shows and who supplies its data.",
        parameter_schema={{
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="{color}",
                description="Marker colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Brightness factor.",
            ),
        }},
        runtime_inputs={{
            "direction_deg": ParamDefinition(
                name="direction_deg", type=ParamType.ANGLE_DEG,
                required=True, nullable=True, unit="deg",
                description="Direction supplied while the overlay runs.",
            ),
        }},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        # None leaves the layers below visible; black would hide them.
        frame = ctx.transparent_frame()
        direction = ctx.inputs["direction_deg"]
        if direction is None:
            # No value yet, or the source went quiet. Show nothing.
            return frame
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        frame[position_for_angle(direction, ctx.led_count)] = color
        return frame
'''

_TIMED = '''\
from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ParamDefinition,
    ParamType,
    RenderContext,
    TimedOverlayDefinition,
    parse_color,
    scale_color,
)


class {class_name}(BaseEffect):
    """A timed overlay: activated once, removed by the engine when its time is up."""

    definition = TimedOverlayDefinition(
        id="{effect_id}",
        title="{title}",
        description="Describe what this overlay shows for its short lifetime.",
        parameter_schema={{
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="{color}",
                description="Overlay colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Brightness factor.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=1200,
                minimum=1, unit="ms", description="How long it stays visible.",
            ),
        }},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        # Progress comes from the clock, never from a frame counter.
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0
        lit = max(1, int(round(progress * ctx.led_count)))
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        frame = ctx.transparent_frame()
        for index in range(lit):
            frame[index] = color
        return frame
'''

_EVENT = '''\
from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    EventDefinition,
    ParamDefinition,
    ParamType,
    RenderContext,
    parse_color,
    scale_color,
)


class {class_name}(BaseEffect):
    """An event: a single prioritized signal the engine ends on its own."""

    definition = EventDefinition(
        id="{effect_id}",
        title="{title}",
        description="Describe the signal this event conveys.",
        parameter_schema={{
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="{color}",
                description="Signal colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Brightness factor.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=600,
                minimum=1, unit="ms", description="How long the signal lasts.",
            ),
        }},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        fade = 1.0 - min(1.0, ctx.elapsed / total) if total > 0 else 0.0
        color = scale_color(
            parse_color(ctx.params["color"]), ctx.params["brightness"] * fade
        )
        return [color] * ctx.led_count
'''

_TEMPLATES = {
    DefinitionKind.STATE: (_STATE, "#3399FF"),
    DefinitionKind.CONTROLLED_OVERLAY: (_CONTROLLED, "#00C066"),
    DefinitionKind.TIMED_OVERLAY: (_TIMED, "#FFB347"),
    DefinitionKind.EVENT: (_EVENT, "#FF3B30"),
}

_SET_MANIFEST = """\
set_id: {set_id}
source_id: {source_id}
title: {title}
version: 1
description: Describe what belongs in this set.
"""


def init_effect_source(
    directory: str | Path,
    *,
    effect_id: str,
    source_id: str,
    kind: str = "state",
    title: str | None = None,
    class_name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Write a source directory that already validates and packs."""
    root = Path(directory).expanduser().resolve()
    if root.exists() and any(root.iterdir()) and not force:
        raise SourceError(f"{root} is not empty; pass force to write into it anyway")

    resolved_kind = parse_kind(kind)
    template, color = _TEMPLATES[resolved_kind]
    name = class_name or _class_name(effect_id)
    display = title or effect_id.replace("_", " ").title()

    root.mkdir(parents=True, exist_ok=True)
    (root / "effect.yaml").write_text(
        _MANIFEST.format(source_id=source_id, class_name=name), encoding="utf-8"
    )
    (root / "effect.py").write_text(
        template.format(class_name=name, effect_id=effect_id, title=display, color=color),
        encoding="utf-8",
    )
    (root / "presets.yaml").write_text(
        _PRESETS.format(effect_id=effect_id, title=display, color=color), encoding="utf-8"
    )
    return {
        "ok": True,
        "kind": resolved_kind.value,
        "path": str(root),
        "effect_id": effect_id,
        "source_id": source_id,
        "entry_class": name,
    }


def init_effect_set_source(
    directory: str | Path,
    *,
    set_id: str,
    source_id: str,
    title: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(directory).expanduser().resolve()
    if root.exists() and any(root.iterdir()) and not force:
        raise SourceError(f"{root} is not empty; pass force to write into it anyway")

    root.mkdir(parents=True, exist_ok=True)
    (root / "effects").mkdir(exist_ok=True)
    (root / "set.yaml").write_text(
        _SET_MANIFEST.format(set_id=set_id, source_id=source_id, title=title or set_id),
        encoding="utf-8",
    )
    return {"ok": True, "kind": "set", "path": str(root), "set_id": set_id, "source_id": source_id}


__all__ = ["init_effect_set_source", "init_effect_source", "parse_kind"]
