"""The ring window: display plus the controls that stand in for microphones.

A full device double needs both halves. The ring shows what the hardware would
show; the controls produce what the hardware would measure, in the same shape and
the same ranges. Setting the direction here and watching ``direction_indicator``
follow is the same test as speaking into the array.

Everything the socket thread produces crosses into the GUI thread through Qt
signals. Painting from another thread is the classic way to make a Qt program
crash in ways that look like anything but threading.

Needs PySide6. Imported only by the window process.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import protocol
from .client import SimulatorClient
from .provider import DETECTION_STATES
from .ring import LedRingWidget

STYLE = """
QMainWindow, QWidget { background-color: #16181d; color: #d8dce4; }
QGroupBox { border: 1px solid #2b2f39; border-radius: 6px; margin-top: 10px; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #8d94a3; }
QLabel#status_ok { color: #5fd08a; }
QLabel#status_bad { color: #e08a5f; }
"""


class SimulatorWindow(QMainWindow):
    """The simulator's user interface, and the client that feeds it."""

    frame_received = Signal(list)
    led_count_received = Signal(int)
    connection_changed = Signal(bool, str)

    def __init__(
        self,
        *,
        host: str = protocol.DEFAULT_HOST,
        port: int | None = None,
        led_count: int = 12,
    ) -> None:
        super().__init__()
        self.setWindowTitle("reSpeaker LED — Simulator")
        self.setStyleSheet(STYLE)
        self.resize(420, 620)

        self.ring = LedRingWidget(led_count)
        self._build_ui()

        # Queued across threads by Qt, which is the point: the client's reader
        # thread emits, the GUI thread receives.
        self.frame_received.connect(self._on_frame)
        self.led_count_received.connect(self.ring.set_led_count)
        self.connection_changed.connect(self._on_connection)

        self.client = SimulatorClient(
            host=host,
            port=port,
            on_frame=lambda leds, _timestamp: self.frame_received.emit(leds),
            on_led_count=self.led_count_received.emit,
            on_state=lambda connected, detail: self.connection_changed.emit(
                connected, detail or ""
            ),
        )
        self.client.start()
        self._publish_controls()

    # -- construction -------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.status = QLabel("Verbinde …")
        self.status.setObjectName("status_bad")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)
        layout.addWidget(self.ring, stretch=1)
        layout.addWidget(self._build_controls())

        central = QWidget(self)
        central.setLayout(layout)
        self.setCentralWidget(central)

    def _build_controls(self) -> QGroupBox:
        box = QGroupBox("Simulierte Eingaben")
        form = QFormLayout()

        self.direction = QSlider(Qt.Orientation.Horizontal)
        # Whole degrees over the full circle: 360 is 0, so the range stops one
        # short of it — exactly the range the firmware reports.
        self.direction.setRange(0, 359)
        self.direction.valueChanged.connect(self._publish_controls)
        self.direction_label = QLabel("0°")

        row = QHBoxLayout()
        row.addWidget(self.direction, stretch=1)
        row.addWidget(self.direction_label)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Richtung", holder)

        self.detection = QComboBox()
        self.detection.addItems(DETECTION_STATES)
        self.detection.currentTextChanged.connect(self._publish_controls)
        form.addRow("Erkennung", self.detection)

        # The runtime input is nullable, and a device that measures nothing is a
        # case effects have to survive. Without this the null path could only be
        # reached by unplugging something.
        self.reporting = QCheckBox("Richtung melden")
        self.reporting.setChecked(True)
        self.reporting.toggled.connect(self._publish_controls)
        form.addRow("", self.reporting)

        box.setLayout(form)
        return box

    # -- signals ------------------------------------------------------------

    def _publish_controls(self) -> None:
        degrees = float(self.direction.value())
        self.direction_label.setText(f"{int(degrees)}°")
        self.client.set_controls(
            direction_deg=degrees if self.reporting.isChecked() else None,
            detection_state=self.detection.currentText(),
        )

    def _on_frame(self, leds: list) -> None:
        self.ring.set_colors([int(value) for value in leds])

    def _on_connection(self, connected: bool, detail: str) -> None:
        self.status.setText(
            f"Verbunden mit {self.client.host}:{self.client.port}"
            if connected
            else (detail or "Nicht verbunden")
        )
        self.status.setObjectName("status_ok" if connected else "status_bad")
        # Qt only re-evaluates the stylesheet when told the selector changed.
        self.status.style().polish(self.status)
        if not connected:
            self.ring.set_colors([0] * self.ring.led_count)

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt's spelling
        """Closing the window is the simulator's equivalent of unplugging."""
        self.client.stop()
        super().closeEvent(event)


__all__ = ["SimulatorWindow"]
