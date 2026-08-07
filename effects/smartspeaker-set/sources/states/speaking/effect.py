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


class SpeakingState(BaseEffect):
    """Speaking: symmetric segments pulsing in offset phases.

    A rhythm of its own rather than a level meter. A state has no runtime inputs
    by contract, so anything driven by live audio would have to be a controlled
    overlay — this stays self-contained on purpose.
    """

    definition = StateDefinition(
        id="speaking",
        title="Speaking",
        description="The device is playing audio back.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00A0FF",
                description="Segment colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.90,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "min_brightness": ParamDefinition(
                name="min_brightness", type=ParamType.FLOAT, default=0.18,
                minimum=0.0, maximum=1.0, description="Brightness between pulses.",
            ),
            "segment_length": ParamDefinition(
                name="segment_length", type=ParamType.INT, default=2,
                minimum=1, maximum=12, unit="count",
                description="How many LEDs each segment covers.",
            ),
            "speed": ParamDefinition(
                name="speed", type=ParamType.FLOAT, default=1.25,
                minimum=0.05, maximum=10.0, unit="multiplier",
                description="Multiplier on the pulse rate.",
            ),
        },
        color_model=ColorModel.MONO,
        animated=True,
        slots=(StateSlot.PRIMARY,),
        tags=("smartspeaker", "state", "speaking"),
    )

    BASE_PERIOD_S = 1.2

    def render(self, ctx: RenderContext) -> list[int | None]:
        led_count = ctx.led_count
        length = max(1, min(ctx.params["segment_length"], led_count))
        segments = max(1, led_count // length)

        period = self.BASE_PERIOD_S / ctx.params["speed"]
        phase = (ctx.elapsed % period) / period
        peak = ctx.params["brightness"]
        floor = min(ctx.params["min_brightness"], peak)
        base = parse_color(ctx.params["color"])

        frame: list[int | None] = [scale_color(base, floor)] * led_count
        for segment in range(segments):
            # Offsetting each segment by a fraction of the cycle is what makes
            # the ring read as rhythm rather than as one flashing block.
            offset = segment / segments
            wave = 0.5 - 0.5 * math.cos(2.0 * math.pi * ((phase + offset) % 1.0))
            level = floor + (peak - floor) * wave
            color = scale_color(base, level)
            for step in range(length):
                index = segment * length + step
                if index < led_count:
                    frame[index] = color
        return frame
