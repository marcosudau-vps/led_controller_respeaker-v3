# LEFX V3 Documentation & Guides

Willkommen zur offiziellen Dokumentation von **LEFX V3**, dem modernen LED-Effekt-System und Controller für den **reSpeaker XVF3800** (und kompatible Hardware sowie Simulatoren).

Dieses Handbuch bietet praxisnahe Anleitungen, vollständige Parameter-Referenzen, Copy/Paste-fähige Beispiele und detaillierte Integrationsleitfäden für Entwickler und Anwender.

---

## 📚 Themenübersicht

| Guide | Beschreibung | Zielgruppe |
|---|---|---|
| 🚀 **[Schnellstart](getting_started.md)** | Erste Schritte, Installation, Service-Start und erste Effekte in unter 5 Minuten. | Einsteiger & Anwender |
| 💻 **[CLI-Referenz](cli_guide.md)** | Vollständige Dokumentation des Befehlszeilen-Werkzeugs `lefx` mit allen Verben & Parametern. | Terminal-Nutzer & Skripte |
| 🌐 **[HTTP-API-Referenz](api_guide.md)** | REST-Schnittstelle unter `/api/v3/*` mit JSON-Schemas, Endpunkten & `curl`-Beispielen. | Web/Network Integratoren |
| 🔌 **[Integration Guide](integration_guide.md)** | Einbettung von `led-controller-version-3` in eigene Python-Anwendungen (in-process & client). | Python-Entwickler |
| 🎨 **[Core-Set Effekte](core_effects.md)** | Katalog aller 13 Kern-Effekte und 24 Presets (Basismuster, Aussteuerungsanzeigen, DoA). | Anwender & Designer |
| 🗣️ **[Smart Speaker-Set Effekte](smartspeaker_effects.md)** | Katalog aller 23 Voice-Assistant-Effekte & 47 Presets (Listening, Thinking, Speaking, Mute). | Smart-Assistant Entwickler |
| 📦 **[Release & Build Guide](release_guide.md)** | Erstellung von `.lefxset`-Paketen, Workspace-Aufbau, CI/CD und PyPI-Release. | Package-Packer & Admins |
| 🛠️ **[Troubleshooting](troubleshooting.md)** | Diagnose von Treiberproblemen (WinUSB/Zadig), Port-Konflikten & Parameter-Fehlern. | Admins & Entwickler |

---

## 💡 Das LEFX V3 System auf einen Blick

LEFX V3 löst frühere Iterationen durch eine bereinigte, modulare Architektur ab:

1. **Paketname auf PyPI**: `led-controller-version-3`
2. **Kommandozeilen-Tool**: `lefx` (Verb-First Syntax, z. B. `lefx set state solid_fill`)
3. **HTTP REST-API**: `/api/v3/*` (Standard-Port: `8765`, interaktive Swagger-Doku unter `/docs`)
4. **Python Namespace**: `lefx.sdk`, `lefx.engine`, `lefx.interfaces`, `lefx.device.respeaker`
5. **Schichten-Architektur**:
   - **`lefx-sdk`**: Schema, Wertnormalisierung, Farbmathematik, Hardware-Ports (`FrameSink`, `InputProvider`).
   - **`lefx-engine`**: Ebenen-Komposition (Slots & Channels), Lebenszyklen, Renderschleife, Registry.
   - **`lefx-interfaces`**: CLI, REST-API, HTTP-Client, Service-Hosting, Konfiguration.
   - **`lefx-device-respeaker`**: USB-Treiberanbindung an den reSpeaker XVF3800.
   - **`lefx-device-simulated-respeaker`**: GUI-Simulator als vollwertiges Entwicklungs-Double.

---

## 🏁 Schnelleinstieg für Eilige

```bash
# 1. Paket installieren
pip install led-controller-version-3

# 2. Controller-Service starten (z. B. mit Simulator oder Null-Sink)
lefx serve --sink simulator

# 3. In einem zweiten Terminal: Zustand setzen
lefx set state solid_fill --config '{"color": "cyan", "brightness": 0.8}'

# 4. DoA-Richtungsanzeige als Overlay aufschalten
lefx set overlay direction_indicator --channel doa --inputs '{"direction_deg": 180}'

# 5. Status abfragen
lefx status
```

Für eine tiefergehende Anleitung fahre bitte mit dem **[Schnellstart-Guide](getting_started.md)** fort.
