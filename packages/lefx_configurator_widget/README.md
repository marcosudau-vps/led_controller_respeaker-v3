# lefx_configurator_widget

Qt-Editoren für vorhandene LEFX-Effekte, Presets und LED-Aufrufe zu frei definierten Anwendungsereignissen. Das Paket läuft mit Python 3.12, LEFX 3.0.4 und PySide6 Essentials. Die lokale Vorschau rendert über die LEFX-Engine in einen Speicher-Sink.

## Installation und Start

Im Repository-Stamm unter PowerShell:

```powershell
uv venv --python 3.12 work/configurator-venv
uv pip install --python work/configurator-venv/Scripts/python.exe ./packages/lefx_configurator_widget
work/configurator-venv/Scripts/python.exe -m lefx.configurator_widget
```

Für ein bereits gebautes Wheel übergib dessen Pfad anstelle des Paketordners an `uv pip install`. Der Programmeinstieg unter Windows heißt `lefx-configurator-widget.exe` und liegt im `Scripts`-Verzeichnis der Umgebung. `python -m lefx.configurator_widget --smoke` öffnet und schließt das TestLab für einen kurzen Starttest.

Die Distribution heißt `lefx_configurator_widget`. Paketindizes normalisieren den Namen zu `lefx-configurator-widget`. Python importiert aus dem LEFX-Namespace `lefx.configurator_widget`. Der aktuelle Stand wird lokal aus dem Paketordner oder Wheel installiert. Die Integration in die Release-Pipeline ist ein eigener Schritt.

## Einbettung

```python
from lefx.configurator_widget import EventSpec, LedFeedbackConfigurator, LefxCatalogueAdapter

catalogue = LefxCatalogueAdapter.installed()
widget = LedFeedbackConfigurator(
    [EventSpec("sync.done", "Synchronisierung abgeschlossen")],
    catalogue,
    rules={"sync.done": {"emit_event": "pulse_signal"}},
)
widget.applied.connect(store_led_rules)  # Callback der Hostanwendung
```

Die Hostanwendung besitzt die `QApplication`, hängt das Widget in ihre Oberfläche ein und ruft `catalogue.close()` nach der Nutzung auf. Das Paket stellt auch einen `QDialog`, einen einzelnen Effekteditor und separat kopierbare Qt-Widgets bereit.

- [TestLab und Bedienung](docs/benutzeranleitung.md)
- [Entwicklung, API und Build](docs/entwickleranleitung.md)
- [Autarke Qt-Widgets und Kopierbeispiele](docs/widgets.md)
- [Voice-STT-V2-Integration](docs/voice-stt.md)
- [Einzeleffekt-Beispiel](examples/single_effect.py)
- [Beispiel für einen Host mit QStackedWidget](examples/stacked_host.py)
