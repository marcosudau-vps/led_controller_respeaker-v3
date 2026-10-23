"""Versioned, validated design documents, independent of Qt and runtime state."""

from copy import deepcopy
import keyword
import re
from uuid import uuid4

from lefx.sdk import RESERVED_PARAMETERS, DefinitionKind

from .blocks import BLOCKS, LAYER_PROPERTIES, DesignError

FORMAT = "lefx-studio"
VERSION = 1
MAX_OBJECTS = 2048


def identity():
    return uuid4().hex


def new_document():
    return {
        "format": FORMAT, "schema_version": VERSION, "revision": 0,
        "effect": {"id": "visual_effect", "title": "Visueller Effekt",
                   "description": "Mit LEFX Studio gestaltet.", "source_id": "studio-designs",
                   "kind": "state", "composition": "opaque", "duration_ms": 2000},
        "layers": [], "animations": [], "exposures": [],
    }


def identifier(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z][a-z0-9_]*", value)) and not keyword.iskeyword(value)


def fields(item, expected, path):
    if not isinstance(item, dict) or set(item) != set(expected.split()):
        raise DesignError(f"{path}: erwartet Felder {expected}.")


def text(value, path):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise DesignError(f"{path}: nichtleerer Text bis 4000 Zeichen erforderlich.")


def objects(document):
    def descendants(children):
        for child in children:
            yield child
            if child["type"] == "group":
                yield from descendants(child["children"])
    for layer in document["layers"]:
        yield layer
        yield from descendants(layer["children"])
    yield from document["animations"]


def find(document, target):
    for item in objects(document):
        if item["id"] == target:
            return item
    raise DesignError(f"Unbekanntes Objekt {target!r}.")


def property_specs(item):
    if item.get("type") == "group":
        return {}
    return LAYER_PROPERTIES if "blend" in item else BLOCKS[item["type"]].properties


def validate(document):
    fields(document, "format schema_version revision effect layers animations exposures", "Projekt")
    if document["format"] != FORMAT or type(document["schema_version"]) is not int or document["schema_version"] != VERSION:
        raise DesignError("Unbekanntes Studioformat oder unbekannte Formatversion.")
    if type(document["revision"]) is not int or document["revision"] < 0:
        raise DesignError("Revision muss eine nichtnegative Ganzzahl sein.")
    effect = document["effect"]
    fields(effect, "id title description source_id kind composition duration_ms", "Effekt")
    if not identifier(effect["id"]):
        raise DesignError("Effekt-ID muss ein Python-Bezeichner in snake_case sein.")
    for name in ("title", "description", "source_id"):
        text(effect[name], name)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", effect["source_id"]):
        raise DesignError("Ungültige Quellkennung.")
    if effect["kind"] not in {kind.value for kind in DefinitionKind}:
        raise DesignError("Unbekannter LEFX-Lebenszyklus.")
    if effect["composition"] not in ("opaque", "transparent"):
        raise DesignError("Ungültige Runtime-Komposition.")
    if type(effect["duration_ms"]) is not int or not 1 <= effect["duration_ms"] <= 600000:
        raise DesignError("Dauer muss zwischen 1 und 600000 ms liegen.")
    for name in ("layers", "animations", "exposures"):
        if not isinstance(document[name], list) or len(document[name]) > MAX_OBJECTS:
            raise DesignError(f"{name}: ungültige Liste oder zu viele Einträge.")
    if len(document["layers"]) > 64:
        raise DesignError("Maximal 64 Ebenen pro Effekt.")
    seen = set()
    by_id = {}

    def add(item):
        ident = item["id"]
        if not isinstance(ident, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", ident) or ident in seen:
            raise DesignError("Objekt-IDs müssen gültig und eindeutig sein.")
        seen.add(ident)
        by_id[ident] = item
        if len(seen) > MAX_OBJECTS:
            raise DesignError("Zu viele Objekte im Entwurf.")

    def properties(item, specs):
        if not isinstance(item["properties"], dict) or set(item["properties"]) != set(specs):
            raise DesignError(f"{item['id']}: Eigenschaften entsprechen nicht der Bausteindefinition.")
        for name, spec in specs.items():
            spec.validate(item["properties"][name], f"{item['id']}.{name}")
        props = item["properties"]
        if "minimum" in props and props["minimum"] > props["maximum"]:
            raise DesignError("Minimum darf Maximum nicht überschreiten.")

    def children(items, depth):
        if not isinstance(items, list) or len(items) > MAX_OBJECTS or depth > 8:
            raise DesignError("Ungültige Gruppe oder mehr als acht Gruppenebenen.")
        for item in items:
            if not isinstance(item, dict):
                raise DesignError("Element muss ein Objekt sein.")
            if item.get("type") == "group":
                fields(item, "id type name children", "Gruppe")
                text(item["name"], "Gruppenname")
                add(item)
                children(item["children"], depth + 1)
            else:
                block(item, "element")

    def block(item, category):
        fields(item, "id type version properties" + (" target" if category == "animation" else ""), "Baustein")
        if not isinstance(item["type"], str):
            raise DesignError("Ungültiger Bausteintyp.")
        definition = BLOCKS.get(item["type"])
        if definition is None or definition.category != category or type(item["version"]) is not int or item["version"] != definition.version:
            raise DesignError("Unbekannter Bausteintyp oder unbekannte Bausteinversion.")
        add(item)
        properties(item, definition.properties)

    for layer in document["layers"]:
        fields(layer, "id name enabled blend properties children", "Ebene")
        add(layer)
        text(layer["name"], "Ebenenname")
        if type(layer["enabled"]) is not bool or layer["blend"] not in ("over", "add", "max"):
            raise DesignError("Ungültiger Ebenenstatus oder Mischmodus.")
        properties(layer, LAYER_PROPERTIES)
        children(layer["children"], 0)
    layer_ids = {layer["id"] for layer in document["layers"]}
    bindings = set()
    for animation in document["animations"]:
        block(animation, "animation")
        if not isinstance(animation["target"], str) or animation["target"] not in layer_ids:
            raise DesignError("Animationen können ausschließlich an ganze Ebenen gebunden werden.")
        pair = (animation["target"], animation["type"])
        if pair in bindings:
            raise DesignError("Pro Ebene ist jeder Animationstyp nur einmal zulässig.")
        bindings.add(pair)
    names, exposed = set(), set()
    for entry in document["exposures"]:
        fields(entry, "name target property", "Öffentlicher Parameter")
        if not identifier(entry["name"]) or entry["name"] in names or entry["name"] in RESERVED_PARAMETERS:
            raise DesignError("Öffentliche Namen müssen eindeutig sein und dürfen nicht reserviert sein.")
        if not isinstance(entry["target"], str) or not isinstance(entry["property"], str):
            raise DesignError("Ungültige Eigenschaftsbindung.")
        target = by_id.get(entry["target"])
        if target is None or entry["property"] not in property_specs(target):
            raise DesignError("Öffentlicher Parameter verweist auf eine unbekannte Eigenschaft.")
        pair = (entry["target"], entry["property"])
        if pair in exposed:
            raise DesignError("Eine Eigenschaft darf nur einmal öffentlich gebunden werden.")
        names.add(entry["name"])
        exposed.add(pair)
    return deepcopy(document)
