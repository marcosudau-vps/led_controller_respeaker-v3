import math

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


class PulseSignal(BaseEffect):
    """A short pulse that pushes past everything else for a moment.

    An event runs on the top layer, is always finite, and cannot be updated once
    it starts. Priority decides the order of what is waiting — it never
    interrupts what is already showing.
    """

    definition = EventDefinition(
        id="pulse_signal",
        title="Pulse Signal",
        description="A brief prioritized pulse on top of everything else.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FFB347",
                description="Pulse colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=600,
                minimum=1, maximum=10_000, unit="ms",
                description="How long the pulse lasts.",
            ),
            "pulse_count": ParamDefinition(
                name="pulse_count", type=ParamType.INT, default=2,
                minimum=1, maximum=10, unit="count",
                description="How many pulses fit into the duration.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        tags=("core", "event"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0
        wave = abs(math.sin(math.pi * progress * ctx.params["pulse_count"]))
        if wave <= 0.01:
            return ctx.transparent_frame()
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"] * wave)
        return [color] * ctx.led_count
