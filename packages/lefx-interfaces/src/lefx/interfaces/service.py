"""The controller service: render loop, sink, providers and persistence.

Everything the engine needs from the outside world is assembled here — and only
here. The service knows which sink is installed and where state is kept; the
engine knows neither.

It carries no application meaning. There is no state named "offline", no
countdown, no direction command. When the output goes away the fact is published
and reported; deciding what the ring should then show is an application's job,
and the recipe for doing it sits in an integration rather than in this file.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from lefx.engine import (
    EffectLibrary,
    EffectRuntime,
    EngineConfig,
    Invocation,
    LayerId,
    slot_for,
)
from lefx.sdk import FrameSink, StateSlot

from . import discovery, paths, presentation

logger = logging.getLogger("lefx.interfaces.service")

StatusListener = Callable[[str, dict[str, Any]], None]


class ControllerService:
    """Owns the runtime, the render thread and everything around them."""

    def __init__(
        self,
        *,
        sink: FrameSink | str | None = None,
        led_count: int = 12,
        fps: float = 30.0,
        search_paths: list[str | Path] | None = None,
        state_file: str | Path | None = None,
        sink_options: Mapping[str, Any] | None = None,
        autostart_providers: bool = True,
    ) -> None:
        self.config = EngineConfig(led_count=led_count, fps=fps)
        self.library = EffectLibrary(
            search_paths=search_paths if search_paths is not None else paths.package_search_paths()
        )

        self.sink_name, self.sink = self._build_sink(sink, dict(sink_options or {}))
        self.providers: dict[str, Any] = (
            discovery.create_providers(led_count=led_count) if autostart_providers else {}
        )

        self.runtime = EffectRuntime(
            self.library.registry,
            sink=self.sink,
            config=self.config,
            input_providers=discovery.provider_callables(self.providers),
        )

        self.state_file = Path(state_file) if state_file is not None else paths.background_state_file()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._render_count = 0
        self._last_error: str | None = None
        self._started_at: float | None = None
        self._listeners: list[StatusListener] = []
        self._sink_available: bool | None = None
        self._persisted_signature: str | None = None

        self.restore_background_state()

    # -- construction -------------------------------------------------------

    def _build_sink(
        self, sink: FrameSink | str | None, options: dict[str, Any]
    ) -> tuple[str, FrameSink]:
        if sink is None:
            return discovery.NullSink.name, discovery.NullSink()
        if isinstance(sink, str):
            options.setdefault("led_count", self.config.led_count)
            return sink, discovery.create_sink(sink, **options)
        return getattr(sink, "name", type(sink).__name__), sink

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._loop, name="lefx-render", daemon=True)
        self._thread.start()
        logger.info(
            "service started sink=%s led_count=%s fps=%s effects=%s",
            self.sink_name,
            self.config.led_count,
            self.config.fps,
            len(self.library.registry),
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            self.runtime.close()
        self.library.close()
        self._started_at = None
        logger.info("service stopped")

    def __enter__(self) -> "ControllerService":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _loop(self) -> None:
        interval = 1.0 / self.config.fps
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.render_once(started)
            except Exception as exc:
                self._last_error = repr(exc)
                logger.exception("render loop iteration failed")
            self._stop.wait(max(0.0, interval - (time.monotonic() - started)))

    def render_once(self, now: float | None = None) -> None:
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._refresh_providers(moment)
            self.runtime.render_once(moment)
            self._render_count += 1
            self._publish_sink_state()
            self._persist_background_state()

    def _refresh_providers(self, now: float) -> None:
        """Poll each provider on its own schedule, not once per effect instance."""
        for name, provider in self.providers.items():
            refresh = getattr(provider, "refresh", None)
            if refresh is None:
                continue
            try:
                refresh(now)
            except Exception as exc:
                logger.warning("input provider %r failed to refresh: %s", name, exc)

    # -- status publication -------------------------------------------------

    def add_listener(self, listener: StatusListener) -> None:
        """Subscribe to service-level events such as the output going away.

        The engine has no concept of a device. An application that wants the
        ring to say something when the hardware disappears listens here and
        issues an ordinary command; that mapping stays out of the engine.
        """
        self._listeners.append(listener)

    def _publish_sink_state(self) -> None:
        status = self.sink.status()
        if status.available == self._sink_available:
            return
        self._sink_available = status.available
        payload = {"sink": self.sink_name, **status.to_dict()}
        logger.info("output %s (%s)", "available" if status.available else "unavailable", self.sink_name)
        self._emit("sink_changed", payload)

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event, payload)
            except Exception:
                logger.exception("status listener failed for %r", event)

    # -- background state persistence ---------------------------------------

    def restore_background_state(self) -> None:
        """Bring back the background state a previous run left behind.

        Only the background slot is persisted, and only for definitions that
        declare themselves restorable. The primary state is a live application
        concern and is not service configuration.

        Public because the catalogue can change after construction — after a
        source is registered, the state that could not be restored before may
        now exist.
        """
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        target = payload.get("effect_id")
        if not target:
            return
        try:
            self.runtime.set_state(
                target, payload.get("config"), slot=StateSlot.BACKGROUND, now=time.monotonic()
            )
            logger.info("restored background state %r", target)
        except Exception as exc:
            logger.warning("could not restore background state %r: %s", target, exc)

    def _persist_background_state(self) -> None:
        invocation = self.runtime.store.active(LayerId.BACKGROUND_STATE)
        signature = None if invocation is None else self._signature(invocation)
        if signature == self._persisted_signature:
            return
        self._persisted_signature = signature

        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            if invocation is None:
                self.state_file.unlink(missing_ok=True)
                return
            if not getattr(invocation.definition, "restorable", False):
                self.state_file.unlink(missing_ok=True)
                return
            self.state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "effect_id": invocation.effect_id,
                        "config": invocation.params,
                        "saved_at": time.time(),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("could not persist background state: %s", exc)

    @staticmethod
    def _signature(invocation: Invocation) -> str:
        return json.dumps(
            {"id": invocation.effect_id, "config": invocation.params}, sort_keys=True, default=str
        )

    # -- commands -----------------------------------------------------------

    def _command(self, action: Callable[[], Any]) -> Any:
        """Run a command, then render so the change is visible immediately."""
        with self._lock:
            result = action()
            self.runtime.render_once(time.monotonic())
            self._persist_background_state()
            return result

    def set_state(
        self, target: str, config: Mapping[str, Any] | None = None, *, slot: str = "primary",
        action: str = "on",
    ) -> dict[str, Any]:
        invocation = self._command(
            lambda: self.runtime.set_state(target, config, slot=slot, action=action)
        )
        return self._acknowledge("set", "state", target=target, slot=slot, action=action,
                                 invocation=invocation)

    def clear_state(self, *, slot: str = "primary") -> dict[str, Any]:
        self._command(lambda: self.runtime.clear_state(slot=slot))
        return self._acknowledge("clear", "state", slot=slot)

    def set_overlay(
        self, target: str, *, channel: str | None = None,
        config: Mapping[str, Any] | None = None, inputs: Mapping[str, Any] | None = None,
        action: str = "on",
    ) -> dict[str, Any]:
        invocation = self._command(
            lambda: self.runtime.set_overlay(
                target, channel=channel, config=config, inputs=inputs, action=action
            )
        )
        return self._acknowledge("set", "overlay", target=target, channel=channel,
                                 action=action, invocation=invocation)

    def update_overlay(self, channel: str, inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
        invocation = self._command(lambda: self.runtime.update_overlay(channel, inputs))
        return self._acknowledge("update", "overlay", channel=channel, invocation=invocation)

    def clear_overlay(self, channel: str) -> dict[str, Any]:
        self._command(lambda: self.runtime.clear_overlay(channel))
        return self._acknowledge("clear", "overlay", channel=channel)

    def emit_event(
        self, target: str, config: Mapping[str, Any] | None = None, *,
        priority: int | None = None, duration_ms: int | None = None,
    ) -> dict[str, Any]:
        invocation = self._command(
            lambda: self.runtime.emit_event(
                target, config, priority=priority, duration_ms=duration_ms
            )
        )
        return self._acknowledge("emit", "event", target=target, invocation=invocation)

    def set_output(
        self, *, brightness: float | None = None, enabled: bool | None = None
    ) -> dict[str, Any]:
        def apply() -> None:
            if brightness is not None:
                self.runtime.set_brightness(brightness)
            if enabled is not None:
                self.runtime.set_enabled(enabled)

        self._command(apply)
        return {
            "ok": True,
            "operation": "output",
            "brightness": self.runtime.output.brightness,
            "enabled": self.runtime.output.enabled,
        }

    def clear_all(self) -> dict[str, Any]:
        self._command(self.runtime.clear_all)
        return self._acknowledge("clear", "all")

    def _acknowledge(
        self, operation: str, subject: str, *, invocation: Invocation | None = None, **fields: Any
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": True, "operation": operation, "type": subject}
        payload.update({key: value for key, value in fields.items() if value is not None})
        if invocation is not None:
            slot = slot_for(invocation.layer)
            payload["applied"] = {
                "invocation_id": invocation.invocation_id,
                "effect_id": invocation.effect_id,
                "layer": invocation.layer.value,
                "slot": None if slot is None else slot.value,
                "channel": invocation.channel,
                "preset_id": invocation.preset_id,
                "config": dict(invocation.params),
                "duration_ms": invocation.duration_ms,
            }
        elif operation in {"set"}:
            payload["applied"] = None
        return payload

    # -- reads --------------------------------------------------------------

    def list_definitions(self, definition_type=None, *, details: bool = False) -> list[Any]:
        with self._lock:
            effects = self.library.registry.list_effects(definition_type=definition_type)
        if not details:
            return [effect.effect_id for effect in effects]
        return [presentation.definition(effect) for effect in effects]

    def list_presets(self, definition_type=None, *, details: bool = False) -> list[Any]:
        with self._lock:
            presets = self.library.registry.list_presets(definition_type=definition_type)
        if not details:
            return [item.preset_id for item in presets]
        return [presentation.preset(item) for item in presets]

    def show(self, target: str) -> dict[str, Any]:
        with self._lock:
            return presentation.resolved(target, self.library.registry.resolve(target))

    def status(self) -> dict[str, Any]:
        with self._lock:
            payload = self.runtime.status(time.monotonic())
        payload.update(
            {
                "service": {
                    "running": self._thread is not None and self._thread.is_alive(),
                    "started_at": self._started_at,
                    "render_count": self._render_count,
                    "last_error": self._last_error,
                    "sink": self.sink_name,
                },
                "effects": {
                    "definitions": len(self.library.registry),
                    "presets": len(self.library.registry.list_presets()),
                    "sources": self.library.sources(),
                },
                "input_providers": {
                    name: provider.status(time.monotonic())
                    for name, provider in self.providers.items()
                    if hasattr(provider, "status")
                },
                "installed": discovery.describe(),
            }
        )
        return payload

    def health(self) -> dict[str, Any]:
        sink = self.sink.status()
        return {
            "status": "ok" if sink.available and self._last_error is None else "degraded",
            "running": self._thread is not None and self._thread.is_alive(),
            "sink": {"name": self.sink_name, **sink.to_dict()},
            "render_count": self._render_count,
            "last_error": self._last_error,
        }

    # -- package sources ----------------------------------------------------

    def list_sources(self) -> list[dict[str, Any]]:
        with self._lock:
            return self.library.sources()

    def register_source(self, path: str, *, enabled: bool = True) -> dict[str, Any]:
        with self._lock:
            entry = self.library.add_source(path, enabled=enabled)
            self.runtime.set_registry(self.library.registry)
            return {"ok": True, "source": entry.to_dict(), "sources": self.library.sources()}

    def reload_sources(self) -> dict[str, Any]:
        with self._lock:
            self.library.reload()
            self.runtime.set_registry(self.library.registry)
            return {"ok": True, "sources": self.library.sources()}

    def remove_source(self, source_id: str) -> dict[str, Any]:
        with self._lock:
            self.library.remove_source(source_id)
            self.runtime.set_registry(self.library.registry)
            return {"ok": True, "sources": self.library.sources()}


__all__ = ["ControllerService", "StatusListener"]
