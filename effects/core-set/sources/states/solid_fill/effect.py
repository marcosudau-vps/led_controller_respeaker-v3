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


class SolidFill(BaseEffect):
    """One colour on every LED — the simplest complete definition there is.

    Worth reading first: it shows the whole shape of a package. The schema
    declares what may be set, the colour model ties ``color`` and ``brightness``
    together, and render does nothing but turn canonical values into pixels.
    """

    definition = StateDefinition(
        id="solid_fill",
        title="Solid Fill",
        description="Fills the ring with a single colour.",
        parameter_schema={
            "color": ParamDefinition(
                name="color",
                type=ParamType.COLOR,
                default="#3399FF",
                description="Ring colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness",
                type=ParamType.FLOAT,
                default=0.8,
                minimum=0.0,
                maximum=1.0,
                description="Brightness factor.",
            ),
        },
        color_model=ColorModel.MONO,
        slots=(StateSlot.PRIMARY, StateSlot.BACKGROUND),
        restorable=True,
        tags=("core", "state", "static"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        return [color] * ctx.led_count
