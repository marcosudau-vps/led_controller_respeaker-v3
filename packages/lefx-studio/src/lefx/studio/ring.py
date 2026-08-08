"""The ring the studio shows: what the device is being sent, as it is sent.

Not a second rendering of the effect — the frames come off the path to the
device, so what is drawn here and what the LEDs do cannot drift apart.

Two things this draws that the simulator's window deliberately does not. LED
indices, because when you are tuning an effect the question is usually "which
one is that" rather than "how does it look". And the half-LED sectors, because
a direction lands on one of ``2 * led_count`` of them and a ring without the
gaps marked makes calibrating one a matter of counting.

Black is drawn as black. ``0x000000`` is a colour that covers; an LED that is
off looks the same but means something else, and a monitor that showed them
alike would hide the difference exactly where it is being checked.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

BODY_COLOR = QColor(20, 22, 28)
RIM_COLOR = QColor(44, 48, 58)
SOCKET_COLOR = QColor(32, 35, 42)
INDEX_COLOR = QColor(120, 126, 140)
SECTOR_COLOR = QColor(70, 76, 92)
MARK_COLOR = QColor(210, 170, 60)


class RingMonitor(QWidget):
    """Draws one frame at a time, at whatever size it is given."""

    led_clicked = Signal(int)
    """Which LED was clicked. Calibrating is pointing at one and saying 'that one'."""

    def __init__(self, led_count: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._led_count = max(1, int(led_count))
        self._colors: list[int] = [0] * self._led_count
        self._show_indices = True
        self._show_sectors = False
        self._marked_sector: int | None = None
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # -- what it shows ------------------------------------------------------

    @property
    def led_count(self) -> int:
        return self._led_count

    def set_led_count(self, led_count: int) -> None:
        count = max(1, int(led_count))
        if count == self._led_count:
            return
        self._led_count = count
        self._colors = [0] * count
        self.update()

    def set_colors(self, colors: list[int] | tuple[int, ...]) -> None:
        """Take a frame. A frame of the wrong length is ignored, not reshaped.

        The same rule the sinks follow: padding would light positions the
        renderer never addressed, and the monitor exists to show what was sent.
        """
        values = list(colors)
        if len(values) != self._led_count:
            return
        self._colors = [int(value) & 0xFFFFFF for value in values]
        self.update()

    def set_show_indices(self, show: bool) -> None:
        self._show_indices = bool(show)
        self.update()

    def set_show_sectors(self, show: bool) -> None:
        """Draw the ``2 * led_count`` half-LED sectors a direction can land on."""
        self._show_sectors = bool(show)
        self.update()

    def mark_sector(self, sector: int | None) -> None:
        """Highlight one sector, for stepping through a calibration."""
        self._marked_sector = None if sector is None else int(sector) % (2 * self._led_count)
        self.update()

    # -- drawing ------------------------------------------------------------

    def _geometry(self) -> tuple[QPointF, float, float]:
        side = min(self.width(), self.height())
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        radius = side * 0.36
        led_size = max(6.0, min(side * 0.075, 2.0 * math.pi * radius / self._led_count * 0.62))
        return center, radius, led_size

    def _angle_of(self, index: int) -> float:
        """LED zero at the top, clockwise — the way the ring sits on a desk."""
        return math.radians(index * 360.0 / self._led_count - 90.0)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt's spelling
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center, radius, led_size = self._geometry()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BODY_COLOR)
        painter.drawEllipse(center, radius * 1.42, radius * 1.42)
        painter.setBrush(SOCKET_COLOR)
        painter.drawEllipse(center, radius * 0.55, radius * 0.55)
        painter.setPen(QPen(RIM_COLOR, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius * 1.42, radius * 1.42)

        if self._show_sectors:
            self._draw_sectors(painter, center, radius)

        for index, color_int in enumerate(self._colors):
            angle = self._angle_of(index)
            position = QPointF(
                center.x() + radius * math.cos(angle), center.y() + radius * math.sin(angle)
            )
            color = QColor(
                (color_int >> 16) & 0xFF, (color_int >> 8) & 0xFF, color_int & 0xFF
            )
            painter.setPen(QPen(RIM_COLOR, 1.0))
            painter.setBrush(color)
            painter.drawEllipse(position, led_size / 2.0, led_size / 2.0)

            if self._show_indices:
                painter.setPen(QPen(INDEX_COLOR))
                font = QFont(painter.font())
                font.setPointSizeF(max(6.0, led_size * 0.42))
                painter.setFont(font)
                label = QRectF(
                    center.x() + radius * 1.22 * math.cos(angle) - 12.0,
                    center.y() + radius * 1.22 * math.sin(angle) - 8.0,
                    24.0,
                    16.0,
                )
                painter.drawText(label, Qt.AlignmentFlag.AlignCenter, str(index))
        painter.end()

    def _draw_sectors(self, painter: QPainter, center: QPointF, radius: float) -> None:
        sectors = 2 * self._led_count
        for sector in range(sectors):
            angle = math.radians(sector * 360.0 / sectors - 90.0)
            inner = radius * 0.72
            outer = radius * 0.86 if sector % 2 else radius * 0.92
            marked = sector == self._marked_sector
            painter.setPen(QPen(MARK_COLOR if marked else SECTOR_COLOR, 3.0 if marked else 1.0))
            painter.drawLine(
                QPointF(center.x() + inner * math.cos(angle), center.y() + inner * math.sin(angle)),
                QPointF(center.x() + outer * math.cos(angle), center.y() + outer * math.sin(angle)),
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt's spelling
        center, radius, led_size = self._geometry()
        point = event.position()
        for index in range(self._led_count):
            angle = self._angle_of(index)
            spot = QPointF(
                center.x() + radius * math.cos(angle), center.y() + radius * math.sin(angle)
            )
            if math.hypot(point.x() - spot.x(), point.y() - spot.y()) <= led_size:
                self.led_clicked.emit(index)
                return


__all__ = ["RingMonitor"]
