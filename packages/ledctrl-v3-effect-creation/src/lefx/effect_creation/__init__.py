"""LEFX V3 authoring tools — scaffolding, validation and package building.

Developer tooling, not part of a runtime installation. The build is a quality
gate: a source that violates its own contract is not packed, and a package the
loader would reject is not reported as built.
"""

from __future__ import annotations

from .build import build_effect_set, pack_effect, pack_effect_set
from .imports import ALLOWED_ROOTS, ALLOWED_STDLIB, ImportViolation, check_imports
from .scaffold import init_effect_set_source, init_effect_source, parse_kind
from .source import (
    EffectSetSource,
    EffectSource,
    SourceError,
    load_effect_set_source,
    load_effect_source,
)
from .validate import (
    SMOKE_LED_COUNTS,
    ValidationReport,
    import_effect_class,
    smoke_render,
    validate_effect_set_source,
    validate_effect_source,
)

AUTHORING_VERSION = "3.0.0"

__all__ = [
    "ALLOWED_ROOTS",
    "ALLOWED_STDLIB",
    "AUTHORING_VERSION",
    "EffectSetSource",
    "EffectSource",
    "ImportViolation",
    "SMOKE_LED_COUNTS",
    "SourceError",
    "ValidationReport",
    "build_effect_set",
    "check_imports",
    "import_effect_class",
    "init_effect_set_source",
    "init_effect_source",
    "load_effect_set_source",
    "load_effect_source",
    "pack_effect",
    "pack_effect_set",
    "parse_kind",
    "smoke_render",
    "validate_effect_set_source",
    "validate_effect_source",
]
