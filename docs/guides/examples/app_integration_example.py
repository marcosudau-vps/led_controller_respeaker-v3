"""LEFX V3 Integration Example: Smart Assistant Application

Dieses Beispiel zeigt, wie der LEFX V3 LED-Controller (`led-controller-version-3`)
direkt in eine eigene Python-Anwendung eingebettet werden kann.

Voraussetzung / Installation:
    pip install led-controller-version-3

Ausführung dieses Beispiels:
    python app_integration_example.py
"""

from __future__ import annotations

import sys
import time

# Im echten Projekt: `from lefx.interfaces import ControllerService, ControllerClient`
try:
    from lefx.interfaces.client import ControllerClient
    from lefx.interfaces.service import ControllerService
except ImportError:
    print("ERR: 'led-controller-version-3' ist nicht im Python-Pfad installiert.")
    print("Bitte ausführen: pip install led-controller-version-3")
    sys.exit(1)


# ============================================================================
# 1. VARIANTE A: Direct In-Process Embedding mit ControllerService
# ============================================================================
class SmartVoiceAssistantApp:
    """Beispiel einer Sprachassistenten-Anwendung mit direktem LED-Controller."""

    def __init__(self, sink_name: str = "null") -> None:
        """Initialisiert die Anwendung und den LED-Controller.

        :param sink_name: 'respeaker' (USB-Hardware), 'simulator' (GUI) oder 'null' (Headless).
        """
        print(f"[App] Initialisiere ControllerService mit sink='{sink_name}'...")
        self.service = ControllerService(
            sink=sink_name,
            led_count=12,
            fps=30.0,
        )

    def run_demo_workflow(self) -> None:
        """Demonstriert einen typischen Sprachassistenten-Lebenszyklus."""
        # Service starten (startet Render-Thread und Device-Provider)
        self.service.start()
        print("[App] Service gestartet.")

        try:
            # 1. Bereitschaftszustand (Standby / Ready)
            print("\n--- Step 1: Bereit / Standby ---")
            self.service.set_state("ready_state")
            time.sleep(0.5)

            # 2. Wake-Word erkannt! -> Event emittieren + State auf 'listening'
            print("\n--- Step 2: Wake-Word erkannt! ---")
            self.service.emit_event("wakeword_detected")
            self.service.set_state("listening", config={"color": "#00AAFF"})
            time.sleep(0.5)

            # 3. Controlled Overlay für Level Meter / Lautstärke aufschalten
            # 'config' sind statische Parameter (z.B. color), 'inputs' sind dynamische Runtime-Inputs (z.B. progress)
            print("\n--- Step 3: Level Meter Controlled Overlay aufschalten ---")
            self.service.set_overlay(
                "level_meter",
                channel="volume",
                config={"color": "#00FFCC"},
                inputs={"progress": 0.75},
            )
            time.sleep(0.5)

            # Level Meter über update_overlay aktualisieren
            print("[App] Level Meter via update_overlay auf progress=0.95 aktualisieren...")
            self.service.update_overlay(
                "volume",
                inputs={"progress": 0.95},
            )
            time.sleep(0.5)

            # Overlay manuell wieder entfernen
            self.service.clear_overlay("volume")

            # 4. Nachdenken / Verarbeiten (Thinking / Processing)
            print("\n--- Step 4: Sprache verarbeiten (Thinking) ---")
            self.service.set_state("thinking")
            time.sleep(0.5)

            # 5. Antwort ausgeben (Speaking)
            print("\n--- Step 5: Antwort sprechen (Speaking) ---")
            self.service.set_state("speaking")
            time.sleep(0.5)

            # 6. Aktion erfolgreich abgeschlossen -> Confirm Event
            print("\n--- Step 6: Bestätigungs-Event ---")
            self.service.emit_event("confirm_event")
            time.sleep(0.5)

            # 7. Mikrofon stummschalten (Mic Mute State)
            print("\n--- Step 7: Mikrofon stummgeschaltet ---")
            self.service.set_state("mic_mute")
            time.sleep(0.5)

            # 8. Zurück in den Bereit-Zustand
            print("\n--- Step 8: Zurück in Bereitschaft ---")
            self.service.set_state("ready_state")
            time.sleep(0.5)

        finally:
            # Sauberes Herunterfahren des Render-Threads
            print("\n[App] Stoppe ControllerService...")
            self.service.stop()
            print("[App] Service beendet.")


# ============================================================================
# 2. VARIANTE B: Python Context Manager (with-Statement)
# ============================================================================
def run_context_manager_demo() -> None:
    """Demonstriert die Nutzung von ControllerService als Context Manager."""
    print("\n==================================================")
    print("VARIANTE B: Context Manager (with ControllerService)")
    print("==================================================")

    # In einem with-Block wird start() automatisch aufgerufen und stop() garantiert beim Verlassen.
    with ControllerService(sink="null") as service:
        service.set_state("solid_fill", config={"color": "#FF00FF", "brightness": 0.5})
        print("[ContextManager] State 'solid_fill' in Magenta/HEX gesetzt.")
        time.sleep(0.3)
        service.emit_event("pulse_signal", config={"color": "white"})
        print("[ContextManager] Event 'pulse_signal' emittiert.")
        time.sleep(0.3)


# ============================================================================
# 3. VARIANTE C: Inter-Process Remote Control mit ControllerClient (HTTP)
# ============================================================================
def run_http_client_demo() -> None:
    """Demonstriert die Steuerung eines separat laufenden 'lefx serve' über HTTP."""
    print("\n==================================================")
    print("VARIANTE C: ControllerClient (über HTTP API)")
    print("==================================================")

    client = ControllerClient(host="127.0.0.1", port=8765, timeout=2.0)

    # Health Check
    health_res = client.health()
    if not health_res.ok:
        print(f"[Client] Service unter 127.0.0.1:8765 nicht erreichbar ({health_res.error}).")
        print("[Client] Starte erst 'lefx serve' in einem anderen Terminal für diesen Test.")
        return

    print(f"[Client] Service erreichbar! Sink: {health_res.data.get('sink')}")

    # State setzen über HTTP
    res = client.set_state("solid_fill", config={"color": "cyan"}, slot="primary", action="on")
    print(f"[Client] set_state Status: {res.ok}")

    time.sleep(0.3)

    # Event emittieren über HTTP
    res_evt = client.emit_event("pulse_signal", config={"color": "yellow"}, priority=100, duration_ms=800)
    print(f"[Client] emit_event Status: {res_evt.ok}")


# ============================================================================
# Haupt-Einstiegspunkt
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("LEFX V3 INTEGRATION DEMO APPLICATION")
    print("=" * 60)

    # Starte In-Process Workflow Demo (Verwendet sink='null' für universelle Ausführbarkeit)
    app = SmartVoiceAssistantApp(sink_name="null")
    app.run_demo_workflow()

    # Starte Context Manager Demo
    run_context_manager_demo()

    # Versuche HTTP Client Demo (optional)
    run_http_client_demo()
