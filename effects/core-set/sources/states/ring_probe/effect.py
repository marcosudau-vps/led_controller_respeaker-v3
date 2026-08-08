from lefx.sdk import (
    BaseEffect,
    ColorModel,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    StateSlot,
    parse_color,
    positions_for_angle,
    scale_color,
)


class RingProbe(BaseEffect):
    """Lights the direction you name, so you can see where the ring thinks it is.

    Not decoration. It answers the question every other directional effect
    depends on and none of them can be used to ask: *which way is zero, and
    which LED is that?* Point it at an angle, look at the ring, and the mapping
    between the two is no longer something to be worked out from a datasheet.

    That is what makes it the instrument a calibration is performed with. The
    microphone array's zero and the LED ring's zero are not the same direction
    on a real board — on a reSpeaker the cable enters between the last LED and
    the first — and measuring the difference means being able to light a known
    bearing and speak from it.

    Angles land on the same half-LED sectors a measured direction does: one LED
    when the bearing points at one, two at half brightness when it falls between
    them. A probe that rounded to the nearest LED would be a poorer instrument
    than the thing being measured with it.
    """

    definition = StateDefinition(
        id="ring_probe",
        title="Ring Probe",
        description="Marks a named direction on the ring, for checking and calibrating it.",
        parameter_schema={
            "direction_deg": ParamDefinition(
                name="direction_deg",
                type=ParamType.ANGLE_DEG,
                default=0.0,
                unit="deg",
                description="The bearing to mark.",
            ),
            "color": ParamDefinition(
                name="color",
                type=ParamType.COLOR,
                default="#FFB000",
                description="Marker colour.",
            ),
            "brightness": ParamDefinition(
                name="brightness",
                type=ParamType.FLOAT,
                default=1.0,
                minimum=0.0,
                maximum=1.0,
                description="Marker brightness.",
            ),
            "background_color": ParamDefinition(
                name="background_color",
                type=ParamType.COLOR,
                default="#000000",
                description="What the unmarked positions show.",
            ),
        },
        color_model=ColorModel.MONO,
        slots=(StateSlot.PRIMARY,),
        # Deliberately not restorable. A probe is something you point at a
        # direction while you are looking at it, not a state to come back to
        # after a restart.
        restorable=False,
        directional=False,
        tags=("core", "state", "diagnostic", "calibration"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        background = parse_color(ctx.params["background_color"])
        frame: list[int | None] = [background] * ctx.led_count

        marked = positions_for_angle(ctx.params["direction_deg"], ctx.led_count)
        # Split between two the same way the direction indicator does, so the
        # instrument and the thing it measures show a bearing identically.
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"] / len(marked))
        for position in marked:
            frame[position] = color
        return frame
