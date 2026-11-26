"""Declarative block catalogue shared by validation, the inspector and export."""

from dataclasses import dataclass
import math
import re
from typing import Any, Callable

from . import kernel


class DesignError(ValueError):
    """A rejected authoring operation; the previous design remains intact."""


@dataclass(frozen=True)
class Property:
    label: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, value: Any, path: str) -> None:
        if self.kind == "color":
            valid = isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value)
        elif self.kind == "bool":
            valid = type(value) is bool
        else:
            valid = type(value) in (int, float) and math.isfinite(value)
            if self.kind == "int":
                valid = valid and type(value) is int
            if valid:
                valid = (self.minimum is None or value >= self.minimum) and (
                    self.maximum is None or value <= self.maximum)
        if not valid:
            raise DesignError(f"{path}: ungültiger Wert {value!r} ({self.label}).")


@dataclass(frozen=True)
class Block:
    label: str
    category: str
    properties: dict[str, Property]
    evaluate: Callable
    version: int = 1

    def defaults(self):
        return {name: prop.default for name, prop in self.properties.items()}


POSITION = Property("Position (Umdrehungen)", "float", 0.0, 0, 1)
COLOR = Property("Farbe", "color", "#3399FF")
BRIGHTNESS = Property("Grundhelligkeit", "float", 1.0, 0, 1)
PHASE = Property("Phase (Umdrehungen)", "float", 0.0, 0, 1)
FREQUENCY = Property("Frequenz (Hz)", "float", 1.0, 0.001, 100)

BLOCKS = {
    "point": Block("Punkt", "element", dict(position=POSITION, color=COLOR, brightness=BRIGHTNESS), kernel.point),
    "segment": Block("Segment", "element", dict(position=POSITION,
        length=Property("Länge (Ringanteil)", "float", 0.25, 0, 1), color=COLOR, brightness=BRIGHTNESS), kernel.segment),
    "fill": Block("Vollfläche", "element", dict(color=COLOR, brightness=BRIGHTNESS), kernel.fill),
    "gradient": Block("Farbverlauf", "element", dict(color=COLOR,
        end_color=Property("Endfarbe", "color", "#FF9900"), brightness=BRIGHTNESS), kernel.gradient),
    "rotation": Block("Rotation", "animation", dict(
        rate=Property("Umdrehungen / Sekunde", "float", 0.25, 0, 100),
        reverse=Property("Rückwärts", "bool", False), phase=PHASE), kernel.rotation),
    "blink": Block("Blinken", "animation", dict(frequency=FREQUENCY, phase=PHASE,
        duty=Property("Einschaltdauer (Anteil)", "float", 0.5, 0, 1),
        minimum=Property("Minimalfaktor", "float", 0.0, 0, 1),
        maximum=Property("Maximalfaktor", "float", 1.0, 0, 1)), kernel.blink),
    "pulse": Block("Pulsieren (Helligkeitsshift)", "animation", dict(frequency=FREQUENCY, phase=PHASE,
        minimum=Property("Minimalshift (Prozentpunkte)", "float", -20.0, -100, 100),
        maximum=Property("Maximalshift (Prozentpunkte)", "float", 0.0, -100, 100)), kernel.pulse),
    "color_cycle": Block("Farbwechsel", "animation", dict(
        rate=Property("Farbzyklen / Sekunde", "float", 0.1, 0, 100), phase=PHASE), kernel.color_cycle),
    "sparkle": Block("Deterministisches Funkeln", "animation", dict(frequency=FREQUENCY,
        seed=Property("Seed", "int", 0, 0, 2147483647),
        density=Property("Leuchtender Anteil", "float", 0.5, 0, 1)), kernel.sparkle),
}

LAYER_PROPERTIES = {
    "opacity": Property("Deckkraft", "float", 1.0, 0, 1),
    "brightness_shift": Property("Helligkeitsshift (Prozentpunkte)", "float", 0.0, -100, 100),
    "mask_start": Property("Maske: Start (Umdrehungen)", "float", 0.0, 0, 1),
    "mask_length": Property("Maske: Ringanteil", "float", 1.0, 0, 1),
    "mask_invert": Property("Maske umkehren", "bool", False),
}

# The same catalogue functions are evaluated directly only for diagnostics;
# previews compile their exact source into the standalone generated effect.
kernel.ELEMENTS = {key: block.evaluate for key, block in BLOCKS.items() if block.category == "element"}
kernel.ANIMATIONS = {key: block.evaluate for key, block in BLOCKS.items() if block.category == "animation"}
