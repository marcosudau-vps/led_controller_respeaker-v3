import math

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


class ThinkingState(BaseEffect):
    """Composing an answer: a wide, softly tapering sweep circling the ring."""

    definition = StateDefinition(
        id="thinking",
        title="Thinking",
        description="The device is generating a response.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#8000FF",
                description="Sweep colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.76,
                minimum=0.0, maximum=1.0, description="Brightness at the centre of the sweep.",
            ),
            "width": ParamDefinition(
                name="width", type=ParamType.INT, default=5,
                minimum=1, maximum=24, unit="count",
                description="How many LEDs the sweep spans.",
            ),
            "falloff": ParamDefinition(
                name="falloff", type=ParamType.FLOAT, default=0.55,
                minimum=0.05, maximum=1.0, unit="ratio",
                description="How softly the sweep tapers at its edges.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=0.48,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the sweep speed.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Sweep the other way.",
            ),
        },
        color_model=ColorModel.MONO,
        animated=True,
        directional=True,
        slots=(StateSlot.PRIMARY,),
        tags=("smartspeaker", "state", "thinking"),
    )

    BASE_PERIOD_S = 3.0

    def render(self, ctx: RenderContext) -> list[int | None]:
        led_count = ctx.led_count
        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        if ctx.params["reverse"]:
            phase = 1.0 - phase
        centre = phase * led_count

        base = parse_color(ctx.params["color"])
        brightness = ctx.params["brightness"]
        half = max(0.5, min(ctx.params["width"], led_count) / 2.0)
        falloff = ctx.params["falloff"]

        frame: list[int | None] = []
        for index in range(led_count):
            # Shortest distance around the ring, so the sweep wraps smoothly.
            raw = abs(index - centre)
            distance = min(raw, led_count - raw)
            if distance >= half:
                frame.append(0)
                continue
            taper = math.cos((distance / half) * (math.pi / 2.0)) ** (1.0 / falloff)
            frame.append(scale_color(base, brightness * taper))
        return frame
