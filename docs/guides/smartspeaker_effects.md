# Smart Speaker Effekt-Katalog (`smartspeaker-set`)

Das `smartspeaker-set` enthält alle speziell entwickelten Lichtmuster und Animationen für **Sprachassistenten, Smart-Home-Lautsprecher und Sprachbediensysteme** (z. B. Wake-Word Erkennung, STT Listening, LLM Thinking, TTS Speaking, Stummschaltung und System-Meldungen).

- **Paket-ID**: `smartspeaker-set`
- **Anzahl Effekte**: 23 (10 States, 4 Overlays, 9 Events)
- **Anzahl Presets**: 47

---

## 🗣️ Sprachassistenten-Lebenszyklus

Ein typischer Ablauf der LED-Steuerung in einer Smart-Speaker-Anwendung:

```
[Bereit] ──► (Wake-Word) ──► [Listening] ──► (Sprache Ende) ──► [Thinking] ──► [Speaking] ──► [Bereit]
ready_state   wakeword_detected  listening                       thinking      speaking      ready_state
```

---

## 🎨 1. States (Dauerzustände)

---

### `ready_state` — Bereitschaft / Standby
Dezenter Hintergrundzustand, wenn der Sprachassistent betriebsbereit ist und auf das Wake-Word wartet.

- **Typ**: State
- **Farbmodell**: Mono (`color`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#003366` | Hex / Farbname | Dezente Standby-Farbe |
| `brightness` | FLOAT | `0.3` | `0.0` bis `1.0` | Gedimmte Helligkeit |

---

### `listening` — Spracherkennung (Listening)
Signalisiert dem Nutzer, dass das Mikrofon offen ist und Sprache aufzeichnet.

- **Typ**: State
- **Farbmodell**: Mono (`color`)
- **Animiert**: Ja

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00AAFF` | Hex / Farbname | Hauptfarbe für Zuhören |
| `brightness` | FLOAT | `0.85` | `0.0` bis `1.0` | Helligkeit |
| `speed` | FLOAT | `1.0` | `> 0.0` | Pulsiergeschwindigkeit |

#### Presets:
- `listening_default` (`color`: `#00AAFF`, `brightness`: `0.85`)
- `listening_cyan` (`color`: `#00FFCC`, `brightness`: `0.90`)

---

### `thinking` — Verarbeiten / KI-Nachdenken (Thinking)
Animiertes Rotations- oder Wellenmuster, während die Sprache analysiert oder eine LLM-Antwort generiert wird.

- **Typ**: State
- **Farbmodell**: Dual (`color_a`, `color_b`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color_a` | COLOR | `#00FFCC` | Hex / Farbname | Erste Verlaufsfarbe |
| `color_b` | COLOR | `#9900FF` | Hex / Farbname | Zweite Verlaufsfarbe |
| `speed` | FLOAT | `1.5` | `> 0.0` | Rotationsgeschwindigkeit |
| `brightness` | FLOAT | `0.85` | `0.0` bis `1.0` | Helligkeit |

---

### `speaking` — Sprachausgabe (TTS Speaking)
Dynamisches Muster während der Sprachausgabe des Assistenten.

- **Typ**: State
- **Farbmodell**: Mono (`color`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00E5FF` | Hex / Farbname | Hauptfarbe bei Sprachausgabe |
| `brightness` | FLOAT | `0.85` | `0.0` bis `1.0` | Helligkeit |
| `speed` | FLOAT | `1.0` | `> 0.0` | Bewegungstempo |

---

### `mic_mute` — Mikrofon stummgeschaltet
Dauerhafte rote/orange Warnfarbe, wenn das Mikrofon per Hardware- oder Software-Schalter deaktiviert wurde.

- **Typ**: State
- **Farbmodell**: Mono (`color`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#FF0033` | Hex / Farbname | Warnfarbe (Standard: Rot) |
| `brightness` | FLOAT | `0.7` | `0.0` bis `1.0` | Helligkeit |

---

### `processing` — Befehlsverarbeitung
Kurze Phase der Befehlsauswertung vor der Antwort.

- **Typ**: State

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00FFCC` | Hex / Farbname | Verarbeitungsfarbe |
| `speed` | FLOAT | `1.2` | `> 0.0` | Tempo |

---

### `transcribe` — Live-Transkription
Visualisiert die fortlaufende Sprachtranskription.

- **Typ**: State

---

### `waiting` — Warten auf Nutzereingabe
Wartemodus mit gelbem/orangefarbenem Lichtimpuls.

- **Typ**: State

---

### `reconnect_mic_state` — Mikrofon-Verbindungsfehler
Signalisiert ein Problem mit der Audio-Eingabehardware.

- **Typ**: State

---

### `reconnect_network_state` — Netzwerk-Verbindungsfehler
Signalisiert fehlende Internet- oder Serververbindung.

- **Typ**: State

---

## 🌊 2. Overlays (Überlagerungen)

---

### `countdown_ring` — Countdown-Ring (Timed Overlay)
Visualisiert einen ablaufenden Timer um den Ring (z. B. "Noch 5 Sekunden zum Antworten").

- **Typ**: Timed Overlay

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#FF9900` | Hex / Farbname | Farbe des ablaufenden Rings |
| `duration_ms` | DURATION_MS | `5000` | `>= 1` ms | Countdown-Dauer in ms |
| `brightness` | FLOAT | `0.85` | `0.0` bis `1.0` | Helligkeit |

---

### `progress_ring` — Fortschritts-Ring (Controlled Overlay)
Visualisiert einen veränderbaren Fortschrittsring.

- **Typ**: Controlled Overlay

#### Konfiguration (`--config`):
- `color`: `#00FF88`
- `background_color`: `#002211`

#### Runtime Inputs (`--inputs`):
- `progress`: Float `0.0` bis `1.0`

---

### `loading_spinner` — Lade-Spinner Overlay
Drehender Lade-Spinner über dem aktuellen Hintergrund.

- **Typ**: Controlled Overlay

---

### `timeout_segment` — Timeout-Segment
Fällt als verkürzendes Segment ab.

- **Typ**: Timed Overlay

---

## ⚡ 3. Events (Einmalige Meldungen)

---

### `wakeword_detected` — Wake-Word erkannt!
Kurzer, heller Cyan/Blau-Blitz beim Erkennen des Aktivierungsworts (z. B. "Hey Assistant").

- **Typ**: Event

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00E5FF` | Hex / Farbname | Blitzfarbe |
| `duration_ms` | DURATION_MS | `500` | `>= 1` ms | Aufblitz-Dauer |

---

### `confirm_event` — Bestätigung
Kurzer grüner Doppelblitz für erfolgreich verstandene Befehle.

- **Typ**: Event

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00FF66` | Hex / Farbname | Bestätigungsfarbe |
| `duration_ms` | DURATION_MS | `600` | `>= 1` ms | Dauer |

---

### `success_event` — Erfolg
Signalisiert eine erfolgreich abgeschlossene Aktion (z. B. "Licht eingeschaltet").

- **Typ**: Event

---

### `error_event` — Fehler
Roter Fehlerblitz (z. B. "Befehl nicht verstanden" oder "Server nicht erreichbar").

- **Typ**: Event

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#FF0033` | Hex / Farbname | Fehlerfarbe |
| `duration_ms` | DURATION_MS | `1000` | `>= 1` ms | Fehlerdauer |

---

### `warn_event` — Warnung
Orangefarbene Warnmeldung.

- **Typ**: Event

---

### `reject_event` — Ablehnung
Kurzes rotes Doppel-Aufblitzen bei verweigerter Aktion.

- **Typ**: Event

---

### `notification_event` — Benachrichtigung
Gelb/Orange pulsierende Erinnerung oder ungelesene Nachricht.

- **Typ**: Event

---

### `connected_event` — Gerät verbunden
Begrüßungs-Animation beim Verbinden des Geräts oder Starten des Service.

- **Typ**: Event

---

### `init_event` — Initialisierung / Boot
Bootup-Animation beim Systemstart.

- **Typ**: Event

---

## 💻 Praxisbeispiele für Smart-Speaker-Entwickler

```bash
# 1. Standby aktivieren
lefx set state ready_state

# 2. Wake-Word Event emittieren
lefx emit event wakeword_detected

# 3. Listening State aktivieren (Mikrofon aktiv)
lefx set state listening --config '{"color": "cyan"}'

# 4. In Thinking wechseln (Verarbeitung)
lefx set state thinking

# 5. In Speaking wechseln (Antwort)
lefx set state speaking

# 6. Bestätigungs-Event senden
lefx emit event confirm_event

# 7. Zurück zu Standby
lefx set state ready_state
```
