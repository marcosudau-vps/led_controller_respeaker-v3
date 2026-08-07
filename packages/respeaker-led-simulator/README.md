# respeaker-led-simulator

Ein vollständiger Software-Ersatz für die Hardware — dieselben Ports, dieselbe
Rolle. Der Dienst merkt nicht, dass die Gegenstelle kein Gerät ist.

Es enthält:

- `SimulatorFrameSink` — überträgt den LED-Frame über einen lokalen Transport,
- `SimulatorDoaProvider` — liest die im Fenster eingestellte Richtung und
  Sprachaktivität zurück,
- die Ringanzeige als eigenständige Anwendung.

Die dienstseitige Hälfte braucht kein Qt. PySide6 ist ein Extra und wird nur
gebraucht, wenn das Fenster geöffnet wird:

```bash
uv pip install "respeaker-led-simulator[gui]"
respeaker-led-simulator
```

Damit lassen sich auch kontrollierte Overlays wie `direction_indicator` ohne
angeschlossenen reSpeaker entwickeln und prüfen — der Effekt fragt nach der
Fähigkeit `doa` und bekommt sie hier ebenso wie von der Hardware.

## Transport

Der Dienst hört auf `127.0.0.1:8787`, das Fenster verbindet sich dorthin.
Diese Richtung entspricht der Hardware: der Dienst läuft, ob ein Gerät
angeschlossen ist oder nicht, und ein später erscheinendes Fenster ist ein
gewöhnliches Ereignis, kein Neustart. Das Fenster verbindet sich selbsttätig neu.

Der Port lässt sich auf beiden Seiten setzen:

```bash
uv run lefx serve --sink simulator --sink-option port=8770
```

Alternativ über `LEFX_SIMULATOR_PORT`, das beide Hälften lesen.

## Grenzen

Ohne verbundenes Fenster meldet die Senke `available=False` und der Provider
liefert `None` — dieselbe Bedeutung wie ein abgezogenes Kabel. Der Dienst läuft
weiter, kontrollierte Overlays gehen über `waiting` nach `failed`.
