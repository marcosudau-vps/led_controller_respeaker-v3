# led-ctrl-v3

LED-Ring-Steuerung für den reSpeaker XVF3800 — das LEFX-V3-System, als eine
Installation.

```bash
pip install led-ctrl-v3
```

Das ist die Normalversion und für sich genommen vollständig: Schema, Laufzeit,
Steuerungsoberfläche (`lefx`) und die Hardware-Anbindung. Sie spielt fertige
`.lefx`- und `.lefxset`-Dateien auf einem reSpeaker ab und braucht dafür keines
der optionalen Pakete.

Dieses Paket enthält selbst keinen Code. Es ist der Name, unter dem das System
installiert wird, damit „welche Pakete brauche ich" eine Antwort hat statt vier.

## Was drin ist

| Distribution | Import | Rolle |
|---|---|---|
| `lefx-sdk` | `lefx.sdk` | Der Autorenvertrag: Definitionsschema, Wertnormalisierung, Ports |
| `lefx-engine` | `lefx.engine` | Layer, Komposition, Lebenszyklen, Registry, `lefx/3`-Loader |
| `lefx-interfaces` | `lefx.interfaces` | HTTP-API v3, CLI, Client, Prozess-Hosting, Konfiguration |
| `lefx-device-respeaker` | `lefx.device.respeaker` | USB-Transport, LED-Senke, DoA-Provider |

## Optionen

```bash
pip install "led-ctrl-v3[simulated-respeaker]"   # Software-Geräteersatz mit Ringfenster
pip install "led-ctrl-v3[effect-creation]"       # Effekte erstellen: lefx-pack und lefx-studio
pip install "led-ctrl-v3[core-set]"              # Referenzkatalog
pip install "led-ctrl-v3[smartspeaker-set]"      # Sprachassistenz-Katalog
pip install "led-ctrl-v3[all]"                   # alles davon
```

Mehrere zugleich gehen wie üblich: `pip install "led-ctrl-v3[core-set,smartspeaker-set]"`.

Jede Option ist ein eigenes Paket, keine Funktion, die eingeschaltet wird. Was
nicht installiert ist, existiert im laufenden System nicht — Geräte und
Effektsätze werden über Entry Points gefunden, nicht importiert.

## Erste Schritte

```bash
lefx serve --sink respeaker
```

```bash
lefx list states
lefx set state listening
lefx emit event notification
```

Ohne angeschlossene Hardware:

```bash
pip install "led-ctrl-v3[simulated-respeaker,core-set]"
lefx-simulator
lefx serve --sink simulator
```

## Konfiguration

Alles Projektweite steht in einer `config.yaml` im Arbeitsverzeichnis (oder
unter `~/.lefx/config.yaml`, oder wohin `LEFX_CONFIG` zeigt), und jeder
Schlüssel lässt sich als Umgebungsvariable in Großbuchstaben überschreiben —
mit `LEFX_`-Präfix oder ohne.

```yaml
led_count: 12
sink: respeaker
port: 8765
included_lefxset: [core, smartspeaker]
```

```bash
INCLUDED_LEFXSET=[core, smartspeaker] lefx serve
```

`lefx config` zeigt, welcher Wert gerade gilt und woher er kommt.
