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


class WaitingState(BaseEffect):
    """Waiting on something: one slow dot circling an otherwise dark ring."""

    definition = StateDefinition(
        id="waiting",
        title="Waiting",
        description="The device is waiting for an external step to finish.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00D0D0",
                description="Dot colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.70,
                minimum=0.0, maximum=1.0, description="Dot brightness.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.28,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the rotation speed.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Rotate the other way.",
            ),
        },
        color_model=ColorModel.MONO,
        animated=True,
        directional=True,
        slots=(StateSlot.PRIMARY,),
        tags=("smartspeaker", "state", "waiting"),
    )

    BASE_PERIOD_S = 3.0

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame: list[int | None] = [0] * ctx.led_count
        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        if ctx.params["reverse"]:
            phase = 1.0 - phase
        index = int(phase * ctx.led_count) % ctx.led_count
        frame[index] = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        return frame
