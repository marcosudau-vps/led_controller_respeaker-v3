import colorsys
import random

from lefx.sdk import (
    BaseEffect,
    ColorModel,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    StateSlot,
    rgb,
    scale_color,
)


class RandomSparkle(BaseEffect):
    """Sparkles drawn from a bounded HSV range, reproducibly.

    The reference for the ``random_range`` colour model. The seed is what makes
    it a definition rather than a surprise: the same configuration produces the
    same sequence every time, so a preset means something and a bug can be
    reproduced.
    """

    definition = StateDefinition(
        id="random_sparkle",
        title="Random Sparkle",
        description="Lights changing positions in colours drawn from a bounded range.",
        parameter_schema={
            "color_range": ParamDefinition(
                name="color_range",
                type=ParamType.COLOR_RANGE,
                default={
                    "hue": [180.0, 280.0],
                    "saturation": [0.6, 1.0],
                    "brightness": [0.4, 1.0],
                },
                description="HSV bounds the sparkle colours are drawn from.",
            ),
            "random_seed": ParamDefinition(
                name="random_seed", type=ParamType.INT, default=1,
                minimum=0, maximum=2_147_483_647,
                description="Same seed, same sequence.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.8,
                minimum=0.0, maximum=1.0, description="Brightness factor.",
            ),
            "density": ParamDefinition(
                name="density", type=ParamType.FLOAT, default=0.35,
                minimum=0.0, maximum=1.0, unit="ratio",
                description="Share of the ring lit at any moment.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=1.0,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on how often the pattern changes.",
            ),
        },
        color_model=ColorModel.RANDOM_RANGE,
        animated=True,
        slots=(StateSlot.PRIMARY,),
        tags=("core", "state", "animated", "random"),
    )

    #: One pattern change at speed 1.0.
    BASE_STEP_S = 0.5

    def render(self, ctx: RenderContext) -> list[int | None]:
        bounds = ctx.params["color_range"]
        step = self.BASE_STEP_S / ctx.params["speed"]
        tick = int(ctx.elapsed / step)

        # Seeding from the tick keeps render deterministic: the same moment of
        # the same run always produces the same frame.
        source = random.Random(f"{ctx.params['random_seed']}:{tick}")
        lit = round(ctx.led_count * ctx.params["density"])

        frame: list[int | None] = [0] * ctx.led_count
        for index in source.sample(range(ctx.led_count), lit):
            hue = source.uniform(*bounds["hue"]) / 360.0
            saturation = source.uniform(*bounds["saturation"])
            value = source.uniform(*bounds["brightness"])
            red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
            frame[index] = scale_color(
                rgb(red * 255.0, green * 255.0, blue * 255.0), ctx.params["brightness"]
            )
        return frame
