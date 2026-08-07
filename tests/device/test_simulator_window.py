"""The ring window, checked without anyone looking at it.

Qt is an optional extra, so these skip wherever it is not installed — which is
the normal state of a service machine and of the CI. What they are worth is
catching the mistakes that only appear when Qt is real: a signal whose signature
does not match its slot, a widget built before its layout, a paint that throws.
None of that shows up in a headless review of the file.

They do not check that the ring looks right. That needs eyes.
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("PySide6", reason="the ring window needs the gui extra")

# Must be set before the first QApplication: there is no display here.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from respeaker_led.simulator.ring import LedRingWidget  # noqa: E402

from .conftest import FakeWindow, free_port, until  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    """One QApplication for the module; Qt allows exactly one per process."""
    return QApplication.instance() or QApplication([])


def render(widget) -> QImage:
    """Paint into an image, which is the only way to prove painting works."""
    image = QImage(240, 240, QImage.Format.Format_RGB32)
    image.fill(0)
    widget.resize(240, 240)
    widget.render(image)
    return image


def test_the_ring_draws_at_any_size(qt_app):
    """The ring size is configuration; twelve is not baked in anywhere."""
    for led_count in (1, 5, 12, 24, 60):
        widget = LedRingWidget(led_count)
        widget.set_colors([0x00FF00] * led_count)
        assert render(widget).width() == 240


def test_black_is_drawn_as_black_not_as_off(qt_app):
    """``None`` means "contribute nothing"; 0x000000 is a colour and covers.

    Only opaque integers reach a sink, so what arrives at the window is always a
    colour. Painting black as "unlit" would misrepresent a ring the hardware
    would genuinely light dark.
    """
    widget = LedRingWidget(12)
    widget.set_colors([0x000000] * 12)
    dark = render(widget)

    widget.set_colors([0xFFFFFF] * 12)
    lit = render(widget)

    assert dark != lit, "black and white must not paint the same"


def test_a_frame_of_the_wrong_length_is_ignored(qt_app):
    widget = LedRingWidget(12)
    widget.set_colors([0xFF0000] * 12)
    before = render(widget)

    widget.set_colors([0x00FF00] * 6)

    assert render(widget) == before


def test_resizing_the_ring_clears_it(qt_app):
    widget = LedRingWidget(12)
    widget.set_colors([0xFF0000] * 12)
    widget.set_led_count(24)

    assert widget.led_count == 24
    # A frame for the old size must not be accepted against the new one.
    widget.set_colors([0xFF0000] * 12)
    assert render(widget) == render(LedRingWidget(24))


def test_the_window_connects_signals_that_actually_match_their_slots(qt_app):
    """The class of mistake that only surfaces once Qt is real.

    Builds the whole window against a live link, which is also the only place
    the client, the protocol and the widget are wired together the way the
    console script wires them.
    """
    from respeaker_led.simulator.link import SimulatorLink
    from respeaker_led.simulator.window import SimulatorWindow

    link = SimulatorLink(host="127.0.0.1", port=free_port(), led_count=8)
    link.start()
    window = SimulatorWindow(host=link.host, port=link.port, led_count=8)
    try:
        until(lambda: link.connected, "the window never reached the service")

        # The sliders report on connection, so a reading is already in flight.
        until(lambda: link.latest_inputs() is not None, "no reading arrived")
        reading = link.latest_inputs()
        assert reading["detection_state"] == "none"
        assert reading["direction_deg"] == 0.0

        # And a frame from the service side reaches the widget. It crosses
        # threads through a Qt signal, so it only lands once the event loop is
        # pumped — which is exactly the wiring under test.
        link.send_frame([0x0000FF] * 8, 0.0)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and window.ring._colors != [0x0000FF] * 8:
            qt_app.processEvents()
            time.sleep(0.01)
        assert window.ring._colors == [0x0000FF] * 8
    finally:
        window.close()
        link.close()


def test_the_window_is_never_imported_by_the_service_half():
    """The extra is only honest if nothing on the service path leads to Qt.

    Checked by reading the modules rather than by importing them: importing
    proves nothing here, because Qt happens to be installed in this environment.
    """
    import ast
    from pathlib import Path

    import respeaker_led.simulator as package

    root = Path(package.__file__).parent
    service_side = [
        "__init__.py",
        "registration.py",
        "link.py",
        "sink.py",
        "provider.py",
        "protocol.py",
        "client.py",
        "app.py",
    ]

    for name in service_side:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        # Only module level: app.py deliberately reaches for Qt inside main(),
        # which is what lets the console script's entry point be imported — and
        # its error message printed — on a machine without the extra.
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            assert not any(item.startswith("PySide6") for item in imported), (
                f"{name} imports Qt at module level"
            )
