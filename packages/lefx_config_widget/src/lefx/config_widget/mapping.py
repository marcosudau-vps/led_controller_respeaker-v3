"""Host events, LED call validation and the Voice STT V2 document adapter."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from lefx.engine.errors import CommandError
from lefx.engine.invocation import duration_from_config
from lefx.engine.layers import layer_for
from lefx.sdk import DefinitionKind, ParameterValidationError, StateSlot

from .catalogue import CatalogueProvider


class LedVerb(StrEnum):
    SET_STATE = "set_state"
    CLEAR_STATE = "clear_state"
    SET_OVERLAY = "set_overlay"
    EMIT_EVENT = "emit_event"
    SET_OUTPUT = "set_output"


FORMS = {
    LedVerb.SET_STATE: DefinitionKind.STATE,
    LedVerb.SET_OVERLAY: DefinitionKind.TIMED_OVERLAY,
    LedVerb.EMIT_EVENT: DefinitionKind.EVENT,
}
MODIFIERS = {
    LedVerb.SET_STATE: frozenset(("config", "slot", "action")),
    LedVerb.CLEAR_STATE: frozenset(),
    LedVerb.SET_OVERLAY: frozenset(("config", "action")),
    LedVerb.EMIT_EVENT: frozenset(("config", "duration_ms", "priority")),
    LedVerb.SET_OUTPUT: frozenset(),
}


@dataclass(frozen=True)
class EventSpec:
    id: str
    label: str
    group: str = ""
    description: str = ""
    verbs: frozenset[LedVerb] = frozenset(LedVerb)


@dataclass(frozen=True)
class HostCapabilities:
    verbs: frozenset[LedVerb] = frozenset(LedVerb)
    slots: tuple[StateSlot, ...] = (StateSlot.PRIMARY, StateSlot.BACKGROUND)
    state_actions: tuple[str, ...] = ("on", "off", "toggle")
    duration_max: int | None = 60000
    allow_duration: bool = True
    allow_priority: bool = True
    default_state_slot: StateSlot | None = None

    @classmethod
    def voice_stt(cls) -> HostCapabilities:
        return cls(default_state_slot=StateSlot.PRIMARY)

    def allowed(self, event: EventSpec) -> tuple[LedVerb, ...]:
        return tuple(verb for verb in LedVerb if verb in self.verbs and verb in event.verbs)


@dataclass(frozen=True)
class Diagnostic:
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


def call_verb(raw) -> LedVerb | None:
    if not isinstance(raw, Mapping):
        return None
    found = [verb for verb in LedVerb if verb in raw]
    return found[0] if len(found) == 1 else None


def unsupported_call(raw) -> str | None:
    verb = call_verb(raw)
    if verb is None:
        return "Unbekannte Aufrufform"
    extra = raw.keys() - {verb} - MODIFIERS[verb]
    if extra:
        return f"Unbekannte Aufruffelder {', '.join(sorted(map(str, extra)))}"
    if verb is LedVerb.SET_OUTPUT and isinstance(raw[verb], Mapping):
        extra = raw[verb].keys() - {"brightness", "enabled"}
        if extra:
            return f"Unbekannte Ausgabefelder {', '.join(sorted(map(str, extra)))}"
    return None


def validate_call(raw, catalogue: CatalogueProvider, capabilities=HostCapabilities(),
                  event: EventSpec | None = None) -> tuple[Diagnostic, ...]:
    """Validate the mapping contract and delegate effect rules to LEFX."""
    unsupported = unsupported_call(raw)
    if unsupported:
        return (Diagnostic("led", unsupported),)
    verb = call_verb(raw)
    if verb not in capabilities.verbs or (event and verb not in event.verbs):
        return (Diagnostic("led", f"{verb} ist für dieses Ereignis gesperrt"),)
    diagnostics = []

    def issue(field, message):
        diagnostics.append(Diagnostic(field, message))

    value = raw[verb]
    if verb is LedVerb.CLEAR_STATE:
        if value not in capabilities.slots:
            issue("slot", "Wähle einen erlaubten Slot.")
        return tuple(diagnostics)
    if verb is LedVerb.SET_OUTPUT:
        if not isinstance(value, Mapping):
            return (Diagnostic("set_output", "Erwartet wird ein Objekt."),)
        brightness, enabled = value.get("brightness"), value.get("enabled")
        if brightness is None and enabled is None:
            issue("set_output", "Gib Helligkeit oder einen Ausgabestatus an.")
        if brightness is not None and (
            type(brightness) not in (int, float) or not 0 <= brightness <= 1
        ):
            issue("brightness", "Erwartet wird eine Zahl zwischen 0 und 1.")
        if enabled is not None and type(enabled) is not bool:
            issue("enabled", "Erwartet wird true oder false.")
        return tuple(diagnostics)

    entry = None
    if not isinstance(value, str) or not value.strip():
        issue(str(verb), "Wähle einen Effekt oder ein Preset.")
    else:
        try:
            entry = catalogue.resolve(value)
            if entry.form is not FORMS[verb]:
                issue(str(verb), f"Erwartete Form: {FORMS[verb].value}.")
                entry = None
        except ValueError as exc:
            issue(str(verb), str(exc))

    if verb in (LedVerb.SET_STATE, LedVerb.SET_OVERLAY):
        allowed = capabilities.state_actions if verb is LedVerb.SET_STATE else ("on",)
        action = raw.get("action")
        if (action if action is not None else "on") not in allowed:
            issue("action", f"Erlaubt: {', '.join(allowed)}.")

    config = raw.get("config")
    params = None
    if config is not None and (not isinstance(config, Mapping)
                               or any(not isinstance(key, str) for key in config)):
        issue("config", "Erwartet wird ein Objekt mit Textschlüsseln oder null.")
    elif entry is not None:
        try:
            params = entry.resolve_config(config)
            for name, value in params.items():
                if isinstance(value, float) and not isfinite(value):
                    issue(f"config.{name}", "Erwartet wird eine endliche Zahl.")
        except ParameterValidationError as exc:
            diagnostics.extend(Diagnostic(problem.field, problem.message) for problem in exc.issues)
        except (OverflowError, ValueError, TypeError) as exc:
            issue("config", str(exc))

    if verb is LedVerb.SET_STATE:
        slot = raw.get("slot")
        if slot is None:
            slot = capabilities.default_state_slot
            if slot is None and entry is not None:
                slot = entry.definition.slots[0]
        if slot is not None:
            if slot not in capabilities.slots:
                issue("slot", "Wähle einen erlaubten Slot.")
            elif entry is not None:
                try:
                    layer_for(entry.definition, slot=StateSlot(slot))
                except CommandError as exc:
                    issue("slot", str(exc))

    if verb is LedVerb.EMIT_EVENT:
        duration, priority = raw.get("duration_ms"), raw.get("priority")
        maximum = capabilities.duration_max
        if duration is not None:
            if (not capabilities.allow_duration or type(duration) is not int
                    or duration < 1 or (maximum is not None and duration > maximum)):
                bounds = f"1 bis {maximum}" if maximum is not None else "mindestens 1"
                issue("duration_ms", f"Ganzzahl {bounds} ms oder weglassen."
                      if capabilities.allow_duration else "Der Host sperrt die Daueroption.")
            elif entry is not None and params is not None:
                try:
                    duration_from_config(entry.definition, params, override_ms=duration)
                except CommandError as exc:
                    issue("duration_ms", str(exc))
        if priority is not None and (not capabilities.allow_priority or type(priority) is not int):
            issue("priority", "Erwartet wird eine Ganzzahl oder ein ausgelassenes Feld."
                  if capabilities.allow_priority else "Der Host sperrt die Prioritätsoption.")
    return tuple(diagnostics)


_ABSENT = object()


def ordered_calls(rule) -> list:
    """Copy the raw calls of a single LED rule. Reject an opaque rule shape."""
    if rule is None:
        return []
    if isinstance(rule, Mapping):
        return [deepcopy(rule)]
    if isinstance(rule, (list, tuple)):
        return list(deepcopy(rule))
    raise ValueError("Die LED-Regel muss ein Objekt, eine Liste oder null sein.")


class FeedbackDocument:
    """Lossless adapter for the feedback_mappings section (version 2)."""

    def __init__(self, section: Mapping):
        if (type(section.get("schema_version")) is not int
                or section["schema_version"] != 2
                or not isinstance(section.get("events"), Mapping)):
            raise ValueError("Erwartet wird feedback_mappings mit schema_version 2 und events.")
        self._section = deepcopy(dict(section))

    def led_rules(self) -> dict:
        return {
            event: deepcopy(rule["led"]) for event, rule in self._section["events"].items()
            if isinstance(rule, Mapping) and "led" in rule
        }

    def opaque_events(self) -> tuple:
        """Event IDs whose complete rule cannot be edited through an LED view."""
        return tuple(key for key, raw in self._section["events"].items()
                     if not isinstance(raw, Mapping))

    def with_led_rules(self, rules: Mapping) -> dict:
        result = deepcopy(self._section)
        for event, original in self.led_rules().items():
            if event not in rules:
                del result["events"][event]["led"]
        for event, led in rules.items():
            previous = result["events"].get(event, _ABSENT)
            if previous is _ABSENT:
                result["events"][event] = {"led": deepcopy(led)}
            elif isinstance(previous, Mapping):
                previous["led"] = deepcopy(led)
            else:
                raise ValueError(f"Ereignis {event!r} hat eine unbekannte Regelform.")
        return result
