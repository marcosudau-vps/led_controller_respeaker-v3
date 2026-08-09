"""Where the service keeps its runtime state, and where it looks for effects.

Deliberately the only module that turns settings into locations. The engine
reads no environment and resolves no paths; that question belongs here, and the
answers come from :mod:`lefx.interfaces.config` so that a file and an
environment variable are the same mechanism rather than two.

The old names still work, because they are what the settings table produces:
``state_root`` and ``package_path`` are read from ``LEFX_STATE_ROOT`` and
``LEFX_PACKAGE_PATH`` exactly as before, and now also from ``config.yaml`` and
from the unprefixed forms.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import config, discovery

ENV_STATE_ROOT = "LEFX_STATE_ROOT"
ENV_PACKAGE_PATH = "LEFX_PACKAGE_PATH"


def state_root() -> Path:
    """Directory for logs, the instance file and persisted state."""
    configured = config.get("state_root")
    root = Path(configured).expanduser() if configured else Path(tempfile.gettempdir()) / "lefx-runtime"
    root.mkdir(parents=True, exist_ok=True)
    return root


def background_state_file() -> Path:
    return state_root() / "background_state.json"


def instance_file() -> Path:
    return state_root() / "active_service.json"


def log_file() -> Path:
    return state_root() / "service.log"


def package_search_paths() -> list[Path]:
    """Directories scanned for ``.lefx`` and ``.lefxset`` files, in order.

    Three sources, each answering a different question:

    * the installed effect set distributions, filtered by ``included_lefxset``
      — this is where a normal installation gets its catalogue, and where a
      checkout gets it too, because the workspace installs the same packages
      editable;
    * ``package_path``, for archives kept outside any distribution;
    * ``effects/`` beside the working directory, so a file dropped into a
      checkout is picked up without configuring anything.

    ``package_path`` does not replace the installed sets. It used to replace
    everything, which meant that pointing at one extra directory silently
    turned the shipped catalogue off.
    """
    found: dict[Path, None] = {}
    for path in discovery.effect_set_search_paths():
        found.setdefault(path, None)
    for item in config.get("package_path"):
        found.setdefault(Path(item).expanduser(), None)
    found.setdefault(Path.cwd() / "effects", None)
    return list(found)


__all__ = [
    "ENV_PACKAGE_PATH",
    "ENV_STATE_ROOT",
    "background_state_file",
    "instance_file",
    "log_file",
    "package_search_paths",
    "state_root",
]
