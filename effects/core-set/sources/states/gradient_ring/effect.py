from lefx.sdk import (
    BaseEffect,
    ColorModel,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    StateSlot,
    blend,
    parse_color,
    scale_color,
)


class GradientRing(BaseEffect):
    """A gradient wrapped around the ring.

    The reference for the ``gradient`` colour model. Stops arrive sorted, span
    zero to one, and are already canonical — the schema guarantees all three, so
    the interpolation below can be written without a single guard.
    """

    definition = StateDefinition(
        id="gradient_ring",
        title="Gradient Ring",
        description="Wraps a colour gradient around the ring.",
        parameter_schema={
            "gradient": ParamDefinition(
                name="gradient",
                type=ParamType.GRADIENT,
                default=[
                    {"at": 0.0, "color": "#0040FF"},
                    {"at": 0.5, "color": "#8000FF"},
                    {"at": 1.0, "color": "#FF0080"},
                ],
                description="Ordered colour stops from the start of the ring to its end.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.8,
                minimum=0.0, maximum=1.0, description="Brightness factor.",
            ),
        },
        color_model=ColorModel.GRADIENT,
        slots=(StateSlot.PRIMARY, StateSlot.BACKGROUND),
        restorable=True,
        tags=("core", "state", "static", "gradient"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        stops = [
            (float(stop["at"]), parse_color(stop["color"])) for stop in ctx.params["gradient"]
        ]
        brightness = ctx.params["brightness"]
        divisor = max(1, ctx.led_count - 1)

        frame: list[int | None] = []
        for index in range(ctx.led_count):
            frame.append(scale_color(self._sample(stops, index / divisor), brightness))
        return frame

    @staticmethod
    def _sample(stops: list[tuple[float, int]], position: float) -> int:
        for index in range(len(stops) - 1):
            left_at, left_color = stops[index]
            right_at, right_color = stops[index + 1]
            if position <= right_at:
                span = right_at - left_at
                mix = 0.0 if span <= 0.0 else (position - left_at) / span
                return blend(left_color, right_color, mix)
        return stops[-1][1]
