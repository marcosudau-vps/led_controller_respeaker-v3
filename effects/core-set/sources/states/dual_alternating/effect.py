import math

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


class DualAlternating(BaseEffect):
    """Two colours on alternating LEDs, cross-fading into each other.

    The reference for the ``dual`` colour model: two equally important colours,
    neither of them a background. The model requires both ``color`` and
    ``secondary_color``, so a definition cannot claim to be dual and then ship
    only one.
    """

    definition = StateDefinition(
        id="dual_alternating",
        title="Dual Alternating",
        description="Alternates two colours around the ring and fades between them.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FFB347",
                description="First colour.",
            ),
            "secondary_color": ParamDefinition(
                name="secondary_color", type=ParamType.COLOR, default="#4A1E00",
                description="Second colour, equal in standing to the first.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.85,
                minimum=0.0, maximum=1.0, description="Brightness factor.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.45,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the designed cross-fade cadence.",
            ),
        },
        color_model=ColorModel.DUAL,
        animated=True,
        slots=(StateSlot.PRIMARY, StateSlot.BACKGROUND),
        restorable=True,
        tags=("core", "state", "animated", "dual"),
    )

    BASE_PERIOD_S = 3.2

    def render(self, ctx: RenderContext) -> list[int | None]:
        first = parse_color(ctx.params["color"])
        second = parse_color(ctx.params["secondary_color"])
        brightness = ctx.params["brightness"]

        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        mix = 0.5 - 0.5 * math.cos(2.0 * math.pi * phase)

        even = scale_color(blend(first, second, mix), brightness)
        odd = scale_color(blend(second, first, mix), brightness)
        return [even if index % 2 == 0 else odd for index in range(ctx.led_count)]
