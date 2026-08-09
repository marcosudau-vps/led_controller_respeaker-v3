# led-ctrl-v3

LED-Ring-Steuerung für den reSpeaker XVF3800 — das LEFX-V3-System.

```bash
pip install led-ctrl-v3
```

Das ist die Normalversion und für sich vollständig: Schema, Laufzeit,
Steuerungsoberfläche, die Hardware-Anbindung und beide Effektkataloge. Sie
spielt fertige `.lefx`- und `.lefxset`-Dateien auf einem reSpeaker ab und
braucht keines der optionalen Pakete.

```bash
lefx serve --sink respeaker
lefx list states
lefx set state listening
lefx emit event notification
```

## Optionen

```bash
pip install "led-ctrl-v3[simulated-respeaker]"   # Software-Geräteersatz mit Ringfenster
pip install "led-ctrl-v3[effect-creation]"       # Effekte erstellen: lefx-pack und lefx-studio
pip install "led-ctrl-v3[all]"                   # beides
```

Beide sind eigene Distributionen, keine Schalter. Was nicht installiert ist,
existiert im laufenden System nicht — Geräte werden über Entry Points gefunden,
nicht importiert.

Ohne Hardware:

```bash
pip install "led-ctrl-v3[simulated-respeaker]"
lefx-simulator
lefx serve --sink simulator
```

## Was drin ist

| Modul | Rolle |
|---|---|
| `lefx.sdk` | Der Vertrag zwischen Effektpaketen und der Engine |
| `lefx.engine` | Layer, Komposition, Lebenszyklen, Registry, Paketformat `lefx/3` |
| `lefx.interfaces` | HTTP-API v3, CLI, Client, Prozess-Hosting, Konfiguration |
| `lefx.device.respeaker` | USB-Transport, LED-Senke, DoA-Provider |
| `lefx.sets.core_set` | Referenzkatalog, gebaut als `.lefxset` |
| `lefx.sets.smartspeaker_set` | Sprachassistenz-Katalog |

**`lefx.sdk`** ist das Einzige, was ein Effektautor importiert: die
typ-spezifischen Definitionsklassen, die Parametertypen und ihre
Zulässigkeitsregeln, die kanonische Wertnormalisierung, die Farbmathematik, die
Kontexte und die Ports `FrameSink` und `InputProvider`. Es hängt an nichts. Eine
ungültige Definition ist nicht konstruierbar — geprüft wird im Konstruktor,
nicht in einem eigenen Validierungsschritt.

**`lefx.engine`** kennt Typen, Lebenszyklen und Layer, aber niemals eine
konkrete Definition-ID: Layerstapel und Komposition, die vier Lebenszyklusformen,
die Event-Warteschlange mit Priorität und FIFO, Runtime-Eingaben mit
Input-Health, die Registry und das Laden von `lefx/3`- und `lefxset/3`-Paketen.

**`lefx.interfaces`** trägt CLI und HTTP-API mit denselben Kommandos; keine der
beiden hat eigene Fachlogik. Dazu der Client, das Prozess-Hosting und die
Konfiguration.

## Effektsätze

Beide Kataloge sind enthalten. Welche geladen werden, entscheidet
`included_lefxset`:

```yaml
included_lefxset: [core, smartspeaker]
```

```bash
INCLUDED_LEFXSET=[core] lefx serve --sink respeaker
```

Leer heißt: alle. Namen dürfen mit oder ohne `-set`-Suffix geschrieben werden.

## Konfiguration

Alles Projektweite steht in einer `config.yaml` im Arbeitsverzeichnis, unter
`~/.lefx/config.yaml`, oder wohin `LEFX_CONFIG` zeigt. Jeder Schlüssel lässt
sich als Umgebungsvariable in Großbuchstaben überschreiben — mit `LEFX_`-Präfix
oder ohne; ein Kommandozeilenschalter schlägt beides.

```yaml
led_count: 12
sink: respeaker
port: 8765
included_lefxset: [core, smartspeaker]
```

`lefx config` zeigt, welcher Wert gerade gilt und woher er kommt.

## Wenn das Gerät belegt ist

Ein WinUSB-Handle ist exklusiv. Ein zweiter Prozess reiht sich nicht ein, er
bekommt `Errno 13` — das liest sich wie ein Treiber- oder Rechteproblem und
schickt einen in die falsche Richtung. Meistens läuft schlicht noch ein anderer
Controller.

```bash
lefx-respeaker probe
```

`probe` sagt, ob das Gerät ansprechbar ist, und listet andernfalls die Prozesse,
die ein USB-Gerät halten — mit Kommandozeile, denn erfahrungsgemäß heißen alle
Kandidaten `python.exe`.

```bash
lefx-respeaker claim --dry-run
```

`claim` beendet, was im Weg steht, und prüft danach nach. Zwei Dinge begrenzen
den Schaden:

- **Es wird einzeln beendet und nach jedem Schritt neu geprüft.** Sobald das
  Gerät antwortet, hört es auf. Der Prozess, der wirklich im Weg war, ist damit
  der letzte, den es trifft.
- **Fremde USB-Software wird nicht angefasst.** Maus-, Tastatur- und
  RGB-Software hält dauerhaft offene WinUSB-Handles und taucht in derselben
  Suche auf. Sie wird aufgelistet und in Ruhe gelassen; nur Prozesse, die sich
  als reSpeaker-Software zu erkennen geben, kommen in Frage.
  `--include-unrelated` hebt das auf — bewusst und einzeln.

Im Dienst ist dasselbe als Senken-Option verfügbar:

```bash
lefx serve --sink respeaker --sink-option force_claim=true
```

Eine Senken-Option und kein `lefx`-Schalter, weil `lefx` nichts über reSpeaker
wissen soll. Der Transport ruft es höchstens **einmal pro Verbindungszyklus**
auf, nur bei einem Zugriffsfehler: der Wiederholungsversuch läuft alle paar
Sekunden, und etwas, das in diesem Takt Prozesse beendet, wäre eine Plage. Ein
fehlendes Gerät gilt nicht als Konkurrenz — ein gezogenes Kabel ist kein fremder
Prozess.
