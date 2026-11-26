"""Starting points for experiments, built with the editor's own operations.

Each one is one of the concept cases the Lab is meant to explore. They are
documents like any other: built through :class:`Editor` calls, validated by it,
and editable, savable and exportable once loaded. No Qt here.
"""

from __future__ import annotations

from typing import Callable

from lefx.effect_creation.visual import Editor

TWELFTH = 1 / 12


def two_points_rotating() -> dict:
    editor = Editor()
    editor.metadata(id="zwei_punkte", title="Zwei Punkte, gemeinsame Rotation")
    layer = editor.add_layer("Punkte")
    editor.add_element(layer, "point", position=0.0, color="#FF5533")
    editor.add_element(layer, "point", position=0.5, color="#3399FF")
    editor.add_animation(layer, "rotation", rate=0.25)
    return editor.document


def counter_rotating_segments() -> dict:
    editor = Editor()
    editor.metadata(id="gegenlaeufige_segmente", title="Gegenläufige Segmente")
    first = editor.add_layer("Segment A")
    editor.add_element(first, "segment", position=0.0, length=5 * TWELFTH, color="#FF3311")
    editor.add_animation(first, "rotation", rate=0.25)
    second = editor.add_layer("Segment B")
    editor.configure_layer(second, blend="add")
    editor.add_element(second, "segment", position=0.5, length=3 * TWELFTH, color="#1155FF")
    editor.add_animation(second, "rotation", rate=0.25, reverse=True)
    return editor.document


def alternating_pattern() -> dict:
    """A/B over the whole ring, from six points — no pattern block exists yet."""
    editor = Editor()
    editor.metadata(id="ab_muster", title="A/B-Muster (aus Punkten)")
    background = editor.add_layer("B-Farbe")
    editor.add_element(background, "fill", color="#202060")
    layer = editor.add_layer("A-Punkte")
    for index in range(0, 12, 2):
        editor.add_element(layer, "point", position=index * TWELFTH, color="#FFAA00")
    editor.add_animation(layer, "rotation", rate=1 / 12)
    return editor.document


def segment_with_colour_cycle() -> dict:
    editor = Editor()
    editor.metadata(id="segment_farbwechsel", title="Rotierendes Segment mit Farbwechsel")
    layer = editor.add_layer("Segment")
    editor.add_element(layer, "segment", length=5 * TWELFTH, color="#FF0000")
    editor.add_animation(layer, "rotation", rate=0.2)
    editor.add_animation(layer, "color_cycle", rate=0.5)
    return editor.document


def overlapping_layers() -> dict:
    editor = Editor()
    editor.metadata(id="ueberlagerung", title="Überlagerung über einem Verlauf")
    ground = editor.add_layer("Hintergrund")
    editor.add_element(ground, "gradient", color="#001133", end_color="#003311", brightness=0.6)
    sparks = editor.add_layer("Funkeln")
    editor.configure_layer(sparks, blend="max")
    editor.add_element(sparks, "fill", color="#FFFFFF", brightness=0.8)
    editor.add_animation(sparks, "sparkle", frequency=4.0, density=0.2, seed=7)
    pulse = editor.add_layer("Puls")
    editor.configure_layer(pulse, blend="add")
    editor.add_element(pulse, "segment", length=4 * TWELFTH, color="#AA00FF")
    editor.add_animation(pulse, "pulse", frequency=0.5, minimum=-80.0, maximum=0.0)
    editor.add_animation(pulse, "rotation", rate=0.1, reverse=True)
    return editor.document


EXAMPLES: dict[str, tuple[str, Callable[[], dict]]] = {
    "two_points": ("Zwei Punkte rotieren gemeinsam", two_points_rotating),
    "counter_rotation": ("Zwei Segmente, gegenläufig auf zwei Ebenen", counter_rotating_segments),
    "alternating": ("A/B-Muster über den ganzen Ring", alternating_pattern),
    "colour_cycle": ("Rotierendes Segment mit Farbwechsel", segment_with_colour_cycle),
    "overlap": ("Ebenen überlagern sich (Verlauf, Funkeln, Puls)", overlapping_layers),
}

__all__ = ["EXAMPLES"]
