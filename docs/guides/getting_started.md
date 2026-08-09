# V3 Schnellstart (Getting Started)

Diese Anleitung führt Schritt für Schritt durch die Installation, Konfiguration und erste Benutzung des **LEFX V3 LED-Controllers** für den reSpeaker XVF3800.

---

## 📋 Voraussetzungen

- **Python 3.12** (64-Bit)
- **Betriebssystem**: Windows 10/11 oder Linux
- **Hardware (optional)**: Seeed Studio reSpeaker XVF3800 USB (unter Windows wird der WinUSB-Treiber benötigt, installierbar über [Zadig](https://zadig.akeo.ie/))
- **Alternativ**: Kein Gerät erforderlich — LEFX V3 enthält eine Null-Senke (Headless) sowie einen GUI-Simulator.

---

## 📦 1. Installation

Installiere das Paket direkt über `pip` oder `uv`:

```powershell
pip install led-controller-version-3
```

Für die Nutzung des grafischen Simulators (Qt/PySide6) installiere das optionale Extra:

```powershell
pip install led-controller-version-3[simulated-respeaker]
```

Nach der Installation steht das zentrale CLI-Werkzeug `lefx` zur Verfügung.

---

## 🚀 2. Controller-Service starten

Der Controller läuft als lokaler Service im Hintergrund oder im eigenen Terminalfenster.

### Varianten zum Starten:

#### A) Ohne Hardware (Null-Sink, z. B. auf Servern oder in Tests):
```powershell
lefx serve --sink null
```

#### B) Mit GUI-Simulator (virtueller Ring mit DoA-Regler):
```powershell
lefx serve --sink simulator
```

#### C) Mit echter reSpeaker XVF3800 USB-Hardware:
```powershell
lefx serve --sink respeaker
```

> [!NOTE]
> Der Service startet standardmäßig auf Host `127.0.0.1` und Port `8765`. Er schreibt beim Start seine PID und Verbindungsdaten in die Statusdatei `active_service.json`.

---

## 🔍 3. Verbindung & Status prüfen

Öffne ein **zweites Terminal** für die Steuerbefehle:

```powershell
# Service-Status und aktive Komponenten abfragen
lefx status
```

Beispiel-Antwort (JSON):
```json
{
  "sink": "respeaker",
  "sink_status": {
    "available": true,
    "detail": "connected"
  },
  "led_count": 12,
  "fps": 30.0,
  "output": {
    "brightness": 1.0,
    "enabled": true
  },
  "layers": {
    "background": null,
    "primary": null,
    "overlays": {},
    "event": null
  }
}
```

Installierte Senken, Input-Provider und Effekt-Sets auflisten:
```powershell
lefx sinks
```

---

## 🔎 4. Verfügbare Effekte und Presets entdecken

```powershell
# Verfügbare States auflisten
lefx list states

# Verfügbare Overlays auflisten
lefx list overlays

# Verfügbare Events auflisten
lefx list events

# Verfügbare Presets auflisten
lefx list presets

# Details und Parameter-Schema eines bestimmten Effekts anzeigen
lefx show solid_fill
```

---

## 🎨 5. Grundzustand (State) setzen

Ein **State** ist ein dauerhafter Hintergrund- oder Hauptzustand.

### Auf dem primären Slot aktivieren:
```powershell
lefx set state solid_fill --config '{"color": "#00FF88", "brightness": 0.8}'
```

### Einen persistenten Hintergrundzustand (Background Slot) setzen:
```powershell
lefx set state solid_fill --slot background --config '{"color": "#112244"}'
```

### State ausschalten:
```powershell
lefx set state solid_fill --off
# Oder den Slot direkt leeren:
lefx clear state --slot primary
```

---

## 🧭 6. Richtungsanzeige & Overlays steuern

**Overlays** werden über den aktiven Zustand gerendert (z. B. eine DoA-Richtungsanzeige für Sprachassistenten).

### Controlled Overlay aktivieren (Kanal `doa`):
```powershell
lefx set overlay direction_indicator --channel doa --config '{"color": "gelb"}' --inputs '{"direction_deg": 135.0}'
```

### Live-Eingabewerte aktualisieren (z. B. neue Sprecherrichtung):
```powershell
lefx update overlay doa --inputs '{"direction_deg": 270.0}'
```

### Overlay entfernen:
```powershell
lefx clear overlay doa
```

---

## ⚡ 7. Kurzzeitiges Event auslösen

**Events** sind einmalige Animationen (z. B. Bestätigung, Fehler oder Wake-Word-Impuls). Sie unterbrechen den Zustand kurz und stellen ihn danach automatisch wieder her.

```powershell
# Kurzer Puls auslösen
lefx emit event pulse_signal --config '{"color": "rot", "duration_ms": 600}'
```

---

## 🔆 8. Helligkeit und Ausgabe steuern

```powershell
# Helligkeit auf 50% begrenzen
lefx output --brightness 0.5

# LED-Ausgabe temporär deaktivieren (Engine läuft weiter)
lefx output --enabled false

# LED-Ausgabe wieder aktivieren
lefx output --enabled true
```

---

## 🛑 9. Service beenden

```powershell
lefx shutdown
```

---

## 📚 Nächste Schritte

- 💻 **[CLI-Referenz](cli_guide.md)** — Alle Kommandos, Flags und CLI-Tricks im Detail.
- 🌐 **[HTTP-API-Referenz](api_guide.md)** — HTTP REST-Endpunkte für Webanwendungen.
- 🔌 **[Integration Guide](integration_guide.md)** — Direct Python Integration in eigenen Apps.
- 🎨 **[Core-Set Effekte](core_effects.md)** & **[Smart Speaker-Set Effekte](smartspeaker_effects.md)** — Alle 36 Effekte im Detail.
