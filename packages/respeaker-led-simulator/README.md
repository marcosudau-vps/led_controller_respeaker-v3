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
angeschlossenen reSpeaker entwickeln und prüfen.
