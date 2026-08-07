import math

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


class BreathingRing(BaseEffect):
    """A whole-ring breath, driven by the clock rather than by frame counting.

    ``speed`` is a multiplier on the designed cadence, not a frame rate. The
    engine may render at any rate it likes and one breath still takes the same
    wall-clock time, because the phase comes from ``ctx.elapsed``.
    """

    definition = StateDefinition(
        id="breathing_ring",
        title="Breathing Ring",
        description="Fades the whole ring in and out at a steady pace.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00C066",
                description="Ring colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.75,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "min_brightness": ParamDefinition(
                name="min_brightness", type=ParamType.FLOAT, default=0.15,
                minimum=0.0, maximum=1.0, description="Brightness at the bottom of a breath.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.5,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the designed breathing cadence.",
            ),
        },
        color_model=ColorModel.MONO,
        animated=True,
        slots=(StateSlot.PRIMARY, StateSlot.BACKGROUND),
        restorable=True,
        tags=("core", "state", "animated"),
    )

    #: One full breath at speed 1.0.
    BASE_PERIOD_S = 4.0

    def render(self, ctx: RenderContext) -> list[int | None]:
        peak = ctx.params["brightness"]
        floor = min(ctx.params["min_brightness"], peak)
        period = self.BASE_PERIOD_S / ctx.params["speed"]

        phase = (ctx.elapsed % period) / period
        wave = 0.5 - 0.5 * math.cos(2.0 * math.pi * phase)
        level = floor + (peak - floor) * wave

        color = scale_color(parse_color(ctx.params["color"]), level)
        return [color] * ctx.led_count
