# LEFX V3 CLI-Referenz (`lefx`)

Diese Referenz dokumentiert das Befehlszeilenwerkzeug `lefx`. Alle CLI-Befehle folgen dem **Verb-First-Prinzip** (`lefx <verb> <subject> [target] [options]`), genau wie die HTTP-API.

---

## 🛠️ Aufrufsyntax & Grundprinzipien

```powershell
lefx [Kommando] [Optionen]
```

### Hilfe abrufen:
```powershell
lefx --help
lefx <kommando> --help
```

### JSON-Argumente in der CLI:
Optionen wie `--config` und `--inputs` erwarten ein gültiges JSON-Objekt.
In der PowerShell umschließt man das JSON-Objekt mit einfachen Anführungszeichen `'...'`:

```powershell
--config '{"color": "#00FF88", "brightness": 0.8}'
```

> [!NOTE]
> **Implizites vs. Explizites Verhalten**:
> `lefx set` bedeutet immer **Einschalten (`--on`)**. Ein erneuter Aufruf schaltet das Ziel nicht unbeabsichtigt aus. Zum Ausschalten muss explizit `--off` oder `--toggle` angegeben werden.

---

## 🌐 Globale Verbindungsoptionen

Alle Befehle, die einen laufenden Service steuern, unterstützen folgende Verbindungsoptionen (nach dem Subcommand):

| Option | Typ | Standardwert | Beschreibung |
|---|---|---|---|
| `--host` | String | `127.0.0.1` | Service-Hostadresse |
| `--port` | Integer | `8765` | Service-Port |
| `--timeout` | Float | `5.0` | HTTP-Timeout in Sekunden |

Beispiel:
```powershell
lefx status --host 192.168.1.50 --port 8765 --timeout 2.0
```

---

## 📋 Befehlsreferenz

---

### 1. `lefx serve` — Service starten

Startet den Controller-Service, die Renderschleife sowie Senken und Provider.

```powershell
lefx serve [Optionen]
```

#### Parameter:

| Option | Typ | Standardwert | Beschreibung |
|---|---|---|---|
| `--host` | String | `127.0.0.1` | Bind-Adresse für HTTP REST-API |
| `--port` | Integer | `8765` | Bevorzugter HTTP-Port |
| `--port-pool` | String | `""` | Fallback-Portbereich, z. B. `8765,8770-8774` |
| `--sink` | String | `null` | Frame-Sink (`respeaker`, `simulator`, `null`) |
| `--sink-option` | Key=Value | `[]` | Optionen für Gerät/Sink (wiederholbar, z. B. `port=8770`) |
| `--input-device` | String | gleich `--sink` | Abweichendes Eingabegerät für DoA/Inputs |
| `--led-count` | Integer | `12` | Anzahl LEDs auf dem Ring |
| `--fps` | Float | `30.0` | Render-Framerate pro Sekunde |

#### Beispiele:

```powershell
# Mit GUI-Simulator auf Port 8765 starten
lefx serve --sink simulator

# Mit reSpeaker-Hardware starten, 12 LEDs, 30 FPS
lefx serve --sink respeaker --led-count 12 --fps 30.0

# Headless / Testmodus ohne Hardware
lefx serve --sink null

# Mit gerätespezifischen Optionen
lefx serve --sink simulator --sink-option port=8770
```

---

### 2. `lefx status` — Service-Zustand lesen

Liest den aktuellen Laufzeit-Zustand, aktiven Ebenen, Senken-Status und Frame-Zähler aus.

```powershell
lefx status [--json]
```

#### Beispiele:
```powershell
lefx status
lefx status --json
```

---

### 3. `lefx sinks` — Senken & Provider auflisten

Listet alle im System installierten Frame-Sinks, Input-Provider und Effekt-Sets auf.

```powershell
lefx sinks
```

---

### 4. `lefx config` — Konfiguration anzeigen

Zeigt alle aktiven Einstellungen, deren Werte und Herkunft (Standard, config.yaml, Umgebungsvariable) an.

```powershell
lefx config [--json]
```

---

### 5. `lefx list` — Katalog durchsuchen

Listet registrierte Effekte oder Presets auf.

```powershell
lefx list <kind> [--details] [--json]
```

#### Parameter:
- `kind`: `state` (oder `states`), `overlay` (oder `overlays`), `event` (oder `events`), `preset` (oder `presets`).
- `--details`: Zeigt vollständige JSON-Verträge inkl. Parameter-Schema an.
- `--json`: Formatiert die Ausgabe als JSON-Array.

#### Beispiele:

```powershell
# Alle State-IDs auflisten
lefx list states

# Alle Overlays mit Details anzeigen
lefx list overlays --details

# Presets im JSON-Format ausgeben
lefx list presets --json
```

---

### 6. `lefx show` — Einzelnen Effekt oder Preset auflösen

Zeigt das vollständige Schema und die Parameterbeschreibungen eines Effekts oder Presets an.

```powershell
lefx show <target>
```

#### Beispiele:

```powershell
lefx show solid_fill
lefx show direction_indicator
lefx show breathing_ring_calm_cyan
```

---

### 7. `lefx set` — State oder Overlay aktivieren

Setzt einen dauerhaften Zustand (State) oder ein überlagerndes Overlay.

```powershell
lefx set state <target> [--slot primary|background] [--config <JSON>] [--on|--off|--toggle]
lefx set overlay <target> --channel <name> [--config <JSON>] [--inputs <JSON>] [--on|--off|--toggle]
```

#### Parameter:

| Option | Standardwert | Beschreibung |
|---|---|---|
| `<target>` | Pflicht | Effekt-ID oder Preset-ID |
| `--slot` | `primary` | `primary` (Hauptanzeige) oder `background` (Hintergrund) |
| `--channel` | `null` | Kanalname bei Overlays (z. B. `doa`, `volume`) |
| `--config` | `{}` | Stabile Konfigurations-Parameter als JSON-Objekt |
| `--inputs` | `{}` | Dynamic Runtime Inputs für Controlled Overlays |
| `--on` | Standard | Ziel sicher aktivieren |
| `--off` | - | Ziel ausschalten (falls aktiv) |
| `--toggle` | - | Aktivierungszustand umschalten |

#### Beispiele:

```powershell
# State im primären Slot aktivieren
lefx set state solid_fill --config '{"color": "blue", "brightness": 0.8}'

# State im Hintergrund-Slot setzen
lefx set state solid_fill --slot background --config '{"color": "#112233"}'

# State ausschalten
lefx set state solid_fill --off

# Controlled Overlay setzen (Kanal 'doa')
lefx set overlay direction_indicator --channel doa --config '{"color": "green"}' --inputs '{"direction_deg": 120}'

# Timed Overlay setzen (ohne Channel)
lefx set overlay countdown_ring --config '{"total_ms": 5000}'
```

---

### 8. `lefx update` — Controlled Overlay aktualisieren

Sendet neue Live-Eingabewerte an ein aktives Controlled Overlay.

```powershell
lefx update overlay <channel> --inputs <JSON>
```

#### Beispiele:

```powershell
# Richtung im Kanal 'doa' aktualisieren
lefx update overlay doa --inputs '{"direction_deg": 240.5}'

# Leeres Objekt als Heartbeat/Lebenszeichen
lefx update overlay doa --inputs '{}'
```

---

### 9. `lefx clear` — Slots oder Kanäle leeren

Entfernt einen aktivierten State, ein Overlay oder leert alle Ebenen.

```powershell
lefx clear state [--slot primary|background]
lefx clear overlay <channel>
lefx clear all
```

#### Beispiele:

```powershell
# Primary State-Slot leeren
lefx clear state

# Background State-Slot leeren
lefx clear state --slot background

# Overlay-Kanal 'doa' leeren
lefx clear overlay doa

# Alle aktiven States, Overlays & Events zurücksetzen
lefx clear all
```

---

### 10. `lefx emit` — Event auslösen

Löst eine einmalige, zeitlich begrenzte Event-Animation aus.

```powershell
lefx emit event <target> [--config <JSON>] [--priority <int>] [--duration-ms <int>]
```

#### Parameter:

| Option | Standardwert | Beschreibung |
|---|---|---|
| `<target>` | Pflicht | Event-ID oder Event-Preset |
| `--config` | `{}` | Konfigurations-Parameter als JSON-Objekt |
| `--priority` | `null` | Priorität für die Warteschlange (höher = wichtiger) |
| `--duration-ms` | `null` | Explizite Dauer in Millisekunden (überschreibt Standard) |

#### Beispiele:

```powershell
# Einfaches Impuls-Event auslösen
lefx emit event pulse_signal

# Warnblinken mit hoher Priorität und 1,5s Dauer
lefx emit event pulse_signal --config '{"color": "rot"}' --priority 500 --duration-ms 1500
```

---

### 11. `lefx output` — Helligkeit & globale Ausgabe steuern

Regelt die globale Gesamthelligkeit oder schaltet die LED-Ausgabe stumm.

```powershell
lefx output [--brightness <float>] [--enabled <bool>]
```

#### Beispiele:

```powershell
# Helligkeit auf 40% reduzieren
lefx output --brightness 0.4

# Ausgabe deaktivieren (Render-Loop läuft im Hintergrund weiter)
lefx output --enabled false

# Ausgabe wieder aktivieren
lefx output --enabled true
```

---

### 12. `lefx sources` — Effekt-Paketquellen verwalten

Verwaltet dynamisch geladene `.lefx` oder `.lefxset` Paketdateien zur Laufzeit.

```powershell
lefx sources [list|register|reload|remove] [Wert]
```

#### Beispiele:

```powershell
# Alle geladenen Paketquellen anzeigen
lefx sources list

# Neues Effektset registrieren
lefx sources register C:\effects\custom-set.lefxset

# Quellen aus dem Dateisystem neu einlesen
lefx sources reload

# Paketquelle entfernen
lefx sources remove custom-set
```

---

### 13. `lefx shutdown` — Service beenden

Fährt den laufenden Service und die Renderschleife geordnet herunter.

```powershell
lefx shutdown
```
