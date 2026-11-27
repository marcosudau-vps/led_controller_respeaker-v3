from copy import deepcopy
from dataclasses import replace

import pytest

from lefx.sdk import DefinitionKind, StateSlot
from lefx.config_widget import (
    EventSpec, FeedbackDocument, HostCapabilities, LedVerb, LefxCatalogueAdapter,
    MemoryCatalogue, validate_call,
)
from lefx.config_widget.testlab import STT_SAMPLE


def test_real_catalogue_and_every_preset(catalogue):
    entries = catalogue.entries()
    assert {source["source_id"] for source in catalogue.sources()} == {"core-set", "smartspeaker-set"}
    assert all(source["error"] is None for source in catalogue.sources())
    assert {entry.form for entry in entries} == set(DefinitionKind)
    assert sum(entry.preset is not None for entry in entries) > 50
    for entry in entries:
        assert catalogue.resolve(entry.qualified_id).qualified_id == entry.qualified_id
        assert entry.source_id and entry.package_id and entry.definition.version >= 1
        assert set(entry.resolve_config()) == set(entry.definition.parameter_schema)
    preset = next(e for e in entries if e.definition.id == "solid_fill" and e.preset)
    assert preset.resolve_config({"color": "#D76000"})["color"] == "#D76000"
    assert preset.preset == catalogue.resolve(preset.qualified_id).preset


def test_unknown_ambiguous_and_removed_targets(catalogue):
    entry = catalogue.resolve("solid_fill")
    assert catalogue.resolve("core-set.solid_fill").qualified_id == entry.qualified_id
    twin = replace(entry, qualified_id="other::solid_fill", source_id="other")
    memory = MemoryCatalogue([entry, twin])
    with pytest.raises(ValueError, match="Mehrdeutiges Ziel.*core-set.*other"):
        memory.resolve("solid_fill")
    assert memory.resolve("other::solid_fill") is twin
    with pytest.raises(ValueError, match="No effect or preset"):
        catalogue.resolve("missing_target")
    with LefxCatalogueAdapter.installed(("smartspeaker-set",)) as smaller:
        assert validate_call({"set_state": "solid_fill"}, smaller)


@pytest.mark.parametrize("raw", [
    {"set_state": "core-set::solid_fill", "slot": "background", "action": "toggle",
     "config": {"color": "#007733"}},
    {"clear_state": "primary"},
    {"set_overlay": "countdown_ring", "action": "on", "config": {"duration_ms": "3s"}},
    {"emit_event": "pulse_signal", "priority": -15},
    {"emit_event": "success_event", "duration_ms": None, "priority": None},
    {"set_output": {"brightness": .3, "enabled": False}},
    {"set_output": {"enabled": True, "brightness": None}},
])
def test_valid_calls(raw, catalogue):
    assert validate_call(raw, catalogue, HostCapabilities.voice_stt()) == ()


@pytest.mark.parametrize(("raw", "field"), [
    ({"set_overlay": "level_meter"}, "set_overlay"),
    ({"set_overlay": "countdown_ring", "action": "off"}, "action"),
    ({"set_state": "pulse_signal"}, "set_state"),
    ({"set_state": "solid_fill", "slot": "bottom"}, "slot"),
    ({"set_state": "ready_state", "config": "oops"}, "config"),
    ({"set_state": "solid_fill", "config": {"brightness": "nan"}}, "config.brightness"),
    ({"clear_state": "primary", "config": {}}, "led"),
    ({"emit_event": "success_event", "duration_ms": 60001}, "duration_ms"),
    ({"emit_event": "pulse_signal", "duration_ms": 60000}, "duration_ms"),
    ({"emit_event": "success_event", "duration_ms": True}, "duration_ms"),
    ({"emit_event": "success_event", "priority": True}, "priority"),
    ({"set_output": {"enabled": 0}}, "enabled"),
    ({"set_output": {"brightness": 2}}, "brightness"),
    ({"set_output": {}}, "set_output"),
])
def test_invalid_calls(raw, field, catalogue):
    assert field in [issue.field for issue in validate_call(raw, catalogue)]


def test_host_capabilities(catalogue):
    restricted = HostCapabilities(slots=(StateSlot.PRIMARY,), allow_duration=False,
                                  allow_priority=False, state_actions=("on",))
    event = EventSpec("app.done", "Fertig", verbs=frozenset({LedVerb.EMIT_EVENT}))
    assert validate_call({"clear_state": "primary"}, catalogue, restricted, event)[0].field == "led"
    assert validate_call({"clear_state": "background"}, catalogue, restricted)[0].field == "slot"
    assert validate_call({"set_state": "solid_fill", "action": "off"}, catalogue, restricted)[0].field == "action"
    issues = validate_call({"emit_event": "pulse_signal", "duration_ms": 100, "priority": 0},
                           catalogue, restricted, event)
    assert {issue.field for issue in issues} == {"duration_ms", "priority"}


def test_event_with_declared_duration_override(catalogue):
    entry = catalogue.resolve("pulse_signal")
    supported = replace(entry, definition=replace(entry.definition, supports_duration_override=True))
    provider = MemoryCatalogue([supported])
    call = {"emit_event": "pulse_signal", "duration_ms": 60000}
    assert validate_call(call, provider) == ()
    call["duration_ms"] += 1
    assert validate_call(call, provider)[0].field == "duration_ms"


def test_document_preserves_order_opaque_data_and_scalar_form():
    section = deepcopy(STT_SAMPLE)
    section["unknown"] = {"a": None}
    section["events"]["other"] = {"led": None, "extensions": {"beta": True}}
    section["events"]["uninterpreted"] = "literal"
    section["events"]["without_led"] = {"sound": None}
    section["events"]["unsupported"] = {"led": {"future_verb": {"data": None}}}
    document = FeedbackDocument(section)
    draft = document.led_rules()
    assert document.with_led_rules(draft) == section
    first = "server.transcription.completed"
    draft[first][0]["config"]["duration_ms"] = 1500
    updated = document.with_led_rules(draft)
    assert list(section["events"]) == list(updated["events"])
    for key, original in section["events"].items():
        if key != first:
            assert updated["events"][key] == original
    assert updated["events"][first]["sound"] == section["events"][first]["sound"]
    assert updated["events"][first]["app"] == section["events"][first]["app"]
    assert updated["events"][first]["led"][1]["action"] is None
    assert section["events"][first]["led"][0]["config"]["duration_ms"] == 700
    assert document.led_rules()[first][0]["config"]["duration_ms"] == 700
