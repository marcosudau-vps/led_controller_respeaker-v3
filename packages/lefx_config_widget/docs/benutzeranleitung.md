# TestLab und Bedienung

Starte das TestLab über `python -m lefx.config_widget` in der Umgebung, in der das Paket installiert ist.

## Effekte und Presets

1. Wähle Core, Smartspeaker oder beide Quellen. Suche nach Titel, ID oder Beschreibung und filtere nach Lebenszyklusform oder Effekt/Preset.
2. Öffne das Ziel per Enter, Doppelklick oder Schaltfläche. Die eindeutige ID enthält die Quelle. Die aktuelle Definition zeigt ihre Versionsnummer in der Trefferdetailansicht.
3. Wähle je Parameter die Wertquelle. **Standard** und **Preset** zeigen den aktuell geerbten Wert. **Eigener Wert** legt einen Override an. **Explizit null** schreibt bei einem entsprechenden Schema einen eigenen Nullwert.
4. Öffne Farbliste, Verlauf oder HSV-Bereich über **Details…**. **Übernehmen** schreibt den Wert in den Elternentwurf. **Abbrechen** lässt seinen vorherigen Wert bestehen. Gradient-Positionen lassen sich im Detail numerisch bearbeiten. Klicks auf die Verlaufsleiste wählen den nächstgelegenen Stützpunkt.

Parameternamen entsprechen den Schlüsseln der Definition. Der Tooltip nennt Beschreibung, Typ, Einheit, Grenzen und Aliase. Ein Parameter ohne Vorgabe zeigt **Ausgelassen**. Der Testwert `progress` beim gesteuerten Overlay **Level Meter** ist ein Beispiel für einen erforderlichen Wert ohne Default. Null ist z. B. als transparente Hintergrundfarbe verfügbar.

## Ereigniszuordnung

Die Übersicht unterscheidet **Nicht konfiguriert**, **Leer**, **Ungültig** und schreibgeschützte Regeln mit unbekannter Form. Öffne ein Ereignis und füge Aufrufe mit **+** hinzu oder öffne einen vorhandenen Aufruf. **↑** und **↓** ändern die Reihenfolge. Mit **−** entfernst du nach Bestätigung einen Aufruf.

- **Ziel auswählen…** öffnet die nach Aufrufart gefilterte Auswahl. Bestehende Kurz-IDs bleiben erhalten. Neu ausgewählte Ziele nutzen qualifizierte IDs. Bei unvereinbaren Optionen fragt das TestLab vor dem Zurücksetzen nach.
- **Aufruf übernehmen** übernimmt einen gültigen Aufruf in den Mapping-Entwurf. **Zurück · Entwurf behalten** bewahrt auch eine noch ungültige Eingabe. **Aufrufänderungen verwerfen** stellt den Ausgangswert der Unterseite wieder her.
- **Zuordnung übernehmen** akzeptiert einen gültigen Gesamtentwurf und aktualisiert die TestLab-Daten im Arbeitsspeicher. **Entwurf verwerfen** setzt auf die letzte Übernahme zurück. In einer eingebetteten Version kehrt **Zum Host** zur Anwendung zurück und behält den Entwurf.

**Aufgabe abgeschlossen** zeigt zwei geordnete LED-Aufrufe. **Voice-STT-Beispiel** wechselt zu einem Testdokument mit LED-, Sound- und App-Feldern. **Nur Core** demonstriert fehlende Smartspeaker-Ziele. **Namenskollision (Demo)** macht die Kurz-ID `solid_fill` mehrdeutig. Ein qualifiziertes Core-Ziel löst diese Mehrdeutigkeit auf. **Schreibgeschützt** lässt das Inspizieren der Zuordnung zu.

## Vorschau

**Start / Wiederholen** rendert den ausgewählten Effekt mit den aktuellen gültigen Parametern. Mit LED-Anzahl und Vorschauhelligkeit veränderst du den Ring im TestLab. **Stopp** hält das letzte Bild an. Tab-, Seiten- und Fensterwechsel beenden die aktive Vorschau.

Setze für ein gesteuertes Overlay die separat beschrifteten **Laufzeitwerte der Vorschau**. **Level Meter** benötigt `progress` in Prozentpunkten. **Direction Indicator** benötigt `direction_deg`. Für eine sichtbare Markierung setze außerdem `detection_state` auf `sound` oder `speech`. Diese Testwerte werden bei der Vorschau isoliert eingespeist.

## Galerie und Datenaustausch

In der Galerie kannst du alle sieben allgemeinen Widgets ausprobieren und zwischen editierbaren und schreibgeschützten Eingaben umschalten. Über der Tab-Leiste lassen sich Systempalette, Hell und Dunkel auswählen.

**Import / Export** arbeitet mit dem JSON-Objekt des Abschnitts `feedback_mappings`. Füge Daten ein oder öffne eine JSON-Datei und wähle **JSON als Entwurf importieren**. **Entwurf anzeigen** prüft die LED-Regeln und schreibt die Daten in das Textfeld. **JSON speichern…** fordert ausdrücklich einen Zielpfad an. Die Dateiform ist JSON. Die Voice-STT-Integration übergibt in Python bereits eingelesene YAML-Daten an denselben Adapter.
