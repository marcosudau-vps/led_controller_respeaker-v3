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


class InitEvent(BaseEffect):
    """Starting up: the ring fills, then flashes once."""

    definition = EventDefinition(
        id="init_event",
        title="Initialising",
        description="Announces that the device has started.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#3399FF",
                description="Fill colour.",
            ),
            "secondary_color": ParamDefinition(
                name="secondary_color", type=ParamType.COLOR, default="#FFFFFF",
                description="Colour of the closing flash.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.95,
                minimum=0.0, maximum=1.0, description="Peak brightness.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=1400,
                minimum=1, maximum=10_000, unit="ms",
                description="How long the whole sequence takes.",
            ),
        },
        color_model=ColorModel.DUAL,
        composition=CompositionMode.OPAQUE,
        tags=("smartspeaker", "event", "startup"),
    )

    #: Share of the duration spent filling, before the flash.
    FILL_SHARE = 0.75

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0
        brightness = ctx.params["brightness"]

        if progress >= self.FILL_SHARE:
            flash = 1.0 - (progress - self.FILL_SHARE) / (1.0 - self.FILL_SHARE)
            color = scale_color(
                parse_color(ctx.params["secondary_color"]), brightness * flash
            )
            return [color] * ctx.led_count

        lit = int(round((progress / self.FILL_SHARE) * ctx.led_count))
        color = scale_color(parse_color(ctx.params["color"]), brightness)
        # Opaque: unfilled positions are black, not transparent.
        return [color if index < lit else 0 for index in range(ctx.led_count)]
