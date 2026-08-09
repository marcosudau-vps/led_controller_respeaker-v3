# led_controller_respeaker-v3

LEFX V3 — das Effektsystem für den LED-Ring des reSpeaker XVF3800, geschnitten
in eigenständig installierbare Pakete.

Dies ist das **Entwicklungs-Repository**. Veröffentlicht wird aus
[`marcosudau-vps/led-ctrl-v3`](https://github.com/marcosudau-vps/led-ctrl-v3),
das ausschließlich maschinell beschrieben wird — siehe
[docs/release_guide.md](docs/release_guide.md).

## Installation

```bash
pip install led-ctrl-v3
```

Das ist die Normalversion und für sich vollständig: Schema, Laufzeit,
Steuerungsoberfläche und Hardware-Anbindung. Sie spielt fertige `.lefx`- und
`.lefxset`-Dateien ab.

```bash
pip install "led-ctrl-v3[simulated-respeaker]"   # Software-Geräteersatz mit Ringfenster
pip install "led-ctrl-v3[effect-creation]"       # lefx-pack und lefx-studio
pip install "led-ctrl-v3[core-set]"              # Referenzkatalog
pip install "led-ctrl-v3[smartspeaker-set]"      # Sprachassistenz-Katalog
pip install "led-ctrl-v3[all]"
```

## Warum ein eigenes Repository

Der Vorgängerstand trug zwei Systemgenerationen gleichzeitig: den
dokumentierten Effektvertrag und einen älteren, anwendungsspezifischen Pfad, der
im Betrieb weiterhin verdrahtet war. V3 beginnt ohne diese Doppelung. Es gibt
keinen stillen Kompatibilitätsmodus und keine automatische Migration älterer
Pakete.

## Pakete

Neun Distributionen, eine Versionsnummer, gemeinsam veröffentlicht.

| Paket | Import | Aufgabe | Teil von |
|---|---|---|---|
| `led-ctrl-v3` | — | Der Name, unter dem installiert wird. Kein Code. | — |
| `led-ctrl-v3-sdk` | `lefx.sdk` | Definitionsschema, Wertnormalisierung, Ports | Standard |
| `led-ctrl-v3-engine` | `lefx.engine` | Layer, Komposition, Lebenszyklen, Registry, Paketladen | Standard |
| `led-ctrl-v3-interfaces` | `lefx.interfaces` | HTTP-API, CLI, Client, Prozess-Hosting, Konfiguration | Standard |
| `led-ctrl-v3-device-respeaker` | `lefx.device.respeaker` | USB-Transport, LED-Ausgabe, DoA-Eingabe | Standard |
| `led-ctrl-v3-device-simulated-respeaker` | `lefx.device.simulated_respeaker` | Software-Geräteersatz mit Ringanzeige | `[simulated-respeaker]` |
| `led-ctrl-v3-effect-creation` | `lefx.effect_creation` | Scaffolding, Quellenvalidierung, Paketbau, Studio | `[effect-creation]` |
| `led-ctrl-v3-set-core` | `lefx.sets.core_set` | Referenzkatalog als gebautes `.lefxset` | `[core-set]` |
| `led-ctrl-v3-set-smartspeaker` | `lefx.sets.smartspeaker_set` | Sprachassistenz-Katalog | `[smartspeaker-set]` |

## Abhängigkeitsrichtung

```
led-ctrl-v3-sdk                         → (nichts)
led-ctrl-v3-engine                      → led-ctrl-v3-sdk
led-ctrl-v3-interfaces                  → led-ctrl-v3-sdk, led-ctrl-v3-engine
led-ctrl-v3-effect-creation             → led-ctrl-v3-sdk, led-ctrl-v3-engine, led-ctrl-v3-interfaces
led-ctrl-v3-device-respeaker            → led-ctrl-v3-sdk
led-ctrl-v3-device-simulated-respeaker  → led-ctrl-v3-sdk
led-ctrl-v3-set-core                    → (nichts)
led-ctrl-v3-set-smartspeaker            → (nichts)
```

`led-ctrl-v3-interfaces` importiert weder Hardware noch Simulator noch einen Katalog.
Alle drei melden sich über Entry Points an (`lefx.frame_sinks`,
`lefx.input_providers`, `lefx.effect_sets`); der Dienst liest ein, was
installiert ist. Ein Architekturtest bricht bei jeder Verletzung dieser
Richtung.

## Konfiguration

Alles Projektweite steht in `config.yaml` (im Arbeitsverzeichnis, unter
`~/.lefx/config.yaml`, oder wohin `LEFX_CONFIG` zeigt). Jeder Schlüssel lässt
sich als Umgebungsvariable in Großbuchstaben überschreiben, mit `LEFX_`-Präfix
oder ohne; ein Kommandozeilenschalter schlägt beides.

```bash
cp config.example.yaml config.yaml
```

```bash
INCLUDED_LEFXSET=[core, smartspeaker] lefx serve --sink simulator
```

```bash
lefx config      # welcher Wert gilt, und woher er kommt
```

## Entwicklung

```bash
uv sync
```

```bash
uv run python scripts/build_effects.py
```

```bash
uv run pytest -m "not hardware"
```

Die Effektkataloge sind gebaute Ausgabe und liegen in der Distribution, die sie
ausliefert — `packages/led-ctrl-v3-set-<name>/`. Derselbe Ort im Checkout wie in einem
installierten Wheel, weshalb `uv sync` plus `build_effects.py` genügt, um einen
vollständigen Katalog zu haben.

Ohne Hardware:

```bash
uv run lefx-simulator
```

```bash
uv run lefx serve --sink simulator
```

## Release

```bash
uv run python scripts/release.py
```

Fragt nach der Version, fragt nach, ob du sicher bist, und macht dann alles
allein — inklusive Warten auf grünes CI, bevor getaggt wird. Details in
[docs/release_guide.md](docs/release_guide.md).

## Lizenz

MIT — siehe [LICENSE](LICENSE).
