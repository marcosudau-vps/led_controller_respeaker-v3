"""Where the service keeps its runtime state.

Deliberately the only module that knows about install layout. The engine reads
no environment variables and resolves no paths; that question belongs here.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

ENV_STATE_ROOT = "LEFX_STATE_ROOT"
ENV_PACKAGE_PATH = "LEFX_PACKAGE_PATH"


def state_root() -> Path:
    """Directory for logs, the instance file and persisted state."""
    configured = os.environ.get(ENV_STATE_ROOT)
    if configured:
        root = Path(configured).expanduser()
    else:
        root = Path(tempfile.gettempdir()) / "lefx-runtime"
    root.mkdir(parents=True, exist_ok=True)
    return root


def background_state_file() -> Path:
    return state_root() / "background_state.json"


def instance_file() -> Path:
    return state_root() / "active_service.json"


def log_file() -> Path:
    return state_root() / "service.log"


def package_search_paths() -> list[Path]:
    """Directories scanned for ``.lefx`` and ``.lefxset`` files.

    ``LEFX_PACKAGE_PATH`` takes the platform path separator, like ``PATH``
    itself. Without it the service looks beside the working directory, which is
    where a checkout keeps its built catalogue.
    """
    configured = os.environ.get(ENV_PACKAGE_PATH)
    if configured:
        return [Path(item).expanduser() for item in configured.split(os.pathsep) if item]
    return [Path.cwd() / "build" / "effects", Path.cwd() / "effects"]


__all__ = [
    "ENV_PACKAGE_PATH",
    "ENV_STATE_ROOT",
    "background_state_file",
    "instance_file",
    "log_file",
    "package_search_paths",
    "state_root",
]
