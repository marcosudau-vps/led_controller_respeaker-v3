"""A thin HTTP client for the local service.

Uses the standard library so that talking to the service costs no dependency.
Failures come back as a result object rather than an exception, because the CLI
reports them as JSON like any other outcome.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from .contract import API_PREFIX


@dataclass(slots=True, frozen=True)
class Result:
    ok: bool
    status: int | None = None
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, "data": self.data}
        return {"ok": False, "status": self.status, "error": self.error, "detail": self.data}


class ControllerClient:
    def __init__(self, *, host: str = "127.0.0.1", port: int = 8765, timeout: float = 5.0) -> None:
        self.base = f"http://{host}:{port}"
        self.timeout = timeout

    def _call(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Result:
        url = f"{self.base}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
                return Result(ok=True, status=response.status, data=json.loads(text) if text else None)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(text)
            except json.JSONDecodeError:
                detail = text
            return Result(ok=False, status=exc.code, data=detail, error=_message(detail, exc))
        except urllib.error.URLError as exc:
            return Result(ok=False, error=f"cannot reach the service at {self.base}: {exc.reason}")
        except OSError as exc:
            return Result(ok=False, error=f"cannot reach the service at {self.base}: {exc}")

    # -- reads --------------------------------------------------------------

    def health(self) -> Result:
        return self._call("GET", "/health")

    def status(self) -> Result:
        return self._call("GET", f"{API_PREFIX}/status")

    def list(self, kind: str, *, details: bool = False) -> Result:
        query = "?details=true" if details else ""
        return self._call("GET", f"{API_PREFIX}/{kind}{query}")

    def show(self, target: str) -> Result:
        return self._call("GET", f"{API_PREFIX}/show/{target}")

    # -- commands -----------------------------------------------------------

    def set_state(self, target: str, config: Mapping[str, Any], *, slot: str, action: str) -> Result:
        return self._call(
            "POST",
            f"{API_PREFIX}/set/state",
            {"target": target, "config": dict(config), "slot": slot, "action": action},
        )

    def clear_state(self, *, slot: str) -> Result:
        return self._call("POST", f"{API_PREFIX}/clear/state", {"slot": slot})

    def set_overlay(
        self, target: str, *, channel: str | None, config: Mapping[str, Any],
        inputs: Mapping[str, Any], action: str,
    ) -> Result:
        return self._call(
            "POST",
            f"{API_PREFIX}/set/overlay",
            {
                "target": target,
                "channel": channel,
                "config": dict(config),
                "inputs": dict(inputs),
                "action": action,
            },
        )

    def update_overlay(self, channel: str, inputs: Mapping[str, Any]) -> Result:
        return self._call(
            "POST", f"{API_PREFIX}/update/overlay", {"channel": channel, "inputs": dict(inputs)}
        )

    def clear_overlay(self, channel: str) -> Result:
        return self._call("POST", f"{API_PREFIX}/clear/overlay", {"channel": channel})

    def emit_event(
        self, target: str, config: Mapping[str, Any], *, priority: int | None,
        duration_ms: int | None,
    ) -> Result:
        return self._call(
            "POST",
            f"{API_PREFIX}/emit/event",
            {
                "target": target,
                "config": dict(config),
                "priority": priority,
                "duration_ms": duration_ms,
            },
        )

    def clear_all(self) -> Result:
        return self._call("POST", f"{API_PREFIX}/clear/all")

    def set_output(self, *, brightness: float | None, enabled: bool | None) -> Result:
        return self._call(
            "POST", f"{API_PREFIX}/output", {"brightness": brightness, "enabled": enabled}
        )

    # -- sources ------------------------------------------------------------

    def list_sources(self) -> Result:
        return self._call("GET", f"{API_PREFIX}/sources")

    def register_source(self, path: str, *, enabled: bool = True) -> Result:
        return self._call(
            "POST", f"{API_PREFIX}/sources/register", {"path": path, "enabled": enabled}
        )

    def reload_sources(self) -> Result:
        return self._call("POST", f"{API_PREFIX}/sources/reload")

    def remove_source(self, source_id: str) -> Result:
        return self._call("DELETE", f"{API_PREFIX}/sources/{source_id}")

    def shutdown(self) -> Result:
        return self._call("POST", f"{API_PREFIX}/shutdown")


def _message(detail: Any, exc: urllib.error.HTTPError) -> str:
    if isinstance(detail, Mapping):
        inner = detail.get("detail", detail)
        if isinstance(inner, Mapping):
            if "message" in inner:
                return str(inner["message"])
            issues = inner.get("issues")
            if isinstance(issues, list) and issues:
                return "; ".join(str(item.get("message", item)) for item in issues)
    return f"{exc.code} {exc.reason}"


__all__ = ["ControllerClient", "Result"]
