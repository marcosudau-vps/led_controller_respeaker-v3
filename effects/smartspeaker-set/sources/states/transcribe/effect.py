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


class TranscribeState(BaseEffect):
    """Turning speech into text: a bright head with a short trailing tail."""

    definition = StateDefinition(
        id="transcribe",
        title="Transcribing",
        description="The device is converting captured speech into text.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#3399FF",
                description="Head colour; the tail is the same colour, dimmed.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.95,
                minimum=0.0, maximum=1.0, description="Head brightness.",
            ),
            "trail_length": ParamDefinition(
                name="trail_length", type=ParamType.INT, default=4,
                minimum=1, maximum=24, unit="count",
                description="How many LEDs the tail spans.",
            ),
            "falloff": ParamDefinition(
                name="falloff", type=ParamType.FLOAT, default=0.62,
                minimum=0.05, maximum=1.0, unit="ratio",
                description="How quickly the tail fades; lower is sharper.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=1.35,
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
        tags=("smartspeaker", "state", "transcribe"),
    )

    BASE_PERIOD_S = 2.0

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame: list[int | None] = [0] * ctx.led_count
        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        reverse = ctx.params["reverse"]
        if reverse:
            phase = 1.0 - phase
        head = int(phase * ctx.led_count) % ctx.led_count

        base = parse_color(ctx.params["color"])
        brightness = ctx.params["brightness"]
        falloff = ctx.params["falloff"]
        length = min(ctx.params["trail_length"], ctx.led_count)

        for step in range(length):
            level = brightness * (falloff**step)
            index = (head + step) % ctx.led_count if reverse else (head - step) % ctx.led_count
            frame[index] = scale_color(base, level)
        return frame
