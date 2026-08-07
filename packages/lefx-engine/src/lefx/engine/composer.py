"""Turns active invocations into layer frames.

The composer owns one effect instance per invocation, samples pull sources when
their policy says so, and checks that what a definition returns matches what it
declared. There is no intermediate scene object: earlier generations wrapped a
closure in a dict inside a dataclass only for the renderer to unwrap it again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from lefx.sdk import (
    BaseEffect,
    CompositionMode,
    InputContext,
    InputMode,
    RenderContext,
    normalize_runtime_inputs,
)

from .errors import RenderError
from .inputs import effective_inputs
from .invocation import Invocation
from .layers import LayerId
from .registry import EffectRegistry

logger = logging.getLogger("lefx.engine.composer")

InputProviderFn = Callable[[InputContext], Mapping[str, Any] | None]

MAX_COLOR = 0xFFFFFF


@dataclass(slots=True, frozen=True)
class LayerFrame:
    """One layer's contribution, bottom-to-top order preserved by the caller."""

    layer: LayerId
    invocation_id: str
    pixels: list[int | None]


class SceneComposer:
    def __init__(
        self,
        registry: EffectRegistry,
        *,
        input_providers: Mapping[str, InputProviderFn] | None = None,
    ) -> None:
        self._registry = registry
        self._input_providers = dict(input_providers or {})
        self._instances: dict[str, BaseEffect] = {}

    def set_input_providers(self, providers: Mapping[str, InputProviderFn]) -> None:
        self._input_providers = dict(providers)

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._input_providers))

    def compose(
        self, invocations: list[Invocation], now: float, led_count: int
    ) -> list[LayerFrame]:
        frames = [
            LayerFrame(
                layer=invocation.layer,
                invocation_id=invocation.invocation_id,
                pixels=self._render(invocation, now, led_count),
            )
            for invocation in invocations
        ]
        self._drop_stale_instances({item.invocation_id for item in invocations})
        return frames

    def _drop_stale_instances(self, live_ids: set[str]) -> None:
        for invocation_id in [key for key in self._instances if key not in live_ids]:
            del self._instances[invocation_id]

    def _instance_for(self, invocation: Invocation) -> BaseEffect:
        """One instance per activation, so per-run Python state is safe to keep."""
        registered = self._registry.get(invocation.effect_id)
        instance = self._instances.get(invocation.invocation_id)
        if instance is None or not isinstance(instance, registered.effect_class):
            instance = registered.effect_class()
            self._instances[invocation.invocation_id] = instance
        return instance

    def _render(self, invocation: Invocation, now: float, led_count: int) -> list[int | None]:
        instance = self._instance_for(invocation)
        definition = invocation.definition
        self._sample_inputs(instance, invocation, now, led_count)

        context = RenderContext(
            now=now,
            started_at=invocation.activated_at or invocation.created_at,
            led_count=led_count,
            definition=definition,
            params=invocation.params,
            inputs=effective_inputs(definition, invocation, now),
        )
        pixels = instance.render(context)
        self._check_frame(pixels, invocation, led_count)
        return list(pixels)

    def _check_frame(
        self, pixels: Any, invocation: Invocation, led_count: int
    ) -> None:
        """Hold a definition to the contract it declared.

        The opacity check matters as much as the length one: a definition that
        calls itself opaque and then returns ``None`` is claiming to cover the
        layer below while leaving it visible.
        """
        definition = invocation.definition
        if not isinstance(pixels, (list, tuple)):
            raise RenderError(f"{definition.id!r} returned {type(pixels).__name__}, expected a list")
        if len(pixels) != led_count:
            raise RenderError(
                f"{definition.id!r} returned {len(pixels)} positions, expected {led_count}"
            )
        opaque = definition.composition is CompositionMode.OPAQUE
        for index, value in enumerate(pixels):
            if value is None:
                if opaque:
                    raise RenderError(
                        f"{definition.id!r} is declared opaque but returned None at "
                        f"position {index}; use black to switch an LED off, or declare "
                        "the definition transparent to let the layer below show through"
                    )
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise RenderError(
                    f"{definition.id!r} returned {value!r} at position {index}; "
                    "expected an RGB integer or None"
                )
            if not 0 <= value <= MAX_COLOR:
                raise RenderError(
                    f"{definition.id!r} returned {value:#x} at position {index}, "
                    "outside 0x000000..0xFFFFFF"
                )

    def _sample_inputs(
        self, instance: BaseEffect, invocation: Invocation, now: float, led_count: int
    ) -> None:
        """Pull values according to the declared policy, if it is due."""
        definition = invocation.definition
        policy = definition.input_sampling
        if policy is None or policy.mode is not InputMode.PULL:
            return
        if invocation.input_last_attempt_at is not None:
            elapsed_ms = (now - invocation.input_last_attempt_at) * 1000.0
            if elapsed_ms < policy.interval_ms:
                return

        invocation.input_last_attempt_at = now
        context = InputContext(
            now=now,
            led_count=led_count,
            config=invocation.params,
            previous_inputs=dict(invocation.inputs),
        )
        try:
            if policy.provider_id is None:
                sampled = instance.sample_inputs(context)
            else:
                provider = self._input_providers.get(policy.provider_id)
                if provider is None:
                    raise RuntimeError(
                        f"input provider {policy.provider_id!r} is not available"
                    )
                sampled = provider(context)
            if sampled is None:
                invocation.input_error = "input source returned no value"
                return
            normalized = normalize_runtime_inputs(definition, sampled)
        except Exception as exc:
            # A failing source is a health event, not a render failure. The last
            # good values stay in place until the grace period runs out.
            invocation.input_error = str(exc)
            logger.warning(
                "input sampling failed effect=%s invocation=%s error=%s",
                definition.id,
                invocation.invocation_id,
                exc,
            )
            return

        invocation.inputs.update(normalized)
        invocation.input_last_success_at = now
        invocation.input_error = None


__all__ = ["LayerFrame", "SceneComposer"]
