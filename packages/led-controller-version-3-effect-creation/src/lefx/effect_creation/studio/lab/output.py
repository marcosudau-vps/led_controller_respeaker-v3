"""The Lab's frames on the studio's output, through the ordinary device path.

The Lab owns its preview time — it can pause, scrub back and step — and the
engine's own clock cannot do any of that. So the Lab does not hand the engine
its design to run; it hands over each frame it has just rendered for the ring.
A tiny state definition, :data:`FEED_ID`, returns the most recent of them on
every engine tick. From there the frame takes the same way as any effect's:
composition, global brightness and on/off from the output settings, the
:class:`~lefx.effect_creation.studio.session.TappedSink`, the device.

So there is still one computation of the effect — the compiled design, in the
Lab — and the device shows exactly what the Lab ring shows, at the engine's
frame rate. Nothing is packed, no source is registered, no private registry is
replaced: the feed is added through the registry's public ``register_effect``
under its own source id.

A reload or a reopen replaces the registry while the engine keeps rendering,
and a paused preview sends no frame that could notice. So the output does not
wait for one: the session tells it before and after every rebuild. Before, the
feed's state is taken off its layer — the engine must never hold a state whose
definition has just gone, or every tick after it fails. After, the feed is put
back; if that is not possible, the output ends and says why.

What the Lab claims and what the engine does are compared, not assumed:
:attr:`LabOutput.carried` asks the runtime whether the feed is on its layer,
and :meth:`LabOutput.verify` ends the output when it is not — after
"Ausgabe → Alles löschen", for instance. A clear is not undone behind the
user's back: sending starts again only when it is asked for again.

Three refusals keep the device safe, all checked before anything is sent:

* a preview ring of a different size than the output is not sent at all — the
  reSpeaker sink expects twelve LEDs, and a frame of sixteen is no frame for it;
* no output open, no sending;
* a takeover clears what the Player had on the device, on purpose, so the two
  never mix on one ring. Only one embedded service exists, so Player,
  calibration and Lab never hold the USB device side by side.
"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from lefx.sdk import BaseEffect, ColorModel, CompositionMode, RenderContext, StateDefinition

from ..session import NULL_OUTPUT, StudioSession

logger = logging.getLogger("lefx.effect_creation.studio.lab.output")

FEED_ID = "studio_lab_live"
FEED_SOURCE = "studio-lab"


class _Latest:
    """One frame, swapped whole. A tuple assignment is atomic for the render thread."""

    frame: tuple[int, ...] | None = None


def feed_effect(latest: _Latest) -> type[BaseEffect]:
    class StudioLabFeed(BaseEffect):
        definition = StateDefinition(
            id=FEED_ID,
            title="Studio Lab (live)",
            description="Zeigt das gerade im Studio Lab berechnete Bild. Nur im Studio vorhanden.",
            color_model=ColorModel.NONE,
            composition=CompositionMode.OPAQUE,
        )

        def render(self, ctx: RenderContext) -> list[int | None]:
            frame = latest.frame
            if frame is None or len(frame) != ctx.led_count:
                return [0] * ctx.led_count
            return list(frame)

    return StudioLabFeed


class LabOutput:
    """Sends the Lab's frames to whatever output the session has open."""

    ENDED_FROM_OUTSIDE = (
        "Die Lab-Ausgabe liegt nicht mehr auf dem Gerät und wurde beendet. "
        "Zum Fortsetzen „An Ausgabe senden“ erneut aktivieren."
    )

    def __init__(self, session: StudioSession) -> None:
        self.session = session
        self._latest = _Latest()
        self.effect_class = feed_effect(self._latest)
        self.active = False
        self.on_ended: Callable[[str], None] | None = None
        """Told the reason whenever the output ends without :meth:`stop`."""
        self._unwatch = session.watch_rebuilds(self._on_rebuild)

    @property
    def target(self) -> str:
        return self.session.output_name

    @property
    def is_hardware(self) -> bool:
        return self.session.output_name != NULL_OUTPUT

    @property
    def carried(self) -> bool:
        """Whether the engine really shows the feed: on its layer, and resolvable."""
        if self.session.service is None or not self._feed_on_layer():
            return False
        entry = self.session.registry.effects.get(FEED_ID)
        return entry is not None and entry.effect_class is self.effect_class

    def problem(self, led_count: int) -> str | None:
        """Why frames of ``led_count`` positions cannot be sent, or ``None``."""
        if self.session.service is None:
            return "Keine Ausgabe geöffnet."
        if int(led_count) != self.session.led_count:
            return (
                f"Die Vorschau hat {led_count} LEDs, die Ausgabe {self.session.led_count}. "
                "Es wird nichts gesendet."
            )
        return None

    def start(self, frame: Sequence[int]) -> None:
        """Take over the output and show ``frame`` on it. Raises with the reason."""
        problem = self.problem(len(frame))
        if problem is not None:
            raise RuntimeError(problem)
        self._latest.frame = tuple(frame)
        self._attach()
        self.active = True

    def push(self, frame: Sequence[int]) -> None:
        """Replace the frame on the device; ends the output if nothing shows it any more."""
        if not self.active:
            return
        if self.problem(len(frame)) is not None:
            self.stop()
            return
        self._latest.frame = tuple(frame)
        self.verify()

    def verify(self, reason: str | None = None) -> bool:
        """Whether the output is still carried; if it claims to be and is not, end it.

        ``reason`` is what :attr:`on_ended` is told. Ending happens once: asking
        again afterwards only answers ``False``.
        """
        if not self.active:
            return False
        if self.carried:
            return True
        self._end(reason or self.ENDED_FROM_OUTSIDE)
        return False

    def stop(self) -> None:
        if not self.active:
            return
        self.active = False
        self._latest.frame = None
        self._retire()

    def close(self) -> None:
        """Stop, and stop listening to the session's rebuilds."""
        self.stop()
        self._unwatch()

    def _on_rebuild(self, phase: str) -> None:
        if phase == "before":
            # Off the layer while the definition still exists: the render
            # thread may tick between the rebuild and our "after".
            self._retire()
            return
        if not self.active:
            return
        frame = self._latest.frame or ()
        problem = self.problem(len(frame))
        if problem is not None:
            self._end(f"Lab-Ausgabe beendet: {problem}")
            return
        try:
            self._attach()
        except Exception as exc:
            logger.exception("restoring the Studio Lab feed failed")
            self._end(f"Lab-Ausgabe nach dem Neuladen nicht wiederherstellbar und beendet: {exc}")

    def _end(self, reason: str) -> None:
        was_active = self.active
        self.active = False
        self._latest.frame = None
        self._retire()
        logger.info("Studio Lab output ended: %s", reason)
        if was_active and self.on_ended is not None:
            self.on_ended(reason)

    def _feed_on_layer(self) -> bool:
        service = self.session.service
        if service is None:
            return False
        layer = service.runtime.status()["layers"]["primary_state"]
        return layer is not None and layer["effect_id"] == FEED_ID

    def _retire(self) -> None:
        """Take the feed's state off the engine, if it is there. Never raises."""
        try:
            if self._feed_on_layer():
                self.session.service.clear_state()
        except Exception:
            logger.exception("clearing the Studio Lab state failed")

    def _attach(self) -> None:
        registry = self.session.registry
        existing = registry.effects.get(FEED_ID)
        if existing is not None and existing.effect_class is not self.effect_class:
            registry.remove_source(FEED_SOURCE)
            existing = None
        if existing is None:
            registry.register_effect(self.effect_class, source_id=FEED_SOURCE)
        self.session.clear_everything()
        self.session.play_state(FEED_ID, {})
        logger.info("Studio Lab sends to %s", self.session.output_name)


__all__ = ["FEED_ID", "FEED_SOURCE", "LabOutput", "feed_effect"]
