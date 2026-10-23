# Evidenz – Reviewbericht R01 (dokumentierte Kopie)

| Feld | Wert |
|---|---|
| Quelle | https://github.com/marcosudau-vps/led_controller_respeaker-v3/pull/1#issuecomment-6355020849 |
| GitHub-Kommentar-ID | `6355020849` |
| Autor (GitHub-Login) | `marcosudau-vps` |
| Erstellt / zuletzt geändert | `2026-10-23T01:15:46Z` / `2026-10-23T01:15:46Z` |
| Abgerufen | 2026-10-23, per `gh api repos/marcosudau-vps/led_controller_respeaker-v3/issues/comments/6355020849` |
| Geprüfter PR-Head laut Bericht | `2bc9896ee3d82c1dec64ac81a1cb76850ca13e5d` |
| PR-Head beim Abruf (`git rev-parse origin/claude/lefx-studio-lab-prompt-0f58f5`) | `2bc9896ee3d82c1dec64ac81a1cb76850ca13e5d` — identisch, kein Drift |
| SHA-256 des Berichtstexts (UTF-8, unten zwischen den Markierungen) | `a1a4f81c771c3e2240a3c6f247b66a697901ef8dea3bf6a045bba859b26b15d0` |

Der Text zwischen den Markierungen ist der Kommentarinhalt **byte-identisch**
aus der GitHub-API übernommen, nicht abgetippt.

## Zuordnung der Befund-IDs

| Befund-ID | Kurztitel laut Bericht | Benannte Dateien / Funktionen |
|---|---|---|
| `LAB-001-R01-F01` | Katalog-Reload während pausierter Lab-Hardwareausgabe | `studio/lab/output.py` (`push()`, `_attach()`), `studio/lab/page.py` (`refresh()`), `studio/window.py` (`_reload_sources()`) |
| `LAB-001-R01-F02` | „Ausgabe → Alles löschen" desynchronisiert Lab-Sendestatus | `studio/window.py` (`_clear_everything()`), `studio/lab/output.py` (`active`), `studio/lab/page.py` (`_refresh_output_state()`, `_on_send_toggled()`) |
| `LAB-001-R01-F03` | Exportziel wird vor abschließender Prüfung geschrieben | `visual/compiler.py` (`export_package()`, `verify_package()`), `studio/lab/page.py` (`export_to()`) |

Hinweis aus dem Bericht selbst, für die Einordnung wichtig: *„Die genannten
F01–F03 beruhen auf statischer Codeanalyse und identifizierten Testlücken,
nicht auf einer von mir selbst reproduzierten Windows-Hardwarefehlfunktion."*
Die Reproduktion vor der Korrektur ist deshalb Teil dieser Nachbesserung
(siehe `../pruefungen/`).

<!-- BEGIN REVIEW BODY -->
# LEFX-STUDIO-LAB-001 – Technische Abnahme (R01)

**STATUS: `CHANGES_REQUIRED`**
**Geprüfter PR-Head:** `2bc9896ee3d82c1dec64ac81a1cb76850ca13e5d`
**PR:** #1, Basis `main`

> **GitHub-Hinweis:** Dies ist der verbindliche fachliche Reviewbericht als PR-Kommentar. GitHub erlaubt dem aktuell verbundenen Account keine native `REQUEST_CHANGES`-Review auf dem eigenen PR (HTTP 422). Der Workflowstatus ist ausdrücklich **CHANGES_REQUIRED**; der GitHub-native Reviewstatus bleibt davon unberührt.

## Gesamtbefund

Die erste Studio-Lab-Version ist weitgehend gelungen. Die Qt-Oberfläche mit Ebenenbaum, generischem Inspektor, zeit- und schrittbasierter Vorschau sowie ReSpeaker-Ausgabe verwendet den vorhandenen `visual.Editor` als Dokumentautorität. Vorschau und Export verwenden den gleichen generierten Effektcode, und die fünf Mindestabläufe A–E sind über die echten Widgets automatisiert getestet.

**Verifizierte CI-Evidenz am PR-Head:** GitHub Actions erfolgreich; im hardwarefreien CI-Testlauf `1597 passed, 18 skipped, 6 deselected`; außerdem Architektur-, Legacy- und Buildprüfungen erfolgreich. Der Agent berichtet lokal zusätzlich `1616 passed, 5 skipped` sowie einen realen ReSpeaker-Sink-Durchstich. Die tatsächliche optische LED-Ausgabe und ein manueller Windows-Klickdurchgang wurden in dieser unabhängigen Prüfung nicht durchgeführt.

**Ergebnis: CHANGES_REQUIRED.** Drei gezielte Korrekturen vor erneuter Abnahme, keine Neuimplementierung.

## Korrekturaufträge

### `LAB-001-R01-F01` – Katalog-Reload während pausierter Lab-Hardwareausgabe

**Dateien:** `studio/lab/output.py` (`push()`, `_attach()`), `studio/lab/page.py` (`refresh()`), `studio/window.py` (`_reload_sources()`).

Beim `session.reload_sources()` wird die Registry neu aufgebaut; die temporäre Definition `studio_lab_live` kann dabei entfallen. Der Wiederanschluss wird momentan in `LabOutput.push()` bei einem neuen Frame geprüft. Bei pausierter Vorschau muss kein weiterer Push stattfinden, sodass der tatsächliche Laufzeitstatus von der Lab-Anzeige abweichen kann.

**Erwartete Korrektur:** Die Ausgabe nach dem Reload unmittelbar kontrolliert wiederherstellen **oder** zuverlässig deaktivieren und korrekt anzeigen, ohne auf einen späteren Timer-Tick zu warten. Reproduzierbaren Regressionstest mit aktivem Lab-Feed, pausierter Vorschau und Reload ergänzen.

### `LAB-001-R01-F02` – „Ausgabe → Alles löschen“ desynchronisiert Lab-Sendestatus

**Dateien:** `studio/window.py` (`_clear_everything()`), `studio/lab/output.py` (`active`), `studio/lab/page.py` (`_refresh_output_state()`, `_on_send_toggled()`).

Ein globales `clear_all()` entfernt den aktiven Runtime-State, ohne zwangsläufig `LabOutput.active` und die Send-Checkbox zu aktualisieren. Die Oberfläche kann dadurch weiterhin „Sendet“ anzeigen, obwohl die Ausgabe entfernt wurde.

**Erwartete Korrektur:** Ausgabezustand, Checkbox und tatsächlichen aktiven Feed zuverlässig synchronisieren. Die Regel zur anschließenden Wiederaufnahme festlegen und mit einem Regressionstest über den eingebetteten Service und RecordingSink absichern.

### `LAB-001-R01-F03` – Exportziel wird vor abschließender Prüfung geschrieben

**Dateien:** `visual/compiler.py` (`export_package()`, `verify_package()`), `studio/lab/page.py` (`export_to()`).

`export_to()` erzeugt bzw. ersetzt die finale `.lefx`-Datei über `export_package()`, bevor `verify_package()` den Loader- und Framevergleich abgeschlossen hat. Bei einem fehlgeschlagenen Vergleich kann ein ungeprüfter Kandidat am endgültigen Ziel verbleiben.

**Erwartete Korrektur:** Exportkandidaten vor dem endgültigen Ersetzen prüfen, vorhandenes gültiges Ziel bei Fehlschlag erhalten, Erfolg nur nach bestandener Prüfung melden. Positiv-/Negativtests ergänzen.

## Weitere Hinweise (keine gesonderten Blocker)

- Der PR umfasst zusätzlich den früheren Commit `117b064` (V3-Glossar) und mehrere Dokumentationsänderungen. Vor einem Merge den erweiterten PR-Umfang bewusst berücksichtigen.
- Das vorläufige Gruppenmodell, die noch fehlenden öffentlichen Parameter-Widgets, Farbkollektionen und ein eigenständiger segmentinterner Musterzyklus **sind keine LAB-001-Abnahmeblocker**. Dies sind gewollte Folgeexperimente.
- Die genannten F01–F03 beruhen auf statischer Codeanalyse und identifizierten Testlücken, nicht auf einer von mir selbst reproduzierten Windows-Hardwarefehlfunktion.

## Bedingungen für erneute Abnahme

1. F01–F03 gezielt beheben; keine Änderungen an Engine, SDK oder LEFX-Runtime-Verträgen.
2. Gezielte Regressionstests ergänzen und komplette hardwarefreie CI prüfen.
3. Umgesetzte Korrekturen, Testnachweise und Restpunkte im lokalen LAB-001-Bericht festhalten.
4. Korrigierten PR-Head mit **`REVIEW_READY`** zur erneuten unabhängigen Prüfung einreichen.

**Bis dahin: kein Merge; erneute Abnahme und ausdrückliche Freigabe erforderlich.**

— Unabhängige technische Reviewprüfung, 23.10.2026
<!-- END REVIEW BODY -->
