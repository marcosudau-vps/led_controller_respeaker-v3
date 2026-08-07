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


class ErrorEvent(BaseEffect):
    """Something failed: fast red pulses, optionally in two bursts.

    Declares a higher default priority so a failure moves ahead of routine
    signals already waiting. It still does not interrupt whatever is currently
    showing — priority orders the queue, it does not preempt.
    """

    definition = EventDefinition(
        id="error_event",
        title="Error",
        description="Announces that something went wrong.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FF0000",
                description="Pulse colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "pulse_count": ParamDefinition(
                name="pulse_count", type=ParamType.INT, default=3,
                minimum=1, maximum=10, unit="count",
                description="Pulses per burst.",
            ),
            "repeat_count": ParamDefinition(
                name="repeat_count", type=ParamType.INT, default=1,
                minimum=1, maximum=5, unit="count",
                description="How many bursts, separated by a short gap.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=900,
                minimum=1, maximum=10_000, unit="ms",
                description="How long the whole sequence takes.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.OPAQUE,
        default_priority=800,
        tags=("smartspeaker", "event", "negative"),
    )

    #: Share of each burst spent dark, so repeats read as separate.
    GAP_SHARE = 0.25

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0

        bursts = ctx.params["repeat_count"]
        within = (progress * bursts) % 1.0
        if within > (1.0 - self.GAP_SHARE):
            return ctx.blank_frame()

        active = within / (1.0 - self.GAP_SHARE)
        level = ctx.params["brightness"] * abs(
            math.sin(math.pi * active * ctx.params["pulse_count"])
        )
        return [scale_color(parse_color(ctx.params["color"]), level)] * ctx.led_count
