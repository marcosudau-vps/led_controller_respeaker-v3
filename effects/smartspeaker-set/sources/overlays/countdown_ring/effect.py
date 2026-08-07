import math

from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ParamDefinition,
    ParamType,
    RenderContext,
    TimedOverlayDefinition,
    blend,
    parse_color,
    scale_color,
)


class CountdownRingOverlay(BaseEffect):
    """A ring that empties as its time runs out, warming from green to red.

    Timed rather than controlled because the countdown owns its own clock: the
    duration is fixed when it starts and the engine removes it at the end. A
    countdown whose remaining time is owned by an application elsewhere would be
    a controlled overlay instead — the shape on screen is the same, the contract
    is not.
    """

    definition = TimedOverlayDefinition(
        id="countdown_ring",
        title="Countdown Ring",
        description="Empties the ring over a fixed duration, shifting colour as it goes.",
        parameter_schema={
            "colors": ParamDefinition(
                name="colors",
                type=ParamType.COLOR_LIST,
                default=["#00C066", "#FFE000", "#FF0000"],
                minimum=2,
                maximum=8,
                unit="count",
                description="Colours passed through from start to finish.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.90,
                minimum=0.0, maximum=1.0, description="Ring brightness.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=10_000,
                minimum=1, maximum=3_600_000, unit="ms",
                description="How long the countdown runs.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Empty the ring the other way round.",
            ),
        },
        color_model=ColorModel.PALETTE,
        composition=CompositionMode.TRANSPARENT,
        directional=True,
        supports_duration_override=True,
        tags=("smartspeaker", "overlay", "timed", "countdown"),
    )

    #: Below this share of the time remaining, the rest starts pulsing.
    URGENT_BELOW = 0.2

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        remaining = max(0.0, 1.0 - (ctx.elapsed / total)) if total > 0 else 0.0

        brightness = ctx.params["brightness"]
        if remaining < self.URGENT_BELOW:
            # The last stretch pulses, so the end is noticeable without sound.
            pulse = 0.6 + 0.4 * abs(math.sin(ctx.elapsed * math.pi * 3.0))
            brightness *= pulse

        color = scale_color(self._colour_at(ctx.params["colors"], 1.0 - remaining), brightness)
        lit = int(round(remaining * ctx.led_count))

        frame = ctx.transparent_frame()
        for step in range(lit):
            index = ctx.led_count - 1 - step if ctx.params["reverse"] else step
            frame[index % ctx.led_count] = color
        return frame

    @staticmethod
    def _colour_at(colors: list[str], position: float) -> int:
        stops = [parse_color(value) for value in colors]
        scaled = min(1.0, max(0.0, position)) * (len(stops) - 1)
        left = min(int(scaled), len(stops) - 2)
        return blend(stops[left], stops[left + 1], scaled - left)
