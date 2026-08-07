# Handoff — LEFX V3, Fortsetzung ab Phase 6

Technischer Übergabestand für eine neue Session. Enthält nur, was für die
verbleibenden Phasen gebraucht wird.

Repo: `C:\Users\marco\source\repos\respeaker-led-v3` — lokales Git, **kein
Remote**. Push erst nach ausdrücklicher Freigabe.

---

## 1. Gesamtstand

**Phasen 1–5 abgeschlossen und verifiziert.** 683 Tests grün. Nicht erneut
prüfen.

Vorhanden:

| Paket | Import | Inhalt |
|---|---|---|
| `lefx-sdk` | `lefx.sdk` | Definitionsschema, Wertnormalisierung, Ports, Kontexte |
| `lefx-engine` | `lefx.engine` | Layer, Komposition, Lebenszyklen, Registry, `lefx/3`-Loader |
| `lefx-authoring` | `lefx.authoring` | Scaffolding, Quellenvalidierung, Paketbau (`lefx-pack`) |
| `lefx-interfaces` | `lefx.interfaces` | HTTP-API `/api/v3`, CLI `lefx`, Client, Service, Discovery |
| Effektkatalog | `effects/` | 35 Definitionen, 69 Presets in zwei Sets |

**Ausstehend:**

- **Phase 6 + 7** — `respeaker-led-device` und `respeaker-led-simulator`.
  Zusammenhängender Geräteblock, gemeinsam umzusetzen. **Beide Paketgerüste
  existieren bereits** (pyproject, README, `__init__.py`); es fehlt der Inhalt.
- **Phase 8** — Doku, Architekturtests/CI, Build/Release.

Arbeitsbefehle:

```bash
uv sync
```

```bash
uv run pytest -q
```

```bash
uv run python scripts/build_effects.py
```

---

## 2. Architektur, soweit für den Rest relevant

### Abhängigkeitsrichtung (verbindlich)

```
lefx-sdk                 → (nichts, nur stdlib)
lefx-engine              → lefx-sdk
lefx-authoring           → lefx-sdk, lefx-engine
lefx-interfaces          → lefx-sdk, lefx-engine
respeaker-led-device     → lefx-sdk            ← Phase 6
respeaker-led-simulator  → lefx-sdk            ← Phase 7
```

**Device und Simulator dürfen `lefx.engine` und `lefx.interfaces` nicht
importieren.** Sie hängen ausschließlich am SDK. Die Verbindung läuft in die
andere Richtung: `lefx-interfaces` findet sie über Entry Points.

`lefx-interfaces` importiert seinerseits weder Device noch Simulator. Das ist
kein Stilprinzip, sondern der Mechanismus — wer ein Paket nicht installiert, hat
es nicht im laufenden System.

### Entry-Point-Vertrag

Die Deklarationen stehen bereits in beiden `pyproject.toml`. Die genannten
Module **fehlen noch und sind zu erstellen**. Die Provider-Namen sind dabei
**anzupassen** (siehe unten):

| Gruppe | Name | Zielsymbol (anzulegen) |
|---|---|---|
| `lefx.frame_sinks` | `respeaker` | `respeaker_led.device.registration:create_frame_sink` |
| `lefx.input_providers` | `respeaker.doa` | `respeaker_led.device.registration:create_doa_provider` |
| `lefx.frame_sinks` | `simulator` | `respeaker_led.simulator.registration:create_frame_sink` |
| `lefx.input_providers` | `simulator.doa` | `respeaker_led.simulator.registration:create_doa_provider` |

Bis diese Module existieren, meldet die Discovery beim Start eine Warnung und
überspringt sie — das ist so getestet und beabsichtigt.

#### Provider-Namen sind Fähigkeiten, keine Hersteller

Ein Effekt braucht Richtungsdaten, nicht „Daten aus einem USB-Gerät". Deshalb:

- Ein Entry Point heißt `<gerät>.<fähigkeit>`, also `respeaker.doa` und
  `simulator.doa`. Damit kollidieren sie nicht, auch wenn beide Pakete
  installiert sind.
- Die Engine sieht nur die **Fähigkeit**. Eine Definition deklariert
  `provider_id="doa"`.
- Der Service aktiviert die Provider des gewählten Geräts und stellt sie der
  Engine unter dem bloßen Fähigkeitsnamen bereit. `--sink simulator` wählt
  also `simulator.doa` als `doa`.

Damit läuft derselbe Effekt unverändert gegen Hardware und Simulator — das ist
die praktische Bedeutung von „der Simulator ist ein vollwertiges Geräte-Double".

**Daraus folgende Anpassungen in Phase 7:**

1. `discovery.py` und `service.py`: Provider nach Gerät auswählen und unter dem
   Fähigkeitsnamen registrieren (heute wird jeder gefundene Provider unter
   seinem vollen Entry-Point-Namen durchgereicht).
2. `effects/core-set/sources/overlays/direction_indicator/effect.py`:
   `provider_id="respeaker_doa"` → `provider_id="doa"`, danach
   `scripts/build_effects.py` erneut laufen lassen.
3. Optional, falls je gebraucht: `--input-device NAME`, um Ein- und Ausgabe
   getrennt zu wählen (Hardware-DoA bei Simulator-Anzeige). Nicht nötig für die
   Abnahme.

**Aufrufkonvention der Factories:** beide erhalten Keyword-Argumente; der
Service übergibt derzeit `led_count`. Die Signaturen müssen daher
`**options` verkraften:

```python
def create_frame_sink(*, led_count: int = 12, **options) -> FrameSink: ...
def create_doa_provider(*, led_count: int = 12, **options) -> InputProvider: ...
```

Siehe [discovery.py](packages/lefx-interfaces/src/lefx/interfaces/discovery.py)
(`create_sink`, `create_providers`) und
[service.py](packages/lefx-interfaces/src/lefx/interfaces/service.py)
(`_build_sink`, `_refresh_providers`).

### SDK-Ports — der einzuhaltende Vertrag

[packages/lefx-sdk/src/lefx/sdk/ports.py](packages/lefx-sdk/src/lefx/sdk/ports.py)

```python
@dataclass(slots=True, frozen=True)
class OutputFrame:
    leds: tuple[int, ...]      # ein deckender RGB-Int je LED
    timestamp: float

@dataclass(slots=True, frozen=True)
class SinkStatus:
    available: bool
    detail: str | None = None

class FrameSink(Protocol):
    def apply_frame(self, frame: OutputFrame) -> None: ...   # darf bei Gerätefehler NICHT werfen
    def status(self) -> SinkStatus: ...                      # ohne Schreibversuch
    def close(self) -> None: ...

class InputProvider(Protocol):
    def sample(self, ctx: InputContext) -> Mapping[str, Any] | None: ...   # nicht blockierend
```

**Optionale Zusatzmethoden auf Providern** (der Service ruft sie per
Duck-Typing auf, falls vorhanden):

- `refresh(now: float) -> bool` — wird einmal pro Renderframe aufgerufen; hier
  gehört der eigentliche Gerätezugriff hinein.
- `status(now: float) -> dict` — erscheint unter `input_providers` im
  Statuspayload.

Diese Trennung ist der Grund, warum Effektanzahl und Geräteabfragerate
entkoppelt bleiben: `refresh` pollt nach eigenem Takt, `sample` gibt nur den
Cache heraus.

`InputContext` liefert `now`, `led_count`, `config`, `previous_inputs`.

---

## 3. Bestehende Bausteine, die zu verwenden sind

| Zweck | Vorhandenes Symbol / Datei |
|---|---|
| Polling-Cache für Provider | `PolledInputProvider` in [inputs.py](packages/lefx-engine/src/lefx/engine/inputs.py) — **liegt in der Engine, darf von Device/Simulator nicht importiert werden**; als Vorlage nachbauen oder die Logik lokal halten |
| Fallback-Senke | `NullSink` in [discovery.py](packages/lefx-interfaces/src/lefx/interfaces/discovery.py) — Referenz für eine minimale, vertragskonforme Senke |
| Statusveröffentlichung | `ControllerService.add_listener`, Ereignis `sink_changed` in [service.py](packages/lefx-interfaces/src/lefx/interfaces/service.py) |
| Testdoppel als Muster | `RecordingSink` in [tests/interfaces/test_interfaces.py](tests/interfaces/test_interfaces.py) |
| Farb-/Geometriehilfen | `lefx.sdk`: `parse_color`, `scale_color`, `position_for_angle` |

### Zu portierende Quellen aus dem Altrepo

Pfad: `C:\Users\marco\source\repos\led_controller_respeaker\.claude\worktrees\effect-system-refactor-c81d5a\`

| Quelle | Zeilen | Ziel | Anmerkung |
|---|---:|---|---|
| `src/respeaker_led/integrations/usb_connection.py` | 250 | `respeaker_led.device.transport` | `UsbConnectionManager`: Geräteerkennung, Reconnect-Thread, Heartbeat (`read("VERSION")`), thread-sicheres `read`/`write`, `is_connected`, `connection_stats`. Belastbar, weitgehend übernehmbar. `_notify` dispatcht Callbacks bewusst off-thread — beibehalten. |
| `src/respeaker_led/integrations/adapters.py` | 127 | aufteilen | Enthält heute `ReSpeakerAdapter` mit **beiden** Richtungen. Ausgabe: `write("LED_EFFECT",[5])` einmalig + `write("LED_RING_COLOR", leds)` mit Change-Detection. Eingabe: `read("DOA_VALUE")` → Validierung → `{direction_deg, detection_state}`. |
| `src/respeaker_led/python_control/xvf_host.py` | 414 | `respeaker_led.device.xvf` | **Statisch einbinden.** Heute per `importlib.util.spec_from_file_location` über einen Dateipfad geladen — genau die Konstruktion, die im PyInstaller-Build bricht. |
| `examples/pyside6_demo.py`, `VirtualLedRingWidget` (Zeile 41) | ~60 | `respeaker_led.simulator.ring` | Ringzeichnung als Vorlage. Zwei Altlasten: LED-Anzahl ist auf 12 hartkodiert (muss `led_count` werden) und die Datei importiert `from src import ControllerService` (Pfad existiert nicht mehr). Nur das Widget übernehmen, nicht die Datei. |

`DOA_VALUE`-Payload: zwei `uint16`. `payload[0]` → `direction_deg` (0–359),
`payload[1]` → VAD, `0` → `"none"`, `1` → `"sound"`. Ein inaktives VAD ist ein
**gültiger, gesunder Messwert**, kein Providerfehler.

---

## 4. Verbindliche Invarianten für den Rest

Nicht erneut zur Diskussion stellen:

1. **`None` ≠ Schwarz.** Im Frame heißt `None` „nichts beitragen, darunter
   durchscheinen lassen"; `0x000000` ist eine Farbe und verdeckt. Für die
   Ausgabe irrelevant (`OutputFrame.leds` enthält nur deckende Ints), aber die
   Simulator-Anzeige muss Schwarz als Schwarz darstellen, nicht als „aus".
2. **Die Engine kennt kein Gerät.** Kein `offline`-State, keine Definition-ID
   irgendwo in Engine oder Service. Verbindungsverlust wird über `SinkStatus`
   gemeldet und vom Service als Ereignis veröffentlicht — mehr nicht.
3. **Ausgabe und Eingabe sind getrennte Objekte** über einem gemeinsamen
   Transport. Kein `isinstance`-Test entscheidet, ob DoA verfügbar ist; beide
   registrieren sich einzeln und können unabhängig ausfallen.
4. **`apply_frame` wirft nicht** bei einem transienten Geräteproblem. Der
   Zustand gehört in `status()`.
5. **Ringgröße ist Konfiguration**, keine Konstante. Nirgends eine feste 12.
6. **Kein stiller Kompatibilitätsmodus.** Keine V1/V2-Pfade, keine Altrouten.
7. Der Import-Whitelist des Authoring-Builds gilt **nur für Effektquellen**.
   Device und Simulator sind normale Distributionen und dürfen `usb`, `socket`,
   `PySide6` usw. verwenden.
8. **Der Simulator ist ein vollwertiger Geräteersatz, kein Vorschaumodus.**
   Er erfüllt dieselben Ports, liefert DoA-Werte im selben Format und
   Wertebereich wie die Hardware und besteht dieselbe Konformitätssuite. Kein
   Effekt und kein Aufrufer darf unterscheiden müssen, welches von beidem
   angeschlossen ist.

---

## 5. Geräteblock Phase 6 + 7

Beide Pakete erfüllen dieselben Ports und sind gegeneinander austauschbar. Das
ist der Kern: der Dienst merkt nicht, ob die Gegenstelle Hardware oder Software
ist.

### `respeaker-led-device` (Phase 6)

Abhängigkeiten stehen schon in der `pyproject.toml`: `lefx-sdk`, `pyusb`,
`libusb-package`.

Anzulegen unter `packages/respeaker-led-device/src/respeaker_led/device/`:

- `transport.py` — `UsbTransport` (portiert aus `usb_connection.py`).
- `xvf.py` — `xvf_host` statisch.
- `sink.py` — `ReSpeakerFrameSink`: `apply_frame` schreibt den Ring, überspringt
  unveränderte Frames, fängt Gerätefehler ab; `status()` spiegelt
  `transport.is_connected` samt letzter Fehlermeldung.
- `provider.py` — `ReSpeakerDoaProvider`: `refresh(now)` liest `DOA_VALUE` mit
  max. 30 Hz und cached; `sample(ctx)` gibt den Cache heraus; `status(now)`
  meldet Alter, Zählerstand und letzten Fehler.
- `registration.py` — `create_frame_sink`, `create_doa_provider`. **Beide müssen
  sich denselben Transport teilen** (Modul-Singleton oder Lazy-Factory), sonst
  öffnen zwei Objekte zwei USB-Verbindungen.

### `respeaker-led-simulator` (Phase 7)

Vollständiges Geräte-Double: Anzeige **und** simulierte Eingaben.

- **Dienstseitige Hälfte darf kein Qt importieren.** PySide6 ist ein
  `gui`-Extra. `registration.py`, Transport, Sink und Provider müssen ohne Qt
  importierbar sein — sonst zieht jede Installation des Simulators Qt in den
  Serviceprozess.
- Eigener Prozess, lokaler Transport: TCP auf Loopback, längenpräfigierte
  JSON-Frames (Plan-Entscheidung).
- `SimulatorFrameSink` sendet Frames; `status()` meldet, ob das Fenster
  verbunden ist. Ohne Fenster: `available=False` mit Detail — der Dienst läuft
  weiter.
- `SimulatorDoaProvider` liest Richtung und VAD zurück, die im Fenster per
  Regler gesetzt werden. **Format und Wertebereich sind identisch zur
  Hardware**: `direction_deg` als Float in `[0, 360)`, `detection_state` aus
  `("none", "sound", "speech")`. Ohne verbundenes Fenster liefert `sample`
  `None` — dieselbe Bedeutung wie ein nicht erreichbares Gerät, worauf die
  Engine mit `waiting` und nach der Karenzzeit mit `failed` reagiert.
- Qt-Anwendung: Ringanzeige parametrisiert auf `led_count`, Konsolenskript
  `respeaker-led-simulator` (Eintrag existiert bereits in der `pyproject.toml`).

### Gemeinsamkeiten und Unterschiede

| | Hardware | Simulator |
|---|---|---|
| Ports | identisch | identisch |
| DoA-Format und -Wertebereich | identisch | identisch |
| Fähigkeitsname für die Engine | `doa` | `doa` |
| Konformitätssuite | dieselbe | dieselbe |
| Transport | USB, Reconnect-Thread, Heartbeat | TCP-Loopback, Verbindung optional |
| Ausgabe | Change-Detection sinnvoll (USB-Writes teuer) | jeder Frame kann gesendet werden |
| Eingabe | `refresh` pollt echte Hardware, max. 30 Hz | `refresh` liest den letzten Reglerwert |
| Nicht verfügbar | Kabel ab → `available=False` | Fenster zu → `available=False` |
| Schwere Abhängigkeit | `pyusb`, `libusb-package` | `PySide6` **nur im `gui`-Extra** |

Die ersten vier Zeilen sind der Punkt: alles, was oberhalb der Ports liegt,
darf keinen Unterschied sehen. Die restlichen Zeilen sind Innenleben.

### Teststrategie: eine Suite, zwei Geräte

Weil Hardware und Simulator denselben Vertrag erfüllen, gehört **dieselbe
Konformitätssuite gegen beide** ausgeführt. Sie ist die ausführbare Form des
Port-Vertrags und der gemeinsame Nenner der beiden Pakete.

`tests/device/test_device_contract.py`, parametrisiert über die verfügbaren
Geräte:

- Simulator: läuft immer, auch im CI.
- Hardware: läuft, wenn ein Gerät angeschlossen ist, sonst `skip`.

Prüft am Vertrag, nicht an der Implementierung:

- `apply_frame` nimmt einen `OutputFrame` mit `led_count` Einträgen an und wirft
  nicht, auch nicht bei nicht verfügbarem Gerät.
- `status()` liefert `SinkStatus`; `available=False` trägt ein `detail`.
- `sample(ctx)` liefert entweder `None` oder ein Mapping, dessen Werte gegen
  `direction_indicator.runtime_input_schema` validieren — insbesondere
  `direction_deg` in `[0, 360)` und `detection_state` aus den deklarierten
  Enum-Werten.
- `refresh(now)` respektiert die eigene Taktgrenze.
- `close()` ist idempotent.
- Ein voller Durchlauf über `ControllerService`: State setzen, Overlay auf einem
  Channel, Event, Frame kommt an der Senke an.

Daneben, ergänzend statt ersetzend:

| Ebene | Womit | Wann |
|---|---|---|
| Konformität | echte Senke/Provider beider Geräte | immer (Simulator), bei Gerät auch Hardware |
| Logik | Transport-Doppel: Change-Detection, Payload-Validierung, Reaktion auf Verbindungsabbruch | immer |
| Gerätespezifisch | echtes USB | `@pytest.mark.hardware`, ohne Gerät `skip` |

Die dritte Ebene ist die, die kein Doppel ersetzen kann: nimmt der reSpeaker
`LED_RING_COLOR` wirklich an, kommt `DOA_VALUE` im erwarteten Format zurück,
meldet sich ein gezogenes Kabel als `available=False`. Diese Tests sind zu
schreiben — sie laufen nur nicht im CI.

Empfohlene Marker in `pyproject.toml` ergänzen:

```toml
markers = ["hardware: needs a connected reSpeaker; skipped without one"]
```

### Manuelle Abnahme

```bash
uv run lefx serve --sink simulator
```

Dann in einer zweiten Konsole `lefx set state`, `lefx set overlay --channel`,
`lefx emit event`; DoA-Regler bewegen und prüfen, dass `direction_indicator`
folgt. Danach dasselbe mit `--sink respeaker` gegen echte Hardware, inklusive
Kabel ziehen und stecken.

---

## 6. Phase 8

Nach dem Geräteblock, ohne weitere Vorplanung:

- `docs/effect-system` als V3-Referenz schreiben.
- Architekturtest, der die Abhängigkeitsmatrix aus Abschnitt 2 im CI erzwingt,
  plus Markertest gegen wiederauftauchende V1-Begriffe.
- Build- und Release-Setup.

---

## 7. Offene Hinweise

**Sink-Optionen.** `create_sink` reicht `led_count` und beliebige weitere
Optionen durch, aber die CLI hat derzeit **keinen Schalter für sink-spezifische
Optionen** (z. B. Simulator-Port). Falls der Simulator konfigurierbar sein soll,
ist `lefx serve` in Phase 7 um etwas wie `--sink-option key=value` zu ergänzen.

**Provider-Optionen.** `create_providers(**options)` ruft *jede* installierte
Factory mit denselben Optionen auf. Factories müssen unbekannte Keywords
tolerieren.

**Testumgebung.** Der System-Temp ist auf dieser Maschine nicht zuverlässig
erreichbar; `pyproject.toml` setzt deshalb
`addopts = "--basetemp=tests/.cache/tmp"`. Beibehalten.

**Gebaute Artefakte** (`build/effects/*.lefxset`) sind reproduzierbare Ausgabe
und per `.gitignore` ausgeschlossen. Vor einem Servicestart einmal
`scripts/build_effects.py` laufen lassen, sonst findet die Discovery keinen
Katalog. Suchpfade: `LEFX_PACKAGE_PATH`, sonst `./build/effects` und `./effects`.
