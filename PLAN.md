# LEFX V3 — neues Repo, bereinigte Architektur

## Context

Der aktuelle Stand in `led_controller_respeaker` trägt zwei vollständige Systeme
parallel: den dokumentierten V2-Pfad und einen V1-Pfad, der nicht Restbestand
ist, sondern im Betriebspfad verdrahtet bleibt (`service.py` ruft bei
USB-Verlust hart `runtime.set_state("offline")`). Dazu kommen verletzte
Modulgrenzen (Engine importiert Integrationen, Integration importiert Engine,
Integration importiert Interface), ein Schema, das ungültige Definitionen
konstruierbar lässt, und 34 von 57 Effektquellen, die die Wertnormalisierung im
Paket nachbauen und `ctx.inputs` in die Parameter verschmelzen.

Statt das im gewachsenen Repo zu operieren, entsteht ein **neues, reines Repo**.
Das bestehende bleibt unangetastet und weiterhin verfügbar — es gibt daher
keinerlei Kompatibilitätsauflagen.

Ziel: ein Stand, der `docs/effect-system` nicht nur beschreibt, sondern
erzwingt — durch typ-spezifische Definitionsklassen, echte Distributionsgrenzen
und Architekturtests, die Rückfälle im CI brechen.

## Getroffene Entscheidungen

| Thema | Entscheidung |
|---|---|
| Repo | Neues lokales Git-Repo, Greenfield mit gezielter Übernahme, **kein Remote** bis freigegeben |
| Schema | Typ-spezifische Definitionsklassen, Validierung in `__post_init__` |
| Modularisierung | Echte Distributionsgrenzen (eigenständig installierbare Pakete) |
| Ports | `FrameSink` / `InputProvider` im SDK — Engine und Hardware hängen beide nur am SDK |
| Hardware | Eigenes Paket; `ReSpeakerFrameSink` und `ReSpeakerDoaProvider` getrennt über einem Transport |
| Fake-Hardware | Vollständiges Geräte-Double (Anzeige + simulierte DoA/VAD), eigener Prozess, lokaler Transport |
| Offline-Verhalten | Nicht in der Engine — Status wird veröffentlicht, Zuordnung macht eine Anwendungsintegration |
| Authoring | Build-/Scaffolding-Logik verlässt das Laufzeitpaket |
| Katalog | `smartspeaker-set` (23) portieren + kleines kuratiertes `core-set` (8–12) neu bauen |
| Format | `lefx/3` / `lefxset/3`; Generation durchgängig **V3** |
| Alt-Tools | Effect-Tester und DoA-Kalibrierskripte werden zunächst nicht übernommen |

### Namensannahme (bitte bei der Freigabe bestätigen)

Da die Generation durchgängig V3 heißt:

- Verzeichnis: `C:\Users\marco\source\repos\respeaker-led-v3`
- Distributionen: `lefx-sdk`, `lefx-engine`, `lefx-interfaces`, `lefx-authoring`,
  `respeaker-led-device`, `respeaker-led-simulator` — alle startend bei
  Version `3.0.0`, damit Paketversion und Systemgeneration übereinstimmen
- Importnamen: `lefx.sdk`, `lefx.engine`, `lefx.interfaces`, `lefx.authoring`,
  `respeaker_led.device`, `respeaker_led.simulator` (PEP-420-Namespaces)

## Zielarchitektur

```
respeaker-led-v3/
├── pyproject.toml              uv-Workspace
├── packages/
│   ├── lefx-sdk/               lefx.sdk
│   ├── lefx-engine/            lefx.engine
│   ├── lefx-interfaces/        lefx.interfaces
│   ├── lefx-authoring/         lefx.authoring
│   ├── respeaker-led-device/   respeaker_led.device
│   └── respeaker-led-simulator/respeaker_led.simulator
├── effects/
│   ├── core-set/               kuratierte Referenzdefinitionen
│   └── smartspeaker-set/       portiert
├── docs/effect-system/         V3-Referenz
└── tests/
```

**Erlaubte Abhängigkeitsrichtung** (Architekturtest erzwingt sie):

```
lefx-sdk          → (nichts)
lefx-engine       → lefx-sdk
lefx-authoring    → lefx-sdk, lefx-engine
lefx-interfaces   → lefx-sdk, lefx-engine
respeaker-*-device→ lefx-sdk
respeaker-*-simulator → lefx-sdk
```

`lefx-interfaces` importiert **weder** Device **noch** Simulator. Beide
registrieren sich über Entry Points (`lefx.frame_sinks`,
`lefx.input_providers`), die der Service über `importlib.metadata` einliest.
Damit ist die Distributionsgrenze nicht nur Konvention, sondern Mechanik: wer
den Simulator nicht installiert, hat ihn nicht.

## Was übernommen wird, was neu entsteht

### Weitgehend unverändert übernehmen

| Quelle | Ziel | Anmerkung |
|---|---|---|
| [core/value_normalization.py](src/respeaker_led/core/value_normalization.py) | `lefx.sdk.values` | Sauber, vollständig, gut getestet |
| [core/parameter_validation.py](src/respeaker_led/core/parameter_validation.py) | `lefx.sdk.validation` | `type`-Vergleiche auf Enum umstellen |
| [core/color_math.py](src/respeaker_led/core/color_math.py) | `lefx.sdk.color` | `LED_COUNT`-Import entfernen |
| [engine/effect_package_loader.py](src/respeaker_led/engine/effect_package_loader.py) | `lefx.engine.packages` | ZIP/Hash/Isolationslogik ist tragfähig |
| [engine/effect_package_schema.py](src/respeaker_led/engine/effect_package_schema.py) | `lefx.engine.packages` | Serialisierung an Schema V3 anpassen, Stempel `lefx/3` |
| [engine/input_provider.py](src/respeaker_led/engine/input_provider.py) | `lefx.engine.inputs` | `PolledInputProvider` unverändert brauchbar |
| [integrations/usb_connection.py](src/respeaker_led/integrations/usb_connection.py) | `respeaker_led.device.transport` | Reconnect/Heartbeat/Locking sind belastbar |
| [python_control/xvf_host.py](src/respeaker_led/python_control/xvf_host.py) | `respeaker_led.device.xvf` | **Statisch** einbinden statt Pfad-Loading |
| [examples/pyside6_demo.py:41](examples/pyside6_demo.py) `VirtualLedRingWidget` | `respeaker_led.simulator.ring` | `led_count` parametrisieren |
| [infrastructure/*](src/respeaker_led/infrastructure/) | verteilt | Pfade/Logging/YAML pro Paket, keine gemeinsame Infra-Schicht |

### Neu bauen

Schema, Layer/Store, Composer, Renderer, Runtime, Registry-Auflösung, Service,
API, CLI, Client, Simulator-Transport, Authoring-CLI.

### Ersatzlos entfällt

`ControllerCommandNormalizer` samt Farbtabellen, `BASE_STATE_NAMES`,
`EVENT_NAMES`, `CountdownState`, `BaseState`, `LEGACY_SCENE_NAMES`,
`Scene`/`Visual`/`LayerVisual`, `main_layer_valid`, `exclusive`, `/api/v1/*`,
die V1-CLI-Kommandos, `set_progress`, `set_direction`, `stt_adapter`.

## Schema V3

### Typ-spezifische Definitionsklassen

`lefx.sdk.definitions` ersetzt die flache `EffectDefinition`:

```
DefinitionBase        id, title, description, parameter_schema, defaults,
                      color_model, composition, animated, directional,
                      tags, version

StateDefinition       + slots: tuple[StateSlot, ...]   (BACKGROUND | PRIMARY)
                      + restorable: bool               (nur mit BACKGROUND)

ControlledOverlayDefinition
                      + runtime_input_schema
                      + input_sampling: InputSamplingPolicy

TimedOverlayDefinition
                      + duration_field: DURATION_MS | TOTAL_MS
                      + supports_duration_override: bool

EventDefinition       + duration_field
                      + supports_duration_override: bool
                      + default_priority: int | None
```

Damit ist „welche Option wann zulässig" strukturell beantwortet: ein State
**kann** kein `runtime_input_schema` haben, weil das Feld dort nicht existiert.

**`layer_rules` entfällt vollständig.** Alles, was heute darin steht, ist aus
dem Typ ableitbar — `requires_finite_duration`, `allowed_playback_modes`,
`allows_transparency` (sagt schon `composition`), `queue_mode` (nur Events
haben eine Queue). Einzige echte Wahl war der State-Platz; die wird zu `slots`.

**`EffectCapabilities` entfällt ebenfalls.** `preemptible` aktiviert laut
Doku nichts, `supports_queueing` ist typbedingt, `data_driven` ist aus
`runtime_input_schema` ableitbar, `supports_transparency` dupliziert
`composition`, `playback_modes` folgt dem Typ. Übrig bleibt
`supports_duration_override` — als reguläres Feld der endlichen Typen, das die
Runtime auch tatsächlich auswertet.

### Parameter-Zulässigkeitsmatrix

`type` wird ein Enum (`ParamType`). Erlaubte Zusatzfelder pro Typ:

| Typ | minimum/maximum | enum_values | unit | nullable |
|---|---|---|---|---|
| `BOOL` | – | – | – | nur Runtime-Input |
| `INT`, `FLOAT` | ja | – | ja | nur Runtime-Input |
| `DURATION_MS` | ja | – | ja (`ms`) | nur Runtime-Input |
| `ANGLE_DEG` | – | – | ja (`deg`) | nur Runtime-Input |
| `ENUM` | – | **Pflicht**, ≥1 | – | nur Runtime-Input |
| `COLOR` | – | – | – | nur Runtime-Input |
| `COLOR_LIST` | ja (Listenlänge) | – | – | nur Runtime-Input |
| `GRADIENT`, `COLOR_RANGE` | – | – | – | nur Runtime-Input |

Zusätzlich erzwungen:

- `default` wird durch denselben Normalisierer geprüft wie ein Eingabewert
- `required=True` **und** `default` gesetzt → Fehler
- `aliases` kollisionsfrei über `parameter_schema` ∪ `runtime_input_schema`
- Farbmodell-Pflichtfelder mit erzwungenem Typ: `color`/`secondary_color` →
  `COLOR`, `colors` → `COLOR_LIST`, `gradient` → `GRADIENT`, `color_range` →
  `COLOR_RANGE`, `random_seed` → `INT`
- `animated=True` → `speed` als `FLOAT` mit `minimum > 0`
- `directional=True` → `reverse` als `BOOL`
- endliche Typen → `duration_ms`/`total_ms` als `DURATION_MS`, `minimum ≥ 1`
- reservierte Namen mit fester Semantik: `brightness` (`FLOAT` 0..1),
  `direction_deg` (`ANGLE_DEG`), `progress` (`FLOAT` 0..100)

Alle Prüfungen laufen in `__post_init__` — eine ungültige Definition ist nicht
konstruierbar, nicht bloß nicht validierbar.

## Engine

- **Scene-Indirektion entfällt.** Heute erzeugt der Composer
  `Visual("dynamic_frame", {"provider": lambda})`, das der Renderer wieder
  auspackt. Neu: Composer liefert eine geordnete `list[LayerFrame]`, der
  Renderer komponiert. `main_layer_valid` und `exclusive` sind tot und fallen weg.
- **`LayerStore` ohne Anwendungszustand** — nur Layer plus globale
  Ausgabeeinstellungen (`brightness`, `enabled`).
- **Keine `__`-Metadaten in `params`.** `activated_at`, `channel`, `source`
  werden reguläre Felder der Invocation.
- **`led_count` aus der Runtime-Konfiguration**, nicht als Modulkonstante.
  Der Renderer prüft die Framelänge dagegen.
- **Renderschleife gehört der Engine** (headless, einbettbar); Prozess-Hosting
  (uvicorn, Ports, PID-Datei) gehört zu `lefx-interfaces`.

## Paketformat lefx/3

Struktur bleibt (ZIP mit `manifest.json`, `payload/`, `hashes.json`,
optional `effect-presets.json`). Änderungen:

- Stempel `lefx/3` / `lefxset/3`
- Manifest serialisiert die typ-spezifische Definition; `layer_rules` und
  `capabilities` verschwinden, `slots` / `duration_field` /
  `supports_duration_override` kommen hinzu
- Import-Whitelist für Quellen zeigt auf `lefx.sdk.*` statt `src.core.*`
- Manifest-/Klassen-Gleichheitsprüfung und SHA-256 bleiben unverändert

## Hardware und Simulator

Beide erfüllen dieselben SDK-Ports und sind gegeneinander austauschbar.

**`respeaker-led-device`**
- `UsbTransport` (portiert aus `usb_connection.py`)
- `ReSpeakerFrameSink` — `LED_EFFECT`/`LED_RING_COLOR`, Change-Detection
- `ReSpeakerDoaProvider` — `DOA_VALUE` → `{direction_deg, detection_state}`
- Getrennte Objekte, beide über Entry Points registriert. Damit entfällt die
  `isinstance(adapter, DoAInputAdapter)`-Prüfung aus
  [service.py:51](src/respeaker_led/services/service.py:51), und Ausgabe- und
  Eingabeverfügbarkeit können unabhängig ausfallen.
- `xvf_host` als normales Modul — beseitigt das `spec_from_file_location`-Laden,
  das im PyInstaller-Build bricht

**`respeaker-led-simulator`**
- `SimulatorFrameSink` schreibt Frames über einen lokalen Transport
  (TCP auf Loopback, längenpräfigierte JSON-Frames) an den Simulatorprozess
- Qt-Anwendung: Ring-Anzeige (parametrisiert auf `led_count`) plus Regler für
  `direction_deg` und VAD
- `SimulatorDoaProvider` liest diese Werte zurück
- Der Service weiß nicht, dass die Gegenstelle Software ist

**Verbindungsverlust:** Der Status erscheint in `/status` und wird über einen
Callback des Service veröffentlicht. Die Engine kennt keinen „offline"-Zustand
und keine Definition-ID. Eine Anwendungsintegration, die daraus einen State
macht, ist dokumentiertes Rezept, nicht Bestandteil des Kerns.

## Steuerungsoberfläche

Nur `/api/v3/*`, keine Altrouten:

```
GET  /api/v3/states|overlays|events|presets      ?details=true
GET  /api/v3/show/{target}
POST /api/v3/set/state       clear/state
POST /api/v3/set/overlay     update/overlay     clear/overlay
POST /api/v3/emit/event
GET  /api/v3/status          POST /api/v3/output   (brightness, enabled)
GET  /api/v3/sources         POST register|reload  DELETE /{source_id}
```

CLI-Verben: `list`, `show`, `set`, `clear`, `update`, `emit`, `output`,
`sources`, `serve`, `status`. Die Serialisierung wandert aus dem Service in
eine eigene Präsentationsschicht in `lefx-interfaces`.

## Effektkatalog

- **`smartspeaker-set` portieren** (23 Quellen, 4.866 Zeilen). Der Satz ist
  sauber: null Treffer für paketlokale Normalisierung oder
  `params.update(ctx.inputs)`, bereits gegen `led_count` 5 und 12 geprüft, mit
  eigener Umsetzungsspezifikation. Anpassungsbedarf beschränkt sich auf die
  neuen Definitionsklassen.
- **`core-set` neu kurieren** (8–12 Definitionen): deckt alle vier
  Lebenszyklusformen und alle Farbmodelle ab, dient zugleich als
  Referenzmaterial. Enthält einen `direction_indicator`, der ohne
  `_parse_color`/`_merge_params` auskommt.
- `default-effects` (34 Quellen) wandert **nicht** mit.

## Dokumentation

`docs/effect-system` wird als V3 neu geschrieben. Nachträge gegenüber heute:

1. Neues Kapitel **Modulschichten und Abhängigkeitsrichtung** mit der
   Paketmatrix und dem Entry-Point-Mechanismus
2. Kapitel 09 erweitern um Ausgabeeinstellungen, Statusabfrage und
   Paketquellen-Verwaltung — heute fehlen sie komplett
3. SDK-Importpfade korrigieren (`src.core.*` → `lefx.sdk.*`)
4. Kapitel 05 bekommt die Zulässigkeitsmatrix als Tabelle
5. Neues Kapitel **Fehlerformat und Fehlercodes**
6. Neues Kapitel **Status, Persistenz und Service-Lebenszyklus**
7. Neues Kapitel **Hardware, Simulator und Ports**
8. `led_count`: Ringgröße wird konfigurierbar, Doku und Code stimmen überein
9. Versionierungs- und Deprecation-Regel: kein stiller Kompatibilitätsmodus
10. Kapitel 12 neu — die V1-Altlastenliste ist mit dem Fork erledigt

## Umsetzungsreihenfolge

| # | Phase | Ergebnis |
|---|---|---|
| 0 | Verzeichnisfreigabe + Repo-Init | Leeres Git-Repo, uv-Workspace, kein Remote |
| 1 | `lefx-sdk` | Schema V3, Werte, Validierung, Farbmathematik, Ports |
| 2 | `lefx-engine` | Layer, Composer, Renderer, Runtime, Registry, `lefx/3`-Loader |
| 3 | `lefx-authoring` | Builder, Scaffolding, Packager, Set-Builder |
| 4 | Effektkatalog | `core-set` neu, `smartspeaker-set` portiert, beide gebaut |
| 5 | `lefx-interfaces` | API v3, CLI, Client, Prozess-Hosting |
| 6 | `respeaker-led-device` | Transport, Frame-Senke, DoA-Provider, `xvf_host` |
| 7 | `respeaker-led-simulator` | Transport, Ring-Anzeige, simulierte Eingaben |
| 8 | Doku + Architekturtests + Build | V3-Referenz, CI-Regeln, Release-Setup |

Phasen 1–3 sind hardwarefrei und vollständig testbar. Phase 7 macht Phase 4–5
ohne ReSpeaker demonstrierbar.

## Verifikation

**Automatisiert, pro Phase:**

- **Architekturtest** — parst die Importe aller Pakete und bricht bei jeder
  Verletzung der Abhängigkeitsmatrix; zusätzlich Marker-Test gegen
  wiederauftauchende V1-Begriffe (`base_state`, `countdown`, `api/v1`,
  `LEGACY_`, `Visual(`)
- **Schema-Matrixtests** — für jede Zeile der Zulässigkeitsmatrix je ein
  gültiger und ein ungültiger Fall; ungültige Definitionen müssen bereits im
  Konstruktor scheitern
- **Wertnormalisierung** — die bestehenden Fälle aus
  [tests/test_value_normalization.py](tests/test_value_normalization.py) und
  [tests/test_parameter_validation.py](tests/test_parameter_validation.py)
  übernehmen
- **Paket-Roundtrip** — Quelle → validieren → packen → verifizieren → laden →
  Smoke-Render für jede Definition, gegen mehrere `led_count`-Werte
- **Runtime** — Layer-Belegung, Event-Queue mit Priorität und FIFO,
  Input-Health-Übergänge (`waiting` → `healthy` → `failed`), Channel-Lebenszyklus
- **API/CLI** — Endpunkte gegen `httpx`, CLI gegen den eingebetteten Service

**Manuell, am Ende:**

```bash
uv run lefx serve --sink simulator
```

Simulator zeigt den Ring; `set state`, `set overlay --channel`, `emit event`
gegen den laufenden Dienst; DoA-Regler bewegen und prüfen, dass
`direction_indicator` folgt.

```bash
uv run lefx serve --sink respeaker
```

Dasselbe gegen echte Hardware, inklusive Kabel ziehen und stecken, um
Reconnect und Statusveröffentlichung zu prüfen.

## Offene Punkte für später

- Push nach GitHub, sobald du den Stand gesehen hast
- Effect-Tester gegen die V3-API neu bauen
- Bewertung der 34 `default-effects`-Quellen einzeln
- Signatur-/Trust-Modell (in V2 bewusst nicht vorhanden, bleibt offen)