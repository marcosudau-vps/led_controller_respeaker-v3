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


class ReconnectMicState(BaseEffect):
    """Reconnecting to the microphone: alternating oranges breathing together."""

    definition = StateDefinition(
        id="reconnect_mic_state",
        title="Reconnecting — Microphone",
        description="The device lost its audio hardware and is retrying.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FF8000",
                description="Bright alternating colour.",
            ),
            "secondary_color": ParamDefinition(
                name="secondary_color", type=ParamType.COLOR, default="#4A2400",
                description="Dim alternating colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.88,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "min_brightness": ParamDefinition(
                name="min_brightness", type=ParamType.FLOAT, default=0.20,
                minimum=0.0, maximum=1.0, description="Brightness at the bottom of a breath.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.46,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the breathing cadence.",
            ),
        },
        color_model=ColorModel.DUAL,
        animated=True,
        slots=(StateSlot.PRIMARY,),
        tags=("smartspeaker", "state", "reconnect"),
    )

    BASE_PERIOD_S = 3.6

    def render(self, ctx: RenderContext) -> list[int | None]:
        peak = ctx.params["brightness"]
        floor = min(ctx.params["min_brightness"], peak)
        period = self.BASE_PERIOD_S / ctx.params["speed"]
        wave = 0.5 - 0.5 * math.cos(2.0 * math.pi * ((ctx.elapsed % period) / period))
        level = floor + (peak - floor) * wave

        bright = scale_color(parse_color(ctx.params["color"]), level)
        dim = scale_color(parse_color(ctx.params["secondary_color"]), level)
        return [bright if index % 2 == 0 else dim for index in range(ctx.led_count)]
