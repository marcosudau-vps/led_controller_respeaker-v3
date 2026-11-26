"""Preview snapshots and a compile cache. Experimental, Studio Lab only.

A preview never edits the design. Looking at one layer alone, or checking which
positions no layer covers, is done on a validated *copy* whose layer switches
or composition differ — the stored document, its revision and its undo history
are untouched, and nothing is registered anywhere.

Every frame still comes from ``compile_design``: the same generated source the
export packs. The cache only makes sure that source is generated once per
distinct snapshot rather than once per animation frame.
"""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass

from lefx.sdk import scale_color

from .compiler import compile_design
from .model import validate
from .persistence import digest

COMPOSITE = "composite"
ISOLATED = "isolated"
FOCUS = "focus"
VIEWS = {COMPOSITE: "Gesamteffekt", ISOLATED: "Ebene isoliert", FOCUS: "Ebene hervorgehoben"}

CONTEXT_DIM = 0.22
"""How bright the other layers stay in the focus view. Display only."""


def snapshot(document, *, solo=None, without=None, reveal_coverage=False):
    """A validated copy of ``document`` with preview-only switches applied.

    ``solo`` keeps exactly that layer, shown even if it is hidden in the full
    effect. ``without`` drops one layer. ``reveal_coverage`` compiles the copy as
    transparent, so positions no layer covers come back as ``None`` instead of
    the black an opaque effect sends there; nothing else changes.
    """
    copy = deepcopy(validate(document))
    if solo is not None:
        for layer in copy["layers"]:
            layer["enabled"] = layer["id"] == solo
    if without is not None:
        for layer in copy["layers"]:
            if layer["id"] == without:
                layer["enabled"] = False
    if reveal_coverage:
        copy["effect"]["composition"] = "transparent"
    return validate(copy)


class PreviewCompiler:
    """Compiles each distinct snapshot once; a small LRU keeps recent ones."""

    def __init__(self, capacity=12, compile=compile_design):
        self._compile = compile
        self._capacity = capacity
        self._cache = OrderedDict()
        self.compilations = 0

    def compiled(self, document):
        key = digest(document)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        result = self._compile(document)
        self.compilations += 1
        self._cache[key] = result
        while len(self._cache) > self._capacity:
            self._cache.popitem(last=False)
        return result


@dataclass(frozen=True)
class PreviewFrame:
    """What the Lab shows and sends for one moment.

    ``colors`` is the frame in the renderer's own terms: an RGB integer, or
    ``None`` where nothing was contributed. ``device`` is the same frame as a
    sink receives it, where nothing contributed means off.
    """

    elapsed: float
    colors: tuple

    @property
    def device(self):
        return tuple(0 if value is None else value for value in self.colors)


class PreviewPlan:
    """The compiled designs one view of one document needs.

    Built once per document revision and view change; ``frame(t)`` is then only
    a render call on designs that are already compiled.
    """

    def __init__(self, compiler, document, view=COMPOSITE, layer=None, reveal_coverage=True):
        layer_ids = [item["id"] for item in document["layers"]]
        if view != COMPOSITE and layer not in layer_ids:
            view, layer = COMPOSITE, None
        self.view, self.layer = view, layer
        self.revision = document["revision"]
        # Coverage is revealed by compiling transparent; an effect that is
        # already transparent needs no second look at it.
        reveal = reveal_coverage and document["effect"]["composition"] == "opaque"
        if view == COMPOSITE:
            self._main = compiler.compiled(snapshot(document, reveal_coverage=reveal))
            self._context = None
        else:
            self._main = compiler.compiled(snapshot(document, solo=layer, reveal_coverage=True))
            self._context = None if view == ISOLATED else compiler.compiled(
                snapshot(document, without=layer, reveal_coverage=reveal))

    def frame(self, elapsed, led_count):
        colors = self._main.render(elapsed, led_count)
        if self._context is not None:
            behind = self._context.render(elapsed, led_count)
            colors = [own if own is not None else (None if other is None else scale_color(other, CONTEXT_DIM))
                      for own, other in zip(colors, behind)]
        return PreviewFrame(float(elapsed), tuple(colors))


__all__ = ["COMPOSITE", "FOCUS", "ISOLATED", "VIEWS", "PreviewCompiler", "PreviewFrame",
           "PreviewPlan", "snapshot"]
