"""Hardware-Durchstich LAB-001-R01, Befunde F01 und F02, mit dem echten reSpeaker.

Ergänzt ``r01_reproduktion.py`` (Fake-Senke) um einen Lauf über die echte
USB-Ausgabe: dasselbe ``StudioWindow``, dieselben Menüaktionen, aber
``initial_output="respeaker"`` und **keine** ersetzte Senke.

Was dieser Lauf belegen kann: der Dienst rendert nach dem Katalog-Reload
fehlerfrei weiter, die Senke meldet sich verfügbar, die Frames, die über den
``TappedSink`` an das Gerät gehen, sind die des Labs, und der Lab-Status
stimmt mit dem Runtime-Zustand überein. Was er **nicht** belegen kann: was die
LEDs optisch zeigen. Niemand hat bei diesem Lauf auf den Ring geschaut.

F03 (Export) berührt keine Hardware und ist hier nicht enthalten.

    uv run python -I <dieses Skript> <ausgabe.json>
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from lefx.effect_creation.studio.session import StudioSession, device_in_use  # noqa: E402
from lefx.effect_creation.studio.window import StudioWindow  # noqa: E402

SETTLE_S = 0.4


class LoopErrors(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def emit(self, record) -> None:
        if "render loop iteration failed" in record.getMessage():
            self.count += 1


def trigger(window, menu: str, label: str) -> None:
    for entry in window.menuBar().actions():
        if entry.text().replace("&", "") == menu:
            for action in entry.menu().actions():
                if action.text() == label:
                    action.trigger()
                    return
    raise SystemExit(f"Menüeintrag fehlt: {menu} → {label}")


def settle() -> None:
    time.sleep(SETTLE_S)
    QApplication.processEvents()


def observe(window, shown) -> dict:
    lab = window.lab
    service = window.session.service
    runtime = service.runtime.status()
    layer = runtime["layers"]["primary_state"]
    sink = service.sink
    return {
        "sink_available": sink.status().available,
        "sink_detail": sink.status().detail,
        "frames_sent_to_sink": sink.frame_count,
        "last_frame_sent_equals_lab_frame": runtime["frame"] == list(shown),
        "last_frame_sent_is_black": runtime["frame"] == [0] * len(shown),
        "lab_output_active": lab.output.active,
        "send_box_checked": lab.send_box.isChecked(),
        "status_text": lab.output_state.text(),
        "message_text": lab.message.text(),
        "primary_state_effect": None if layer is None else layer["effect_id"],
        "service_last_error": service.status()["service"]["last_error"],
    }


def main() -> int:
    application = QApplication.instance() or QApplication([])
    del application
    busy = device_in_use()
    if busy is not None:
        raise SystemExit(f"Gerät belegt: {busy}")
    errors = LoopErrors()
    logging.getLogger("lefx.interfaces.service").addHandler(errors)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "packages"],
                                capture_output=True, text=True).stdout.strip())
    with tempfile.TemporaryDirectory(prefix="lab001-r01-hw-") as temporary:
        root = Path(temporary)
        session = StudioSession(search_paths=[], state_file=root / "background.json")
        window = StudioWindow(session, initial_output="respeaker")
        try:
            lab = window.lab
            lab.ask_before_discarding = False
            window.tabs.setCurrentWidget(lab)
            QApplication.processEvents()
            lab.load_example("two_points")
            lab.send_box.setChecked(True)
            if lab.clock.playing:
                lab.pause()
            shown = tuple(lab.frame.device)
            settle()
            sending = observe(window, shown)

            before = errors.count
            trigger(window, "Katalog", "Quellen neu laden")
            settle()
            after_reload = {"render_loop_failures_after_reload": errors.count - before,
                            **observe(window, shown)}

            trigger(window, "Ausgabe", "Alles löschen")
            settle()
            after_clear = observe(window, shown)

            lab.send_box.setChecked(True)
            settle()
            after_resume = observe(window, shown)

            lab.send_box.setChecked(False)
            settle()
            after_stop = observe(window, shown)
            report = {
                "commit": head,
                "uncommitted_changes_under_packages": dirty,
                "python": sys.version.split()[0],
                "device": "respeaker (echte USB-Ausgabe); optische LED-Anzeige nicht beobachtet",
                "output_name": session.output_name,
                "lab_frame": list(shown),
                "1_sending_paused": sending,
                "2_LAB-001-R01-F01_after_reload": after_reload,
                "3_LAB-001-R01-F02_after_clear": after_clear,
                "4_LAB-001-R01-F02_after_resume": after_resume,
                "5_after_unticking": after_stop,
            }
        finally:
            window.close()
            session.close()
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
