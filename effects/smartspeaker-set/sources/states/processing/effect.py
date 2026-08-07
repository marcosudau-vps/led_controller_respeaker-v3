from lefx.sdk import (
    BaseEffect,
    ColorModel,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    StateSlot,
    evenly_spaced_positions,
    parse_color,
    scale_color,
)


class ProcessingState(BaseEffect):
    """Working on it: several evenly spaced dots circling together."""

    definition = StateDefinition(
        id="processing",
        title="Processing",
        description="The device is working on a request.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#3399FF",
                description="Dot colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.85,
                minimum=0.0, maximum=1.0, description="Dot brightness.",
            ),
            "point_count": ParamDefinition(
                name="point_count", type=ParamType.INT, default=3,
                minimum=1, maximum=12, unit="count",
                description="How many dots travel around the ring.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.90,
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
        tags=("smartspeaker", "state", "processing"),
    )

    BASE_PERIOD_S = 2.0

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame: list[int | None] = [0] * ctx.led_count
        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        if ctx.params["reverse"]:
            phase = 1.0 - phase
        offset = int(phase * ctx.led_count)

        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        count = min(ctx.params["point_count"], ctx.led_count)
        for base in evenly_spaced_positions(count, ctx.led_count):
            frame[(base + offset) % ctx.led_count] = color
        return frame
