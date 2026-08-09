# respeaker-led-v3

LEFX V3 — das Effektsystem für den LED-Ring des reSpeaker XVF3800, geschnitten
in eigenständig installierbare Pakete.

## Warum ein eigenes Repository

Der Vorgängerstand trug zwei Systemgenerationen gleichzeitig: den
dokumentierten Effektvertrag und einen älteren, anwendungsspezifischen Pfad, der
im Betrieb weiterhin verdrahtet war. V3 beginnt ohne diese Doppelung. Es gibt
keinen stillen Kompatibilitätsmodus und keine automatische Migration älterer
Pakete.

## Pakete

| Paket | Import | Aufgabe |
|---|---|---|
| `lefx-sdk` | `lefx.sdk` | Definitionsschema, Wertnormalisierung, Ports |
| `lefx-engine` | `lefx.engine` | Layer, Komposition, Lebenszyklen, Registry, Paketladen |
| `lefx-interfaces` | `lefx.interfaces` | HTTP-API, CLI, Client, Prozess-Hosting |
| `lefx-authoring` | `lefx.authoring` | Scaffolding, Quellenvalidierung, Paketbau |
| `lefx-device-respeaker` | `lefx.device.respeaker` | USB-Transport, LED-Ausgabe, DoA-Eingabe |
| `lefx-device-simulated-respeaker` | `lefx.device.simulated_respeaker` | Software-Geräteersatz mit Ringanzeige |

## Abhängigkeitsrichtung

```
lefx-sdk                 → (nichts)
lefx-engine              → lefx-sdk
lefx-authoring           → lefx-sdk, lefx-engine
lefx-interfaces          → lefx-sdk, lefx-engine
lefx-device-respeaker     → lefx-sdk
lefx-device-simulated-respeaker  → lefx-sdk
```

`lefx-interfaces` importiert weder Hardware noch Simulator. Beide melden ihre
Frame-Senke und ihren Input-Provider über Entry Points an
(`lefx.frame_sinks`, `lefx.input_providers`); der Dienst liest ein, was
installiert ist. Ein Architekturtest bricht bei jeder Verletzung dieser
Richtung.

## Entwicklung

```bash
uv sync
```

```bash
uv run pytest
```

## Lizenz

MIT — siehe [LICENSE](LICENSE).
