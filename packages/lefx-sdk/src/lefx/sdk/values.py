"""Canonical value normalization at the system boundary.

LEFX is forgiving about how a value arrives and strict about what it stores.
``blau``, ``#0000FF`` and ``0x0000FF`` all mean the same colour; internally only
``#0000FF`` exists. Every parser here is total: it either returns the canonical
form or raises with a code, the rejected value and — where useful — suggestions.

Effect packages never call these. They receive values that are already
canonical, which is why a renderer needs no second input language of its own.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from .errors import ValueNormalizationError


@dataclass(slots=True, frozen=True)
class NamedColor:
    name: str
    value: int
    aliases: tuple[str, ...] = ()

    @property
    def hex_value(self) -> str:
        return f"#{self.value:06X}"


COLOR_CATALOG: tuple[NamedColor, ...] = (
    NamedColor("black", 0x000000, ("schwarz",)),
    NamedColor("white", 0xFFFFFF, ("weiss", "weiß")),
    NamedColor("red", 0xFF0000, ("rot",)),
    NamedColor("green", 0x00FF00, ("gruen", "grün")),
    NamedColor("blue", 0x0000FF, ("blau",)),
    NamedColor("cyan", 0x00FFFF, ("tuerkis", "türkis")),
    NamedColor("yellow", 0xFFFF00, ("gelb",)),
    NamedColor("orange", 0xFF8000, ()),
    NamedColor("purple", 0x8000FF, ("lila", "violett", "violet")),
    NamedColor("pink", 0xFF1493, ("rosa",)),
)

_COLOR_BY_ALIAS: dict[str, NamedColor] = {
    alias.casefold(): color
    for color in COLOR_CATALOG
    for alias in (color.name, *color.aliases)
}

_DURATION_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(ms|s)?$", re.IGNORECASE)
_PERCENT_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*%$")
_ANGLE_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:deg|°)?$", re.IGNORECASE)


def parse_color(value: Any) -> int:
    """Accept a colour name, ``#RRGGBB``, ``0xRRGGBB`` or an RGB integer."""
    if isinstance(value, bool):
        raise _invalid_color(value)
    if isinstance(value, int):
        if 0 <= value <= 0xFFFFFF:
            return value
        raise ValueNormalizationError(
            f"Color integer must be in range 0..0xFFFFFF, got {value!r}",
            code="color_out_of_range",
            value=value,
        )
    if not isinstance(value, str):
        raise _invalid_color(value)

    text = value.strip()
    named = _COLOR_BY_ALIAS.get(text.casefold())
    if named is not None:
        return named.value

    digits = text[1:] if text.startswith("#") else text[2:] if text.lower().startswith("0x") else ""
    if len(digits) == 6 and all(character in "0123456789abcdefABCDEF" for character in digits):
        return int(digits, 16)

    suggestions = tuple(
        difflib.get_close_matches(text.casefold(), sorted(_COLOR_BY_ALIAS), n=3, cutoff=0.55)
    )
    raise ValueNormalizationError(
        f"Unknown color {value!r}",
        code="unknown_color",
        value=value,
        suggestions=suggestions,
    )


def format_color(value: Any) -> str:
    """Canonical colour form: uppercase ``#RRGGBB``."""
    return f"#{parse_color(value):06X}"


def describe_color(value: Any) -> dict[str, Any]:
    parsed = parse_color(value)
    named = next((color for color in COLOR_CATALOG if color.value == parsed), None)
    payload: dict[str, Any] = {"hex": f"#{parsed:06X}"}
    if named is not None:
        payload["name"] = named.name
        payload["aliases"] = list(named.aliases)
    return payload


def parse_duration_ms(value: Any, *, minimum: int = 0) -> int:
    """Accept a number, ``1500ms`` or ``1.5s``; return whole milliseconds."""
    if isinstance(value, bool):
        raise _invalid_value("invalid_duration", "Duration must be numeric or use ms/s", value)
    if isinstance(value, (int, float)):
        milliseconds = float(value)
    elif isinstance(value, str):
        match = _DURATION_RE.fullmatch(value.strip())
        if match is None:
            raise _invalid_value(
                "invalid_duration",
                "Duration must use a value such as 1500ms or 1.5s",
                value,
            )
        milliseconds = float(match.group(1))
        if (match.group(2) or "ms").lower() == "s":
            milliseconds *= 1000.0
    else:
        raise _invalid_value("invalid_duration", "Duration must be numeric or use ms/s", value)

    rounded = int(round(milliseconds))
    if rounded < minimum:
        raise ValueNormalizationError(
            f"Duration must be >= {minimum}ms",
            code="duration_out_of_range",
            value=value,
        )
    return rounded


def parse_ratio(value: Any) -> float:
    """Accept ``0.5`` or ``50%``; return a float between 0 and 1."""
    if isinstance(value, bool):
        raise _invalid_value("invalid_ratio", "Ratio must be between 0 and 1 or use a percentage", value)
    if isinstance(value, (int, float)):
        ratio = float(value)
    elif isinstance(value, str):
        text = value.strip()
        percent = _PERCENT_RE.fullmatch(text)
        if percent is not None:
            ratio = float(percent.group(1)) / 100.0
        else:
            try:
                ratio = float(text)
            except ValueError as exc:
                raise _invalid_value(
                    "invalid_ratio",
                    "Ratio must be between 0 and 1 or use a percentage such as 50%",
                    value,
                ) from exc
    else:
        raise _invalid_value("invalid_ratio", "Ratio must be between 0 and 1 or use a percentage", value)
    if not 0.0 <= ratio <= 1.0:
        raise ValueNormalizationError(
            "Ratio must be between 0 and 1",
            code="ratio_out_of_range",
            value=value,
        )
    return ratio


def parse_angle_degrees(value: Any) -> float:
    """Accept ``90``, ``90deg`` or ``90°``; return a float in ``[0, 360)``."""
    if isinstance(value, bool):
        raise _invalid_value("invalid_angle", "Angle must be numeric or use deg", value)
    if isinstance(value, (int, float)):
        angle = float(value)
    elif isinstance(value, str):
        match = _ANGLE_RE.fullmatch(value.strip())
        if match is None:
            raise _invalid_value("invalid_angle", "Angle must use a value such as 90 or 90deg", value)
        angle = float(match.group(1))
    else:
        raise _invalid_value("invalid_angle", "Angle must be numeric or use deg", value)
    return angle % 360.0


def parse_bool(value: Any) -> bool:
    """Accept English and German switch words as well as ``0``/``1``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on", "ja", "an"}:
            return True
        if normalized in {"0", "false", "no", "off", "nein", "aus"}:
            return False
    raise _invalid_value(
        "invalid_boolean",
        "Boolean must be true/false, on/off, an/aus or ja/nein",
        value,
    )


def _invalid_color(value: Any) -> ValueNormalizationError:
    return ValueNormalizationError(
        "Color must be a named color, #RRGGBB, 0xRRGGBB or an RGB integer",
        code="invalid_color",
        value=value,
    )


def _invalid_value(code: str, message: str, value: Any) -> ValueNormalizationError:
    return ValueNormalizationError(message, code=code, value=value)
