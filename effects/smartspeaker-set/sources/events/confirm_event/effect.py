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


class ConfirmEvent(BaseEffect):
    """Understood: a brief, soft green acknowledgement.

    Shorter and quieter than success. Confirming that something was heard is a
    smaller statement than reporting that it worked.
    """

    definition = EventDefinition(
        id="confirm_event",
        title="Confirmed",
        description="Acknowledges that an input was accepted.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00C066",
                description="Pulse colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.80,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=380,
                minimum=1, maximum=10_000, unit="ms",
                description="How long the pulse lasts.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.OPAQUE,
        tags=("smartspeaker", "event", "positive"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0
        level = ctx.params["brightness"] * math.sin(math.pi * progress)
        return [scale_color(parse_color(ctx.params["color"]), level)] * ctx.led_count
