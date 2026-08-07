"""Layer placement, frame contracts and composition."""

from __future__ import annotations

import pytest

from lefx.engine import (
    COMPOSITION_ORDER,
    CommandError,
    EffectRuntime,
    EngineConfig,
    LayerId,
    OutputSettings,
    RenderError,
    SceneComposer,
    SceneRenderer,
    build_registry,
    layer_for,
)
from lefx.engine.composer import LayerFrame
from lefx.sdk import (
    BaseEffect,
    ColorModel,
    CompositionMode,
    ParamDefinition,
    ParamType,
    RenderContext,
    StateDefinition,
    StateSlot,
)

from .sample_effects import (
    ALL_EFFECTS,
    BackgroundOnlyState,
    DirectionMarker,
    FlashOverlay,
    PulseEvent,
    SolidState,
)


def runtime(**kwargs) -> EffectRuntime:
    return EffectRuntime(
        build_registry(ALL_EFFECTS), config=EngineConfig(led_count=4), **kwargs
    )


# -- layer placement --------------------------------------------------------


def test_the_stack_composes_bottom_to_top():
    assert COMPOSITION_ORDER == (
        LayerId.BACKGROUND_STATE,
        LayerId.PRIMARY_STATE,
        LayerId.TIMED_OVERLAY,
        LayerId.CONTROLLED_OVERLAY,
        LayerId.EVENT,
    )


def test_the_form_decides_the_layer():
    assert layer_for(SolidState.definition) is LayerId.PRIMARY_STATE
    assert layer_for(DirectionMarker.definition) is LayerId.CONTROLLED_OVERLAY
    assert layer_for(FlashOverlay.definition) is LayerId.TIMED_OVERLAY
    assert layer_for(PulseEvent.definition) is LayerId.EVENT


def test_a_state_may_only_use_a_slot_it_declares():
    assert layer_for(BackgroundOnlyState.definition) is LayerId.BACKGROUND_STATE
    with pytest.raises(CommandError, match="does not allow the primary slot"):
        layer_for(BackgroundOnlyState.definition, slot=StateSlot.PRIMARY)


def test_only_states_take_a_slot():
    with pytest.raises(CommandError, match="only states have a slot"):
        layer_for(PulseEvent.definition, slot=StateSlot.PRIMARY)


# -- the frame contract -----------------------------------------------------


def _bad_effect(pixels, *, composition=CompositionMode.TRANSPARENT):
    class Broken(BaseEffect):
        definition = StateDefinition(
            id="broken_state",
            title="Broken",
            description="Returns a frame that breaks its own contract.",
            parameter_schema={
                "color": ParamDefinition(name="color", type=ParamType.COLOR, default="blue"),
                "brightness": ParamDefinition(
                    name="brightness", type=ParamType.FLOAT, default=1.0, minimum=0.0, maximum=1.0
                ),
            },
            color_model=ColorModel.MONO,
            composition=composition,
        )

        def render(self, ctx: RenderContext):
            return pixels

    return Broken


def _render_broken(effect_class) -> None:
    engine = EffectRuntime(
        build_registry([effect_class], source_id="broken"), config=EngineConfig(led_count=4)
    )
    engine.set_state("broken_state", now=0.0)
    engine.render_once(now=0.0)


def test_a_frame_must_have_one_entry_per_led():
    with pytest.raises(RenderError, match="returned 3 positions, expected 4"):
        _render_broken(_bad_effect([1, 2, 3]))


def test_an_opaque_definition_may_not_return_none():
    """Declaring opacity is a promise to cover the layer below."""
    with pytest.raises(RenderError, match="declared opaque but returned None"):
        _render_broken(_bad_effect([0, None, 0, 0], composition=CompositionMode.OPAQUE))


def test_a_transparent_definition_may_return_none():
    engine = EffectRuntime(
        build_registry([_bad_effect([0, None, 0, 0])], source_id="ok"),
        config=EngineConfig(led_count=4),
    )
    engine.set_state("broken_state", now=0.0)
    assert engine.render_once(now=0.0).leds == (0, 0, 0, 0)


def test_a_frame_entry_must_be_a_colour_or_none():
    with pytest.raises(RenderError, match="expected an RGB integer or None"):
        _render_broken(_bad_effect([0, "red", 0, 0]))
    with pytest.raises(RenderError, match="outside 0x000000"):
        _render_broken(_bad_effect([0, 0x1000000, 0, 0]))


def test_a_frame_must_be_a_sequence():
    with pytest.raises(RenderError, match="expected a list"):
        _render_broken(_bad_effect(None))


# -- composition ------------------------------------------------------------


def test_none_keeps_what_is_below_and_black_hides_it():
    """The distinction the whole layer model rests on."""
    renderer = SceneRenderer()
    below = LayerFrame(layer=LayerId.PRIMARY_STATE, invocation_id="a", pixels=[0x0000FF] * 4)

    transparent = LayerFrame(
        layer=LayerId.CONTROLLED_OVERLAY, invocation_id="b", pixels=[None, 0x00FF00, None, None]
    )
    assert renderer.compose([below, transparent], led_count=4, timestamp=0.0).leds == (
        0x0000FF,
        0x00FF00,
        0x0000FF,
        0x0000FF,
    )

    opaque_black = LayerFrame(
        layer=LayerId.CONTROLLED_OVERLAY, invocation_id="b", pixels=[0, 0x00FF00, 0, 0]
    )
    assert renderer.compose([below, opaque_black], led_count=4, timestamp=0.0).leds == (
        0x000000,
        0x00FF00,
        0x000000,
        0x000000,
    )


def test_layers_are_applied_in_the_order_they_arrive():
    renderer = SceneRenderer()
    frames = [
        LayerFrame(layer=LayerId.BACKGROUND_STATE, invocation_id="bg", pixels=[0x111111] * 4),
        LayerFrame(layer=LayerId.PRIMARY_STATE, invocation_id="st", pixels=[0x222222] * 4),
        LayerFrame(
            layer=LayerId.EVENT, invocation_id="ev", pixels=[None, None, 0xFF0000, None]
        ),
    ]
    assert renderer.compose(frames, led_count=4, timestamp=0.0).leds == (
        0x222222,
        0x222222,
        0xFF0000,
        0x222222,
    )


def test_global_brightness_dims_the_composed_frame_only():
    renderer = SceneRenderer()
    frames = [LayerFrame(layer=LayerId.PRIMARY_STATE, invocation_id="a", pixels=[0xFFFFFF] * 2)]
    settings = OutputSettings(brightness=0.5)
    assert renderer.compose(
        frames, led_count=2, timestamp=0.0, settings=settings
    ).leds == (0x7F7F7F, 0x7F7F7F)


def test_disabling_output_blanks_the_frame_without_touching_the_layers():
    engine = runtime()
    engine.set_state("solid_state", {"color": "red"}, now=0.0)
    engine.set_enabled(False)
    assert engine.render_once(now=0.0).leds == (0, 0, 0, 0)
    engine.set_enabled(True)
    assert engine.render_once(now=0.0).leds == (0xFF0000,) * 4


def test_brightness_is_clamped_into_range():
    settings = OutputSettings()
    settings.with_brightness(5.0)
    assert settings.brightness == 1.0
    settings.with_brightness(-1.0)
    assert settings.brightness == 0.0


# -- the stack end to end ---------------------------------------------------


def test_a_marker_over_a_state_leaves_the_state_visible():
    engine = runtime()
    engine.set_state("solid_state", {"color": "blue"}, now=0.0)
    engine.set_overlay(
        "direction_marker", channel="doa", config={"color": "green"},
        inputs={"direction_deg": 90}, now=0.0,
    )
    assert engine.render_once(now=0.0).leds == (0x0000FF, 0x00FF00, 0x0000FF, 0x0000FF)


def test_every_layer_contributes_in_priority_order():
    engine = runtime()
    engine.set_state("solid_state", {"color": "#111111"}, slot="background", now=0.0)
    engine.set_state("solid_state", {"color": "#222222"}, slot="primary", now=0.0)
    engine.set_overlay("flash_overlay", config={"color": "yellow"}, now=0.0)
    engine.set_overlay(
        "direction_marker", channel="doa", config={"color": "green"},
        inputs={"direction_deg": 90}, now=0.0,
    )
    engine.emit_event("pulse_event", {"color": "red"}, now=0.0)

    assert engine.render_once(now=0.0).leds == (0xFFFF00, 0x00FF00, 0x222222, 0xFF0000)


def test_the_same_definition_renders_at_any_ring_size():
    for led_count in (5, 12, 24):
        engine = EffectRuntime(
            build_registry(ALL_EFFECTS), config=EngineConfig(led_count=led_count)
        )
        engine.set_state("solid_state", {"color": "blue"}, now=0.0)
        frame = engine.render_once(now=0.0)
        assert len(frame.leds) == led_count


def test_an_effect_instance_lives_as_long_as_its_invocation():
    engine = runtime()
    engine.set_state("solid_state", now=0.0)
    engine.render_once(now=0.0)
    composer: SceneComposer = engine.composer
    first = list(composer._instances.values())[0]

    engine.render_once(now=0.1)
    assert list(composer._instances.values())[0] is first

    engine.set_state("solid_state", {"color": "red"}, now=0.2)
    engine.render_once(now=0.2)
    assert list(composer._instances.values())[0] is not first
    assert len(composer._instances) == 1
