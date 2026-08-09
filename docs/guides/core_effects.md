# Core-Set Effekt-Katalog (`core-set`)

Das `core-set` enthält die grundlegenden, universellen Lichteffekte und Testmuster für den LEFX V3 Controller. Es dient als Referenz-Katalog für allgemeine Anwendungen, Statusanzeigen, Richtungsanzeigen und Systemtests.

- **Paket-ID**: `core-set`
- **Anzahl Effekte**: 13 (9 States, 3 Overlays, 1 Event)
- **Anzahl Presets**: 24

---

## 🎨 1. States (Dauerzustände)

---

### `solid_fill` — Einzeitige Farbfüllung
Füllt den gesamten LED-Ring mit einer einzelnen, durchgehenden Farbe. Ideal für statische Zustandsanzeigen.

- **Typ**: State (`StateSlot.PRIMARY`, `StateSlot.BACKGROUND`)
- **Farbmodell**: Mono (`color`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#3399FF` | Hex / Farbname | Hauptfarbe aller LEDs |
| `brightness` | FLOAT | `0.8` | `0.0` bis `1.0` | Helligkeitsfaktor |

#### Presets:
- `solid_fill_soft_white` (`color`: `#DDDDDD`, `brightness`: `0.3`)

#### CLI & HTTP Beispiele:
```bash
# CLI
lefx set state solid_fill --config '{"color": "cyan", "brightness": 0.8}'

# HTTP REST
POST /api/v3/set/state
{"target": "solid_fill", "config": {"color": "#00FFCC", "brightness": 0.8}}
```

---

### `breathing_ring` — Sanftes Pulsieren (Atmen)
Lässt den gesamten LED-Ring in einer sanften Sinuswelle auf- und abdimmen.

- **Typ**: State
- **Farbmodell**: Mono (`color`)
- **Animiert**: Ja

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00D0D0` | Hex / Farbname | Pulsierende Farbe |
| `brightness` | FLOAT | `0.85` | `0.0` bis `1.0` | Maximale Helligkeit |
| `min_brightness` | FLOAT | `0.15` | `0.0` bis `1.0` | Minimale Helligkeit im Tiefpunkt |
| `speed` | FLOAT | `1.0` | `> 0.0` | Geschwindigkeitsmultiplikator |

#### Presets:
- `breathing_ring_calm_cyan` (`color`: `#00D0D0`, `brightness`: `0.68`, `min_brightness`: `0.22`, `speed`: `0.65`)
- `breathing_ring_warm_amber` (`color`: `#FF8800`, `brightness`: `0.85`, `min_brightness`: `0.10`, `speed`: `0.80`)

#### CLI & HTTP Beispiele:
```bash
# CLI
lefx set state breathing_ring --config '{"color": "blue", "speed": 1.2}'
```

---

### `blackout` — Dunkelschaltung
Schaltet alle LEDs vollständig aus (`0x000000`), während der Slot als aktiver State belegt bleibt.

- **Typ**: State
- **Farbmodell**: None
- **Parameter**: keine

#### CLI & HTTP Beispiele:
```bash
lefx set state blackout
```

---

### `dual_alternating` — Zweifarbiges Wechselmuster
Erzeugt ein abwechselndes Muster aus zwei Farben auf geraden und ungeraden LED-Positionen.

- **Typ**: State
- **Farbmodell**: Dual (`primary_color`, `secondary_color`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `primary_color` | COLOR | `#00FFCC` | Hex / Farbname | Erste Farbe |
| `secondary_color` | COLOR | `#FF0066` | Hex / Farbname | Zweite Farbe |
| `brightness` | FLOAT | `0.8` | `0.0` bis `1.0` | Helligkeitsfaktor |
| `speed` | FLOAT | `1.0` | `> 0.0` | Wechselgeschwindigkeit |

#### Presets:
- `dual_alternating_neon` (`primary_color`: `#00FFCC`, `secondary_color`: `#FF0066`, `speed`: `1.5`)

---

### `gradient_ring` — Rotierender Farbverlauf
Erzeugt einen fließenden Farbverlauf zwischen zwei Farben um den Ring herum.

- **Typ**: State
- **Farbmodell**: Gradient (`color_a`, `color_b`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color_a` | COLOR | `#FF0055` | Hex / Farbname | Startfarbe des Verlaufs |
| `color_b` | COLOR | `#00CCFF` | Hex / Farbname | Endfarbe des Verlaufs |
| `brightness` | FLOAT | `0.8` | `0.0` bis `1.0` | Helligkeit |
| `speed` | FLOAT | `1.0` | `> 0.0` | Rotationsgeschwindigkeit |

#### Presets:
- `gradient_ring_sunset` (`color_a`: `#FF4500`, `color_b`: `#8A2BE2`, `speed`: `0.8`)

---

### `palette_cycle` — Paletten-Farbwechsel
Durchläuft kontinuierlich eine Liste von vordefinierten Farben.

- **Typ**: State
- **Farbmodell**: Palette (`colors`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `colors` | COLOR_LIST | `["#FF0055", "#00FFCC", "#FFCC00"]` | Liste von Farben | Farbliste für den Zyklus |
| `brightness` | FLOAT | `0.8` | `0.0` bis `1.0` | Helligkeit |
| `speed` | FLOAT | `1.0` | `> 0.0` | Wechselgeschwindigkeit |

---

### `random_sparkle` — Zufälliger Funkenregen
Lässt zufällige Punkte auf dem Ring in einer Funkenfarbe aufblitzen.

- **Typ**: State
- **Farbmodell**: Dual (`color`, `sparkle_color`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00FFFF` | Hex / Farbname | Grundfarbe des Rings |
| `sparkle_color` | COLOR | `#FFFFFF` | Hex / Farbname | Farbe der aufblitzenden Funken |
| `density` | FLOAT | `0.3` | `0.0` bis `1.0` | Funkendichte |
| `brightness` | FLOAT | `0.8` | `0.0` bis `1.0` | Helligkeit |
| `speed` | FLOAT | `1.0` | `> 0.0` | Funkenfrequenz |

---

### `ring_probe` — Testpunkt-Rotation (Diagnose)
Wandert als einzelner LED-Punkt um den Ring. Ideal zum Testen der LED-Nummerierung und Ausrichtung.

- **Typ**: State
- **Farbmodell**: Mono (`color`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00FF00` | Hex / Farbname | Punktfarbe |
| `speed` | FLOAT | `1.0` | `> 0.0` | Umdrehungen pro Sekunde |

---

### `rotating_segment` — Rotierendes Segment
Ein aus mehreren LEDs bestehendes Segment rotiert um den Ring.

- **Typ**: State
- **Farbmodell**: Mono (`color`)
- **Ausrichtung**: Richtungsfähig (`reverse`)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00AAFF` | Hex / Farbname | Segmentfarbe |
| `segment_size` | INT | `3` | `1` bis `LED_COUNT` | Anzahl leuchtender LEDs |
| `brightness` | FLOAT | `0.8` | `0.0` meist `1.0` | Helligkeit |
| `speed` | FLOAT | `1.0` | `> 0.0` | Rotationsgeschwindigkeit |
| `reverse` | BOOL | `false` | `true`/`false` | Drehrichtung umkehren |

#### Presets:
- `rotating_segment_fast_blue` (`color`: `#0066FF`, `segment_size`: `3`, `speed`: `2.0`)

---

## 🌊 2. Overlays (Überlagerungen)

---

### `direction_indicator` — DoA-Richtungsanzeige (Direction of Arrival)
Zeigt die Richtung einer erkannten Schallquelle auf dem Ring an. Kann automatisch vom Hardware-DoA-Provider gepollt werden oder manuelle Live-Inputs empfangen.

- **Typ**: Controlled Overlay (Channel `doa`)
- **Input Sampling Policy**: Liest automatisch vom Hardware-Provider `doa`

#### Konfigurations-Parameter (`--config`):
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#FFCC00` | Hex / Farbname | Farbe des Richtungszeigers |
| `background_color` | COLOR | `#000000` | Hex / Farbname | Hintergrundfarbe (oder transparent) |
| `width_deg` | FLOAT | `45.0` | `1.0` bis `180.0` | Winkelbreite des Zeigers in Grad |
| `brightness` | FLOAT | `0.9` | `0.0` bis `1.0` | Helligkeit |

#### Live Runtime Inputs (`--inputs`):
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `direction_deg` | ANGLE_DEG | `0.0` | `0.0` bis `360.0` | Aktueller Richtungs-Winkel in Grad |

#### CLI & HTTP Beispiele:
```bash
# CLI: Overlay aktivieren mit 120 Grad Richtung
lefx set overlay direction_indicator --channel doa --config '{"color": "gelb"}' --inputs '{"direction_deg": 120.0}'

# CLI: Live-Richtung auf 240 Grad aktualisieren
lefx update overlay doa --inputs '{"direction_deg": 240.0}'
```

---

### `fade_flash` — Blitz mit Abklingen (Timed Overlay)
Ein kurzes Aufblitzen der LEDs, das innerhalb der angegebenen Dauer sanft abklingt.

- **Typ**: Timed Overlay (Endlicher Lebenszyklus)

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#FFFFFF` | Hex / Farbname | Blitzfarbe |
| `fade_time_ms` | DURATION_MS | `500` | `>= 1` ms | Dauer des Abklingens |
| `brightness` | FLOAT | `1.0` | `0.0` bis `1.0` | Start-Helligkeit |

---

### `level_meter` — Aussteuerungs- / Lautstärkeanzeige
Visualisiert einen Füllstand (z. B. Mikrofon-Lautstärke oder Fortschritt) als kreisförmigen Balken.

- **Typ**: Controlled Overlay

#### Konfigurations-Parameter (`--config`):
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00FFCC` | Hex / Farbname | Farbe des Füllbalkens |
| `background_color` | COLOR | `#001122` | Hex / Farbname | Farbe des leeren Bereichs |
| `brightness` | FLOAT | `0.85` | `0.0` bis `1.0` | Helligkeit |
| `reverse` | BOOL | `false` | `true`/`false` | Füllrichtung umkehren |

#### Live Runtime Inputs (`--inputs`):
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `progress` | FLOAT | `0.0` | `0.0` bis `1.0` | Füllstand (0.0 = leer, 1.0 = voll) |

#### CLI & HTTP Beispiele:
```bash
# Level Meter aktivieren und Fortschritt auf 75% setzen
lefx set overlay level_meter --channel volume --config '{"color": "green"}' --inputs '{"progress": 0.75}'

# Füllstand auf 95% aktualisieren
lefx update overlay volume --inputs '{"progress": 0.95}'
```

---

## ⚡ 3. Events (Einmalige Impulse)

---

### `pulse_signal` — Signal-Impuls
Ein einmaliger Farbimpuls, der aufleuchtet und wieder abklingt.

- **Typ**: Event

#### Parameter:
| Name | Typ | Standardwert | Grenzen | Beschreibung |
|---|---|---|---|---|
| `color` | COLOR | `#00FF88` | Hex / Farbname | Impulsfarbe |
| `duration_ms` | DURATION_MS | `800` | `>= 1` ms | Gesamtdauer des Impulses |
| `brightness` | FLOAT | `1.0` | `0.0` bis `1.0` | Maximale Helligkeit |

#### Presets:
- `pulse_signal_warning_red` (`color`: `#FF0000`, `duration_ms`: `1000`, `brightness`: `1.0`)

#### CLI & HTTP Beispiele:
```bash
# Rotes Warn-Event emittieren
lefx emit event pulse_signal --config '{"color": "red", "duration_ms": 1000}' --priority 500
```
