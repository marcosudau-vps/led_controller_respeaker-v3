# Autarke Qt-Widgets

Die folgenden Dateien unter `src/lefx/configurator_widget/widgets/` lassen sich einzeln kopieren. Sie verwenden CPython und PySide6 Essentials. `widgets/__init__.py` dient dem Paketimport. Katalog-, Parameter-, Aufruf-, Mapping- und Vorschauadapter außerhalb dieses Ordners nutzen das LEFX-SDK.

| Datei und Klasse | Wert und Optionen |
| --- | --- |
| `color_list_editor.py` · `ColorListEditor` | Geordnete Liste von RGB-Strings mit Duplikaten. `minimum`, `maximum`, `compact` und `read_only`. Im Detail Hinzufügen, Entfernen, Umordnen und Farbauswahl. |
| `gradient_editor.py` · `GradientEditor` | Geordnete Liste von Objekten mit `at` in 0–1 und `color`. `minimum`, `maximum`, `require_endpoints`, `compact` und `read_only`. Eingabe der Positionen in der Tabelle, Klickauswahl im Verlauf und explizites Sortieren. |
| `color_range_editor.py` · `ColorRangeEditor` | Mapping der drei Schlüssel `hue`, `saturation`, `brightness` auf Min-/Max-Paare. Farbton in Grad, Sättigung und HSV-Wert in 0–1. `compact` und `read_only`. |
| `range_editor.py` · `RangeEditor` | Numerisches Paar. `number_type=int/float`, `minimum`, `maximum`, `step`, `decimals`, `unit`, `read_only`. Bei `number_type=int` sind ganze Schrittweiten wie `1` oder `1.0` zulässig. Werte und Signalnutzdaten bleiben ganzzahlig. `decimals` steuert die inkrementelle Gleitkommaeingabe. |
| `angle_editor.py` · `AngleEditor` | Zyklischer Winkel. `period` und `decimals` für Periodenlänge und Drehreglerauflösung, `read_only` für Anzeige. `value()` gibt den Winkel modulo Periode zurück. Die Texteingabe behält die Präzision beim Laden. |
| `repeatable_container.py` · `RepeatableContainer` | Geordnete Hostwerte. `make_editor(value, parent)`, `read_editor(widget)`, `new_value()`, `minimum`, `maximum`, `read_only`, `values`. `ids()`, `add()`, `remove(id)` und `move(id, offset)` verwalten UUIDs und Reihenfolge. |
| `led_ring_preview.py` · `LedRingPreview` | Frame aus sRGB-Integern, QColor-kompatiblen Farben oder transparenten `None`-Pixeln. `configure(led_count=..., diameter=..., start_angle=..., clockwise=...)`, `clear()`, `value()`, `set_value(frame)`. |

## Gemeinsame API

Die Werteditoren bieten `value()`, `set_value(value)`, `set_read_only(bool)` und `error()`. `error()` gibt bei gültigen Daten einen leeren String zurück. Winkel- und Range-Editor werfen beim Lesen einer ungültigen Eingabe `ValueError`. Die komplexen Editoren halten ungültige, aber darstellbare Daten als Entwurf und melden sie über `error()`. Unpassende Datenstrukturen können bei `set_value()` eine Ausnahme auslösen. Das Laden löst keine Benutzerereignisse aus. Auf Benutzeränderungen folgen `value_changed(object)` und `value_edited(object)`. Bei ungültigen numerischen Eingaben weisen die Signale auf den Rohentwurf hin.

Farbliste, Verlauf und HSV-Farbbereich sind standardmäßig kompakt. `open_detail()` öffnet einen Qt-Dialog. Mit `create_detail(parent)` erhältst du einen unabhängigen Editor für deinen eigenen Stack. `commit_detail(editor)` übernimmt einen gültigen Wert in den Elternentwurf und meldet per booleschem Rückgabewert Erfolg. Der Detaildialog kann im Read-only-Modus zur Inspektion geöffnet werden.

Beim `RepeatableContainer` hält der Host die Interpretation der Einträge in seinen Callbacks. Ein Kindeditor kann `value_edited` bereitstellen, damit Änderungen durch den Container weitergemeldet werden. `set_value()` lädt eine neue Liste mit neuen Zeilen-IDs. IDs bleiben bei Änderungen eines Werts und beim Verschieben erhalten. Entfernte Qt-Zeilen werden per `deleteLater()` freigegeben.

## Minimale Beispiele nach dem Kopieren

Kopiere die gewünschte Python-Datei aus der Tabelle neben deinen Hostcode. Erzeuge vor der Instanziierung eine `QApplication`. Die folgenden Zeilen sind unabhängige Beispiele für die jeweils kopierte Datei.

```python
from color_list_editor import ColorListEditor
colors = ColorListEditor(value=["#FF7000", "#FF7000", "#1080FF"], minimum=1)

from gradient_editor import GradientEditor
gradient = GradientEditor(value=[{"at": 0, "color": "#000000"}, {"at": 1, "color": "#DD6100"}])

from color_range_editor import ColorRangeEditor
hsv = ColorRangeEditor(value={"hue": [35, 90], "saturation": [.3, 1], "brightness": [.6, 1]})

from range_editor import RangeEditor
pair = RangeEditor(number_type=int, value=(5, 9), minimum=0, step=1, unit="ms")

from angle_editor import AngleEditor
angle = AngleEditor(value=143.12345678, period=360, decimals=2)

from repeatable_container import RepeatableContainer
from PySide6.QtWidgets import QLineEdit
repeat = RepeatableContainer(
    lambda value, parent: QLineEdit(value, parent),
    lambda editor: editor.text(),
    lambda: "",
    values=["A", "B"],
)

from led_ring_preview import LedRingPreview
ring = LedRingPreview(led_count=3)
ring.set_value([0xFF7700, None, "#0077FF"])
```

Füge das ausgewählte Widget in das Layout des Hosts ein. Für Änderungen verwende `widget.value_edited.connect(callback)`, sofern das Widget ein Werteditor ist. Die Kopiertests starten für jede Datei einen frischen isolierten Python-Prozess und prüfen Werte, Benutzerereignisse, Darstellung und Grenzen.
