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


class ProgressRingOverlay(BaseEffect):
    """Progress an application owns, drawn over whatever state is running."""

    definition = ControlledOverlayDefinition(
        id="progress_ring",
        title="Progress Ring",
        description="Fills the ring in proportion to progress supplied at runtime.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00C066",
                description="Fill colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.90,
                minimum=0.0, maximum=1.0, description="Fill brightness.",
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
                description="How far along the task is, from 0 to 100.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        directional=True,
        tags=("smartspeaker", "overlay", "controlled", "progress"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame = ctx.transparent_frame()
        progress = ctx.inputs["progress"]
        if progress is None:
            # Nothing has arrived yet, or the source went quiet. Show nothing
            # rather than a misleading zero.
            return frame

        lit = int(round((progress / 100.0) * ctx.led_count))
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        for step in range(lit):
            index = ctx.led_count - 1 - step if ctx.params["reverse"] else step
            frame[index % ctx.led_count] = color
        return frame
