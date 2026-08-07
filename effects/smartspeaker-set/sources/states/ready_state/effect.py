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


class ReadyState(BaseEffect):
    """Idle and available: a slow green breath over the whole ring."""

    definition = StateDefinition(
        id="ready_state",
        title="Ready",
        description="The device is idle and waiting to be addressed.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00C066",
                description="Ring colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.55,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "min_brightness": ParamDefinition(
                name="min_brightness", type=ParamType.FLOAT, default=0.16,
                minimum=0.0, maximum=1.0, description="Brightness at the bottom of a breath.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.45,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the breathing cadence.",
            ),
        },
        color_model=ColorModel.MONO,
        animated=True,
        slots=(StateSlot.PRIMARY,),
        tags=("smartspeaker", "state", "idle"),
    )

    BASE_PERIOD_S = 4.0

    def render(self, ctx: RenderContext) -> list[int | None]:
        peak = ctx.params["brightness"]
        floor = min(ctx.params["min_brightness"], peak)
        period = self.BASE_PERIOD_S / ctx.params["speed"]
        wave = 0.5 - 0.5 * math.cos(2.0 * math.pi * ((ctx.elapsed % period) / period))
        level = floor + (peak - floor) * wave
        return [scale_color(parse_color(ctx.params["color"]), level)] * ctx.led_count
