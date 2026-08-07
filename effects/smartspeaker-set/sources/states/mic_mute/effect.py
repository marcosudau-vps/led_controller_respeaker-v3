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


class MicMuteState(BaseEffect):
    """Microphone muted: a static, four-fold symmetric red marker.

    Deliberately still. A muted microphone is a condition, not an activity, and
    anything moving would suggest the device is doing something.
    """

    definition = StateDefinition(
        id="mic_mute",
        title="Microphone Muted",
        description="The microphone is switched off.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FF0000",
                description="Marker colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.90,
                minimum=0.0, maximum=1.0, description="Marker brightness.",
            ),
            "segment_length": ParamDefinition(
                name="segment_length", type=ParamType.INT, default=1,
                minimum=1, maximum=6, unit="count",
                description="How many LEDs each of the four markers covers.",
            ),
        },
        color_model=ColorModel.MONO,
        slots=(StateSlot.PRIMARY,),
        tags=("smartspeaker", "state", "muted"),
    )

    MARKERS = 4

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame: list[int | None] = [0] * ctx.led_count
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        length = min(ctx.params["segment_length"], ctx.led_count)
        markers = min(self.MARKERS, ctx.led_count)
        for base in evenly_spaced_positions(markers, ctx.led_count):
            for step in range(length):
                frame[(base + step) % ctx.led_count] = color
        return frame
