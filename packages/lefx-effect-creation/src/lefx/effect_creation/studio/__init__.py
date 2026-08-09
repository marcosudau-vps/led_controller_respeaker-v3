"""LEFX V3 studio: a window for playing, tuning, calibrating and authoring effects.

Only the Qt-free half is re-exported here. ``window``, ``ring``, ``parameters``
and ``app`` import PySide6 and are reached through :func:`lefx.effect_creation.studio.app.main`
or imported directly — so that the pieces worth testing can be imported by a
test run that has no display, and so that importing this package does not build
a toolkit's worth of objects to answer a question about a catalogue.
"""

from __future__ import annotations

from .authoring import (
    PresetDraft,
    check_draft,
    find_source_dir,
    slugify,
    suggest_preset_id,
    write_preset_checked,
)
from .calibrate import (
    MIN_SAMPLES,
    Fit,
    Sample,
    circular_mean,
    circular_spread,
    fit_calibration,
    sector_angle,
    suggested_sectors,
)
from .project import (
    Project,
    recalled,
    remember,
    resolve,
    under_a_frozen_build,
)
from .catalogue import (
    KIND_LABELS,
    Entry,
    Playback,
    entries,
    filtered,
    playback_for,
    pulls_a_provider,
    starting_config,
    starting_inputs,
)
from .session import (
    NULL_OUTPUT,
    STUDIO_CHANNEL,
    StudioSession,
    TappedSink,
    available_outputs,
    device_in_use,
)

STUDIO_VERSION = "3.0.0"

__all__ = [
    "KIND_LABELS",
    "MIN_SAMPLES",
    "NULL_OUTPUT",
    "STUDIO_CHANNEL",
    "STUDIO_VERSION",
    "Entry",
    "Fit",
    "Playback",
    "Project",
    "PresetDraft",
    "Sample",
    "StudioSession",
    "TappedSink",
    "available_outputs",
    "circular_mean",
    "check_draft",
    "circular_spread",
    "device_in_use",
    "entries",
    "filtered",
    "find_source_dir",
    "fit_calibration",
    "playback_for",
    "pulls_a_provider",
    "recalled",
    "remember",
    "resolve",
    "sector_angle",
    "slugify",
    "starting_config",
    "starting_inputs",
    "suggest_preset_id",
    "suggested_sectors",
    "under_a_frozen_build",
    "write_preset_checked",
]
