# lefx-config-widget

Qt-Editoren für vorhandene LEFX-Effekte, Presets und LED-Aufrufe zu frei definierten Anwendungsereignissen. Das Paket läuft mit Python 3.12, LEFX 3.0.4 und PySide6 Essentials. Die lokale Vorschau rendert über die LEFX-Engine in einen Speicher-Sink.

## Installation und Start

Im Entwicklungs-Workspace installierst du alle lokalen Mitglieder mit `uv sync --locked`.
Danach baust du die Kataloge mit `uv run --locked python scripts/build_effects.py` und
startest das TestLab mit `uv run --locked lefx-config-widget`.

Für eine separate Installation des Paketordners führe im Repository-Stamm unter PowerShell aus:

```powershell
uv venv --python 3.12 work/configurator-venv
uv pip install --python work/configurator-venv/Scripts/python.exe ./packages/lefx_config_widget
work/configurator-venv/Scripts/python.exe -m lefx.config_widget
```

Für ein bereits gebautes Wheel übergib dessen Pfad anstelle des Paketordners an `uv pip install`. Der Programmeinstieg unter Windows heißt `lefx-config-widget.exe` und liegt im `Scripts`-Verzeichnis der Umgebung. `python -m lefx.config_widget --smoke` öffnet und schließt das TestLab für einen kurzen Starttest.

Die Distribution heißt `lefx-config-widget`. Wheel- und Sdist-Dateinamen verwenden `lefx_config_widget`. Python importiert aus dem LEFX-Namespace `lefx.config_widget`. Der Workspace koppelt die Version exakt an den Kern. Ab der gemeinsamen Veröffentlichung kannst du das Paket über `pip install "led-controller-version-3[configurator]"` oder direkt über `pip install lefx-config-widget` installieren. `[all]` schließt den Configurator ebenfalls ein.

## Einbettung

```python
from lefx.config_widget import EventSpec, LedFeedbackConfigurator, LefxCatalogueAdapter

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
