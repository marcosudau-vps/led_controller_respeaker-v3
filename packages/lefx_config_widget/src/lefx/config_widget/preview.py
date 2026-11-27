"""Real LEFX frames in a disposable runtime with one latest-frame mailbox."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from math import isfinite
from threading import Condition, Thread
from time import monotonic
from typing import Any, Callable, Mapping, Protocol

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from lefx.engine.config import EngineConfig
from lefx.engine.errors import EngineError
from lefx.engine.registry import EffectRegistry
from lefx.engine.runtime import EffectRuntime
from lefx.sdk import DefinitionKind, InputMode, OutputFrame, SinkStatus
from lefx.sdk.validation import normalize_runtime_inputs

from .widgets import LedRingPreview


class MemoryFrameSink:
    """FrameSink owned by one preview session. Only the last frame is retained."""

    def __init__(self):
        self.latest: OutputFrame | None = None
        self.closed = False

    def apply_frame(self, frame: OutputFrame):
        if not self.closed:
            self.latest = frame

    def status(self) -> SinkStatus:
        return SinkStatus(available=not self.closed)

    def close(self):
        self.closed = True


@dataclass(frozen=True)
class PreviewRequest:
    target: str
    config: Mapping[str, Any] | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    slot: str | None = None
    duration_ms: int | None = None
    priority: int | None = None
    led_count: int = 12
    brightness: float = 1.0


class PreviewAdapter(Protocol):
    def start(self, request: PreviewRequest, now: float) -> None: ...
    def frame(self, now: float) -> OutputFrame: ...
    def close(self) -> None: ...


class PreviewSession:
    """Deterministic preview. Instantiate/use/close on the same worker thread."""

    def __init__(self, registry: EffectRegistry):
        self.registry = registry
        self.runtime: EffectRuntime | None = None
        self.sink: MemoryFrameSink | None = None

    def start(self, request: PreviewRequest, now: float):
        definition = self.registry.resolve(request.target).effect.definition
        if not isfinite(request.brightness) or not 0 <= request.brightness <= 1:
            raise ValueError("Vorschauhelligkeit muss zwischen 0 und 1 liegen.")
        inputs = normalize_runtime_inputs(definition, request.inputs)
        missing = [name for name, param in definition.runtime_input_schema.items()
                   if param.required and inputs.get(name) is None]
        if missing:
            raise ValueError("Testeingaben fehlen: " + ", ".join(missing))

        providers = {}
        policy = definition.input_sampling
        if policy is not None and policy.mode is InputMode.PULL:
            if policy.provider_id:
                if not inputs:
                    raise ValueError(f"Testeingaben für {policy.provider_id} fehlen.")
                providers[policy.provider_id] = lambda _context: inputs
            elif inputs:
                raise ValueError("Dieser Effekt verwendet eine eigene Pull-Quelle für Laufzeitwerte.")

        sink = MemoryFrameSink()
        runtime = EffectRuntime(
            self.registry, sink=sink, input_providers=providers,
            config=EngineConfig(led_count=request.led_count),
        )
        runtime.set_brightness(request.brightness)
        target, config = request.target, request.config
        try:
            if definition.kind is DefinitionKind.STATE:
                runtime.set_state(target, config, slot=request.slot, now=now)
            elif definition.kind is DefinitionKind.EVENT:
                runtime.emit_event(target, config, duration_ms=request.duration_ms,
                                   priority=request.priority, now=now)
            elif definition.kind is DefinitionKind.TIMED_OVERLAY:
                runtime.set_overlay(target, config=config, now=now)
            else:
                runtime.set_overlay(target, config=config, inputs=inputs, channel="preview", now=now)
        except Exception:
            runtime.close()
            raise
        self.close()
        self.runtime, self.sink = runtime, sink

    def frame(self, now: float) -> OutputFrame:
        if self.runtime is None:
            raise RuntimeError("Preview is stopped")
        self.runtime.render_once(now)
        return self.sink.latest

    def close(self):
        if self.runtime is not None:
            self.runtime.close()
            self.runtime = None


class PreviewWorker:
    """Own a preview adapter off the GUI thread. New jobs replace pending jobs."""

    def __init__(self, *, fps=30):
        if not isfinite(fps) or fps <= 0:
            raise ValueError("Preview fps must be positive and finite")
        self._condition = Condition()
        self._interval = 1 / fps
        self._thread = None
        self._generation = 0
        self._closed = False
        self._job = None
        self._latest = None

    def play(self, factory: Callable[[], PreviewAdapter], request: PreviewRequest):
        with self._condition:
            if self._closed:
                raise RuntimeError("Preview worker is closed")
            self._generation += 1
            self._latest = None
            self._job = (factory, deepcopy(request))
            if self._thread is None:
                self._thread = Thread(target=self._render, name="LEFX Preview", daemon=True)
                self._thread.start()
            self._condition.notify()

    def stop(self):
        with self._condition:
            self._generation += 1
            self._job = self._latest = None
            self._condition.notify()

    def close(self):
        with self._condition:
            self._closed = True
            self._generation += 1
            self._job = self._latest = None
            self._condition.notify()

    def wait(self, timeout=None):
        """Join after close from a caller that can wait outside the GUI thread."""
        if self._thread is not None:
            self._thread.join(timeout)
        return self._thread is None or not self._thread.is_alive()

    def take(self):
        with self._condition:
            current, self._latest = self._latest, None
            return current

    def _publish(self, generation, value):
        with self._condition:
            if generation == self._generation:
                self._latest = value

    def _render(self):
        active, generation, adapter = None, -1, None
        try:
            while True:
                with self._condition:
                    if self._closed:
                        break
                    if self._generation == generation and active is None:
                        self._condition.wait()
                        continue
                    changed = generation != self._generation
                    if changed:
                        generation, active = self._generation, self._job
                started = monotonic()
                try:
                    if changed:
                        if adapter is not None:
                            previous, adapter = adapter, None
                            previous.close()
                        if active is not None:
                            factory, request = active
                            adapter = factory()
                            adapter.start(request, started)
                    if adapter is not None:
                        self._publish(generation, adapter.frame(monotonic()))
                except Exception as exc:
                    self._publish(generation, f"Vorschau: {exc}")
                    if adapter is not None:
                        broken, adapter = adapter, None
                        try:
                            broken.close()
                        except Exception:
                            pass
                    active = None
                with self._condition:
                    if generation == self._generation and active is not None and not self._closed:
                        self._condition.wait(timeout=max(0, self._interval - (monotonic() - started)))
        finally:
            if adapter is not None:
                adapter.close()


class PreviewPanel(QWidget):
    """Qt ring and controls. The host supplies the adapter and a request builder."""

    error_changed = Signal(str)

    def __init__(self, factory, request_builder, parent=None):
        super().__init__(parent)
        self._factory, self._builder = factory, request_builder
        self._worker = None
        self._lifecycle = {}
        self.destroyed.connect(lambda *_, workers=self._lifecycle: _close_worker(workers))
        self._playing = False
        self.ring = LedRingPreview(self, diameter=112)
        self.ring.setMinimumHeight(96)
        self.start_button = QPushButton("Start / Wiederholen", self)
        self.stop_button = QPushButton("Stopp", self)
        self.stop_button.setEnabled(False)
        self.state = QLabel(self)
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        self.state.setWordWrap(True)
        self.led_count = QSpinBox(self)
        self.led_count.setRange(1, 256)
        self.led_count.setValue(12)
        self.brightness = QSpinBox(self)
        self.brightness.setRange(0, 100)
        self.brightness.setValue(100)
        self.brightness.setSuffix(" %")
        form = QFormLayout()
        form.addRow("LEDs", self.led_count)
        form.addRow("Vorschauhelligkeit", self.brightness)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.ring)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.state)
        self._poll = QTimer(self, interval=33)
        self._poll.timeout.connect(self._read)
        self._debounce = QTimer(self, interval=180, singleShot=True)
        self._debounce.timeout.connect(self.play)
        self.start_button.clicked.connect(self.play)
        self.stop_button.clicked.connect(self.stop)
        self.led_count.valueChanged.connect(self.schedule_update)
        self.brightness.valueChanged.connect(self.schedule_update)

    def schedule_update(self):
        if self._playing:
            self._worker.stop()
            self._debounce.start()

    def play(self):
        self._debounce.stop()
        try:
            count = self.led_count.value()
            request = self._builder(count, self.brightness.value() / 100)
            if self._worker is None:
                self._worker = self._lifecycle["worker"] = PreviewWorker()
            self._worker.play(self._factory(), request)
        except (EngineError, TypeError, ValueError, KeyError) as exc:
            self.stop()
            self.state.setText(str(exc))
            self.error_changed.emit(str(exc))
            return
        if self.ring.led_count != count:
            self.ring.configure(led_count=count, diameter=112)
        self._playing = True
        self.state.setText("Vorschau läuft")
        self.stop_button.setEnabled(True)
        self._poll.start()

    def stop(self):
        self._playing = False
        self._debounce.stop()
        self._poll.stop()
        if self._worker is not None:
            self._worker.stop()
        self.stop_button.setEnabled(False)
        self.state.setText("Vorschau gestoppt")

    def hideEvent(self, event):
        self._release()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._release()
        super().closeEvent(event)

    def _release(self):
        self.stop()
        _close_worker(self._lifecycle)
        self._worker = None

    def _read(self):
        value = self._worker.take()
        if isinstance(value, OutputFrame):
            self.ring.set_value(value.leds)
        elif isinstance(value, str):
            self.stop()
            self.state.setText(value)
            self.error_changed.emit(value)


def _close_worker(workers):
    worker = workers.pop("worker", None)
    if worker is not None:
        worker.close()
