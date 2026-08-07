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


class LevelMeter(BaseEffect):
    """A bar filled from a value an application keeps pushing.

    The push counterpart to the direction indicator. Whoever owns the value
    sends it; the engine only tracks whether it is still arriving. When it stops
    for longer than the grace period the input reads null, and this definition
    decides what that looks like — here, nothing at all.
    """

    definition = ControlledOverlayDefinition(
        id="level_meter",
        title="Level Meter",
        description="Fills part of the ring in proportion to a value supplied at runtime.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00C0FF",
                description="Bar colour.",
            ),
            "background_color": ParamDefinition(
                name="background_color", type=ParamType.COLOR, nullable=True, default=None,
                description=(
                    "Colour of the unfilled part. Null leaves it transparent so the "
                    "state below stays visible; black would hide it."
                ),
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.9,
                minimum=0.0, maximum=1.0, description="Bar brightness.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Fill the other way round the ring.",
            ),
        },
        runtime_inputs={
            "progress": ParamDefinition(
                name="progress", type=ParamType.FLOAT,
                required=True, nullable=True,
                minimum=0.0, maximum=100.0, unit="percent",
                description="How full the bar is, from 0 to 100.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        directional=True,
        tags=("core", "overlay", "controlled", "progress"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        background = ctx.params["background_color"]
        fill = None if background is None else parse_color(background)
        frame: list[int | None] = [fill] * ctx.led_count

        progress = ctx.inputs["progress"]
        if progress is None:
            return frame

        lit = int(round((progress / 100.0) * ctx.led_count))
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        for step in range(lit):
            index = ctx.led_count - 1 - step if ctx.params["reverse"] else step
            frame[index % ctx.led_count] = color
        return frame
