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


class ConnectedEvent(BaseEffect):
    """Connected: one green lap with a soft tail, then gone."""

    definition = EventDefinition(
        id="connected_event",
        title="Connected",
        description="Announces that a connection was established.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00C066",
                description="Sweep colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=0.95,
                minimum=0.0, maximum=1.0, description="Head brightness.",
            ),
            "trail_length": ParamDefinition(
                name="trail_length", type=ParamType.INT, default=4,
                minimum=1, maximum=24, unit="count",
                description="How many LEDs the tail spans.",
            ),
            "duration_ms": ParamDefinition(
                name="duration_ms", type=ParamType.DURATION_MS, default=750,
                minimum=1, maximum=10_000, unit="ms",
                description="How long the lap takes.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Travel the other way.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        directional=True,
        tags=("smartspeaker", "event", "connection"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        total = ctx.params["duration_ms"] / 1000.0
        progress = min(1.0, ctx.elapsed / total) if total > 0 else 1.0
        reverse = ctx.params["reverse"]

        position = 1.0 - progress if reverse else progress
        head = int(position * ctx.led_count) % ctx.led_count

        base = parse_color(ctx.params["color"])
        # Fade the whole sweep out towards the end so it leaves quietly.
        brightness = ctx.params["brightness"] * (1.0 - progress * 0.4)
        length = min(ctx.params["trail_length"], ctx.led_count)

        frame = ctx.transparent_frame()
        for step in range(length):
            level = brightness * (1.0 - step / length)
            if level <= 0.0:
                continue
            index = (head + step) % ctx.led_count if reverse else (head - step) % ctx.led_count
            frame[index] = scale_color(base, level)
        return frame
