from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    InputMode,
    InputSamplingPolicy,
    ParamDefinition,
    ParamType,
    RenderContext,
    parse_color,
    positions_for_angle,
    scale_color,
)


class DirectionIndicator(BaseEffect):
    """Marks the direction a sound came from.

    This package contains no USB code, no device handling and no reconnect
    logic. It declares that it pulls the capability ``doa`` and reads two
    validated values; the controller owns the device, the polling rate and the
    cache. Ten of these running at once would still produce one hardware read
    per interval.

    ``doa`` names what is needed — direction data — not who supplies it. The
    reSpeaker and the simulator both offer it, so this definition runs unchanged
    against either, and against whatever else offers it later. The bearing
    arrives already expressed on the ring: how the microphone array is rotated
    against the LEDs is the device's business, recorded once by calibrating it.

    A direction is as likely to fall between two LEDs as on one, so it is read
    on a scale of half-LED steps — 15° on a twelve-LED ring. Between two, both
    are lit at half brightness, which reads as "there, in the middle" rather
    than rounding to whichever LED happened to be nearer.

    The whole effect is transparent: every position it does not mark stays
    ``None``, so the state underneath shows through untouched.
    """

    definition = ControlledOverlayDefinition(
        id="direction_indicator",
        title="Direction Indicator",
        description="Marks the detected direction of arrival on a single LED.",
        parameter_schema={
            "color": ParamDefinition(
                name="color", type=ParamType.COLOR, default="#00C066",
                description="Marker colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0,
                minimum=0.0, maximum=1.0, description="Marker brightness.",
            ),
            "angle_offset_deg": ParamDefinition(
                name="angle_offset_deg", type=ParamType.FLOAT, default=0.0,
                minimum=-180.0, maximum=180.0, unit="deg",
                description="Physical offset between the microphone array and LED zero.",
            ),
            "reverse": ParamDefinition(
                name="reverse", type=ParamType.BOOL, default=False,
                description="Mirror the measured direction.",
            ),
        },
        runtime_inputs={
            "direction_deg": ParamDefinition(
                name="direction_deg", type=ParamType.ANGLE_DEG,
                required=True, nullable=True, unit="deg",
                aliases=("direction",),
                description="Measured direction of arrival.",
            ),
            "detection_state": ParamDefinition(
                name="detection_state", type=ParamType.ENUM,
                enum_values=("none", "sound", "speech"), default="none",
                description="Voice activity reported alongside the angle.",
            ),
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
        directional=True,
        sampling=InputSamplingPolicy(
            mode=InputMode.PULL,
            provider_id="doa",
            interval_ms=0,
        ),
        tags=("core", "overlay", "controlled", "doa"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        frame = ctx.transparent_frame()

        direction = ctx.inputs["direction_deg"]
        if direction is None or ctx.inputs["detection_state"] not in {"sound", "speech"}:
            # Silence is a valid, healthy reading — not a failure. Showing
            # nothing is the honest response to it.
            return frame

        # Mirror the reading, then rotate it. Rotating first would mirror the
        # rotation along with the angle. Both are deliberate adjustments to the
        # picture; the device's own mounting angle is already accounted for.
        measured = direction % 360.0
        if ctx.params["reverse"]:
            measured = (-measured) % 360.0
        aimed = measured + ctx.params["angle_offset_deg"]

        marked = positions_for_angle(aimed, ctx.led_count)
        # Two LEDs share the marker's brightness rather than each carrying it,
        # so a direction between them does not read as twice as much light as
        # one pointing straight at an LED.
        brightness = ctx.params["brightness"] / len(marked)
        color = scale_color(parse_color(ctx.params["color"]), brightness)
        for position in marked:
            frame[position] = color
        return frame
