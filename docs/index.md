# LEFX V3 — das System auf einen Blick

Sieben Distributionen, ein Vertrag, zwei austauschbare Geräte. Diese Seite ist
der Einstieg: sie zeigt, welches Paket welche Rolle hat, in welche Richtung die
Abhängigkeiten zeigen — und warum an einer Stelle bewusst *keine* Abhängigkeit
steht, obwohl dort etwas zusammenarbeitet.

---

## Das große Bild

```mermaid
flowchart TB
    classDef contract fill:#1d3557,stroke:#457b9d,color:#fff,stroke-width:2px
    classDef core fill:#2a4d3e,stroke:#5b9279,color:#fff,stroke-width:2px
    classDef app fill:#4a3b5c,stroke:#8a6fa8,color:#fff,stroke-width:2px
    classDef device fill:#5c3b31,stroke:#a86f5c,color:#fff,stroke-width:2px
    classDef tool fill:#3c4a5c,stroke:#6f8aa8,color:#fff,stroke-width:2px

    subgraph BEDIENUNG["Bedienung — im Betrieb"]
        direction LR
        CLI["<b>lefx</b> — Kommandozeile<br/>set · clear · update · emit<br/>output · list · show · status"]
        REST["<b>HTTP</b> /api/v3<br/>dieselben Kommandos,<br/>andere Oberfläche"]
    end

    subgraph ANWENDUNG["Anwendungsschicht"]
        IFACE["<b>lefx-interfaces</b><br/><i>lefx.interfaces</i><br/><br/>ControllerService · API v3 · CLI<br/>Client · Discovery · Hosting<br/><br/>Bindet alles zusammen und<br/>hält als Einziges den Renderloop"]
    end

    subgraph WERKZEUG["Werkstatt — vor dem Betrieb"]
        direction LR
        GUI["<b>lefx-studio</b> <i>(Konsolenskript)</i><br/><i>lefx.effect_creation.studio</i><br/><br/>Effekte abspielen und regeln · DoA kalibrieren<br/>Presets kuratieren · neue Quellen entwerfen<br/><br/><i>startet keinen Dienst, sondern<br/>hält seine eigene Engine im Prozess</i>"]
        AUTH["<b>lefx-effect-creation</b><br/><i>lefx.effect_creation</i><br/><br/>Scaffolding · Quellenprüfung<br/>Packen zu lefx/3 · lefx-pack<br/><br/>Eine Distribution mit beiden Hälften.<br/>Optional: gehört in keine Laufzeitinstallation"]
    end

    subgraph KERN["Kern"]
        ENGINE["<b>lefx-engine</b><br/><i>lefx.engine</i><br/><br/>Layer · Composer · Renderer · Runtime<br/>Registry · Paketlader · Input-Health<br/><br/>Kennt kein Gerät, keine Route, kein Qt"]
    end

    subgraph VERTRAG["Vertrag"]
        SDK["<b>lefx-sdk</b><br/><i>lefx.sdk</i><br/><br/>Definitionsschema · Wertnormalisierung<br/>Parameterprüfung · Farb- und Ringmathematik<br/><b>Ports:</b> FrameSink · InputProvider<br/>DoA-Kalibrierung · Kontexte<br/><br/>Hängt an nichts. Absichtlich."]
    end

    subgraph GERAETE["Geräte — beide erfüllen dieselben Ports"]
        direction LR
        DEV["<b>lefx-device-respeaker</b><br/><i>lefx.device.respeaker</i><br/><br/>UsbTransport · xvf · Sink · DoA-Provider<br/>Reconnect · Heartbeat · Change-Detection"]
        SIM["<b>lefx-device-simulated-respeaker</b><br/><i>lefx.device.simulated_respeaker</i><br/><br/>TCP-Link · Protokoll · Sink · DoA-Provider<br/>Ringfenster <i>(Qt nur im gui-Extra)</i>"]
    end

    subgraph KATALOG["Kataloge — Daten, kein Code"]
        SETS["<b>lefxset-core-set</b> · <b>lefxset-smartspeaker-set</b><br/><i>lefx.sets.core_set</i> · <i>lefx.sets.smartspeaker_set</i><br/><br/>Je ein gebautes .lefxset und die Zeile,<br/>die sagt, wo es liegt. Hängen an nichts."]
    end

    CLI --> IFACE
    REST --> IFACE

    IFACE --> ENGINE
    AUTH --> ENGINE
    GUI --> AUTH
    GUI --> IFACE
    ENGINE --> SDK
    IFACE --> SDK
    AUTH --> SDK
    GUI --> SDK

    DEV --> SDK
    SIM --> SDK

    DEV -.->|"Entry Point<br/>lefx.frame_sinks / lefx.input_providers"| IFACE
    SIM -.->|"Entry Point"| IFACE

    class SDK contract
    class ENGINE core
    class IFACE,CLI,REST app
    class GUI,AUTH tool
    class DEV,SIM device
```

**Durchgezogen** heißt „importiert" — eine Abhängigkeit, die in der
`pyproject.toml` steht und ohne die das Paket nicht installierbar ist.
**Gestrichelt** heißt „wird zur Laufzeit über Entry Points gefunden, ohne
importiert zu werden".

Die Werkstatt steht bewusst neben der Bedienung, nicht darin. `lefx` und die
HTTP-API steuern einen **laufenden Dienst** — das ist der Betrieb. Studio und
`lefx-effect-creation` entstehen und arbeiten **davor**: sie entwerfen, prüfen und
bauen, was der Dienst später lädt, und keines von beidem gehört in eine
Installation, die nur Effekte abspielen soll. Das Studio startet dafür auch
keinen Dienst, sondern hält seine eigene Engine — deshalb kann es eine Quelle
rendern, die noch gar nicht gebaut ist.

Die beiden Pfeilarten zeigen bei den Geräten in **entgegengesetzte Richtungen**,
und das ist der Kern der Architektur: Ein Gerät hängt am SDK und sonst an
nichts. Der Dienst hängt *nicht* am Gerät — er liest die Entry Points aus den
installierten Paketmetadaten. Wer den Simulator nicht installiert, hat ihn
nicht, und es gibt keine Codezeile, die man dafür vergessen könnte.

---

## Die neun Distributionen

Alle tragen eine Versionsnummer und werden gemeinsam veröffentlicht. Installiert
wird über einen Namen — `pip install led-ctrl-v3` — plus Extras für alles, was
zum Abspielen nicht gebraucht wird.

| Paket | Import | Rolle | Hängt ab von | Teil von |
|---|---|---|---|---|
| **led-ctrl-v3** | — | Der Name, unter dem installiert wird. Enthält keinen Code; ein Architekturtest hält es dabei. | (nur Abhängigkeiten) | — |
| **lefx-sdk** | `lefx.sdk` | Der Vertrag. Was ein Effekt deklarieren darf, wie Werte normalisiert werden, wie ein Gerät angesprochen wird. | — | Standard |
| **lefx-engine** | `lefx.engine` | Die Laufzeit. Layer, Komposition, Lebenszyklen, Registry, Paketformat `lefx/3`. | sdk | Standard |
| **lefx-interfaces** | `lefx.interfaces` | Die Steuerungsoberfläche: `ControllerService`, HTTP-API, CLI, Client, Discovery, Konfiguration. | sdk, engine | Standard |
| **lefx-device-respeaker** | `lefx.device.respeaker` | Die echte Hardware: USB-Transport, LED-Senke, DoA-Provider. | sdk | Standard |
| **lefx-device-simulated-respeaker** | `lefx.device.simulated_respeaker` | Das Software-Double: lokaler Transport, Ringfenster, simulierte DoA. | sdk | `[simulated-respeaker]` |
| **lefx-effect-creation** | `lefx.effect_creation` | Alles zum Erstellen von Effekten: Gerüst, Prüfung, Bauen (`lefx-pack`) und die Desktop-Werkstatt (`lefx-studio`). | sdk, engine, interfaces | `[effect-creation]` |
| **lefxset-core-set** | `lefx.sets.core_set` | Der Referenzkatalog als gebautes `.lefxset`. | — | `[core-set]` |
| **lefxset-smartspeaker-set** | `lefx.sets.smartspeaker_set` | Der Sprachassistenz-Katalog. | — | `[smartspeaker-set]` |

### Die erlaubte Richtung

```text
lefx-sdk                         → (nichts)
lefx-engine                      → lefx-sdk
lefx-interfaces                  → lefx-sdk, lefx-engine
lefx-effect-creation             → lefx-sdk, lefx-engine, lefx-interfaces
lefx-device-respeaker            → lefx-sdk
lefx-device-simulated-respeaker  → lefx-sdk
lefxset-core-set                 → (nichts)
lefxset-smartspeaker-set         → (nichts)
```

Innerhalb von `lefx-effect-creation` läuft eine zweite Grenze, weil Qt dort
harte Abhängigkeit ist: nichts direkt unter `lefx/effect_creation/` importiert
PySide6, und nichts dort importiert `studio/`. Eine Build-Strecke, die
`lefx-pack` aufruft, fasst den Toolkit also nie an. Auch das sind zwei Tests.

Diese Matrix ist keine Absichtserklärung, sondern ein Test:
`tests/architecture/test_architecture.py` parst die Importe **jeder** Quelldatei
jeder Distribution und bricht bei jeder Verletzung. Ein `from lefx.engine import …`
im Gerätepaket würde im Workspace problemlos funktionieren — genau deshalb wird
es dort geprüft und nicht dem guten Willen überlassen.

---

## Ein Frame, von der Eingabe bis zur LED

```mermaid
flowchart LR
    classDef iface fill:#4a3b5c,stroke:#8a6fa8,color:#fff
    classDef engine fill:#2a4d3e,stroke:#5b9279,color:#fff
    classDef sdk fill:#1d3557,stroke:#457b9d,color:#fff
    classDef dev fill:#5c3b31,stroke:#a86f5c,color:#fff

    CMD["<b>Kommando</b><br/>lefx set state ready_state<br/>oder POST /api/v3/set/state"]
    SVC["<b>ControllerService</b><br/>nimmt an, rendert sofort,<br/>persistiert Background-State"]
    RT["<b>Runtime</b><br/>löst Namen auf, prüft Werte,<br/>legt eine Invocation auf ihren Layer"]
    ST["<b>LayerStore</b><br/>fünf Plätze, Event-Queue,<br/>brightness · enabled"]
    CMP["<b>Composer</b><br/>ruft render je Layer,<br/>zieht Runtime-Inputs"]
    RND["<b>Renderer</b><br/>legt die Layer übereinander,<br/>None lässt durch, skaliert global"]
    FRAME["<b>OutputFrame</b><br/>led_count deckende RGB-Ints<br/>+ Zeitstempel"]
    SINK["<b>FrameSink</b><br/>respeaker · simulator · null"]
    RING(["LED-Ring"])

    CMD --> SVC --> RT --> ST --> CMP --> RND --> FRAME --> SINK --> RING

    class CMD,SVC iface
    class RT,ST,CMP,RND engine
    class FRAME,SINK sdk
    class RING dev
```

Der Schnitt liegt bei `OutputFrame`. Alles links davon ist Komposition, alles
rechts davon ist Gerät — und die Senke bekommt nie etwas anderes als eine Liste
deckender Farben. Sie wirft dabei nicht: ein Kabel, das zwischen zwei Frames
gezogen wird, ist ein normaler Zustand und wird über `status()` gemeldet, nicht
über eine Exception in den Renderloop.

### Der Layerstapel

```mermaid
flowchart BT
    classDef layer fill:#2a4d3e,stroke:#5b9279,color:#fff
    BG["<b>background_state</b> · 100<br/>überlebt Neustarts, wenn restorable"]
    PS["<b>primary_state</b> · 200<br/>der laufende Anwendungszustand"]
    TO["<b>timed_overlay</b> · 400<br/>läuft von selbst ab"]
    CO["<b>controlled_overlay</b> · 500<br/>bekommt Werte, solange es läuft"]
    EV["<b>event</b> · 600<br/>einmalig, mit Queue und Priorität"]
    BG --> PS --> TO --> CO --> EV
    class BG,PS,TO,CO,EV layer
```

Von unten nach oben. Ein controlled overlay liegt **über** einem timed overlay,
weil eine laufende funktionale Anzeige sichtbar bleiben soll; was wirklich für
einen Moment alles verdecken muss, ist ein Event.

Welcher Layer bedient wird, folgt aus dem **Typ der Definition** — nicht aus
einem Feld, das man falsch setzen kann. Die vier Formen sind:

| Form | Verb | Kanal | Endet | Runtime-Inputs |
|---|---|---|---|---|
| `StateDefinition` | `set state` | — | nie | — |
| `TimedOverlayDefinition` | `set overlay` | — | selbst | — |
| `ControlledOverlayDefinition` | `set overlay --channel` | ja | nie | ja |
| `EventDefinition` | `emit event` | — | selbst | — |

---

## Der Weg zurück: Richtungsdaten

Der interessantere Pfad läuft andersherum — vom Gerät in den Effekt.

```mermaid
flowchart LR
    classDef dev fill:#5c3b31,stroke:#a86f5c,color:#fff
    classDef iface fill:#4a3b5c,stroke:#8a6fa8,color:#fff
    classDef engine fill:#2a4d3e,stroke:#5b9279,color:#fff

    MIC["<b>Mikrofonarray</b> oder <b>Regler</b><br/>DOA_VALUE · Simulatorfenster"]
    PROV["<b>InputProvider</b><br/>refresh: liest das Gerät, max. 30 Hz<br/>sample: gibt den Cache heraus<br/>+ Kalibrierung des Geräts"]
    EP["<b>Entry Point</b><br/>respeaker.doa · simulator.doa"]
    CAP["<b>Capability</b> doa<br/>der Name, den die Engine sieht"]
    EFF["<b>direction_indicator</b><br/>provider_id = doa<br/>kennt kein Gerät"]
    OUT(["Marker auf 1 oder 2 LEDs"])

    MIC --> PROV --> EP --> CAP --> EFF --> OUT
    class MIC,PROV dev
    class EP,CAP iface
    class EFF,OUT engine
```

Drei Entscheidungen stecken in dieser Kette:

1. **Entry Points heißen `<gerät>.<fähigkeit>`.** Beide Pakete dürfen gleichzeitig
   installiert sein, ohne zu kollidieren.
2. **Die Engine sieht nur die Fähigkeit.** Eine Definition schreibt
   `provider_id="doa"` — nie `respeaker_doa`. Die Wahl der Senke wählt das Gerät,
   und dessen Provider erreicht die Engine unter dem nackten Fähigkeitsnamen.
   Derselbe Effekt läuft unverändert gegen Hardware und Simulator.
3. **`refresh` und `sample` sind getrennt.** Zehn Overlays, die die Richtung
   beobachten, kosten einen Gerätezugriff pro Intervall statt zehn pro Frame.

### Kalibrierung gehört zum Gerät

Mikrofonarray-Null und LED-Null sind auf einer echten Platine nicht dieselbe
Richtung — beim reSpeaker liegt der Kabelanschluss zwischen der zwölften und der
ersten LED. Diese Drehung ist eine **Eigenschaft des Geräts** und wird dort
angewandt, bevor die Peilung herausgegeben wird:

```text
doa_calibration.json   {"respeaker": {"angle_offset_deg": 129.1, "reverse": false}}
                        └─ pro Gerät, weil ein Simulator keinen Montagewinkel hat
```

Ein Effekt bekommt damit eine Peilung, die schon auf dem Ring liegt, und muss
nicht wissen, wie herum die Platine eingebaut wurde.

**Halbe LED-Schritte.** Eine Richtung trifft genauso oft *zwischen* zwei LEDs wie
auf eine. Der Ring wird deshalb in `2 × led_count` Sektoren gelesen — bei zwölf
LEDs also 15° — und eine Zwischenrichtung leuchtet auf beiden Nachbarn mit
halber Helligkeit, statt auf die nächstgelegene gerundet zu werden.

---

## Effekte: von der Quelle ins laufende System

```mermaid
flowchart LR
    classDef auth fill:#4a3b5c,stroke:#8a6fa8,color:#fff
    classDef pkg fill:#3a3a3a,stroke:#777,color:#fff
    classDef engine fill:#2a4d3e,stroke:#5b9279,color:#fff

    SRC["<b>Quelle</b><br/>effect.py · effect.yaml<br/>presets.yaml"]
    VAL["<b>Prüfung</b><br/>Schema · Import-Whitelist<br/>Smoke-Render bei mehreren led_count"]
    PACK["<b>lefx-pack</b><br/>Manifest · SHA-256"]
    LEFX["<b>.lefx</b> / <b>.lefxset</b><br/>Stempel lefx/3"]
    LOAD["<b>Loader</b><br/>Hashprüfung, isolierter Import"]
    REG["<b>Registry</b><br/>Definitionen + Presets,<br/>global eindeutige Ids"]

    SRC --> VAL --> PACK --> LEFX --> LOAD --> REG
    class SRC,VAL,PACK auth
    class LEFX pkg
    class LOAD,REG engine
```

Eine ungültige Definition ist **nicht konstruierbar** — die Prüfungen laufen in
`__post_init__` der typ-spezifischen Definitionsklassen, nicht in einem
Validator, den man vergessen kann aufzurufen. Der Import-Whitelist gilt dabei
nur für Effektquellen; Gerätepakete sind normale Distributionen und dürfen
`usb`, `socket` und `PySide6` verwenden.

---

## Zwei Geräte, ein Vertrag

|  | Hardware | Simulator |
|---|---|---|
| Ports | identisch | identisch |
| DoA-Format und -Wertebereich | identisch | identisch |
| Fähigkeitsname für die Engine | `doa` | `doa` |
| Konformitätssuite | dieselbe | dieselbe |
| Kalibrierung | dieselbe Mechanik | dieselbe Mechanik |
| Transport | USB, Reconnect-Thread, Heartbeat | TCP-Loopback, Verbindung optional |
| Ausgabe | Change-Detection (USB-Writes sind teuer) | jeder Frame wird gesendet |
| Nicht verfügbar | Kabel ab → `available=False` | Fenster zu → `available=False` |
| Schwere Abhängigkeit | `pyusb`, `libusb-package` | `PySide6` nur im `gui`-Extra |

Die ersten fünf Zeilen sind der Punkt: oberhalb der Ports darf kein Aufrufer
einen Unterschied sehen. Der Rest ist Innenleben.

Deshalb läuft `tests/device/test_device_contract.py` **parametrisiert über beide
Geräte** — gegen den Simulator immer, gegen die Hardware, wenn eine angeschlossen
ist. Die Suite ist die ausführbare Form des Port-Vertrags.

---

## Der Dienst ist auch eine Bibliothek

`ControllerService` ist einbettbar. Prozess-Hosting — Ports, PID-Datei, uvicorn —
liegt daneben in `hosting.py` und wird beim Einbetten schlicht nicht angefasst.
Das `lefx-studio` ist der Beweis dafür: es startet keinen Dienst, sondern hält
seine eigene Engine im Prozess.

```python
from lefx.interfaces import ControllerService

service = ControllerService(sink="simulator", led_count=12, fps=30.0)
service.start()
service.set_state("solid_fill", {"color": "#FF0000"})
```

Die Senke darf auch als **Objekt** übergeben werden statt als Name — so kann ein
Host die Frames mitlesen, die zum Gerät gehen, statt sie ein zweites Mal selbst
zu rendern.

---

## Wo was liegt

```text
respeaker-led-v3/
├── packages/
│   ├── led-ctrl-v3/                     (nur Abhängigkeiten)
│   ├── lefx-sdk/                        lefx.sdk
│   ├── lefx-engine/                     lefx.engine
│   ├── lefx-interfaces/                 lefx.interfaces
│   ├── lefx-effect-creation/            lefx.effect_creation (+ .studio)
│   ├── lefx-device-respeaker/           lefx.device.respeaker
│   ├── lefx-device-simulated-respeaker/ lefx.device.simulated_respeaker
│   ├── lefxset-core-set/                lefx.sets.core_set + gebautes .lefxset
│   └── lefxset-smartspeaker-set/        lefx.sets.smartspeaker_set + .lefxset
├── effects/
│   ├── core-set/                Quellen der kuratierten Referenzdefinitionen
│   └── smartspeaker-set/        Quellen des portierten Produktivsatzes
├── config.example.yaml          jede Einstellung, dokumentiert
├── scripts/
│   ├── build_effects.py         Quellen → .lefxset, in die Distribution hinein
│   ├── build_simulator.py       Ringfenster als Standalone
│   ├── build_studio.py          Studio als Standalone
│   ├── check_release.py         Artefakte bauen und installiert prüfen
│   ├── sync_release_tree.py     den Baum des Release-Repos materialisieren
│   └── release.py               Version, Prüfungen, CI-Gate, Tag
├── tests/
│   ├── sdk/ engine/ authoring/  je Paket
│   ├── catalogue/               jede Definition, mehrere Ringgrößen
│   ├── interfaces/ system/      Service, API, CLI, End-to-End
│   ├── device/                  Vertragssuite über beide Geräte
│   ├── studio/                  Sitzung, Widgets, Kalibrierung
│   └── architecture/            Paketgrenzen und V1-Regressionen
└── docs/
```

## Loslegen

```bash
uv sync
```

```bash
uv run python scripts/build_effects.py
```

```bash
uv run lefx serve --sink simulator
```

```bash
uv run lefx-studio --output simulator
```

Das Studio hat drei Seiten: **Player** (Katalog durchsuchen, Parameter regeln,
live zusehen, Presets sichern), **Kalibrierung** (24 Sektoren durchsteppen und
den Montagewinkel bestimmen) und **Neuer Effekt** (eine Definition entwerfen,
auf dem Gerät ansehen, als Quelle schreiben und zu `.lefx` bauen).

Der Katalog muss einmal gebaut sein, bevor ein Dienst startet — gebaute
Artefakte sind reproduzierbare Ausgabe und liegen nicht im Repository. Sie
landen in der Distribution, die sie ausliefert (`packages/lefxset-<name>/`),
was im Checkout derselbe Ort ist wie in einem installierten Wheel. Gefunden
werden sie über den Entry-Point-Group `lefx.effect_sets`; `included_lefxset`
schränkt ein, welche davon geladen werden, und `package_path` kommt hinzu.
