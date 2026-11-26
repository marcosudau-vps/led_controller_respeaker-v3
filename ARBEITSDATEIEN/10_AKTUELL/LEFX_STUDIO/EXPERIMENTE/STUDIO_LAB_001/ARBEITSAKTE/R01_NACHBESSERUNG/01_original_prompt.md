# 01 – Originalauftrag LAB-001-R01

> **Herkunftsvermerk (nicht Teil des Auftrags).**
> Der Auftrag wurde am 23.10.2026 als eingefügter Text in die Agentensitzung
> übergeben. Unterhalb der Trennlinie steht er **unverändert in der empfangenen
> Fassung**, als Textblock umschlossen, damit die Darstellung nicht durch
> Markdown-Interpretation verändert wird.
>
> **Einschränkung:** Übernommen wurde die Fassung, wie sie in der Sitzung
> ankam. Ob die ursprüngliche Quelle zusätzliche Formatierung trug, die beim
> Einfügen verloren ging (etwa Markdown-Überschriften, die hier als einfache
> Zeilen wie „1. Auftrag und Ausgangslage" erscheinen), ist von dieser Stelle
> aus nicht überprüfbar. Der Wortlaut ist vollständig und nicht redigiert.

---

````text
LEFX-STUDIO-LAB-001 – Nachbesserung nach Review R01
1. Auftrag und Ausgangslage
Du übernimmst die gezielte Nachbesserung des bereits implementierten LEFX Studio Labs.
Repository:
https://github.com/marcosudau-vps/led_controller_respeaker-v3
Pull Request:
https://github.com/marcosudau-vps/led_controller_respeaker-v3/pull/1
Arbeitsbranch:
`claude/lefx-studio-lab-prompt-0f58f5`
Geprüfter Commit:
`2bc9896ee3d82c1dec64ac81a1cb76850ca13e5d`
Aktueller fachlicher Reviewstatus:
`CHANGES_REQUIRED`
Verbindlicher Reviewbericht
https://github.com/marcosudau-vps/led_controller_respeaker-v3/pull/1#issuecomment-6355020849
Lies diesen Reviewbericht vollständig, bevor du Änderungen vornimmst.
Er ist die maßgebliche Grundlage für diese Nachbesserung.
Der Review wurde als PR-Kommentar veröffentlicht, weil GitHub über den verbundenen Account keine native `REQUEST_CHANGES`-Review des eigenen Pull Requests erlaubt.
Der dokumentierte fachliche Status lautet dennoch verbindlich `CHANGES_REQUIRED`.
Ziel ist es, die Reviewbefunde abzuarbeiten, sämtliche Arbeiten nachvollziehbar zu dokumentieren und den PR für eine erneute unabhängige Abnahme vorzubereiten.
2. Verbindliche Arbeitsweise
Diese Aufgabe umfasst zwei gleichwertige Bestandteile:

1. Die technische Nachbesserung der Implementierung einschließlich Regressionstests.
2. Die vollständige Führung einer prüffähigen Arbeitsakte einschließlich Originalprompt, Verlauf, Ergebnissen, Abschlussbericht und Evidenzunterlagen.

Die Arbeitsakte ist ein verpflichtender Bestandteil des Arbeitsergebnisses und kein optionaler Anhang.
Die Aufgabe gilt nicht als abgeschlossen, solange die technische Umsetzung oder die geforderten Arbeitsunterlagen fehlen.
Halte technische Durchführung und dokumentierte Nachweise fortlaufend synchron.
Dokumentiere nur tatsächlich ausgeführte Schritte und beobachtete Ergebnisse. Erfinde keine Testnachweise, Messwerte oder Freigaben.
3. Arbeitsumgebung und Verzeichnisse
Arbeite im vorhandenen lokalen Workspace des Repositories `respeaker-led-v3`.
Benutze den bestehenden lokalen PR-Branch beziehungsweise dessen vorhandenen Worktree.
Erstelle keinen neuen Pull Request und keine parallele Implementierung.
Bestehende Dokumentation
Die vorhandene LAB-001-Dokumentation liegt unter:
`ARBEITSDATEIEN/10_AKTUELL/LEFX_STUDIO/EXPERIMENTE/STUDIO_LAB_001/`
Dort befinden sich bereits unter anderem:

* `README.md`
* `ANWENDERANLEITUNG.md`
* `screenshots/`

Erhalte diese Unterlagen und aktualisiere sie bei Bedarf.
Neue Arbeitsakte für Review R01
Lege für die Nachbesserung die folgende Arbeitsakte an:
`ARBEITSDATEIEN/10_AKTUELL/LEFX_STUDIO/EXPERIMENTE/STUDIO_LAB_001/ARBEITSAKTE/R01_NACHBESSERUNG/`
Vorgesehene Struktur:

```
STUDIO_LAB_001/
├── README.md
├── ANWENDERANLEITUNG.md
├── screenshots/
└── ARBEITSAKTE/
    └── R01_NACHBESSERUNG/
        ├── 01_original_prompt.md
        ├── 02_verlauf.md
        ├── 03_ergebnisse.md
        ├── 04_abschlussbericht.md
        └── evidenz/
            ├── review/
            ├── tests/
            ├── code/
            └── pruefungen/
```

Überprüfe zunächst, ob das Projekt bereits verbindliche Konventionen für Arbeitsakten, Dateinamen, Evidenzverwaltung oder Traceability besitzt.
Falls solche Konventionen existieren, halte sie ein und dokumentiere erforderliche Abweichungen. Die oben genannten Dokumenttypen und die eindeutige Zuordnung zur Reviewrunde R01 müssen erhalten bleiben.
Verwende keine anderen frei gewählten Ablageorte.
4. Anforderungen an die Arbeitsakte
4.1 `01_original_prompt.md`
Diese Datei enthält den vollständigen Originalwortlaut des vorliegenden Nachbesserungsauftrags.
Anforderungen:

* Vollständiger Prompt einschließlich aller Abschnitte.
* Keine Zusammenfassung.
* Keine nachträgliche redaktionelle Überarbeitung.
* Keine Vermischung mit eigenen Schlussfolgerungen.
* Keine nachträgliche Anpassung des Originaltexts an den tatsächlichen Bearbeitungsverlauf.

Die Datei dient als unveränderlicher Beleg dafür, welcher Auftrag erteilt wurde.
Wenn der vollständige ursprüngliche Prompt aus technischen Gründen nicht zuverlässig übernommen werden kann, dokumentiere die Einschränkung ausdrücklich. Stelle eine rekonstruierte Fassung niemals als unverändertes Original dar.
Der ursprüngliche LAB-001-Auftrag ist eine separate Referenz; die vorliegende Arbeitsakte dokumentiert die Nachbesserung R01.
4.2 `02_verlauf.md`
Dokumentiere den tatsächlichen Bearbeitungsverlauf chronologisch.
Mindestens enthalten sein müssen:

* Auftragsübernahme.
* Ausgangsbranch und Ausgangscommit.
* Zustand des lokalen Worktrees vor Beginn.
* Gelesene Referenzen und relevante Projektvorgaben.
* Analyse der einzelnen Reviewbefunde.
* Wesentliche technische Entscheidungen.
* Durchgeführte Codeänderungen.
* Testdurchläufe und deren Ergebnisse.
* Aufgetretene Probleme und deren Behandlung.
* Erzeugte Commits.
* Abschließender Bearbeitungsstand.

Der Verlauf soll die Durchführung rekonstruierbar machen.
Keine künstlichen Zeitstempel oder erfundenen Zwischenschritte.
4.3 `03_ergebnisse.md`
Erstelle eine übersichtliche, befundorientierte Ergebnisdarstellung.
Für jeden Reviewbefund dokumentiere:

* Befund-ID.
* Ursprüngliches Problem.
* Technisch festgestellte Ursache.
* Umgesetzte Korrektur.
* Betroffene Dateien beziehungsweise Funktionen.
* Zugehörige Tests.
* Verweise auf konkrete Evidenzdateien.
* Verbleibende Einschränkungen.
* Bearbeitungsstatus.

Die Zuordnung zwischen Reviewbefund, Änderung und Nachweis muss eindeutig sein.
Eine geeignete Traceability-Tabelle ist ausdrücklich erwünscht.
4.4 `04_abschlussbericht.md`
Der Abschlussbericht muss auch ohne Kenntnis der laufenden Agentensitzung verständlich sein.
Er muss enthalten:

1. Auftragsidentifikation.
2. Referenz auf PR #1 und Review R01.
3. Ausgangszustand.
4. Zusammenfassung der vorgenommenen Änderungen.
5. Vollständige Abdeckung der Reviewbefunde.
6. Teststrategie und durchgeführte Tests.
7. Ergebnisse und Evidenzverweise.
8. Regressionsbewertung.
9. Noch offene Risiken und Einschränkungen.
10. Liste der relevanten Commits.
11. Endgültigen lokalen Git-Status.
12. Stand der PR-Aktualisierung.
13. Abschließenden Bearbeitungs- und Übergabestatus.

Unterscheide ausdrücklich zwischen:

* technisch umgesetzt,
* erfolgreich getestet,
* nicht getestet,
* noch offen,
* zur erneuten Abnahme vorgelegt.

Ein technisch umgesetzter Befund darf nicht automatisch als vollständig verifiziert gelten.
4.5 `evidenz/`
Lege die tatsächlichen Nachweise geordnet ab.
`evidenz/review/`

* Referenz beziehungsweise dokumentierte Kopie des maßgeblichen Reviewberichts.
* Geprüfter Commit.
* Zuordnung der Befund-IDs.
* Bei Bedarf weitere reviewrelevante Informationen.

`evidenz/tests/`

* Ausgeführte Testbefehle.
* Relevante Testausgaben oder Logs.
* Ergebniszusammenfassungen.
* Nachweise der ergänzten Regressionstests.
* Dokumentation von übersprungenen Tests und Einschränkungen.

`evidenz/code/`

* Relevante Commit-IDs.
* Änderungsübersichten.
* Bei Bedarf gezielte Diffs oder Verweise auf die betroffenen Quelltextstellen.

`evidenz/pruefungen/`

* Zusätzliche technische Prüfungen.
* Reproduktions- und Verifikationsprotokolle.
* Nachweise zum Runtime-Zustand.
* Nachweise zur Exportdatei-Konsistenz.
* Gegebenenfalls weitere geeignete Prüfergebnisse.

Speichere Evidenz möglichst als nachvollziehbare Text- oder strukturierte Dateien.
Vermeide redundante Kopien riesiger Testlogs. Vollständige Originalausgaben sind dort zu erhalten, wo sie für die Nachvollziehbarkeit erforderlich sind; andernfalls genügen relevante Auszüge mit klarer Quellenangabe.
Verweise auf externe CI-Läufe müssen deren konkrete URLs beziehungsweise Kennungen enthalten.
Jede zentrale Abnahmebehauptung muss durch eine nachvollziehbare Evidenzreferenz gestützt sein.
5. Technische Korrekturbefunde
Lies die vollständigen Beschreibungen im verlinkten Reviewbericht.
Die folgende Zusammenfassung ersetzt den Review nicht.
LAB-001-R01-F01 – Hardwareausgabe nach Katalog-Reload
Problem:
Ein Katalog-Reload kann die temporäre Lab-Effektdefinition `studio_lab_live` entfernen. Die Wiederanbindung ist derzeit an einen nachfolgenden Frame-Push gekoppelt.
Bei pausierter Vorschau kann dadurch der tatsächliche Hardwarezustand vom angezeigten Lab-Status abweichen.
Anforderungen:

* Vollständigen Ablauf analysieren.
* Aktive Lab-Ausgabe nach dem Reload zuverlässig wiederherstellen oder eindeutig deaktivieren.
* Tatsächlichen Status korrekt anzeigen.
* Keine Abhängigkeit von einem erst später eintretenden Timer-Tick.
* Reproduzierbare Regressionstests ergänzen.

Relevante Module:

* `studio/lab/output.py`
* `studio/lab/page.py`
* `studio/window.py`

Dokumentiere Ursache, Korrektur und Nachweis in der Arbeitsakte unter der Befund-ID `LAB-001-R01-F01`.
LAB-001-R01-F02 – Inkonsistenter Sendestatus nach „Alles löschen“
Problem:
Das globale Löschen der Ausgabe kann den aktiven LEFX-Runtime-State entfernen, ohne den lokalen Lab-Ausgabestatus entsprechend zu aktualisieren.
Anforderungen:

* Lokalen Ausgabestatus und Runtime-Zustand synchronisieren.
* Irreführende Statusmeldungen verhindern.
* Eindeutige Wiederaufnahme ermöglichen.
* Regressionstest über den eingebetteten `ControllerService` und einen RecordingSink ergänzen.

Relevante Module:

* `studio/window.py`
* `studio/lab/output.py`
* `studio/lab/page.py`

Dokumentiere Ursache, Korrektur und Nachweis unter `LAB-001-R01-F02`.
LAB-001-R01-F03 – Exportprüfung vor endgültiger Dateiersetzung
Problem:
Die endgültige `.lefx`-Zieldatei wird aktuell erstellt beziehungsweise ersetzt, bevor die abschließende Loader- und Frameverifikation durchgeführt wurde.
Anforderungen:

* Konsistente, sichere Exportreihenfolge gewährleisten.
* Kandidaten vor endgültiger Dateiersetzung prüfen.
* Vorhandene gültige Exportdateien bei Fehlschlägen unverändert erhalten.
* Erfolg erst nach erfolgreicher Verifikation melden.
* Positive und negative Regressionstests einschließlich Zielerhaltung ergänzen.

Relevante Module:

* `visual/compiler.py`
* `studio/lab/page.py`

Dokumentiere Ursache, Korrektur und Nachweis unter `LAB-001-R01-F03`.
6. Bearbeitungsstrategie
Schritt 1 – Ausgangszustand sichern
Vor Änderungen:

1. PR und Reviewbericht vollständig lesen.
2. Aktuellen PR-Head feststellen.
3. Arbeitsbranch und lokalen Git-Status prüfen.
4. Vorhandene Arbeitsdateien und Projektkonventionen untersuchen.
5. Ausgangsstand in der Arbeitsakte dokumentieren.
6. `01_original_prompt.md` mit dem vollständigen Originalauftrag anlegen.

Vorhandene uncommittete Änderungen anderer Arbeiten dürfen nicht überschrieben werden.
Schritt 2 – Befunde unabhängig nachvollziehen
Untersuche jeden Befund anhand des aktuellen Codes.
Versuche, den beanstandeten Zustand durch passende Tests oder gezielte Prüfungen zu reproduzieren.
Eine nicht zutreffende Reviewannahme darf begründet widerlegt werden, muss dann aber anhand konkreter Evidenz nachvollziehbar sein.
Dokumentiere den Befundstatus vor der Korrektur.
Schritt 3 – Korrekturen implementieren
Führe ausschließlich die erforderlichen gezielten Änderungen durch.
Erhalte dabei:

* Den vorhandenen `visual.Editor` als zentrale Dokumentinstanz.
* Die Trennung zwischen Qt-Oberfläche und Anwendungskern.
* Die bestehende Vorschau- und Compilerarchitektur.
* Die normale `StudioSession`- und `ControllerService`-Integration.
* Die vorhandene ReSpeaker-Ausgabe.
* Die bestehenden Studio-Tabs.
* Das bisherige LEFX-V3-Verhalten.

Keine Änderungen an Engine, SDK, Runtime-Verträgen oder Paketformat.
Keine neuen großen Frameworks oder unnötigen Refactorings.
Schritt 4 – Regressionstests ergänzen
Implementiere geeignete Tests für:

1. Aktiven Lab-Feed bei pausierter Vorschau.
2. Katalog-Reload während dieser Ausgabe.
3. Globales Löschen einer aktiven Lab-Ausgabe.
4. Konsistente Wiederaufnahme.
5. Erfolgreichen `.lefx`-Export.
6. Fehler bei der abschließenden Exportprüfung.
7. Erhalt einer vorhandenen Zieldatei nach einem Fehler.
8. Übereinstimmung des exportierten Effekts mit der Vorschau.

Schritt 5 – Vollständige technische Prüfung
Führe geeignete Prüfungen aus, darunter:

* Neue gezielte Regressionstests.
* Vorhandene Studio-Lab-Tests.
* Relevante Architekturtests.
* Vollständige hardwarefreie Testsuite.
* Geeignete Build- und Startup-Prüfungen.

Dokumentiere die tatsächlich ausgeführten Befehle und Ergebnisse.
Unterscheide automatisierte Fake-Sink-Prüfungen ausdrücklich von Tests mit realer Hardware.
Schritt 6 – Arbeitsakte vervollständigen
Aktualisiere Verlauf, Ergebnisse und Evidenz fortlaufend.
Erstelle anschließend den vollständigen Abschlussbericht.
Prüfe vor Abschluss, dass:

* alle drei Reviewbefunde abgedeckt sind,
* jede Korrektur nachvollziehbar beschrieben ist,
* die zugehörigen Tests dokumentiert sind,
* Evidenzdateien existieren und referenziert sind,
* die angegebenen Commit-IDs stimmen,
* der Originalprompt vollständig und unverändert erhalten ist.

Schritt 7 – Lokalen Abschluss vorbereiten
Erstelle nachvollziehbare lokale Commits mit den Korrekturen, Tests und Arbeitsunterlagen.
Prüfe den abschließenden Git-Status.
Keine fremden Änderungen verwerfen.
Kein Merge nach `main`.
Keine Releases oder Tags.
Remote-Pushes nur bei ausdrücklich bestehender Autorisierung. Andernfalls die lokalen Commits zur Aktualisierung des bestehenden PR #1 bereitstellen.
7. Abgrenzung
Nicht Bestandteil dieser Nachbesserung sind:

* Neue Animationsbausteine.
* Farbkollektionen.
* Ein neuer Farbverlaufseditor.
* Eine umfassende Überarbeitung des Ebenenmodells.
* Neue Gruppen- oder Hierarchiekonzepte.
* Eine allgemeine neue Animations- oder Kollisionsengine.
* Öffentliche Parameter-Widgets.
* Weitere Zeitleistenfunktionen.
* Eine vollständige Neugestaltung der Oberfläche.
* Ein allgemeines Widget-Pluginframework.

Diese Themen gehören in die späteren Studio-Lab-Experimente.
Der zusätzliche Glossar-Commit `117b064` und die weiteren Dokumentationsänderungen sind gemäß Review bewusst einzuordnen, aber nicht eigenmächtig zu entfernen.
8. Abnahmekriterien
Die Nachbesserung ist bereit zur Wiedervorlage, wenn:

1. `LAB-001-R01-F01` vollständig bearbeitet und nachgewiesen ist.
2. `LAB-001-R01-F02` vollständig bearbeitet und nachgewiesen ist.
3. `LAB-001-R01-F03` vollständig bearbeitet und nachgewiesen ist.
4. Geeignete Regressionstests vorliegen.
5. Die vorhandenen Studio-Funktionen nicht regressieren.
6. Die erforderlichen Tests erfolgreich ausgeführt wurden beziehungsweise Abweichungen ausdrücklich dokumentiert sind.
7. Die vollständige Arbeitsakte existiert.
8. `01_original_prompt.md` den vollständigen unveränderten Auftrag enthält.
9. `02_verlauf.md` den tatsächlichen Bearbeitungsverlauf dokumentiert.
10. `03_ergebnisse.md` die Reviewbefunde eindeutig mit Korrekturen und Nachweisen verknüpft.
11. `04_abschlussbericht.md` vollständig ist.
12. Relevante Evidenzunterlagen vorhanden und auffindbar sind.
13. Der bestehende LAB-001-README um die Reviewnachbesserung ergänzt wurde.
14. Der abschließende Git- und PR-Stand eindeutig dokumentiert ist.

Fehlende oder unzureichende Arbeitsaktenbestandteile verhindern den erfolgreichen Abschluss ebenso wie fehlende technische Korrekturen.
9. Abschlussmeldung
Wenn alle Kriterien erfüllt sind, melde ausdrücklich:
`REVIEW_READY`
Der Abschluss muss auf Folgendes verweisen:

* Repository und PR #1.
* Ausgangscommit.
* Aktuellen Abschlusscommit.
* Die drei Reviewbefunde und ihre Ergebnisse.
* Die aktualisierte Arbeitsakte.
* Die wesentlichen Evidenzdateien.
* Konkrete Testergebnisse.
* Verbliebene Einschränkungen.
* Den tatsächlichen Stand der Remote-PR-Aktualisierung.

Wenn technische Befunde oder verpflichtende Arbeitsaktenbestandteile offenbleiben, melde einen entsprechend eingeschränkten Status statt `REVIEW_READY`.
`REVIEW_READY` ist keine Merge-Freigabe.
Die erneute unabhängige Abnahme erfolgt gesondert. Ein Merge ist erst nach ausdrücklicher Freigabe zulässig.
10. Startanweisung
Beginne jetzt mit der Durchführung.
Lies zuerst den verbindlichen Reviewbericht auf GitHub und untersuche danach die tatsächlichen Projektkonventionen und den Code.
Lege die Arbeitsakte an, sichere den Originalauftrag, behebe die Reviewbefunde und ergänze die erforderlichen Tests.
Führe die Arbeitsunterlagen während der gesamten Bearbeitung nachvollziehbar fort.
Ziel: PR #1 einschließlich vollständiger technischer Evidenz und prüffähiger Arbeitsakte von `CHANGES_REQUIRED` nach `REVIEW_READY` führen.
````
