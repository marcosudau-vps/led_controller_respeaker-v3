from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    EventDefinition,
    ParamDefinition,
    ParamType,
    RenderContext,
    parse_color,
    scale_color,
)


class WakewordDetectedEvent(BaseEffect):
    """Heard you: a fast cyan flash that fades away.

    A flash rather than a live level display. An event is a closed sequence with
    no runtime inputs, so anything that had to follow the voice while it spoke
    would be a controlled overlay instead.
    """

    definition = EventDefinition(
        id="wakeword_detected",
        title="Wake Word Detected",
        description="Announces that the wake word was recognised.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00D0D0",
                description="Flash colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=300,
                minimum=1, maximum=10_000, unit="ms",
                description="How long the flash lasts.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.OPAQUE,
        default_priority=650,
        tags=("smartspeaker", "event", "wakeword"),
    )

    #: The rise is deliberately much shorter than the fall: the response has to
    #: feel immediate, the exit should not.
    ATTACK_SHARE = 0.12

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0
        peak = ctx.params["brightness"]

        if progress <= self.ATTACK_SHARE:
            level = peak * (progress / self.ATTACK_SHARE)
        else:
            level = peak * (1.0 - (progress - self.ATTACK_SHARE) / (1.0 - self.ATTACK_SHARE))

        return [scale_color(parse_color(ctx.params["color"]), level)] * ctx.led_count
