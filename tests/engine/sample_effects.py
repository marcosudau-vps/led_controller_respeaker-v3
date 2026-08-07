"""Minimal definitions covering all four forms, shared by the engine tests.

Each one renders something trivially checkable so a test can assert on pixels
without reimplementing the effect's maths.
"""

from __future__ import annotations

from typing import Any

from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    EventDefinition,
    InputMode,
    InputSamplingPolicy,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    StateSlot,
    TimedOverlayDefinition,
    parse_color,
    position_for_angle,
)

COLOR = ParamDefinition(name="color", type=ParamType.COLOR, default="blue")
BRIGHTNESS = ParamDefinition(
    name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=1.0
)
DURATION = ParamDefinition(
    name="duration_ms", type=ParamType.DURATION_MS, default=600, minimum=1
)


class SolidState(BaseEffect):
    """An opaque state that fills the ring."""

    definition = StateDefinition(
        id="solid_state",
        title="Solid State",
        description="Fills the ring with one colour.",
        parameter_schema={"color": COLOR, "brightness": BRIGHTNESS},
        color_model=ColorModel.MONO,
        slots=(StateSlot.PRIMARY, StateSlot.BACKGROUND),
        restorable=True,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        return [parse_color(ctx.params["color"])] * ctx.led_count


class BackgroundOnlyState(BaseEffect):
    """A state that declares only the background slot."""

    definition = StateDefinition(
        id="background_only",
        title="Background Only",
        description="A state designed for the background slot alone.",
        parameter_schema={"color": COLOR, "brightness": BRIGHTNESS},
        color_model=ColorModel.MONO,
        slots=(StateSlot.BACKGROUND,),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        return [parse_color(ctx.params["color"])] * ctx.led_count


DIRECTION = ParamDefinition(
    name="direction_deg",
    type=ParamType.ANGLE_DEG,
    required=True,
    nullable=True,
    aliases=("direction",),
)


class DirectionMarker(BaseEffect):
    """A transparent controlled overlay marking one position."""

    definition = ControlledOverlayDefinition(
        id="direction_marker",
        title="Direction Marker",
        description="Marks a direction supplied at runtime.",
        parameter_schema={"color": COLOR, "brightness": BRIGHTNESS},
        runtime_inputs={"direction_deg": DIRECTION},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame = ctx.transparent_frame()
        direction = ctx.inputs["direction_deg"]
        if direction is not None:
            frame[position_for_angle(direction, ctx.led_count)] = parse_color(
                ctx.params["color"]
            )
        return frame


class PulledMarker(BaseEffect):
    """A controlled overlay whose values come from a named provider."""

    definition = ControlledOverlayDefinition(
        id="pulled_marker",
        title="Pulled Marker",
        description="Marks a direction obtained from a controller provider.",
        parameter_schema={"color": COLOR, "brightness": BRIGHTNESS},
        runtime_inputs={"direction_deg": DIRECTION},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        sampling=InputSamplingPolicy(mode=InputMode.PULL, provider_id="test_doa"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame = ctx.transparent_frame()
        direction = ctx.inputs["direction_deg"]
        if direction is not None:
            frame[position_for_angle(direction, ctx.led_count)] = parse_color(
                ctx.params["color"]
            )
        return frame


class SelfSampledMarker(BaseEffect):
    """A controlled overlay that samples its own values."""

    definition = ControlledOverlayDefinition(
        id="self_sampled_marker",
        title="Self Sampled Marker",
        description="Marks a direction the package obtains itself.",
        parameter_schema={"color": COLOR, "brightness": BRIGHTNESS},
        runtime_inputs={"direction_deg": DIRECTION},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        sampling=InputSamplingPolicy(mode=InputMode.PULL),
    )

    def __init__(self) -> None:
        self.calls = 0

    def sample_inputs(self, ctx) -> dict[str, Any]:
        self.calls += 1
        return {"direction_deg": 0.0}

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame = ctx.transparent_frame()
        direction = ctx.inputs["direction_deg"]
        if direction is not None:
            frame[position_for_angle(direction, ctx.led_count)] = parse_color(
                ctx.params["color"]
            )
        return frame


class FlashOverlay(BaseEffect):
    """A finite transparent overlay lighting the first LED."""

    definition = TimedOverlayDefinition(
        id="flash_overlay",
        title="Flash Overlay",
        description="Lights one position for a fixed time.",
        parameter_schema={"color": COLOR, "brightness": BRIGHTNESS, "duration_ms": DURATION},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        supports_duration_override=True,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame = ctx.transparent_frame()
        frame[0] = parse_color(ctx.params["color"])
        return frame


class PulseEvent(BaseEffect):
    """A finite transparent event lighting the last LED."""

    definition = EventDefinition(
        id="pulse_event",
        title="Pulse Event",
        description="A short prioritized signal.",
        parameter_schema={"color": COLOR, "brightness": BRIGHTNESS, "duration_ms": DURATION},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame = ctx.transparent_frame()
        frame[-1] = parse_color(ctx.params["color"])
        return frame


class CriticalEvent(BaseEffect):
    """An event that declares a higher default priority."""

    definition = EventDefinition(
        id="critical_event",
        title="Critical Event",
        description="A signal that jumps the queue.",
        parameter_schema={"color": COLOR, "brightness": BRIGHTNESS, "duration_ms": DURATION},
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        default_priority=900,
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame = ctx.transparent_frame()
        frame[-1] = parse_color(ctx.params["color"])
        return frame


ALL_EFFECTS = (
    SolidState,
    BackgroundOnlyState,
    DirectionMarker,
    PulledMarker,
    SelfSampledMarker,
    FlashOverlay,
    PulseEvent,
    CriticalEvent,
)
