# LEFX V3 Integration Guide: reSpeaker LED-Controller in eigene Anwendungen einbinden

Dieser Guide richtet sich an Software-Entwickler, die den **LEFX V3 LED-Controller** (`led-controller-version-3`) direkt in ihre Python-Anwendung (z. B. Sprachassistenten, Smart-Home-Anwendungen oder Robotersteuerungen) einbetten möchten.

---

## 📋 Voraussetzungen & Installation

- **Python**: >= 3.12, < 3.13
- **Paket-Installation**:

```bash
pip install led-controller-version-3
```

Falls der GUI-Simulator für lokale Tests ohne Hardware benötigt wird:
```bash
pip install led-controller-version-3[simulated-respeaker]
```

---

## 🛠️ Integrationswege im Überblick

LEFX V3 bietet drei Hauptwege zur Einbindung:

| Integrationsform | Klasse / Schnittstelle | Anwendungsfall |
|---|---|---|
| **1. Direct In-Process Service** | `ControllerService` | **Empfohlen**: Volle Kontrolle im selben Python-Prozess, extrem performant, kein HTTP-Overhead. |
| **2. HTTP REST Client** | `ControllerClient` | Für verteilte Architekturen, Microservices oder wenn `lefx serve` als separater Daemon läuft. |
| **3. Low-Level SDK Ports** | `FrameSink` / `InputProvider` | Für benutzerdefinierte LED-Hardware oder eigene Eingabe-Sensoren. |

---

## 🚀 1. Direct In-Process Integration (`ControllerService`)

Der `ControllerService` verwaltet die Renderschleife (Render-Thread), die Ebenen-Komposition, die Hardware-Senke (`FrameSink`) und die Input-Provider.

### A) Manuelle Lebenszyklus-Steuerung (`start` / `stop`):

```python
from lefx.interfaces import ControllerService

# Controller initialisieren
# sink: 'respeaker' (echte USB-Hardware), 'simulator' (GUI) oder 'null' (Headless Test)
service = ControllerService(sink="respeaker", led_count=12, fps=30.0)

# Render-Thread starten
service.start()

try:
    # Hauptzustand aktivieren
    service.set_state("listening", config={"color": "#00AAFF"})

    # Event auslösen
    service.emit_event("wakeword_detected")
    
    # ... Deine Anwendungslogik ...
finally:
    # Sauberes Beenden des Render-Threads
    service.stop()
```

### B) Context Manager Pattern (garantiertes Beenden):

```python
from lefx.interfaces import ControllerService

# Startet den Service beim Betreten und beendet ihn garantiert beim Verlassen
with ControllerService(sink="respeaker") as service:
    service.set_state("ready_state")
    # ... Anwendungslogik ...
    service.set_state("thinking")
```

---

## 🧭 2. Zustände, Overlays & Events steuern

Der `ControllerService` bietet eine übersichtliche, typ-sichere Python-Schnittstelle:

### 🎨 States (Dauerzustände)

States sind permanente LED-Muster auf dem **Primary**- oder **Background**-Slot.

```python
# Hauptzustand (Primary Slot) aktivieren
service.set_state("solid_fill", config={"color": "cyan", "brightness": 0.8})

# Hintergrund-Zustand (Background Slot) setzen
service.set_state("solid_fill", slot="background", config={"color": "#050510"})

# Zustand im Primary Slot ausschalten
service.set_state("solid_fill", action="off")

# Slot direkt leeren
service.clear_state(slot="primary")
```

---

### 🌊 Overlays (Überlagernde Anzeigen)

Overlays werden über dem aktiven State gerendert (z. B. Lautstärkebalken oder DoA-Richtungsanzeigen).

```python
# Controlled Overlay auf Kanal 'volume' aktivieren
service.set_overlay(
    "level_meter",
    channel="volume",
    config={"color": "#00FFCC"},
    inputs={"progress": 0.75}
)

# Live-Input über update_overlay aktualisieren (z. B. neue Lautstärke)
service.update_overlay("volume", inputs={"progress": 0.95})

# Overlay entfernen
service.clear_overlay("volume")
```

---

### ⚡ Events (Einmalige Animationen)

Events sind kurze Impulse (z. B. Klick, Bestätigung, Fehlerblinken). Sie spielen einmalig ab und stellen danach den vorherigen State wieder her.

```python
# Event auslösen
service.emit_event("wakeword_detected")

# Event mit Konfiguration und Priorität emittieren
service.emit_event(
    "pulse_signal",
    config={"color": "red"},
    priority=500,
    duration_ms=1000
)
```

---

### 🔆 Helligkeit & Not-Aus

```python
# Gesamthelligkeit auf 50% begrenzen (0.0 bis 1.0)
service.set_output(brightness=0.5)

# LED-Ausgabe stummschalten (Engine läuft weiter)
service.set_output(enabled=False)

# LED-Ausgabe wieder aktivieren
service.set_output(enabled=True)
```

---

## 🌐 3. HTTP Client Integration (`ControllerClient`)

Falls deine Anwendung in einem separaten Prozess läuft und mit einem daemonisierten `lefx serve` kommuniziert, nutze den leichtgewichtigen `ControllerClient` (basiert ausschließlich auf der Python Standardbibliothek):

```python
from lefx.interfaces.client import ControllerClient

# Client initialisieren
client = ControllerClient(host="127.0.0.1", port=8765, timeout=2.0)

# Health Check
res_health = client.health()
if res_health.ok:
    print("Service erreichbar!")

# State via HTTP setzen
res = client.set_state("listening", config={"color": "blue"}, slot="primary", action="on")
if not res.ok:
    print(f"Fehler: {res.error}")

# Event emittieren via HTTP
client.emit_event("confirm_event", config={}, priority=None, duration_ms=None)
```

---

## 🖥️ Ausführbares Beispielskript

Ein vollständiges, lauffähiges Beispiel einer Sprachassistenten-Anwendung findest du in der Datei:
📄 **[`examples/app_integration_example.py`](examples/app_integration_example.py)**

Führe das Beispiel direkt im Terminal aus:
```bash
python docs/guides/examples/app_integration_example.py
```

Das Skript demonstriert Schritt für Schritt den vollständigen Lebenszyklus (Bereit -> Wake-Word -> Listening -> Level Meter Overlay -> Thinking -> Speaking -> Confirm -> Mic Mute -> Shutdown).
