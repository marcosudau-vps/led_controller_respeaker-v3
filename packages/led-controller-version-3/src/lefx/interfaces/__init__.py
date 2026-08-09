"""LEFX V3 control surface — HTTP API, CLI, client and service hosting.

CLI and API carry the same commands and hold no logic of their own. Frame sinks
and input providers are discovered through entry points, never imported, so this
package depends on neither the hardware integration nor the simulator.

``create_app`` is resolved on first use rather than on import. It is the only
name here that needs FastAPI, and an application that embeds
:class:`~lefx.interfaces.service.ControllerService` in its own process needs no
HTTP server at all — but it would still have paid for one, because importing any
submodule runs this file first. That cost is not theoretical: in a frozen
single-file build the whole FastAPI, Starlette and Pydantic chain lands in the
binary of an application that never opens a port.

Nothing about the public surface changes. The name remains importable, ``dir()``
still lists it, and type checkers still see it through ``TYPE_CHECKING`` — only
the moment of import moves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .client import ControllerClient, Result
from .contract import API_PREFIX
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

if TYPE_CHECKING:  # pragma: no cover — for type checkers, never at runtime
    from .api import create_app

INTERFACES_VERSION = "3.0.0"

_LAZY: dict[str, str] = {"create_app": ".api"}
"""Name to the module it comes from. Imported on first access, then cached."""


def __getattr__(name: str) -> Any:
    """Resolve a deferred name, once, and bind it for every access after."""
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


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
