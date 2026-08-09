"""The HTTP control surface.

Only ``/api/v3``. There is no compatibility route: an older client gets a clear
404 rather than a shape that silently means something else now.

Every endpoint is a thin call into the service. Validation errors come back as
422 with the field paths the SDK produced, so a caller learns which field was
wrong and what was suggested instead.
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from lefx.engine import (
    AmbiguousTargetError,
    ChannelNotFoundError,
    CommandError,
    PackageError,
    TargetNotFoundError,
)
from lefx.sdk import DefinitionType, ParameterValidationError

from .service import ControllerService

API_PREFIX = "/api/v3"


class SetStateRequest(BaseModel):
    target: str
    config: dict[str, Any] = Field(default_factory=dict)
    slot: Literal["primary", "background"] = "primary"
    action: Literal["on", "off", "toggle"] = "on"


class ClearStateRequest(BaseModel):
    slot: Literal["primary", "background"] = "primary"


class SetOverlayRequest(BaseModel):
    target: str
    channel: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    action: Literal["on", "off", "toggle"] = "on"


class UpdateOverlayRequest(BaseModel):
    channel: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class ClearOverlayRequest(BaseModel):
    channel: str


class EmitEventRequest(BaseModel):
    target: str
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int | None = None
    duration_ms: int | None = None


class OutputRequest(BaseModel):
    brightness: float | None = None
    enabled: bool | None = None


class RegisterSourceRequest(BaseModel):
    path: str
    enabled: bool = True


def create_app(
    service: ControllerService | None = None,
    *,
    lifecycle_callback: Callable[[str], None] | None = None,
    **service_options: Any,
) -> FastAPI:
    controller = service if service is not None else ControllerService(**service_options)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        controller.start()
        if lifecycle_callback is not None:
            lifecycle_callback("started")
        try:
            yield
        finally:
            if lifecycle_callback is not None:
                lifecycle_callback("stopping")
            controller.stop()

    app = FastAPI(
        title="LEFX Controller API",
        version="3.0.0",
        summary="Control surface for the LEFX V3 effect engine",
        lifespan=lifespan,
    )
    app.state.service = controller
    app.state.shutdown_server = None

    def get(request: Request) -> ControllerService:
        return request.app.state.service

    # -- error translation --------------------------------------------------

    @app.exception_handler(ParameterValidationError)
    async def _validation(request: Request, exc: ParameterValidationError):
        del request
        return JSONResponse(status_code=422, content={"detail": exc.to_dict()})

    @app.exception_handler(TargetNotFoundError)
    async def _not_found(request: Request, exc: TargetNotFoundError):
        del request
        return JSONResponse(
            status_code=404,
            content={
                "detail": {
                    "code": "target_not_found",
                    "message": str(exc),
                    "target": exc.target,
                    "suggestions": list(exc.suggestions),
                }
            },
        )

    @app.exception_handler(ChannelNotFoundError)
    async def _channel(request: Request, exc: ChannelNotFoundError):
        del request
        return JSONResponse(
            status_code=404,
            content={
                "detail": {
                    "code": "channel_not_found",
                    "message": str(exc),
                    "channel": exc.channel,
                }
            },
        )

    @app.exception_handler(AmbiguousTargetError)
    async def _ambiguous(request: Request, exc: AmbiguousTargetError):
        del request
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "ambiguous_target",
                    "message": str(exc),
                    "matches": list(exc.matches),
                }
            },
        )

    @app.exception_handler(CommandError)
    async def _command(request: Request, exc: CommandError):
        del request
        return JSONResponse(
            status_code=422, content={"detail": {"code": "invalid_command", "message": str(exc)}}
        )

    @app.exception_handler(PackageError)
    async def _package(request: Request, exc: PackageError):
        del request
        return JSONResponse(
            status_code=422, content={"detail": {"code": "invalid_package", "message": str(exc)}}
        )

    # -- meta ---------------------------------------------------------------

    @app.get("/")
    def root(request: Request):
        controller = get(request)
        return {
            "service": "LEFX Controller API",
            "version": app.version,
            "api_base": API_PREFIX,
            "docs": "/docs",
            "health": "/health",
            "sink": controller.sink_name,
        }

    @app.get("/health")
    def health(request: Request):
        return get(request).health()

    @app.get(f"{API_PREFIX}/status")
    def status(request: Request):
        return get(request).status()

    # -- listings -----------------------------------------------------------

    @app.get(f"{API_PREFIX}/states")
    def states(request: Request, details: bool = False):
        return get(request).list_definitions(DefinitionType.STATE, details=details)

    @app.get(f"{API_PREFIX}/overlays")
    def overlays(request: Request, details: bool = False):
        return get(request).list_definitions(DefinitionType.OVERLAY, details=details)

    @app.get(f"{API_PREFIX}/events")
    def events(request: Request, details: bool = False):
        return get(request).list_definitions(DefinitionType.EVENT, details=details)

    @app.get(f"{API_PREFIX}/presets")
    def presets(
        request: Request,
        type: Literal["state", "overlay", "event"] | None = None,
        details: bool = False,
    ):
        wanted = None if type is None else DefinitionType(type)
        return get(request).list_presets(wanted, details=details)

    @app.get(f"{API_PREFIX}/show/{{target:path}}")
    def show(target: str, request: Request):
        return get(request).show(target)

    # -- commands -----------------------------------------------------------

    @app.post(f"{API_PREFIX}/set/state")
    def set_state(payload: SetStateRequest, request: Request):
        return get(request).set_state(
            payload.target, payload.config, slot=payload.slot, action=payload.action
        )

    @app.post(f"{API_PREFIX}/clear/state")
    def clear_state(payload: ClearStateRequest, request: Request):
        return get(request).clear_state(slot=payload.slot)

    @app.post(f"{API_PREFIX}/set/overlay")
    def set_overlay(payload: SetOverlayRequest, request: Request):
        return get(request).set_overlay(
            payload.target,
            channel=payload.channel,
            config=payload.config,
            inputs=payload.inputs,
            action=payload.action,
        )

    @app.post(f"{API_PREFIX}/update/overlay")
    def update_overlay(payload: UpdateOverlayRequest, request: Request):
        return get(request).update_overlay(payload.channel, payload.inputs)

    @app.post(f"{API_PREFIX}/clear/overlay")
    def clear_overlay(payload: ClearOverlayRequest, request: Request):
        return get(request).clear_overlay(payload.channel)

    @app.post(f"{API_PREFIX}/emit/event")
    def emit_event(payload: EmitEventRequest, request: Request):
        return get(request).emit_event(
            payload.target,
            payload.config,
            priority=payload.priority,
            duration_ms=payload.duration_ms,
        )

    @app.post(f"{API_PREFIX}/clear/all")
    def clear_all(request: Request):
        return get(request).clear_all()

    @app.post(f"{API_PREFIX}/output")
    def output(payload: OutputRequest, request: Request):
        return get(request).set_output(brightness=payload.brightness, enabled=payload.enabled)

    # -- package sources ----------------------------------------------------

    @app.get(f"{API_PREFIX}/sources")
    def sources(request: Request):
        return {"items": get(request).list_sources()}

    @app.post(f"{API_PREFIX}/sources/register")
    def register_source(payload: RegisterSourceRequest, request: Request):
        return get(request).register_source(payload.path, enabled=payload.enabled)

    @app.post(f"{API_PREFIX}/sources/reload")
    def reload_sources(request: Request):
        return get(request).reload_sources()

    @app.delete(f"{API_PREFIX}/sources/{{source_id}}")
    def remove_source(source_id: str, request: Request):
        return get(request).remove_source(source_id)

    @app.post(f"{API_PREFIX}/shutdown")
    def shutdown(request: Request):
        payload = get(request).health()
        stop = getattr(request.app.state, "shutdown_server", None)
        if callable(stop):
            threading.Thread(target=stop, daemon=True).start()
        return {"ok": True, "operation": "shutdown", "status": payload}

    return app


__all__ = ["API_PREFIX", "create_app"]
