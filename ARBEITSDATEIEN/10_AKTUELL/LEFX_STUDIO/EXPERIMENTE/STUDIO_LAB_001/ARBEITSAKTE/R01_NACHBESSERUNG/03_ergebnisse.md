# 03 – Ergebnisse LAB-001-R01

Befundorientierte Darstellung. Grundlage: Reviewbericht R01
(`evidenz/review/2026-10-23_REVIEWBERICHT_R01.md`), geprüfter Commit `2bc9896`.
Code-Commits der Nachbesserung: `42030ed` (F03) und `2106ed5` (F01, F02).
Alle Pfade in den Tabellen relativ zu diesem Verzeichnis (`R01_NACHBESSERUNG/`) bzw. zum
Paket `packages/led-controller-version-3-effect-creation/src/lefx/effect_creation/`.

**Lesart der Prüfarten.** *Fake-Senke* heißt: echtes Studio, echter eingebetteter
`ControllerService` mit laufendem Render-Thread, echte Engine, echter `TappedSink` — nur die
Gerätesenke ist durch eine Aufzeichnung ersetzt. *Echte Hardware* heißt: reSpeaker per USB;
beobachtet wurden Zustände und gesendete Frames, **nicht** die LEDs.

---

## Traceability-Übersicht

| Befund | Problem (kurz) | Festgestellte Ursache | Korrektur | Dateien / Funktionen | Tests | Evidenz | Status |
|---|---|---|---|---|---|---|---|
| **LAB-001-R01-F01** | Nach Katalog-Reload bei pausierter Vorschau: Gerät und Lab-Status weichen ab | Reload ersetzt die Registry, der Feed-Zustand bleibt auf der Ebene; jeder Engine-Tick scheitert; Wiederanbindung nur beim nächsten Push | Session meldet `"before"`/`"after"` um `reload_sources()`/`open()`; Lab nimmt den Feed vorher von der Ebene und spielt ihn danach sofort neu ein oder beendet die Ausgabe mit Grund | `studio/session.py`: `watch_rebuilds`, `_tell`, `open`/`_open`, `reload_sources`; `studio/lab/output.py`: `_on_rebuild`, `_attach`, `_retire`, `_end`, `stop`, `close`; `studio/lab/page.py`: `_on_output_ended`, `shutdown` | 5 in `test_lab_output.py`, 1 in `test_lab_page.py` (siehe F01-Abschnitt) | `evidenz/tests/2026-10-23_REGRESSIONSTESTS_{VORHER,NACHHER}_R01.txt`; `evidenz/pruefungen/2026-10-23_REPRODUKTION_{VORHER,NACHHER}_R01.json` → `LAB-001-R01-F01`; `evidenz/pruefungen/2026-10-23_HARDWARE_DURCHSTICH_NACHHER_R01.json` → `2_…`; `evidenz/code/2026-10-23_DIFF_F01_F02_PRODUKTIONSCODE_R01.diff` | umgesetzt; getestet (Fake-Senke, echte Hardware ohne Sichtprüfung) |
| **LAB-001-R01-F02** | Nach „Alles löschen“ zeigt das Lab weiter „Sendet“ | `clear_all()` entfernt den Feed; `LabOutput.active`, Checkbox und Status werden nicht angepasst; Wiederaufnahme über die noch angehakte Checkbox wirkungslos | `LabOutput.carried`/`verify(reason)` vergleichen Anspruch und Runtime; Fenster fragt direkt nach dem Löschen; zusätzlich bei jedem Push und im sekündlichen Status-Refresh; Ende hakt ab und nennt Grund und Wiederaufnahme | `studio/lab/output.py`: `carried`, `verify`, `push`, `_feed_on_layer`, `on_ended`; `studio/window.py`: `_clear_everything`; `studio/lab/page.py`: `verify_output`, `_on_output_ended`, `_refresh_output_state` | 3 in `test_lab_output.py`, 1 in `test_lab_page.py` (siehe F02-Abschnitt) | wie F01, JSON-Schlüssel `LAB-001-R01-F02` bzw. `3_…`, `4_…` | umgesetzt; getestet (Fake-Senke, echte Hardware ohne Sichtprüfung) |
| **LAB-001-R01-F03** | `.lefx`-Ziel wird vor der Prüfung geschrieben | `export_package()` schrieb per `atomic_write()`, `verify_package()` prüfte erst die geschriebene Datei; die Seite meldete trotzdem „Exportiert nach …“ | Prüfung des Kandidaten im Staging-Verzeichnis; Schreiben nur nach bestandener Prüfung; jeder Fehler `DesignError` „… Die Zieldatei wurde nicht verändert.“; Bericht mit `check` und `sha256` | `visual/compiler.py`: `export_package`, `UNCHANGED`; `studio/lab/page.py`: `export_to` | 5 Funktionen (6 Fälle) in `test_visual_core.py`, 1 in `test_lab_page.py` (siehe F03-Abschnitt) | Testdateien wie oben; JSON-Schlüssel `LAB-001-R01-F03`; `evidenz/code/2026-10-23_DIFF_F03_PRODUKTIONSCODE_R01.diff` | umgesetzt; getestet (automatisiert, ohne Hardwarebezug) |

Testlage gesamt: vor der Korrektur 15 failed / 2 passed, danach 17 passed
(`evidenz/tests/2026-10-23_REGRESSIONSTESTS_VORHER_R01.txt`, `…_NACHHER_R01.txt`).
Gesamte hardwarefreie Suite: 1612 → 1629 passed, keine neuen Fehler oder Skips
(`evidenz/tests/2026-10-23_TESTSUITE_HARDWAREFREI_{VORHER,NACHHER}_R01.txt`).

---

## LAB-001-R01-F01 – Hardwareausgabe nach Katalog-Reload

**Ursprüngliches Problem (Review).** Ein Katalog-Reload kann `studio_lab_live` entfernen; die
Wiederanbindung hängt am nächsten Frame-Push; bei pausierter Vorschau weicht der
Hardwarezustand vom angezeigten Lab-Status ab.

**Technisch festgestellte Ursache.** `ControllerService.reload_sources()` baut die Registry neu
und übergibt sie der Runtime. Die Lab-Definition fehlt darin, ihr Zustand liegt aber weiter auf
der Primärebene. Der Composer findet die Definition nicht, der gesamte Tick scheitert vor
`apply_frame`. Folgen, beobachtet in `evidenz/pruefungen/2026-10-23_REPRODUKTION_VORHER_R01.json`:
9 gescheiterte Render-Iterationen in 0,4 s, Gerät auf dem letzten Frame eingefroren,
`last_error = TargetNotFoundError("No effect or preset named 'studio_lab_live'")` dauerhaft,
Lab-Status „Sendet an …“. Die Vorher-Tests zeigen außerdem: globale Helligkeit schlägt fehl,
ein Ausgabewechsel liefert ein schwarzes neues Gerät, `stop()` räumt nach einem
Registry-Wechsel nicht auf. Der Befund ist damit **schwerer als im Review beschrieben**.

**Umgesetzte Korrektur.** `StudioSession.watch_rebuilds()` benachrichtigt vor und nach jedem
`reload_sources()` und `open()` (auch bei Fehlschlag: `"after"` im `finally`). `LabOutput`:
* `"before"` → `_retire()`: Feed-Zustand per öffentlichem `clear_state()` von der Ebene, solange
  die Definition noch existiert — die Engine hält nie einen Zustand, den sie nicht auflösen kann.
* `"after"` → bei aktiver Ausgabe sofort `_attach()` (Registrieren und Abspielen); kein Frame,
  kein Timer nötig. Scheitert das (oder fehlt danach die Ausgabe / passt die LED-Anzahl nicht),
  `_end(reason)`: Ausgabe aus, nichts bleibt auf der Ebene, `on_ended(reason)` informiert die Seite,
  die die Checkbox abhakt und den Grund meldet.
* `stop()` räumt unabhängig von Registry-Identität auf (`_retire()`).
* `close()` meldet sich von der Session ab; `LabPage.shutdown()` ruft es.

**Tests** (Prüfart: Fake-Senke).
| Test | Was er belegt |
|---|---|
| `tests/studio/test_lab_output.py::test_a_reload_while_the_preview_is_paused_keeps_the_device_fed` | Reload ohne Folge-Push: kein `last_error`, Gerät zeigt Lab-Frame, Feed auf der Ebene, `active` und `carried` |
| `…::test_after_a_reload_the_global_output_settings_still_work` | Helligkeit nach Reload wirkt auf das Gerät |
| `…::test_switching_the_output_while_paused_feeds_the_new_device` | neuer Dienst (Ausgabewechsel) ohne Push: neues Gerät zeigt Lab-Frame |
| `…::test_stopping_after_a_reload_really_clears_the_device` | `stop()` nach Reload: Ebene leer, Gerät schwarz |
| `…::test_a_feed_that_cannot_come_back_is_ended_and_said_so` | Wiederherstellung scheitert: Ausgabe beendet, Grund gemeldet, kein `last_error`, Ebene leer |
| `tests/studio/test_lab_page.py::test_reloading_the_catalogue_keeps_a_paused_lab_on_the_device` | über das echte Menü „Katalog → Quellen neu laden“: Gerät, Runtime, Checkbox und Statustext übereinstimmend |

**Evidenz.** Reproduktion nachher (`…_REPRODUKTION_NACHHER_R01.json`, `LAB-001-R01-F01`):
0 gescheiterte Iterationen, Gerät = Lab-Frame, `last_error` null, Status „Sendet …“ zutreffend.
Echte Hardware (`…_HARDWARE_DURCHSTICH_NACHHER_R01.json`, `2_LAB-001-R01-F01_after_reload`):
0 gescheiterte Iterationen, Senke verfügbar, zuletzt gesendeter Frame = Lab-Frame,
Feed auf der Ebene, `last_error` null.

**Verbleibende Einschränkungen.**
* Während eines Reloads zeigt das Gerät kurz Schwarz (Feed vorübergehend von der Ebene) — bewusster
  Preis für einen Ablauf ohne gescheiterten Tick.
* Das erneute Einspielen ruft wie jede Lab-Übernahme `clear_everything()` auf.
* Der Quelleditor tauscht für seine Vorschau die Registry direkt aus (vorbestehend, README 6.10).
  Dieser Weg meldet nichts; er ist nur erreichbar, wenn das Lab nicht im Vordergrund ist und
  daher nicht sendet. Er wäre zusätzlich vom Abgleich aus F02 erfasst (Beenden statt Wiederherstellen).
* Ein scheiternder `reload_sources()` selbst ist nicht eigens getestet; geprüft ist das Scheitern
  der Wiederherstellung.
* `LabOutput` liest den Ebenenzustand über `service.runtime.status()` vom GUI-Thread aus, ohne das
  Dienst-Lock (öffentliche, lesende Methode). Nebenläufigkeit unter Last wurde nicht eigens geprüft.
* Ausgabewechsel bei pausierter Vorschau nur mit Fake-Senke geprüft, nicht mit echter Hardware.
* Keine Sichtprüfung der LEDs, kein manueller Klickdurchgang unter Windows (Menüaktionen wurden
  programmatisch über ihre `QAction` ausgelöst, Qt offscreen).

**Status.** Technisch umgesetzt; erfolgreich getestet (automatisiert mit Fake-Senke; Durchstich
mit echtem reSpeaker ohne Sichtprüfung); zur erneuten Abnahme bereitgestellt.

---

## LAB-001-R01-F02 – Inkonsistenter Sendestatus nach „Alles löschen“

**Ursprüngliches Problem (Review).** Globales Löschen entfernt den Runtime-Zustand, ohne
`LabOutput.active` und Checkbox anzupassen; die Oberfläche zeigt weiter „Sendet“.

**Technisch festgestellte Ursache.** `window._clear_everything()` ruft nur
`session.clear_everything()`; der Status-Timer liest nur das Flag. Vorher-Reproduktion
(`…_REPRODUKTION_VORHER_R01.json`, `LAB-001-R01-F02`): Gerät schwarz, `lab_output_active` true,
Checkbox angehakt, Status „Sendet an …“. Zusätzlich gefunden: Erneutes Anhaken bewirkte
nichts (`after_resume`: Gerät weiterhin schwarz), weil die Checkbox nie abgehakt worden war.

**Umgesetzte Korrektur.** `LabOutput.carried` prüft, ob der Feed auf der Primärebene liegt und
die Registry ihn mit der eigenen Klasse auflöst; `verify(reason)` beendet eine Ausgabe, die
behauptet zu senden, aber nicht getragen wird (einmalig; danach nur noch `False`). Aufrufer:
`window._clear_everything()` direkt nach dem Löschen (Grund: „Ausgabe → Alles löschen hat das
Senden des Labs beendet. Zum Fortsetzen „An Ausgabe senden“ erneut aktivieren.“), jeder
`push()` und `_refresh_output_state()` (sekündlicher Status-Refresh, Sicherheitsnetz).
`LabPage._on_output_ended()` hakt die Checkbox ab, zeigt den Grund und aktualisiert den Status.

**Wiederaufnahmeregel (festgelegt).** Ein Löschen wird nicht stillschweigend rückgängig gemacht:
Kein Frame der weiterlaufenden Vorschau holt sich das Gerät zurück. Gesendet wird erst wieder,
wenn „An Ausgabe senden“ erneut angehakt wird — dann sofort.

**Tests** (Prüfart: Fake-Senke).
| Test | Was er belegt |
|---|---|
| `tests/studio/test_lab_output.py::test_a_global_clear_ends_the_lab_output_instead_of_pretending` | nach Löschen und weiterem Push: nicht aktiv, Gerät schwarz, Ebene leer |
| `…::test_after_a_global_clear_sending_resumes_only_when_asked` | Push holt nichts zurück; explizites `start()` sendet sofort wieder |
| `…::test_a_global_clear_is_reported_through_the_ended_callback` | Grund geht genau einmal an `on_ended` |
| `tests/studio/test_lab_page.py::test_clearing_everything_ends_the_lab_send_and_says_so` | über das echte Menü „Ausgabe → Alles löschen“: Checkbox ab, kein „Sendet“, Meldung nennt „Alles löschen“, Gerät schwarz; erneutes Anhaken sendet wieder |

**Evidenz.** Reproduktion nachher (`LAB-001-R01-F02`): nicht aktiv, Checkbox ab, Status „Nur
Softwarevorschau …“, Meldung mit Grund; `after_resume`: Gerät = Lab-Frame, „Sendet …“.
Echte Hardware: `3_LAB-001-R01-F02_after_clear` (gesendeter Frame schwarz, Lab nicht aktiv,
Checkbox ab) und `4_LAB-001-R01-F02_after_resume` (gesendeter Frame = Lab-Frame, aktiv).

**Verbleibende Einschränkungen.**
* Ein Löschen auf einem anderen Weg als über das Fenstermenü würde bei pausierter Vorschau erst
  durch den sekündlichen Status-Refresh erkannt (höchstens etwa eine Sekunde). Im eingebetteten
  Studio-Dienst ist kein solcher Weg bekannt, solange das Lab sendet.
* Keine Sichtprüfung der LEDs, kein manueller Klickdurchgang.

**Status.** Technisch umgesetzt; erfolgreich getestet (automatisiert mit Fake-Senke; Durchstich
mit echtem reSpeaker ohne Sichtprüfung); zur erneuten Abnahme bereitgestellt.

---

## LAB-001-R01-F03 – Exportprüfung vor endgültiger Dateiersetzung

**Ursprüngliches Problem (Review).** Die `.lefx`-Zieldatei wird vor Loader- und Frameprüfung
erstellt bzw. ersetzt.

**Technisch festgestellte Ursache.** `export_package()` endete mit `atomic_write(path, …)`;
`page.export_to()` rief `verify_package()` erst danach für die geschriebene Datei auf. Vorher-
Reproduktion (`LAB-001-R01-F03`): Ziel-SHA-256 vorher `3b0266e5…`, nachher `939e6650…`
(`target_unchanged: false`), Meldung „Exportiert nach …, aber 1 von 8 Zeitpunkten weichen von der
Vorschau ab!“, Rückgabe enthielt den Bericht statt `None`.

**Umgesetzte Korrektur.** `export_package(document, path, *, led_count=12, times=CHECK_TIMES)`:
Staging, Packen, `verify_package()` auf dem Kandidaten im Staging-Verzeichnis; `DesignError`
des Loaders und jede andere Ausnahme der Prüfung werden zu `DesignError` mit „Die Zieldatei
wurde nicht verändert.“; Abweichungen ebenso („Export abgebrochen: n von m Zeitpunkten …“).
Erst danach `atomic_write()`. Rückgabe enthält `check` und `sha256` der geschriebenen Bytes.
`LabPage.export_to()` exportiert mit der LED-Zahl der Vorschau und meldet „Exportiert und
geprüft …“ nur aus diesem Bericht; der eigene Import von `verify_package` entfiel.

**Tests** (Prüfart: automatisiert, kein Hardwarebezug).
| Test | Auftragspunkt | Was er belegt |
|---|---|---|
| `tests/authoring/test_visual_core.py::test_a_successful_export_reports_the_check_it_passed` | 5 | Erfolg trägt `check` ohne Abweichung und `sha256` = Hash der Zieldatei; keine Reste im Zielordner |
| `…::test_an_export_whose_frames_disagree_is_never_written` | 6 | Abweichende Frames: `DesignError` „nicht verändert“, Ziel nicht angelegt |
| `…::test_a_refused_export_leaves_the_existing_file_exactly_as_it_was` | 7 | vorhandenes gültiges Paket byte-gleich erhalten |
| `…::test_a_package_the_loader_refuses_is_not_written_either` | 6, 7 | Loader-Ablehnung: Meldung „lehnt das Paket ab … nicht verändert“, Ziel byte-gleich |
| `…::test_the_written_package_renders_what_the_preview_shows[12]`, `[24]` | 8 | geschriebenes Paket, unabhängig von `verify_package` mit `EffectLibrary` geladen, rendert an 5 Zeitpunkten dieselben Frames wie die Vorschau |
| `tests/studio/test_lab_page.py::test_a_failed_export_check_keeps_the_previous_package` | 6, 7 | über die Lab-Seite: Rückgabe `None`, Ziel byte-gleich, keine Erfolgsmeldung, Meldung „nicht verändert“ |

**Evidenz.** Reproduktion nachher (`LAB-001-R01-F03`): `target_unchanged: true`, keine
Restdateien, Rückgabe `null`, Meldung „Export abgebrochen: 1 von 8 Zeitpunkten des Pakets weichen
von der Vorschau ab. Die Zieldatei wurde nicht verändert.“ Hinweis zu den absoluten Hashes:
siehe `02_verlauf.md`, Abschnitt 10 (nur innerhalb eines Laufs vergleichbar).

**Verbleibende Einschränkungen.**
* Abweichung und Loader-Ablehnung sind in den Tests **simuliert** (ersetzte Prüffunktion): Weil
  Vorschau und Paket aus demselben Generator stammen, gibt es keinen natürlichen Fall, der sie
  herbeiführt. Geprüft ist die Reihenfolge und Garantie, nicht eine reale Fehlerursache.
* Vorbestehend und unverändert (README 6.11): `verify_package` schließt die `EffectLibrary`;
  eine vollständige Freigabe aller vom Loader importierten Module wird nicht behauptet.
* Fehler beim Schreiben selbst (z. B. Datenträger voll) wurden nicht neu getestet;
  `atomic_write()` ist unverändert.

**Status.** Technisch umgesetzt; erfolgreich getestet (automatisiert); zur erneuten Abnahme
bereitgestellt. Hardware ist für diesen Befund nicht relevant.

---

## Abdeckung der im Auftrag geforderten Regressionstests (Schritt 4)

| Nr. | Gefordert | Abgedeckt durch |
|---|---|---|
| 1 | Aktiver Lab-Feed bei pausierter Vorschau | `test_a_reload_while_the_preview_is_paused_keeps_the_device_fed`; `test_reloading_the_catalogue_keeps_a_paused_lab_on_the_device` (stellt `not lab.clock.playing` fest) |
| 2 | Katalog-Reload während dieser Ausgabe | dieselben, dazu `test_after_a_reload_the_global_output_settings_still_work`, `test_stopping_after_a_reload_really_clears_the_device`, `test_a_feed_that_cannot_come_back_is_ended_and_said_so`, `test_switching_the_output_while_paused_feeds_the_new_device` |
| 3 | Globales Löschen einer aktiven Lab-Ausgabe | `test_a_global_clear_ends_the_lab_output_instead_of_pretending`, `test_a_global_clear_is_reported_through_the_ended_callback`, `test_clearing_everything_ends_the_lab_send_and_says_so` |
| 4 | Konsistente Wiederaufnahme | `test_after_a_global_clear_sending_resumes_only_when_asked`, zweiter Teil von `test_clearing_everything_ends_the_lab_send_and_says_so` |
| 5 | Erfolgreicher `.lefx`-Export | `test_a_successful_export_reports_the_check_it_passed` |
| 6 | Fehler bei der abschließenden Exportprüfung | `test_an_export_whose_frames_disagree_is_never_written`, `test_a_package_the_loader_refuses_is_not_written_either`, `test_a_failed_export_check_keeps_the_previous_package` |
| 7 | Erhalt einer vorhandenen Zieldatei nach Fehler | `test_a_refused_export_leaves_the_existing_file_exactly_as_it_was`, `test_a_package_the_loader_refuses_is_not_written_either`, `test_a_failed_export_check_keeps_the_previous_package` |
| 8 | Übereinstimmung exportierter Effekt / Vorschau | `test_the_written_package_renders_what_the_preview_shows[12]`, `[24]` |

Die F01/F02-Tests laufen über den eingebetteten `ControllerService` mit einer aufzeichnenden
Senke (`RecordingSink`), wie für F02 im Auftrag verlangt.

## Einordnung weiterer Reviewhinweise

* **Glossar-Commit `117b064` und Dokumentationsänderungen:** `117b064` („docs(konzepte): a
  glossary …“, 10. August 2026) liegt auf dem lokalen `main`, aber nicht auf `origin/main`
  (`aa2f14b`). Weil der PR-Branch vom lokalen `main` abzweigt, trägt PR #1 diesen Commit mit.
  Sämtliche Änderungen unter `docs/` und an `PLAN.md` im PR stammen aus diesem einen Commit; die
  Lab-Commits ändern dort nichts. Die Nachbesserung hat ihn weder entfernt noch verändert.
  Vor einem Merge ist zu entscheiden, ob er mit PR #1 oder getrennt nach `main` gelangen soll.
* **Gruppenmodell, Parameter-Widgets, Farbkollektionen, Musterzyklus:** laut Review keine
  Blocker; nicht bearbeitet (Abgrenzung des Auftrags).
