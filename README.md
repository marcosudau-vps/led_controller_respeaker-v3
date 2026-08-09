# led_controller_respeaker-v3

LEFX V3 — das Effektsystem für den LED-Ring des reSpeaker XVF3800, geschnitten
in eigenständig installierbare Pakete.

Dies ist das **Entwicklungs-Repository**. Veröffentlicht wird aus
[`marcosudau-vps/led-ctrl-v3`](https://github.com/marcosudau-vps/led-ctrl-v3),
das ausschließlich maschinell beschrieben wird — siehe
[docs/release_guide.md](docs/release_guide.md).

## Installation

```bash
pip install led-controller-version-3
```

Das ist die Normalversion und für sich vollständig: Schema, Laufzeit,
Steuerungsoberfläche, Hardware-Anbindung und beide Effektkataloge. Sie spielt
fertige `.lefx`- und `.lefxset`-Dateien ab und hat mit dem *Erstellen* von
Effekten nichts zu tun — das ist ein eigenes Paket.

```bash
pip install "led-controller-version-3[simulated-respeaker]"   # Software-Geräteersatz mit Ringfenster
pip install "led-controller-version-3[effect-creation]"       # lefx-pack und lefx-studio
pip install "led-controller-version-3[all]"                   # beides
```

Beide Effektkataloge sind in der Standardinstallation enthalten; welche geladen
werden, entscheidet `included_lefxset`.

## Warum ein eigenes Repository

Der Vorgängerstand trug zwei Systemgenerationen gleichzeitig: den
dokumentierten Effektvertrag und einen älteren, anwendungsspezifischen Pfad, der
im Betrieb weiterhin verdrahtet war. V3 beginnt ohne diese Doppelung. Es gibt
keinen stillen Kompatibilitätsmodus und keine automatische Migration älterer
Pakete.

## Pakete

Drei Distributionen, eine Versionsnummer, gemeinsam veröffentlicht.

| PyPI-Projekt | Enthält | Installiert durch |
|---|---|---|
| `led-controller-version-3` | `lefx.sdk`, `lefx.engine`, `lefx.interfaces`, `lefx.device.respeaker`, `lefx.sets.core_set`, `lefx.sets.smartspeaker_set` | Standard |
| `led-controller-version-3-device-simulated-respeaker` | `lefx.device.simulated_respeaker` | `[simulated-respeaker]` |
| `led-controller-version-3-effect-creation` | `lefx.effect_creation` (+ `.studio`) | `[effect-creation]` |

Nur Optionales bekommt ein eigenes Projekt. Schema, Engine,
Steuerungsoberfläche und Hardware werden immer zusammen installiert — kein
Extra wählt je zwischen ihnen —, und welche Effektkataloge geladen werden, ist
eine Laufzeitfrage (`included_lefxset`), keine Installationsfrage.

Die PyPI-Namen tragen das Präfix `led-controller-version-3-`; die Importpfade heißen
`lefx.*`. `led-controller-version-3` ist der Arbeitsname dieses Stands, die `lefx-*`-Namen
bleiben auf PyPI frei.

## Schichten und Abhängigkeitsrichtung

Dass drei Wheels entstehen, ändert nichts an den Schichten. Die Regeln gelten
zwischen **Modulen**, nicht zwischen Paketen, und
[`tests/architecture/test_architecture.py`](tests/architecture/test_architecture.py)
prüft sie über die Verzeichnisse unter `src/lefx`:

```
lefx.sdk                         → (nichts)
lefx.engine                      → lefx.sdk
lefx.interfaces                  → lefx.sdk, lefx.engine
lefx.effect_creation             → lefx.sdk, lefx.engine, lefx.interfaces
lefx.device.respeaker            → lefx.sdk
lefx.device.simulated_respeaker  → lefx.sdk
lefx.sets.*                      → (nichts)
```

`lefx.interfaces` importiert weder ein Gerät noch einen Katalog. Beide melden
sich über Entry Points an (`lefx.frame_sinks`, `lefx.input_providers`,
`lefx.effect_sets`); der Dienst liest ein, was installiert ist. Dass Engine und
Hardware jetzt im selben Wheel liegen, macht diese Grenze nicht weicher — sie
hängt seitdem allein an diesem Test, und der bricht bei jeder Verletzung.

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

Die Effektkataloge sind gebaute Ausgabe und liegen unter
`packages/led-controller-version-3/src/lefx/sets/<name>/` — derselbe Ort im Checkout wie in
einem installierten Wheel, weshalb `uv sync` plus `build_effects.py` genügt, um
einen vollständigen Katalog zu haben.

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
