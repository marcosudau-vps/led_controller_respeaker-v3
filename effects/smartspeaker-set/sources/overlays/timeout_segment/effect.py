from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ParamDefinition,
    ParamType,
    RenderContext,
    TimedOverlayDefinition,
    parse_color,
    scale_color,
)


class TimeoutSegmentOverlay(BaseEffect):
    """A segment shrinking quietly to nothing while a timeout runs down."""

    definition = TimedOverlayDefinition(
        id="timeout_segment",
        title="Timeout Segment",
        description="Shrinks a segment to nothing over a fixed duration.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FFC65C",
                description="Segment colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.72,
                minimum=0.0, maximum=1.0, description="Segment brightness.",
            ),
            "segment_length": ParamDefinition(
                name="segment_length", type=ParamType.INT, default=6,
                minimum=1, maximum=64, unit="count",
                description="How many LEDs the segment covers at the start.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=5_000,
                minimum=1, maximum=3_600_000, unit="ms",
                description="How long the timeout runs.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Shrink from the other end.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        directional=True,
        supports_duration_override=True,
        tags=("smartspeaker", "overlay", "timed", "timeout"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        remaining = max(0.0, 1.0 - (ctx.elapsed / total)) if total > 0 else 0.0

        start_length = min(ctx.params["segment_length"], ctx.led_count)
        lit = int(round(remaining * start_length))

        frame = ctx.transparent_frame()
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        for step in range(lit):
            index = ctx.led_count - 1 - step if ctx.params["reverse"] else step
            frame[index % ctx.led_count] = color
        return frame
