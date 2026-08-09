# LEFX V3 HTTP-API-Referenz (`/api/v3`)

Diese Referenz dokumentiert die REST-Schnittstelle des laufenden **LEFX V3 Controller-Service**.

---

## 🌐 Basisdaten & Metadaten

| Eigenschaft | Wert |
|---|---|
| Standard-Basis-URL | `http://127.0.0.1:8765` |
| API-Version | `/api/v3` |
| Transportformat | JSON (`application/json`) |
| Interactive Swagger-Doku | `http://127.0.0.1:8765/docs` |
| OpenAPI Schema | `http://127.0.0.1:8765/openapi.json` |

---

## 📌 Endpunkt-Übersicht

### Allgemeine & Meta-Endpunkte
- `GET /` — Service-Metadaten & API-Version
- `GET /health` — Kompakter System- & Sink-Gesundheitszustand
- `GET /api/v3/status` — Vollständiger Laufzeit-Snapshot (State, Layers, Sink)

### Discovery & Inspektion
- `GET /api/v3/states` — Verfügbare State-IDs oder Details (`?details=true`)
- `GET /api/v3/overlays` — Verfügbare Overlay-IDs oder Details (`?details=true`)
- `GET /api/v3/events` — Verfügbare Event-IDs oder Details (`?details=true`)
- `GET /api/v3/presets` — Verfügbare Presets (`?type=state|overlay|event`, `?details=true`)
- `GET /api/v3/show/{target}` — Vollständigen Vertrag & Schema eines Effekts/Presets abfragen

### Steuerung & Kommandos
- `POST /api/v3/set/state` — State im Slot aktivieren (`primary` oder `background`)
- `POST /api/v3/clear/state` — State-Slot leeren
- `POST /api/v3/set/overlay` — Overlay auf einem Kanal aktivieren
- `POST /api/v3/update/overlay` — Live Runtime-Inputs eines Controlled Overlays aktualisieren
- `POST /api/v3/clear/overlay` — Overlay-Kanal entfernen
- `POST /api/v3/emit/event` — Einmaliges Event auslösen
- `POST /api/v3/clear/all` — Alle aktiven States, Overlays & Events zurücksetzen
- `POST /api/v3/output` — Globale Helligkeit & LED-Aktivierung regeln

### Paketquellen-Verwaltung
- `GET /api/v3/sources` — Geladene Paketquellen auflisten
- `POST /api/v3/sources/register` — Neues Paket (`.lefx`/`.lefxset`) registrieren
- `POST /api/v3/sources/reload` — Paketquellen aus Verzeichnis neu laden
- `DELETE /api/v3/sources/{source_id}` — Paketquelle entfernen

### Lebenszyklus
- `POST /api/v3/shutdown` — Geordnetes Herunterfahren des Service anfordern

---

## 📖 Detaillierte Endpunkt-Spezifikation

---

### 1. Meta & Status

#### `GET /health`
Liefert einen schnellen System-Check.

**Antwort-Beispiel (HTTP 200 OK)**:
```json
{
  "status": "ok",
  "sink": "respeaker",
  "sink_available": true,
  "render_count": 1420,
  "last_error": null
}
```

#### `GET /api/v3/status`
Liefert den vollständigen Laufzeit-Snapshot.

---

### 2. Discovery (`/api/v3/states`, `/overlays`, `/events`, `/presets`)

#### `GET /api/v3/states?details=false`
Liefert eine Liste aller verfügbaren State-IDs.

**Antwort-Beispiel**:
```json
["solid_fill", "breathing_ring", "rotating_segment", "blackout"]
```

Mit `details=true` wird ein Array vollständiger Definitions-Objekte zurückgegeben.

#### `GET /api/v3/show/{target}`
Löst eine Ziel-ID oder ein Preset auf und gibt das vollständige Parameter-Schema zurück.

**Beispiel**: `GET /api/v3/show/solid_fill`

---

### 3. Steuerung & Kommandos

#### `POST /api/v3/set/state`
Aktiviert einen Dauerzustand (State) in einem Slot (`primary` oder `background`).

**Request Body**:
```json
{
  "target": "solid_fill",
  "config": {
    "color": "#00CCFF",
    "brightness": 0.8
  },
  "slot": "primary",
  "action": "on"
}
```

- `target` (String, Pflicht): Effekt-ID oder Preset-ID.
- `config` (Object, Optional): Parameter-Werte. Ungefüllte Parameter erhalten ihre Standardwerte (`default`).
- `slot` (Enum, Optional): `"primary"` (Standard) oder `"background"`.
- `action` (Enum, Optional): `"on"` (Standard), `"off"`, oder `"toggle"`.

**Erfolgsantwort (HTTP 200 OK)**:
```json
{
  "ok": true,
  "operation": "set_state",
  "target": "solid_fill",
  "slot": "primary",
  "action": "on",
  "status": { ... }
}
```

---

#### `POST /api/v3/clear/state`
Leert den angegebenen State-Slot.

**Request Body**:
```json
{
  "slot": "primary"
}
```

---

#### `POST /api/v3/set/overlay`
Aktiviert ein überlagerndes Overlay auf einem bestimmten Kanal.

**Controlled Overlay (mit Live-Inputs)**:
```json
{
  "target": "direction_indicator",
  "channel": "doa",
  "config": {
    "color": "yellow"
  },
  "inputs": {
    "direction_deg": 135.0
  },
  "action": "on"
}
```

**Timed Overlay (zeitlich begrenzt)**:
```json
{
  "target": "countdown_ring",
  "config": {
    "total_ms": 5000
  }
}
```

---

#### `POST /api/v3/update/overlay`
Aktualisiert die Live-Eingabewerte eines aktiven Controlled Overlays.

**Request Body**:
```json
{
  "channel": "doa",
  "inputs": {
    "direction_deg": 225.0
  }
}
```

> [!TIP]
> Ein leeres `inputs`-Objekt (`{}`) dient als Lebenszeichen (Heartbeat) zur Verlängerung des Input-Timeouts.

---

#### `POST /api/v3/clear/overlay`
Entfernt ein Overlay von einem spezifischen Kanal.

**Request Body**:
```json
{
  "channel": "doa"
}
```

---

#### `POST /api/v3/emit/event`
Löst ein einmaliges Animationsevent aus.

**Request Body**:
```json
{
  "target": "pulse_signal",
  "config": {
    "color": "red"
  },
  "priority": 500,
  "duration_ms": 1000
}
```

---

#### `POST /api/v3/output`
Regelt Gesamthelligkeit und Ausgabe-Aktivierung.

**Request Body**:
```json
{
  "brightness": 0.5,
  "enabled": true
}
```

---

## ❌ Fehlerbehandlung & Validierungsformat (HTTP 422)

Wird ein ungültiger Parameter, ein falscher Datentyp oder ein Wert außerhalb der Min/Max-Grenzen gesendet, antwortet die API mit **HTTP Status 422 Unprocessable Entity**.

### Fehlerstruktur (`ParameterValidationError`):

```json
{
  "detail": {
    "code": "parameter_validation_failed",
    "message": "Validation failed for target 'solid_fill'",
    "issues": [
      {
        "code": "value_out_of_range",
        "field": "brightness",
        "message": "Value 1.5 exceeds maximum of 1.0",
        "value": 1.5,
        "suggestions": []
      }
    ]
  }
}
```

### Häufige HTTP Statuscodes:

| Statuscode | Ursache / Bedeutung |
|---|---|
| **200 OK** | Operation erfolgreich ausgeführt. |
| **404 Not Found** | Effekt-ID (`target_not_found`) oder Kanal (`channel_not_found`) nicht vorhanden. |
| **409 Conflict** | Mehrdeutige ID-Referenz (`ambiguous_target`). |
| **422 Unprocessable Entity** | Parameter-Validierung fehlgeschlagen oder ungültiges JSON-Schema. |
| **500 Internal Error** | Unerwarteter interner Serverfehler. |

---

## 💻 `curl` Beispiele

```bash
# 1. State setzen
curl -X POST http://127.0.0.1:8765/api/v3/set/state \
  -H "Content-Type: application/json" \
  -d '{"target": "solid_fill", "config": {"color": "#00AAFF", "brightness": 0.7}, "slot": "primary"}'

# 2. Overlay aktivieren
curl -X POST http://127.0.0.1:8765/api/v3/set/overlay \
  -H "Content-Type: application/json" \
  -d '{"target": "direction_indicator", "channel": "doa", "inputs": {"direction_deg": 90.0}}'

# 3. Live-Input updaten
curl -X POST http://127.0.0.1:8765/api/v3/update/overlay \
  -H "Content-Type: application/json" \
  -d '{"channel": "doa", "inputs": {"direction_deg": 180.0}}'

# 4. Event emittieren
curl -X POST http://127.0.0.1:8765/api/v3/emit/event \
  -H "Content-Type: application/json" \
  -d '{"target": "pulse_signal", "config": {"color": "red"}}'
```
