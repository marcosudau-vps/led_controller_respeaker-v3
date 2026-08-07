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


class PaletteCycle(BaseEffect):
    """An ordered palette laid around the ring and rotated.

    The reference for the ``palette`` colour model. The list length is declared
    in the schema, so a caller cannot pass one colour to something that needs a
    sequence, and the renderer never has to check.
    """

    definition = StateDefinition(
        id="palette_cycle",
        title="Palette Cycle",
        description="Repeats an ordered palette around the ring and rotates it.",
        parameter_schema={
            "colors": ParamDefinition(
                name="colors",
                type=ParamType.COLOR_LIST,
                default=["#FF0040", "#FF8000", "#FFE000", "#00C066", "#0080FF", "#8000FF"],
                minimum=2,
                maximum=32,
                unit="count",
                description="Ordered palette, repeated around the ring.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.7,
                minimum=0.0, maximum=1.0, description="Brightness factor.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.6,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the designed rotation speed.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Rotate the other way.",
            ),
        },
        color_model=ColorModel.PALETTE,
        animated=True,
        directional=True,
        slots=(StateSlot.PRIMARY,),
        tags=("core", "state", "animated", "palette"),
    )

    BASE_PERIOD_S = 4.0

    def render(self, ctx: RenderContext) -> list[int | None]:
        palette = [parse_color(value) for value in ctx.params["colors"]]
        brightness = ctx.params["brightness"]

        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        if ctx.params["reverse"]:
            phase = 1.0 - phase
        offset = int(phase * len(palette))

        return [
            scale_color(palette[(index + offset) % len(palette)], brightness)
            for index in range(ctx.led_count)
        ]
