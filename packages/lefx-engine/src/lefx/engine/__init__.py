"""LEFX V3 engine — layers, lifecycles, composition and package loading.

The engine is generic. It decides by definition form — state, controlled
overlay, timed overlay, event — and never by identity. No branch here asks which
definition it is looking at; that meaning belongs to the package or to an
application integration.

It depends on the SDK and nothing else: no HTTP, no CLI, no USB, no Qt. Output
and input reach it through the SDK ports, so the same runtime drives real
hardware, a simulator or nothing at all.
"""

from __future__ import annotations

from .composer import LayerFrame, SceneComposer
from .config import EngineConfig
from .errors import (
    AmbiguousTargetError,
    ChannelNotFoundError,
    CommandError,
    EngineError,
    PackageError,
    RegistrationError,
    RenderError,
    TargetNotFoundError,
    WrongTargetTypeError,
)
from .inputs import (
    InputHealth,
    PolledInputProvider,
    effective_inputs,
    evaluate_health,
    input_status,
)
from .invocation import Invocation, duration_from_config
from .layers import COMPOSITION_ORDER, LAYER_PRIORITIES, LayerId, layer_for, parse_state_slot
from .library import EffectLibrary, SourceEntry, discover_packages
from .packages import (
    PACKAGE_FORMAT,
    SET_FORMAT,
    LoadedPackage,
    LoadedSource,
    build_package_manifest,
    load_source,
    serialize_definition,
)
from .registry import EffectRegistry, Preset, RegisteredEffect, ResolvedTarget, build_registry
from .renderer import OutputSettings, SceneRenderer
from .runtime import EffectRuntime, normalize_channel
from .store import LayerState, LayerStore

ENGINE_VERSION = "3.0.0"

__all__ = [
    "AmbiguousTargetError",
    "COMPOSITION_ORDER",
    "ChannelNotFoundError",
    "CommandError",
    "ENGINE_VERSION",
    "EffectLibrary",
    "EffectRegistry",
    "EffectRuntime",
    "EngineConfig",
    "EngineError",
    "InputHealth",
    "Invocation",
    "LAYER_PRIORITIES",
    "LayerFrame",
    "LayerId",
    "LayerState",
    "LayerStore",
    "LoadedPackage",
    "LoadedSource",
    "OutputSettings",
    "PACKAGE_FORMAT",
    "PackageError",
    "PolledInputProvider",
    "Preset",
    "RegisteredEffect",
    "RegistrationError",
    "RenderError",
    "ResolvedTarget",
    "SET_FORMAT",
    "SceneComposer",
    "SceneRenderer",
    "SourceEntry",
    "TargetNotFoundError",
    "WrongTargetTypeError",
    "build_package_manifest",
    "build_registry",
    "discover_packages",
    "duration_from_config",
    "effective_inputs",
    "evaluate_health",
    "input_status",
    "layer_for",
    "load_source",
    "normalize_channel",
    "parse_state_slot",
    "serialize_definition",
]
