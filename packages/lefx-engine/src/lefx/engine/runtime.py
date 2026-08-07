"""The command surface and the render step.

Every command is transport-independent and fully validated before it touches
anything: an invalid command leaves the runtime exactly as it was. The verbs
here are the same ones the CLI and the HTTP API expose, because both are
transports for these calls and hold no logic of their own.

The engine decides by form, never by identity. There is no branch anywhere below
that asks which definition it is looking at.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from lefx.sdk import (
    DefinitionBase,
    DefinitionKind,
    DefinitionType,
    FrameSink,
    InputMode,
    OutputFrame,
    StateSlot,
    initial_runtime_inputs,
    normalize_runtime_inputs,
    resolve_configuration,
)

from .composer import InputProviderFn, SceneComposer
from .config import EngineConfig
from .errors import ChannelNotFoundError, CommandError
from .inputs import input_status
from .invocation import Invocation, duration_from_config
from .layers import COMPOSITION_ORDER, LayerId, layer_for, parse_state_slot, slot_for
from .registry import EffectRegistry, ResolvedTarget
from .renderer import OutputSettings, SceneRenderer
from .store import LayerStore

Action = str
_ACTIONS = ("on", "off", "toggle")


def normalize_channel(channel: str | None) -> str:
    text = str(channel or "").strip().lower()
    if not text:
        raise CommandError("A controlled overlay requires a non-empty channel name")
    return text


class EffectRuntime:
    """Holds the layer stack and applies commands to it."""

    def __init__(
        self,
        registry: EffectRegistry,
        *,
        sink: FrameSink | None = None,
        config: EngineConfig | None = None,
        input_providers: Mapping[str, InputProviderFn] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = registry
        self.config = config or EngineConfig()
        self.sink = sink
        self.store = LayerStore()
        self.output = OutputSettings()
        self.composer = SceneComposer(registry, input_providers=input_providers)
        self.renderer = SceneRenderer()
        self._clock = clock
        self._sequence = 0
        self.last_frame: OutputFrame | None = None

    # -- states -------------------------------------------------------------

    def set_state(
        self,
        target: str,
        config: Mapping[str, Any] | None = None,
        *,
        slot: str | StateSlot | None = None,
        action: Action = "on",
        now: float | None = None,
    ) -> Invocation | None:
        """Activate a state, or switch it off. Plain ``set`` always means on.

        An implicit toggle would make retries and repeated API calls unsafe, so
        turning something off is something a caller has to ask for.
        """
        resolved = self.registry.resolve(target, expected_type=DefinitionType.STATE)
        chosen_slot = None if slot is None else parse_state_slot(slot)
        layer = layer_for(resolved.effect.definition, slot=chosen_slot)
        return self._apply_switchable(resolved, layer, config, None, action, now)

    def clear_state(
        self, *, slot: str | StateSlot = StateSlot.PRIMARY
    ) -> list[str]:
        layer = (
            LayerId.BACKGROUND_STATE
            if parse_state_slot(slot) is StateSlot.BACKGROUND
            else LayerId.PRIMARY_STATE
        )
        return self.store.clear_layer(layer)

    # -- overlays -----------------------------------------------------------

    def set_overlay(
        self,
        target: str,
        *,
        channel: str | None = None,
        config: Mapping[str, Any] | None = None,
        inputs: Mapping[str, Any] | None = None,
        action: Action = "on",
        now: float | None = None,
    ) -> Invocation | None:
        resolved = self.registry.resolve(target, expected_type=DefinitionType.OVERLAY)
        definition = resolved.effect.definition
        layer = layer_for(definition)

        if definition.kind is DefinitionKind.TIMED_OVERLAY:
            if action != "on":
                raise CommandError(
                    "A timed overlay ends by itself and supports only action 'on'"
                )
            if channel is not None:
                raise CommandError(
                    "A timed overlay has no channel; only controlled overlays are addressable"
                )
            if inputs:
                raise CommandError("A timed overlay has no runtime inputs")
            return self._activate(resolved, layer, config, None, now=now)

        normalized_channel = normalize_channel(channel)
        return self._apply_switchable(
            resolved, layer, config, inputs, action, now, channel=normalized_channel
        )

    def update_overlay(
        self,
        channel: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        now: float | None = None,
    ) -> Invocation:
        """Apply new runtime values, or record a heartbeat when empty.

        Updates are partial: only supplied fields change. One unknown or invalid
        field rejects the whole update, so an instance is never half applied.
        """
        moment = self._now(now)
        name = normalize_channel(channel)
        invocation = self.store.find_channel(name)
        if invocation is None:
            raise ChannelNotFoundError(name)

        definition = invocation.definition
        policy = definition.input_sampling
        if policy is not None and policy.mode is InputMode.PULL:
            raise CommandError(
                f"{definition.id!r} pulls its runtime inputs"
                + (f" from provider {policy.provider_id!r}" if policy.provider_id else "")
                + "; it does not accept pushed updates"
            )

        normalized = normalize_runtime_inputs(definition, inputs)
        invocation.inputs.update(normalized)
        invocation.input_last_success_at = moment
        invocation.input_error = None
        return invocation

    def clear_overlay(self, channel: str) -> list[str]:
        name = normalize_channel(channel)
        invocation = self.store.find_channel(name)
        if invocation is None:
            raise ChannelNotFoundError(name)
        return self.store.clear_layer(LayerId.CONTROLLED_OVERLAY)

    # -- events -------------------------------------------------------------

    def emit_event(
        self,
        target: str,
        config: Mapping[str, Any] | None = None,
        *,
        priority: int | None = None,
        duration_ms: int | None = None,
        now: float | None = None,
    ) -> Invocation:
        """Queue an event. A running one is never cut short by a newer one."""
        moment = self._now(now)
        resolved = self.registry.resolve(target, expected_type=DefinitionType.EVENT)
        invocation = self._build(resolved, LayerId.EVENT, config, None, moment, duration_ms)
        invocation.priority = priority
        self.store.enqueue_event(invocation, moment)
        return invocation

    # -- output settings ----------------------------------------------------

    def set_brightness(self, level: float) -> None:
        self.output.with_brightness(level)

    def set_enabled(self, enabled: bool) -> None:
        self.output.with_enabled(enabled)

    def clear_all(self) -> list[str]:
        return self.store.clear_all()

    # -- rendering ----------------------------------------------------------

    def render_once(self, now: float | None = None) -> OutputFrame:
        moment = self._now(now)
        self.store.advance(moment)
        frames = self.composer.compose(
            self.store.ordered_active(), moment, self.config.led_count
        )
        frame = self.renderer.compose(
            frames,
            led_count=self.config.led_count,
            timestamp=moment,
            settings=self.output,
        )
        self.last_frame = frame
        if self.sink is not None:
            self.sink.apply_frame(frame)
        return frame

    def close(self) -> None:
        if self.sink is not None:
            self.sink.close()

    # -- status -------------------------------------------------------------

    def status(self, now: float | None = None) -> dict[str, Any]:
        moment = self._now(now)
        return {
            "led_count": self.config.led_count,
            "fps": self.config.fps,
            "output": {
                "brightness": self.output.brightness,
                "enabled": self.output.enabled,
            },
            "sink": None if self.sink is None else self.sink.status().to_dict(),
            "layers": {
                layer.value: self._layer_status(layer, moment) for layer in COMPOSITION_ORDER
            },
            "event_queue": [
                self._invocation_status(item, moment)
                for item in self.store.layer(LayerId.EVENT).queue
            ],
            "frame": None if self.last_frame is None else list(self.last_frame.leds),
        }

    def _layer_status(self, layer: LayerId, now: float) -> dict[str, Any] | None:
        invocation = self.store.active(layer)
        if invocation is None:
            return None
        return self._invocation_status(invocation, now)

    def _invocation_status(self, invocation: Invocation, now: float) -> dict[str, Any]:
        definition = invocation.definition
        slot = slot_for(invocation.layer)
        payload: dict[str, Any] = {
            "invocation_id": invocation.invocation_id,
            "effect_id": definition.id,
            "type": definition.definition_type.value,
            "overlay_mode": None if definition.overlay_mode is None else definition.overlay_mode.value,
            "layer": invocation.layer.value,
            "slot": None if slot is None else slot.value,
            "channel": invocation.channel,
            "preset_id": invocation.preset_id,
            "config": dict(invocation.params),
            "active": invocation.is_active,
            "started_at": invocation.activated_at,
            "duration_ms": invocation.duration_ms,
            "remaining_ms": invocation.remaining_ms(now),
            "priority": invocation.effective_priority(),
        }
        if definition.runtime_input_schema:
            payload["inputs"] = dict(invocation.inputs)
            payload["input_health"] = input_status(definition, invocation, now)
        return payload

    # -- internals ----------------------------------------------------------

    def _now(self, now: float | None) -> float:
        return self._clock() if now is None else now

    def _next_invocation_id(self, definition: DefinitionBase) -> str:
        self._sequence += 1
        return f"{definition.id}:{self._sequence}"

    def _build(
        self,
        resolved: ResolvedTarget,
        layer: LayerId,
        config: Mapping[str, Any] | None,
        inputs: Mapping[str, Any] | None,
        now: float,
        duration_ms: int | None = None,
        channel: str | None = None,
    ) -> Invocation:
        """Resolve and validate everything before anything is placed."""
        definition = resolved.effect.definition
        preset_params = None if resolved.preset is None else resolved.preset.params
        params = resolve_configuration(definition, preset=preset_params, overrides=config)

        values = initial_runtime_inputs(definition)
        if inputs:
            if not definition.runtime_input_schema:
                raise CommandError(f"{definition.id!r} declares no runtime inputs")
            values.update(normalize_runtime_inputs(definition, inputs))

        return Invocation(
            invocation_id=self._next_invocation_id(definition),
            definition=definition,
            layer=layer,
            params=params,
            inputs=values,
            created_at=now,
            duration_ms=duration_from_config(definition, params, override_ms=duration_ms),
            channel=channel,
            preset_id=None if resolved.preset is None else resolved.preset.preset_id,
        )

    def _activate(
        self,
        resolved: ResolvedTarget,
        layer: LayerId,
        config: Mapping[str, Any] | None,
        inputs: Mapping[str, Any] | None,
        *,
        now: float | None = None,
        channel: str | None = None,
    ) -> Invocation:
        moment = self._now(now)
        invocation = self._build(resolved, layer, config, inputs, moment, channel=channel)
        self.store.set_active(invocation, moment)
        return invocation

    def _apply_switchable(
        self,
        resolved: ResolvedTarget,
        layer: LayerId,
        config: Mapping[str, Any] | None,
        inputs: Mapping[str, Any] | None,
        action: Action,
        now: float | None,
        *,
        channel: str | None = None,
    ) -> Invocation | None:
        if action not in _ACTIONS:
            raise CommandError(
                f"Unknown action {action!r}. Expected one of: {', '.join(_ACTIONS)}"
            )
        active = self._is_active(layer, resolved, channel)
        if action == "off" or (action == "toggle" and active):
            if active:
                self.store.clear_layer(layer)
            return None
        return self._activate(resolved, layer, config, inputs, now=now, channel=channel)

    def _is_active(
        self, layer: LayerId, resolved: ResolvedTarget, channel: str | None
    ) -> bool:
        current = self.store.active(layer)
        if current is None:
            return False
        if current.definition.id != resolved.effect.effect_id:
            return False
        if channel is not None and current.channel != channel:
            return False
        # A preset and its bare definition are different targets: switching off
        # "calm_blue" should not switch off a hand-configured activation.
        expected_preset = None if resolved.preset is None else resolved.preset.preset_id
        return current.preset_id == expected_preset


__all__ = ["EffectRuntime", "normalize_channel"]
