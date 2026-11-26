# Entwickleranleitung

## Öffentliche Schnittstellen

| API | Aufgabe |
| --- | --- |
| `CatalogueProvider.entries()`, `resolve(target)` | Typisierte Einträge auflisten und genau ein Ziel auflösen. `resolve` meldet nicht verfügbare oder mehrdeutige Ziele als `ValueError`. |
| `LefxCatalogueAdapter(registry_or_library)` | Registry oder Library eines Hosts lesen. `installed(included, extra_sources=...)` erzeugt eine eigene Library für bereits installierte Kataloge und explizite lokale Quellen. `sources()`, `refresh()` und `close()` verwalten den lokalen Zugriff. |
| `CatalogueEntry`, `MemoryCatalogue(entries)` | Einträge mit Quelle, Paket, qualifizierter ID, LEFX-Definition und optionalen Presetdaten. `entry.form`, `label` und `resolve_config(overrides)` dienen Auswahl und Validierung. |
| `EffectCatalogueWidget(catalogue, parent, forms=..., predicate=...)` | Ziel auswählen. `target_selected(str)` gibt eine qualifizierte ID aus. `refresh()`, `selected_id()`, `set_selected_id(id)` und `activate_current()` unterstützen die Hostnavigation. |
| `EffectEditor(entry, parent, config=..., read_only=...)` | Statische Effekt-Overrides. `value()`, `set_value()`, `validate()`, `resolved_config()`, `set_read_only()` und `draft_changed(object)`. |
| `ParameterForm(schema, parent, inherited=..., values=..., prefix=...)` | Einzelne deklarative LEFX-Schemafelder bearbeiten. `value()`, `set_value()`, `validate()`, `draft_changed(object)` und `set_read_only()`. Für Laufzeitwerte ein eigenes Formular verwenden. |
| `LedCallEditor(catalogue, parent, value=..., event=..., capabilities=..., preview_factory=...)` | Einzelnen Aufruf bearbeiten. `value()`, `set_value()`, `validate()`, `refresh_catalogue()`, `set_read_only()` und `draft_changed(object)`. |
| `FeedbackMappingEditor(events, catalogue, parent, rules=..., capabilities=..., preview_factory=...)` | Ereignisse und geordnete Aufrufe bearbeiten. `open_event(id)`, `show_overview()`, `commit_open_call()`, `validate()`, `warnings()`, `value()`, `set_value()`, `set_draft()`, `set_read_only()`, `refresh_catalogue()` und `draft_changed(object)`. |
| `LedFeedbackConfigurator(events, catalogue, parent, ...)` | Vollständiger Einbettungseinstieg. `show_actions`, `show_back` und `show_status` erlauben eigene Hostaktionen. `apply()`, `cancel()`, `request_back()`, `export()`, `is_dirty()`, `value()`, `set_value()`, `set_draft()`, `validate()`, `warnings()`, `set_read_only()` und `refresh_catalogue()`. |
| `LedFeedbackDialog(events, catalogue, parent, ...)` | Dialog mit `configurator` und `result_rules`. Nach `QDialog.DialogCode.Accepted` enthält `result_rules` den übernommenen Snapshot. |
| `PreviewSession(registry)`, `PreviewRequest`, `PreviewPanel` | Isolierte Vorschau. Adapter implementieren `start(request, now)`, `frame(now) -> OutputFrame` und `close()`. |

Alle öffentlichen Widgets arbeiten auf dem Qt-Thread des Hosts. Sie lassen sich in bestehende Fenster, Tabs, Dialoge und Stacks einhängen. Der Host definiert `EventSpec(id, label, group, description, verbs)`. `HostCapabilities` begrenzt Aufrufarten, Slots, Zustandsaktionen, Priorität, Dauer und optional den Standard-Slot. Die Ereignis-IDs sind eindeutige Strings.

## Daten und Transaktionen

```python
rules = {
    "build.done": [
        {"emit_event": "smartspeaker-set::success_event", "config": {"duration_ms": 750}},
        {"set_state": "core-set::solid_fill", "slot": "primary", "action": "on"},
    ],
    "build.started": {"set_output": {"enabled": True, "brightness": 0.6}},
    "build.reset": {"clear_state": "background"},
    "build.waiting": [],
}
```

Der Konfigurator nimmt pro Ereignis ein Aufrufobjekt, eine geordnete Sequenz oder `None` an. `value()` liefert einen unabhängigen Snapshot des aktuellen Entwurfs einschließlich eines geöffneten Aufrufs. `export()` prüft die bekannten Regeln und meldet Fehler als `ValueError`. Unbekannte Aufrufformen oder Erweiterungsfelder sperren die betroffene Regel. Sie bleiben als Originaldaten erhalten und stehen in `warnings()`. IDs außerhalb des Ereignisschemas werden unverändert durchgereicht. Erstellt der Host eine strengere Exportprüfung, kann er auch diese Warnungen als Sperre behandeln.

`set_value()` lädt eine neue Ausgangskonfiguration. `set_draft()` stellt eine gespeicherte Arbeitskopie zur aktuellen Ausgangskonfiguration wieder her. Programmatisches Laden schließt eine geöffnete Aufrufseite und emittiert weder `draft_changed` noch `applied`. `apply()` prüft, akzeptiert und signalisiert mit `applied(object)` eine Kopie. `validation_failed(object)` übergibt bei einem fehlgeschlagenen Apply feldbezogene `Diagnostic`-Objekte. `cancel()` setzt den Entwurf auf die letzte Ausgangskonfiguration zurück und sendet `cancelled()`. Ändert sich der Entwurf dabei, erhält der Host zusätzlich genau ein `draft_changed`. `back_requested()` gibt die Navigation an den Host ab. `draft_changed(object)` eignet sich für eine Anzeige im Host. Die Persistenz ist dessen Aufgabe.

## Schema und LEFX-Verträge

Die Registry liefert die tatsächlichen typisierten Definitionen. Die zehn `ParamType`-Werte werden durch Auswahl, präzise Texteingabe, Drehregler oder die autarken Farb-Editoren dargestellt. `ParamDefinition` und `resolve_configuration` liefern die Regeln und effektiven Werte. Der Entwurf unterscheidet fehlende Schlüssel, Presetwerte, Schema-Defaults und explizites `None`. Geladene Aliase bleiben als Schlüssel bestehen. Bei konkurrierenden Aliasen oder unbekannten Feldern ermöglicht das Formular eine gezielte Korrektur. Die von LEFX definierte Bildkomposition, Slotvalidierung und Dauerlogik bleiben der Engine bzw. ihren Validierungsfunktionen überlassen.

In LEFX 3.0.4 besitzen statische Konfigurationsfelder immer einen Default. Pflichtfelder ohne Default sind bei Runtime-Inputs möglich. `ParameterForm` kann sie anzeigen. Die echte Kataloganbindung akzeptiert Zustand, zeitgesteuertes Overlay, gesteuertes Overlay und Impuls. Im Mapping ist `set_overlay` die zeitgesteuerte Form. Priorität gilt für `emit_event`. Einen äußeren `duration_ms`-Override zeigt der Editor nur für Events mit Freigabe in der Definition. Die mitgelieferten Events steuern ihre Dauer über `config.duration_ms`.

Katalogwechsel erfolgen explizit. Aktualisiere die hosteigene Registry oder verwende beim Library-Adapter `refresh()`. Danach rufe `refresh_catalogue()` am Widget auf. Geladene Ziel-IDs bleiben erhalten und werden erneut validiert. LEFX-Quellen sind ausführbare Effektpakete. Verwende lokale Quellen aus vertrauenswürdiger Herkunft.

## Vorschau

```python
def preview_factory():
    registry = catalogue.registry  # Snapshot-Referenz auf dem GUI-Thread erfassen
    return lambda: PreviewSession(registry)  # Adapter entsteht im Render-Thread

widget = LedFeedbackConfigurator(events, catalogue, rules=rules, preview_factory=preview_factory)
```

Ohne `preview_factory` bleibt die Vorschau ausgeblendet. Die äußere Factory erfasst die aktuelle Registry im GUI-Thread. Der Worker ruft die innere Factory und alle Methoden des Adapters auf und gibt ausschließlich den letzten LEFX-Frame an Qt weiter. Übergebe eine Registry, die während einer Vorschau unverändert bleibt. Bei einem Quellenwechsel erst aktive Vorschauen stoppen und die Ansicht aktualisieren. `PreviewSession` nutzt ausschließlich `EffectRuntime`, eigene Layer, einen lokalen `MemoryFrameSink` und optional explizite Testwerte. Pull-Overlays mit Provider-ID erhalten eine lokale Testwert-Quelle. Definitionen mit eigener Pull-Abfrage können dafür einen Hostadapter benötigen.

Die Vorschau rendert das ausgewählte Ziel einschließlich seiner Parameter und unterstützten Zeit-/Slotoptionen. Bei einem Zustands-Aufruf zeigt sie die Optik des Ziels. Aufruflisten sowie Leerungs- und Ausgabeoperationen haben keinen eigenen Vorschaumodus. Die Ringanzeige übernimmt die RGB-Pixel vor der Gerätekalibrierung.

## Paketbau und Tests

Führe diese Befehle aus dem Repository-Stamm unter PowerShell aus:

```powershell
uv build --out-dir work/dist ./packages/lefx_configurator_widget
uv venv --python 3.12 work/configurator-test
uv pip install --python work/configurator-test/Scripts/python.exe (Get-ChildItem work/dist/lefx_configurator_widget-*.whl).FullName pytest
$env:QT_QPA_PLATFORM = 'offscreen'
work/configurator-test/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp=work/test-temp packages/lefx_configurator_widget/tests
```

Setze für die Kopiertests `LEFX_QT_ONLY_PYTHON` auf die Python-Executable einer zweiten Umgebung, die ausschließlich `PySide6-Essentials` und dessen Shiboken-Abhängigkeit enthält. Für die GUI-Prüfung unter Windows setze `QT_QPA_PLATFORM=windows`. Mit `LEFX_GUI_EVIDENCE` als vorhandenes Verzeichnis speichern die GUI-Tests ihre Bilder dort.

Im integrierten Workspace synchronisiert `uv sync --locked` alle vier Projekte. Nach
dem Katalogbau erfasst `uv run --locked pytest -m "not hardware"` auch diese
Tests. Die sieben Kopiertests starten pro Datei einen isolierten Prozess.
`LEFX_QT_ONLY_PYTHON` aktiviert zusätzlich die Prüfung mit einer Umgebung ohne
installiertes LEFX.

Der Configurator bleibt über sein eigenes `pyproject.toml` baubar und bezieht den
Kern mit einem exakten Pin. Die zentrale Release-Installationsprüfung verwendet
die Wheels aus dem aktuellen Build und testet direkte Installation und das
Hauptpaket-Extra getrennt. Siehe das [Release-Handbuch](../../../docs/release_guide.md).
