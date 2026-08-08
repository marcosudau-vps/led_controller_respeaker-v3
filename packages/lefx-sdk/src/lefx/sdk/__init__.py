"""LEFX V3 SDK — the contract between effect packages and the engine.

This is the whole public surface an effect author needs. Importing anything
below the top level is supported but not required; importing anything outside
this package from an effect source is rejected by the build.

A minimal state::

    from lefx.sdk import (
        BaseEffect, ColorModel, ParamDefinition, ParamType,
        RenderContext, StateDefinition, parse_color, scale_color,
    )

    class SolidState(BaseEffect):
        definition = StateDefinition(
            id="solid",
            title="Solid",
            description="Fills the ring with one colour.",
            parameter_schema={
                "color": ParamDefinition(name="color", type=ParamType.COLOR, default="blue"),
                "brightness": ParamDefinition(
                    name="brightness", type=ParamType.FLOAT,
                    default=1.0, minimum=0.0, maximum=1.0,
                ),
            },
            color_model=ColorModel.MONO,
        )

        def render(self, ctx: RenderContext) -> list[int | None]:
            color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])
            return [color] * ctx.led_count
"""

from __future__ import annotations

from .calibration import (
    DEFAULT_CALIBRATION_FILE,
    ENV_CALIBRATION_PATH,
    DoaCalibration,
    as_flag,
    calibration_path,
    load_calibration,
    resolve_calibration,
    save_calibration,
)
from .color import (
    blend,
    clamp_channel,
    evenly_spaced_positions,
    position_for_angle,
    positions_for_angle,
    rgb,
    scale_color,
    sector_for_angle,
    segment_lengths,
)
from .context import InputContext, RenderContext
from .definitions import (
    AnyDefinition,
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    DefinitionBase,
    DefinitionKind,
    DefinitionType,
    DurationField,
    EventDefinition,
    InputMode,
    InputSamplingPolicy,
    OverlayMode,
    StateDefinition,
    StateSlot,
    TimedOverlayDefinition,
    resolved_default_configuration,
)
from .effects import BaseEffect
from .errors import (
    ParameterValidationError,
    SchemaError,
    ValidationIssue,
    ValueNormalizationError,
)
from .parameters import (
    MISSING,
    RESERVED_PARAMETERS,
    ParamDefinition,
    ParamType,
    normalize_parameter_value,
)
from .ports import FrameSink, InputProvider, OutputFrame, SinkStatus
from .validation import (
    initial_runtime_inputs,
    normalize_runtime_inputs,
    normalize_values,
    resolve_configuration,
)
from .values import (
    COLOR_CATALOG,
    NamedColor,
    describe_color,
    format_color,
    parse_angle_degrees,
    parse_bool,
    parse_color,
    parse_duration_ms,
    parse_ratio,
)

SDK_VERSION = "3.0.0"
"""Contract generation. A package built against a different major will not load."""

__all__ = [
    "AnyDefinition",
    "BaseEffect",
    "COLOR_CATALOG",
    "ColorModel",
    "CompositionMode",
    "ControlledOverlayDefinition",
    "DefinitionBase",
    "DefinitionKind",
    "DEFAULT_CALIBRATION_FILE",
    "DefinitionType",
    "DoaCalibration",
    "DurationField",
    "ENV_CALIBRATION_PATH",
    "EventDefinition",
    "FrameSink",
    "InputContext",
    "InputMode",
    "InputProvider",
    "InputSamplingPolicy",
    "MISSING",
    "NamedColor",
    "OutputFrame",
    "OverlayMode",
    "ParamDefinition",
    "ParamType",
    "ParameterValidationError",
    "RESERVED_PARAMETERS",
    "RenderContext",
    "SDK_VERSION",
    "SchemaError",
    "SinkStatus",
    "StateDefinition",
    "StateSlot",
    "TimedOverlayDefinition",
    "ValidationIssue",
    "ValueNormalizationError",
    "blend",
    "clamp_channel",
    "describe_color",
    "evenly_spaced_positions",
    "format_color",
    "initial_runtime_inputs",
    "normalize_parameter_value",
    "normalize_runtime_inputs",
    "normalize_values",
    "parse_angle_degrees",
    "parse_bool",
    "parse_color",
    "parse_duration_ms",
    "parse_ratio",
    "as_flag",
    "calibration_path",
    "load_calibration",
    "position_for_angle",
    "positions_for_angle",
    "resolve_calibration",
    "save_calibration",
    "sector_for_angle",
    "resolve_configuration",
    "resolved_default_configuration",
    "rgb",
    "scale_color",
    "segment_lengths",
]
