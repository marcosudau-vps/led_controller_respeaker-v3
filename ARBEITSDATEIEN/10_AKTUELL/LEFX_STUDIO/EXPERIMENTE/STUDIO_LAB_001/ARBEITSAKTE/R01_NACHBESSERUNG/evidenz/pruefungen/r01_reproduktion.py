"""Reproduktions- und Verifikationsprotokoll LAB-001-R01, Befunde F01 bis F03.

Läuft gegen den jeweils ausgecheckten Stand und gibt beobachtete Werte als
JSON aus. Dasselbe Skript wird vor und nach der Korrektur ausgeführt; die beiden
Ausgaben liegen daneben und sind direkt vergleichbar.

Umgebung: das echte ``StudioWindow`` mit eingebettetem ``ControllerService`` und
laufendem Render-Thread, Qt offscreen. Ersetzt ist **nur** die Gerätesenke —
durch eine aufzeichnende Fake-Senke. Keine echte Hardware.

    uv run python -I <dieses Skript> <ausgabe.json>
"""

from __future__ import annotations

import hashlib
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

from lefx.effect_creation.studio import session as studio_session  # noqa: E402
from lefx.effect_creation.studio.lab import page as page_module  # noqa: E402
from lefx.effect_creation.studio.session import StudioSession  # noqa: E402
from lefx.effect_creation.studio.window import StudioWindow  # noqa: E402
from lefx.effect_creation.visual import compiler  # noqa: E402
from lefx.sdk import SinkStatus  # noqa: E402

SETTLE_S = 0.4  # bei 30 fps rund zwölf Ticks des Render-Threads


class RecordingSink:
    name = "fake-respeaker"

    def __init__(self) -> None:
        self.frames: list[tuple[int, ...]] = []
        self.closed = False

    def apply_frame(self, frame) -> None:
        self.frames.append(tuple(frame.leds))

    def status(self):
        return SinkStatus(available=True, detail=None)

    def close(self) -> None:
        self.closed = True


class LoopErrors(logging.Handler):
    """Zählt fehlgeschlagene Iterationen des Render-Threads."""

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


def open_window(root: Path):
    os.environ["LEFX_STATE_ROOT"] = str(root)
    sinks: list[RecordingSink] = []

    def create_sink(name, **options):
        sinks.append(RecordingSink())
        return sinks[-1]

    studio_session.discovery.create_sink = create_sink
    session = StudioSession(search_paths=[], state_file=root / "background.json")
    window = StudioWindow(session, initial_output="fake-respeaker")
    window.lab.ask_before_discarding = False
    window.tabs.setCurrentWidget(window.lab)
    QApplication.processEvents()
    return window, sinks


def start_sending(window) -> tuple[int, ...]:
    lab = window.lab
    lab.load_example("two_points")
    lab.send_box.setChecked(True)
    if lab.clock.playing:
        lab.pause()
    return tuple(lab.frame.device)


def lab_view(window) -> dict:
    lab = window.lab
    layer = window.session.service.runtime.status()["layers"]["primary_state"]
    return {
        "lab_output_active": lab.output.active,
        "send_box_checked": lab.send_box.isChecked(),
        "status_text": lab.output_state.text(),
        "message_text": lab.message.text(),
        "primary_state_effect": None if layer is None else layer["effect_id"],
        "service_last_error": window.session.service.status()["service"]["last_error"],
    }


def f01(root: Path, errors: LoopErrors) -> dict:
    window, sinks = open_window(root)
    try:
        shown = start_sending(window)
        before = errors.count
        trigger(window, "Katalog", "Quellen neu laden")
        time.sleep(SETTLE_S)
        QApplication.processEvents()
        return {
            "scenario": "Lab sendet, Vorschau pausiert, Katalog → Quellen neu laden, danach kein neuer Frame",
            "preview_playing": window.lab.clock.playing,
            "render_loop_failures_after_reload": errors.count - before,
            "device_last_frame_equals_lab_frame": sinks[-1].frames[-1] == shown,
            "device_last_frame": list(sinks[-1].frames[-1]),
            "lab_frame": list(shown),
            **lab_view(window),
        }
    finally:
        window.close()
        window.session.close()


def f02(root: Path) -> dict:
    window, sinks = open_window(root)
    try:
        shown = start_sending(window)
        trigger(window, "Ausgabe", "Alles löschen")
        time.sleep(SETTLE_S)
        QApplication.processEvents()
        observed = {
            "scenario": "Lab sendet, Ausgabe → Alles löschen",
            "device_last_frame_is_black": sinks[-1].frames[-1] == (0,) * len(shown),
            **lab_view(window),
        }
        # Wiederaufnahme laut Regel: Häkchen erneut setzen.
        window.lab.send_box.setChecked(True)
        time.sleep(SETTLE_S)
        QApplication.processEvents()
        observed["after_resume"] = {
            "device_last_frame_equals_lab_frame": sinks[-1].frames[-1] == shown,
            **lab_view(window),
        }
        return observed
    finally:
        window.close()
        window.session.close()


def f03(root: Path) -> dict:
    window, _ = open_window(root)
    lab = window.lab
    target = root / "export" / "kept.lefx"
    try:
        lab.load_example("counter_rotation")
        first = lab.export_to(target)
        sha_before = hashlib.sha256(target.read_bytes()).hexdigest()

        lab.load_example("two_points")  # ein anderes Design liegt jetzt auf der Seite

        def disagree(path, document, **kwargs):
            return {"effect_id": "x", "compared": 8, "mismatches": [0.5]}

        compiler.verify_package = disagree
        if hasattr(page_module, "verify_package"):
            page_module.verify_package = disagree  # Seite importierte den Namen vor der Korrektur selbst

        result = lab.export_to(target)
        sha_after = hashlib.sha256(target.read_bytes()).hexdigest()
        return {
            "scenario": "gültiges Paket liegt am Ziel; neuer Export mit fehlschlagender Abschlussprüfung",
            "first_export_check": None if first is None else first.get("check"),
            "failing_export_returned": None if result is None else {"path": result.get("path"),
                                                                      "check": result.get("check")},
            "target_sha256_before": sha_before,
            "target_sha256_after": sha_after,
            "target_unchanged": sha_before == sha_after,
            "leftover_files_in_target_dir": sorted(p.name for p in target.parent.iterdir()
                                                   if p.name != target.name),
            "message_text": lab.message.text(),
        }
    finally:
        window.close()
        window.session.close()


def main() -> int:
    application = QApplication.instance() or QApplication([])
    del application
    errors = LoopErrors()
    logging.getLogger("lefx.interfaces.service").addHandler(errors)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "packages"],
                                capture_output=True, text=True).stdout.strip())
    with tempfile.TemporaryDirectory(prefix="lab001-r01-") as temporary:
        root = Path(temporary)
        report = {
            "commit": head,
            "uncommitted_changes_under_packages": dirty,
            "python": sys.version.split()[0],
            "device": "fake-respeaker (RecordingSink) — keine echte Hardware",
            "LAB-001-R01-F01": f01(root / "f01", errors),
            "LAB-001-R01-F02": f02(root / "f02"),
            "LAB-001-R01-F03": f03(root / "f03"),
        }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if len(sys.argv) > 1:
        # Direkt als UTF-8 schreiben: die Windows-Konsole kodiert sonst cp1252.
        Path(sys.argv[1]).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
