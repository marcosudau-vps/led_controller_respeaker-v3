"""A Qt-only view for RGB pixels, independent of any renderer."""

from math import cos, isfinite, radians, sin

from PySide6.QtCore import QPointF, QSize
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QWidget


class LedRingPreview(QWidget):
    """Display RGB ints (0xRRGGBB), QColor-compatible strings or transparent None."""

    def __init__(self, parent=None, *, led_count=12, diameter=168,
                 start_angle=-90, clockwise=True):
        super().__init__(parent)
        self._pixels = ()
        self.setAccessibleName("LED-Ring")
        self.configure(led_count=led_count, diameter=diameter,
                       start_angle=start_angle, clockwise=clockwise)

    def configure(self, *, led_count, diameter=168, start_angle=-90, clockwise=True):
        if type(led_count) is not int or led_count < 1:
            raise ValueError("led_count must be a positive integer")
        if diameter < 1 or not isfinite(start_angle):
            raise ValueError("Invalid diameter or angle")
        self.led_count = led_count
        self.diameter = diameter
        self.start_angle = start_angle
        self.clockwise = clockwise
        if len(self._pixels) != led_count:
            self.clear()
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return QSize(self.diameter, self.diameter)

    def value(self):
        return tuple(QColor(pixel) if pixel is not None else None for pixel in self._pixels)

    def set_value(self, pixels):
        colors = []
        for pixel in pixels:
            if pixel is None:
                colors.append(None)
                continue
            if type(pixel) is int:
                if not 0 <= pixel <= 0xFFFFFF:
                    raise ValueError(f"Invalid RGB pixel {pixel!r}")
                color = QColor.fromRgb(pixel)
            else:
                color = QColor(pixel)
            if not color.isValid():
                raise ValueError(f"Invalid RGB pixel {pixel!r}")
            colors.append(color)
        if len(colors) != self.led_count:
            raise ValueError(f"Expected {self.led_count} LEDs, got {len(colors)}")
        self._pixels = tuple(colors)
        self.update()

    def clear(self):
        self._pixels = (None,) * self.led_count
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height(), self.diameter)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = side * 0.37
        dot = min(side * 0.073, radius * sin(radians(180 / max(self.led_count, 2))) * .77)
        palette = self.palette()
        painter.setPen(QPen(palette.color(QPalette.ColorRole.Mid), 1))
        painter.setBrush(palette.brush(QPalette.ColorRole.AlternateBase))
        painter.drawEllipse(center, radius + dot * 1.7, radius + dot * 1.7)
        painter.setBrush(palette.brush(QPalette.ColorRole.Base))
        painter.drawEllipse(center, max(0, radius - dot * 1.7), max(0, radius - dot * 1.7))
        step = (360 if self.clockwise else -360) / self.led_count
        for index, color in enumerate(self._pixels):
            angle = radians(self.start_angle + index * step)
            point = center + QPointF(radius * cos(angle), radius * sin(angle))
            painter.setBrush(color if color is not None
                             else palette.brush(QPalette.ColorRole.Midlight))
            painter.drawEllipse(point, dot, dot)
