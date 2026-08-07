from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    StateSlot,
    parse_color,
    scale_color,
)


class RotatingSegment(BaseEffect):
    """A lit arc travelling around the ring.

    Shows the two things a directional animation needs: a position derived from
    elapsed time, and a ``reverse`` flag that only flips direction. The segment
    length is clamped to the ring, so the same definition behaves on five LEDs
    and on twenty-four.
    """

    definition = StateDefinition(
        id="rotating_segment",
        title="Rotating Segment",
        description="Moves a lit segment around the ring at a steady pace.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#3399FF",
                description="Segment colour.",
            ),
            "background_color": ParamDefinition(
                name="background_color", type=ParamType.COLOR, nullable=True, default="#000000",
                description=(
                    "Colour behind the segment. Null leaves those positions "
                    "untouched so a lower layer stays visible."
                ),
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.85,
                minimum=0.0, maximum=1.0, description="Segment brightness.",
            ),
            "segment_length": ParamDefinition(
                name="segment_length", type=ParamType.INT, default=3,
                minimum=1, maximum=64, unit="count",
                description="How many LEDs the segment covers.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=1.0,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the designed rotation speed.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Rotate the other way.",
            ),
        },
        color_model=ColorModel.MONO,
        # Transparent because a permitted configuration can yield: setting
        # background_color to null leaves the unlit positions untouched. The
        # declaration describes what the definition may do, not what one
        # particular configuration happens to do, so the permissive value is the
        # honest one even though the default background is solid black.
        composition=CompositionMode.TRANSPARENT,
        animated=True,
        directional=True,
        slots=(StateSlot.PRIMARY,),
        tags=("core", "state", "animated", "directional"),
    )

    #: One full turn at speed 1.0.
    BASE_PERIOD_S = 2.4

    def render(self, ctx: RenderContext) -> list[int | None]:
        led_count = ctx.led_count
        background = ctx.params["background_color"]
        # None keeps the layers below; a colour — black included — hides them.
        fill = None if background is None else parse_color(background)
        frame: list[int | None] = [fill] * led_count

        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        if ctx.params["reverse"]:
            phase = 1.0 - phase
        head = int(phase * led_count) % led_count

        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        length = min(ctx.params["segment_length"], led_count)
        for offset in range(length):
            frame[(head + offset) % led_count] = color
        return frame
