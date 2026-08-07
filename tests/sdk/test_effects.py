"""The render contract: what an effect receives and what it must return."""

from __future__ import annotations

import pytest

from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    InputContext,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    parse_color,
    position_for_angle,
    resolve_configuration,
    scale_color,
)

SOLID = StateDefinition(
    id="solid",
    title="Solid",
    description="Fills the ring with one colour.",
    parameter_schema={
        "color": ParamDefinition(name="color", type=ParamType.COLOR, default="blue"),
        "brightness": ParamDefinition(
            name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=1.0
        ),
    },
    color_model=ColorModel.MONO,
)


class SolidState(BaseEffect):
    definition = SOLID

    def render(self, ctx: RenderContext) -> list[int | None]:
        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
        return [color] * ctx.led_count


def make_context(*, led_count: int = 12, now: float = 10.0, started_at: float = 8.0) -> RenderContext:
    return RenderContext(
        now=now,
        started_at=started_at,
        led_count=led_count,
        definition=SOLID,
        params=resolve_configuration(SOLID),
        inputs={},
    )


def test_render_returns_one_entry_per_led():
    for led_count in (5, 12, 24):
        frame = SolidState().render(make_context(led_count=led_count))
        assert len(frame) == led_count
        assert set(frame) == {0x0000FF}


def test_elapsed_is_measured_from_activation_not_from_process_start():
    assert make_context(now=10.0, started_at=8.0).elapsed == pytest.approx(2.0)


def test_context_offers_both_neutral_frames():
    ctx = make_context(led_count=4)
    assert ctx.transparent_frame() == [None, None, None, None]
    assert ctx.blank_frame() == [0, 0, 0, 0]


def test_a_definition_is_reachable_from_the_class():
    assert SolidState.get_definition() is SOLID


def test_render_is_mandatory():
    with pytest.raises(TypeError):

        class Incomplete(BaseEffect):
            definition = SOLID

        Incomplete()  # type: ignore[abstract]


def test_sample_inputs_defaults_to_no_value():
    ctx = InputContext(now=1.0, led_count=12, config={}, previous_inputs={})
    assert SolidState().sample_inputs(ctx) is None


def test_null_and_black_are_different_answers_in_a_frame():
    """The distinction the layer model rests on, exercised end to end.

    A marker with ``background_color=None`` leaves everything but its own LED
    untouched, so the state below stays visible. The same marker with
    ``background_color="black"`` writes black everywhere else and hides it.
    """
    marker = ControlledOverlayDefinition(
        id="marker",
        title="Marker",
        description="Marks one position over whatever is below it.",
        parameter_schema={
            "color": ParamDefinition(name="color", type=ParamType.COLOR, default="green"),
            "background_color": ParamDefinition(
                name="background_color", type=ParamType.COLOR, nullable=True, default=None
            ),
            "brightness": ParamDefinition(
                name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=1.0
            ),
        },
        runtime_inputs={
            "direction_deg": ParamDefinition(
                name="direction_deg", type=ParamType.ANGLE_DEG, required=True, nullable=True
            )
        },
        color_model=ColorModel.MONO,
        composition=CompositionMode.TRANSPARENT,
    )

    class Marker(BaseEffect):
        definition = marker

        def render(self, ctx: RenderContext) -> list[int | None]:
            background = ctx.params["background_color"]
            # None stays None: "contribute nothing here". A colour — including
            # black — is written and therefore hides the layer below.
            fill = None if background is None else parse_color(background)
            frame: list[int | None] = [fill] * ctx.led_count
            direction = ctx.inputs["direction_deg"]
            if direction is not None:
                frame[position_for_angle(direction, ctx.led_count)] = parse_color(
                    ctx.params["color"]
                )
            return frame

    def frame_for(background: object) -> list[int | None]:
        ctx = RenderContext(
            now=1.0,
            started_at=0.0,
            led_count=4,
            definition=marker,
            params=resolve_configuration(marker, overrides={"background_color": background}),
            inputs={"direction_deg": 90.0},
        )
        return Marker().render(ctx)

    assert frame_for(None) == [None, 0x00FF00, None, None]
    assert frame_for("black") == [0x000000, 0x00FF00, 0x000000, 0x000000]
    assert frame_for(None) != frame_for("black")


def test_the_sdk_covers_the_geometry_a_marker_effect_needs():
    """The old direction effect re-implemented colour and angle handling locally.

    Everything it needed is available from the SDK, which is why a package has
    no reason to carry its own parser.
    """
    ctx = make_context(led_count=12)
    frame = ctx.transparent_frame()
    frame[position_for_angle(90.0, ctx.led_count)] = parse_color(ctx.params["color"])
    assert frame == [None, None, None, 0x0000FF] + [None] * 8
