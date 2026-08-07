"""The ring display.

Ported from the old PySide6 demo, with its two defects fixed: the LED count is a
parameter rather than a literal twelve, and the widget no longer reaches into a
controller — it is given colours and draws them, which is all a display does.

Black is drawn as black. In a composed frame ``None`` means "contribute
nothing"; ``0x000000`` is a colour and covers what is under it. Only opaque
integers reach a sink, so what arrives here is always a colour — and painting
one of them as "off" would misrepresent a ring the hardware would light dark.

Importing this module needs PySide6. Nothing on the service side imports it.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

BODY_COLOR = QColor(20, 22, 28)
RIM_COLOR = QColor(40, 44, 52)
SOCKET_COLOR = QColor(32, 35, 42)


class LedRingWidget(QWidget):
    """Draws one LED per position, arranged clockwise from the top."""

    def __init__(self, led_count: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self._led_count = max(1, int(led_count))
        self._colors: list[int] = [0] * self._led_count

    @property
    def led_count(self) -> int:
        return self._led_count

    def set_led_count(self, led_count: int) -> None:
        """Resize the ring — the service announces its size on connection."""
        count = max(1, int(led_count))
        if count == self._led_count:
            return
        self._led_count = count
        self._colors = [0] * count
        self.update()

    def set_colors(self, colors: list[int]) -> None:
        """Show one frame. A frame of the wrong length is not drawn at all.

        Padding or truncating would put colours on positions the sender never
        addressed, which is a worse answer than the ring simply not moving.
        """
        if len(colors) != self._led_count:
            return
        self._colors = list(colors)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt's spelling
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() / 2.0
        center_y = self.height() / 2.0
        radius = min(self.width(), self.height()) / 2.0 - 25.0

        painter.setPen(QPen(RIM_COLOR, 4))
        painter.setBrush(BODY_COLOR)
        painter.drawEllipse(
            int(center_x - radius - 10),
            int(center_y - radius - 10),
            int((radius + 10) * 2),
            int((radius + 10) * 2),
        )

        # Keep the dots from overlapping once the ring is densely populated,
        # and from becoming absurd when it holds three.
        spacing = 2.0 * math.pi * radius / self._led_count
        led_radius = max(3.0, min(14.0, spacing * 0.35))

        for index, color_int in enumerate(self._colors):
            # Zero at the top, increasing clockwise: the same convention
            # position_for_angle uses, so LED n is where an effect expects it.
            angle = math.radians(index * 360.0 / self._led_count - 90.0)
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)

            painter.setPen(QPen(SOCKET_COLOR, 1))
            painter.setBrush(
                QColor((color_int >> 16) & 0xFF, (color_int >> 8) & 0xFF, color_int & 0xFF)
            )
            painter.drawEllipse(
                int(x - led_radius),
                int(y - led_radius),
                int(led_radius * 2),
                int(led_radius * 2),
            )

        painter.end()


__all__ = ["LedRingWidget"]
