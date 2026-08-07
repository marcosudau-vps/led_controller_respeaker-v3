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


class RejectEvent(BaseEffect):
    """Refused: a hard red hit that drops away and twitches once more."""

    definition = EventDefinition(
        id="reject_event",
        title="Rejected",
        description="Announces that an input was refused.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#FF0000",
                description="Pulse colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=460,
                minimum=1, maximum=10_000, unit="ms",
                description="How long the sequence takes.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.OPAQUE,
        default_priority=750,
        tags=("smartspeaker", "event", "negative"),
    )

    #: The main hit occupies the first stretch; an echo follows after a gap.
    HIT_SHARE = 0.45
    ECHO_FROM = 0.65

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0
        peak = ctx.params["brightness"]

        if progress <= self.HIT_SHARE:
            # Full strength immediately, then a fast decay — the shape of a "no".
            level = peak * (1.0 - progress / self.HIT_SHARE)
        elif progress >= self.ECHO_FROM:
            echo = (progress - self.ECHO_FROM) / (1.0 - self.ECHO_FROM)
            level = peak * 0.35 * (1.0 - echo)
        else:
            level = 0.0

        return [scale_color(parse_color(ctx.params["color"]), level)] * ctx.led_count
