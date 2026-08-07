from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    ParamDefinition,
    ParamType,
    RenderContext,
    parse_color,
    scale_color,
)


class LoadingSpinnerOverlay(BaseEffect):
    """A spinner that runs until its channel is cleared.

    Controlled without runtime inputs: the caller decides when it starts and
    when it stops, and nothing is pushed in between. Opaque on purpose — a
    spinner is meant to take over the ring for the duration of the task.
    """

    definition = ControlledOverlayDefinition(
        id="loading_spinner",
        title="Loading Spinner",
        description="Rotates a bright segment over a dark ring until it is cleared.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00D0D0",
                description="Segment colour.",
            ),
            "secondary_color": ParamDefinition(
                name="secondary_color", type=ParamType.COLOR, default="#001018",
                description="Ring colour behind the segment.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.90,
                minimum=0.0, maximum=1.0, description="Segment brightness.",
            ),
            "segment_length": ParamDefinition(
                name="segment_length", type=ParamType.INT, default=3,
                minimum=1, maximum=24, unit="count",
                description="How many LEDs the segment covers.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.85,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the rotation speed.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Rotate the other way.",
            ),
        },
        color_model=ColorModel.DUAL,
        composition=CompositionMode.OPAQUE,
        animated=True,
        directional=True,
        tags=("smartspeaker", "overlay", "controlled", "loading"),
    )

    BASE_PERIOD_S = 1.6

    def render(self, ctx: RenderContext) -> list[int | None]:
        led_count = ctx.led_count
        # Opaque: every position gets a colour, none is left as None.
        frame: list[int | None] = [parse_color(ctx.params["secondary_color"])] * led_count

        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        if ctx.params["reverse"]:
            phase = 1.0 - phase
        head = int(phase * led_count) % led_count

        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        for step in range(min(ctx.params["segment_length"], led_count)):
            frame[(head + step) % led_count] = color
        return frame
