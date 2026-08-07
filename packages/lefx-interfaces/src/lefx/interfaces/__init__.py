"""LEFX V3 control surface — HTTP API, CLI, client and service hosting.

CLI and API carry the same commands and hold no logic of their own. Frame sinks
and input providers are discovered through entry points, never imported, so this
package depends on neither the hardware integration nor the simulator.
"""

from __future__ import annotations

from .api import API_PREFIX, create_app
from .client import ControllerClient, Result
from .discovery import (
    NullSink,
    available_providers,
    available_sinks,
    create_providers,
    create_sink,
    describe,
    split_provider_name,
)
from .service import ControllerService, StatusListener

INTERFACES_VERSION = "3.0.0"

__all__ = [
    "API_PREFIX",
    "ControllerClient",
    "ControllerService",
    "INTERFACES_VERSION",
    "NullSink",
    "Result",
    "StatusListener",
    "available_providers",
    "available_sinks",
    "create_app",
    "create_providers",
    "create_sink",
    "describe",
    "split_provider_name",
]
