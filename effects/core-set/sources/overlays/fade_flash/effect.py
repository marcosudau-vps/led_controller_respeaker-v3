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


class FadeFlash(BaseEffect):
    """A brief fade-out over whatever is showing.

    A timed overlay knows its whole run at activation: start and length are
    fixed, there is no channel and nothing updates it. The engine removes it
    when the time is up — this definition sends no completion signal, because
    there is none to send.
    """

    definition = TimedOverlayDefinition(
        id="fade_flash",
        title="Fade Flash",
        description="Briefly lights the ring and fades out over its duration.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FFFFFF",
                description="Flash colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.9,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=900,
                minimum=1, maximum=60_000, unit="ms",
                description="How long the flash lasts.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        supports_duration_override=True,
        tags=("core", "overlay", "timed"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        remaining = 1.0 - min(1.0, ctx.elapsed / total)
        if remaining <= 0.0:
            return ctx.transparent_frame()
        color = scale_color(
            parse_color(ctx.params["color"]), ctx.params["brightness"] * remaining
        )
        return [color] * ctx.led_count
