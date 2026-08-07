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


class WarnEvent(BaseEffect):
    """A caution: slower, softer yellow blinking than an error."""

    definition = EventDefinition(
        id="warn_event",
        title="Warning",
        description="Announces a condition that deserves attention but is not a failure.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FFE000",
                description="Pulse colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.85,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "pulse_count": ParamDefinition(
                name="pulse_count", type=ParamType.INT, default=2,
                minimum=1, maximum=10, unit="count",
                description="How many pulses fit into the duration.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=1000,
                minimum=1, maximum=10_000, unit="ms",
                description="How long the sequence takes.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.OPAQUE,
        default_priority=700,
        tags=("smartspeaker", "event", "warning"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0
        level = ctx.params["brightness"] * abs(
            math.sin(math.pi * progress * ctx.params["pulse_count"])
        )
        return [scale_color(parse_color(ctx.params["color"]), level)] * ctx.led_count
