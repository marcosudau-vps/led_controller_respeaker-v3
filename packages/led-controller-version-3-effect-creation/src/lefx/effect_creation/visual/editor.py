"""Transactional UI-independent editing commands, snapshots, undo and redo."""

from copy import deepcopy
import logging

from .blocks import BLOCKS, LAYER_PROPERTIES, DesignError
from .model import find, identity, new_document, objects, validate

logger = logging.getLogger(__name__)


class Editor:
    def __init__(self, document=None):
        self._document = validate(new_document() if document is None else document)
        self._undo = []
        self._redo = []
        self._listeners = []

    @property
    def document(self):
        return deepcopy(self._document)

    @property
    def revision(self):
        return self._document["revision"]

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def subscribe(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self):
        for listener in tuple(self._listeners):
            try:
                listener(self.document)
            except Exception:
                # An observer cannot make a committed operation appear rejected.
                logger.exception("Design observer failed")

    def _change(self, operation):
        candidate = self.document
        result = operation(candidate)
        if candidate == self._document:
            return result
        candidate["revision"] = self.revision + 1
        candidate = validate(candidate)
        self._undo.append(self._document)
        self._undo = self._undo[-100:]
        self._redo.clear()
        self._document = candidate
        self._notify()
        return result

    def undo(self):
        self._history(self._undo, self._redo)

    def redo(self):
        self._history(self._redo, self._undo)

    def _history(self, origin, destination):
        if not origin:
            return
        candidate = deepcopy(origin.pop())
        candidate["revision"] = self.revision + 1
        destination.append(self._document)
        self._document = candidate
        self._notify()

    def metadata(self, **values):
        self._change(lambda doc: doc["effect"].update(values))

    def add_layer(self, name="Ebene"):
        ident = identity()
        def operation(doc):
            doc["layers"].append(dict(id=ident, name=name, enabled=True, blend="over",
                properties={name: spec.default for name, spec in LAYER_PROPERTIES.items()}, children=[]))
        self._change(operation)
        return ident

    def add_group(self, parent, name="Gruppe"):
        ident = identity()
        def operation(doc):
            self._children(find(doc, parent)).append(dict(id=ident, type="group", name=name, children=[]))
        self._change(operation)
        return ident

    @staticmethod
    def _children(item):
        if "children" not in item:
            raise DesignError("Dieses Objekt kann keine Elemente enthalten.")
        return item["children"]

    def add_element(self, parent, block_type="point", **properties):
        return self._add_block(parent, block_type, "element", properties)

    def add_animation(self, target, block_type="rotation", **properties):
        return self._add_block(target, block_type, "animation", properties)

    def _add_block(self, target, block_type, category, properties):
        block = BLOCKS.get(block_type)
        if block is None or block.category != category:
            raise DesignError("Unbekannter Bausteintyp.")
        ident = identity()
        item = dict(id=ident, type=block_type, version=block.version,
                    properties={**block.defaults(), **properties})
        def operation(doc):
            if category == "animation":
                item["target"] = target
                doc["animations"].append(item)
            else:
                self._children(find(doc, target)).append(item)
        self._change(operation)
        return ident

    def set_property(self, target, name, value):
        self._change(lambda doc: find(doc, target)["properties"].__setitem__(name, value))

    def rename(self, target, name):
        def operation(doc):
            item = find(doc, target)
            if "name" not in item:
                raise DesignError("Nur Ebenen und Gruppen haben einen Namen.")
            item["name"] = name
        self._change(operation)

    def configure_layer(self, target, *, enabled=None, blend=None):
        def operation(doc):
            item = next((layer for layer in doc["layers"] if layer["id"] == target), None)
            if item is None:
                raise DesignError("Keine Ebene ausgewählt.")
            if enabled is not None:
                item["enabled"] = enabled
            if blend is not None:
                item["blend"] = blend
        self._change(operation)

    def expose(self, target, property_name, public_name):
        self._change(lambda doc: doc["exposures"].append(
            dict(name=public_name, target=target, property=property_name)))

    def unexpose(self, public_name):
        def operation(doc):
            doc["exposures"] = [item for item in doc["exposures"] if item["name"] != public_name]
        self._change(operation)

    @staticmethod
    def _container(doc, target):
        def visit(items):
            for index, item in enumerate(items):
                if item["id"] == target:
                    return items, index
                if "children" in item:
                    found = visit(item["children"])
                    if found is not None:
                        return found
            return None
        found = visit(doc["layers"]) or visit(doc["animations"])
        if found is None:
            raise DesignError("Objekt nicht gefunden.")
        return found

    @staticmethod
    def _ids(item):
        result = {item["id"]}
        for child in item.get("children", []):
            result.update(Editor._ids(child))
        return result

    def remove(self, target):
        def operation(doc):
            container, index = self._container(doc, target)
            removed = self._ids(container.pop(index))
            removed.update(item["id"] for item in doc["animations"] if item["target"] in removed)
            doc["animations"] = [item for item in doc["animations"] if item["id"] not in removed]
            doc["exposures"] = [item for item in doc["exposures"] if item["target"] not in removed]
        self._change(operation)

    def move(self, target, parent=None, index=0):
        def operation(doc):
            container, old_index = self._container(doc, target)
            item = container[old_index]
            if item in doc["animations"]:
                raise DesignError("Animationsbindungen werden nicht über den Inhaltsbaum verschoben.")
            if "blend" in item:
                if parent is not None:
                    raise DesignError("Ebenen können nur in der Ebenenliste verschoben werden.")
                destination = doc["layers"]
            else:
                if parent in self._ids(item):
                    raise DesignError("Eine Gruppe kann nicht in sich selbst verschoben werden.")
                destination = self._children(find(doc, parent))
            container.pop(old_index)
            destination.insert(max(0, min(len(destination), index)), item)
        self._change(operation)

    def duplicate(self, target):
        new_id = identity()
        def operation(doc):
            container, index = self._container(doc, target)
            original = container[index]
            if original in doc["animations"]:
                raise DesignError("Ein Animationstyp darf nicht doppelt an dieselbe Ebene gebunden werden.")
            copied = deepcopy(original)
            ids = {ident: identity() for ident in self._ids(original)}
            ids[target] = new_id
            def rewrite(item):
                item["id"] = ids[item["id"]]
                for child in item.get("children", []):
                    rewrite(child)
            rewrite(copied)
            if "name" in copied:
                copied["name"] += " (Kopie)"
            container.insert(index + 1, copied)
            if "blend" in copied:
                for animation in list(doc["animations"]):
                    if animation["target"] == target:
                        clone = deepcopy(animation)
                        clone["id"] = identity()
                        clone["target"] = new_id
                        doc["animations"].append(clone)
            # Exposures stay attached to the originals; copied properties become private.
        self._change(operation)
        return new_id

    def replace(self, document):
        candidate = validate(document)
        def operation(doc):
            doc.clear()
            doc.update(candidate)
        self._change(operation)
