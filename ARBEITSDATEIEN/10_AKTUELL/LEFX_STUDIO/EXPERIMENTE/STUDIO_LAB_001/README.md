# STUDIO_LAB_001 – Abschlussstand

Stand: 23.10.2026 · Auftrag: `ARBEITSDATEIEN/10_AKTUELL/LEFX_STUDIO/PLANUNG/AUFTRAEGE/prompt_LEFX-STUDIO-LAB-001.md`
(im Hauptcheckout) · Anwenderanleitung: [ANWENDERANLEITUNG.md](ANWENDERANLEITUNG.md) ·
Screenshots: [screenshots/](screenshots/)

Alles hier ist **experimentell**. Die unten genannten Festlegungen sind kleine, umkehrbare
Arbeitsannahmen des Labs, keine genehmigten Produktentscheidungen; ins zentrale
Entscheidungsregister wurde nichts übernommen.

## 1. Was jetzt existiert

Ein neuer Tab **„Studio Lab (experimentell)“** in der bestehenden `StudioWindow`. Player,
Kalibrierung und „Neuer Effekt“ sind unverändert vorhanden.

| Bereich | Umsetzung |
|---|---|
| Ebenen-/Objektbaum | Virtueller Eintrag „Gesamteffekt“, darunter Ebenen (oberste zuerst), darin Elemente und Animationen. Hinzufügen, Umbenennen (Doppelklick/F2), Entfernen, Duplizieren, Reihenfolge ▲▼, Sichtbarkeit per Häkchen, Kontextmenü, Kurztasten. |
| Inspektor | Felder werden aus den `Property`-Deskriptoren (`visual/blocks.py`) erzeugt: Farbe → Farbwahl + Hex, Bool → Checkbox, Int → SpinBox, Float → Slider + DoubleSpinBox mit Min/Max; Ringanteile (Position, Länge, Masken) zusätzlich in LEDs. Ebenen: Name, Sichtbar, Mischmodus. Gesamteffekt: Effektmetadaten. Fehler erscheinen am Feld, nicht als Dialog. |
| Vorschau | `RingMonitor` mit drei Ansichten: Gesamteffekt · Ebene isoliert · Ebene hervorgehoben (übrige abgedunkelt, nur Anzeige). Transparente Positionen (`None`) werden gestrichelt gezeichnet, deckendes Schwarz schwarz. Ringgröße der Vorschau einstellbar (nicht Teil des Entwurfs). |
| Zeitleiste | Play/Pause, Stopp (zurück zum Anfang), gezeichnete Zeitachse mit Abspielkopf (klicken/ziehen springt), „Gehe zu“ auf die Millisekunde, Zeitraum, Tempo 0,1×–4×, Schleife. Zeitbasis: `time.monotonic()` mit Anker (`studio/lab/clock.py`), unabhängig von der UI-Framerate. |
| Schrittansicht | Schrittquelle wählbar: gleichmäßige Abtastpunkte oder jede vorhandene Animation (Rotation → LED-Versätze, Blinken → Phasen an/aus, Funkeln → Takte, Pulsieren/Farbwechsel → ausdrücklich „Abtastpunkte“). Anzeige z. B. „Versatz 3 von 12 LEDs · Zyklus: 12 Schritte bei 12 LEDs, 2 verschiedene Bilder“. |
| Speichern/Laden/Export | Neu, Öffnen (`.lefx-design.json` oder eingebetteter Entwurf aus `.lefx`), Speichern, Speichern unter, Änderungsstatus „ungespeichert“, Rückfrage vor Verwerfen und beim Schließen, Export als `.lefx` mit anschließender Prüfung durch den Engine-Loader und Framevergleich mit der Vorschau. |
| Beispiele | Fünf Startpunkte für die Konzeptfälle (zwei Punkte gemeinsam, gegenläufige Segmente, A/B-Muster, Segment mit Farbwechsel, Überlagerung), gebaut mit den normalen Editor-Operationen. |
| ReSpeaker-Ausgabe | Ausgabewahl im Lab (dieselbe wie im Player), „An Ausgabe senden“, Ringanzeige wahlweise „Entwurf“ oder „Gerätesignal“ (exakt die an das Gerät gesendeten Werte inkl. globaler Helligkeit). |

### Datenfluss (die tragenden Entscheidungen)

* **Eine Quelle der Wahrheit:** `visual.Editor`. Baum und Inspektor senden nur Absichten
  (Signale); die Seite führt sie über Editor-Operationen aus, deren Validierung entscheidet.
  Nach jeder Änderung werden Baum und Inspektor aus dem Dokument neu befüllt; die Auswahl
  hängt an Objekt-IDs. Keine Signalrekursion (Signale beim Befüllen blockiert,
  Inline-Umbenennen zeitversetzt ausgeführt).
* **Eine Effektberechnung:** Jeder Frame kommt aus `compile_design()`. Pro Dokumentänderung
  werden die für die Ansicht nötigen Snapshots einmal kompiliert (LRU-Cache,
  `visual/preview.py`); Wiedergabe, Scrubbing und Schritte rufen nur `render(t)` auf.
  Test sichert: 200 Frames → 1 Kompilierung.
* **Vorschau ändert nie den Entwurf:** Isolieren, Hervorheben und „Unbedeckte Positionen
  zeigen“ arbeiten auf validierten Kopien (`preview.snapshot`), ohne Registry-Eingriffe.
  „Unbedeckt zeigen“ kompiliert die Kopie als `transparent`; die Gerätewerte bleiben dadurch
  nachweislich gleich (Test).
* **Slider-Ziehen** zeigt eine nicht übernommene Vorschau und übernimmt beim Loslassen –
  ein Zug ist ein Undo-Schritt.
* **Hardware über den bestehenden Pfad:** Das Lab registriert über die öffentliche
  `EffectRegistry.register_effect()` eine winzige State-Definition `studio_lab_live`
  (Quelle `studio-lab`), die bei jedem Engine-Tick das zuletzt im Lab berechnete Bild
  zurückgibt. Danach läuft alles wie bei jedem Effekt: Komposition, globale
  Helligkeit/An-Aus, `TappedSink`, Gerät. So funktionieren auch Pause, Scrubbing und
  Schritte auf dem Gerät, ohne zweite Effektberechnung. Kein Packen, kein Austausch privater
  Registry-Strukturen, kein USB-Sonderweg, keine SDK-/Engine-Änderung. Nach einem
  Katalog-Reload oder Ausgabewechsel registriert sich die Einspeisung neu. Primärzustände
  persistiert der Service nicht; der Feed landet also nie in der Hintergrundzustandsdatei (Test).
* **Gerätesicherheit:** Eine Vorschau-Ringgröße ≠ LED-Anzahl der Ausgabe wird nicht
  gesendet. Belegtprüfung (`device_in_use`) und Rückfall auf `null` bleiben in der
  Ausgabewahl des Fensters, die das Lab mitbenutzt. Es gibt nur einen eingebetteten Service,
  daher greifen Player, Kalibrierung und Lab nie parallel auf das USB-Gerät zu. Die
  Übernahme durch das Lab löscht bewusst, was der Player gerade zeigte; beim Verlassen des
  Tabs stoppen Timer und Ausgabe, das Gerät ist wieder frei.

## 2. Geänderte und neue Dateien

Worktree `C:\Users\marco\source\repos\workspace\respeaker-led-v3\.claude\worktrees\lefx-studio-lab-prompt-0f58f5`,
lokaler Branch `claude/lefx-studio-lab-prompt-0f58f5`, nur lokale Commits. Keine Pushes,
keine Remote-Branches, keine PRs. Der Codex-Worktree des Vorgängers wurde nur gelesen.

| Commit | Inhalt |
|---|---|
| `4325828` | Visueller Kern **unverändert** aus dem (dort uncommitteten) Codex-Worktree übernommen – nachvollziehbarer Ausgangsstand |
| `51a995d` | Studio Lab, Vorschau- und Schrittmodule, Ausgabe, Tests |
| `ba315ab` | Schrittbeschriftung, Statusaktualisierung der Ausgabe, Tastaturtest |
| (folgt) | dieser Bericht, Anleitung, Screenshots |

Pfade relativ zu `packages/led-controller-version-3-effect-creation/src/lefx/effect_creation/`:

* neu `visual/preview.py` – Vorschau-Snapshots, Kompilier-Cache, `PreviewPlan`
* neu `visual/steps.py` – Schrittpläne, Zählung verschiedener Bilder
* geändert `visual/compiler.py` – `verify_package()` (Paket mit `EffectLibrary` laden, Frames vergleichen)
* neu `studio/lab/__init__.py`, `clock.py`, `output.py`, `examples.py` (Qt-frei)
* neu `studio/lab/page.py`, `tree.py`, `inspector.py`, `timeline.py` (Qt)
* geändert `studio/ring.py` – `None` wird transparent gezeichnet statt `TypeError`; Ganzzahlen wie bisher
* geändert `studio/window.py` – Tab, Aktivierung/Deaktivierung, Gerätesignal, Schließen mit Rückfrage

Tests: neu `tests/authoring/test_visual_core.py`, `tests/studio/test_lab_output.py`,
`tests/studio/test_lab_page.py`; geändert `tests/architecture/test_architecture.py`
(`studio/lab/` und `visual/` unterliegen jetzt derselben Qt- und Schichtengrenze).

Nicht angefasst: Engine, SDK, Runtime-Layer-Semantik, Paketformat, bestehende Effekte,
sowie `blocks.py`, `kernel.py`, `model.py`, `editor.py`, `persistence.py` des Kerns.

## 3. Lokal starten

```powershell
cd C:\Users\marco\source\repos\workspace\respeaker-led-v3\.claude\worktrees\lefx-studio-lab-prompt-0f58f5
uv sync
uv run python scripts/build_effects.py      # Katalog für Player und Tests
uv run lefx-studio --project . --output null
```

Dann den Tab „Studio Lab (experimentell)“ öffnen. Für den ReSpeaker im Lab unter
„Ausgabe“ `respeaker` wählen und „An Ausgabe senden“ anhaken (vorher keinen
`lefx`-Dienst laufen lassen).

## 4. Prüfungen – tatsächlich ausgeführt

| Prüfung | Ergebnis |
|---|---|
| Baseline `uv run pytest -q` (nach `build_effects.py`, Qt offscreen, Kern bereits kopiert) | **1538 passed, 5 skipped, 0 failed** |
| Nach der Umsetzung, gleicher Befehl | **1616 passed, 5 skipped, 0 failed** |
| Davon neu | 52 Lab-/Kerntests, 6 Architekturtests, 20 automatische Legacy-Scans für die 10 neuen Quelldateien |
| `uv run lefx-studio --project . --self-check` | vollständig, 36 Definitionen, Ausgaben `null, respeaker, simulator` |
| Echter Start `uv run lefx-studio --project . --output null` unter Windows | Fenster geöffnet, keine Fehler im Log; per `CloseMainWindow` geschlossen → `service stopped` |
| Reale Hardware (reSpeaker XVF3800 angeschlossen, kein Dienst aktiv), Skript über den Lab-Pfad | Sink nach erstem Frame verfügbar; nach der Übernahme waren **alle** an den Sink gegangenen Frames Lab-Frames (davor nur Leerlauf-Schwarz); ein pausierter/gescrubbter Frame blieb 1 s stehen; globale Helligkeit 0,3 kam skaliert an (`ff3311` → `4c0f05`); Stopp → Ring schwarz |

Die sechs Fehler des Vorgängerlaufs traten hier nicht auf: Nach `build_effects.py` sind
die generierten Sets vorhanden.

**Nicht durchgeführt / Einschränkungen:**

* Die LEDs selbst habe ich nicht gesehen. Die Hardwareprüfung belegt, dass der Sink die
  richtigen Werte annahm, nicht, wie der Ring aussah – **bitte einmal mit eigenen Augen bestätigen**.
* Kein menschlicher Klick-Durchgang. Die fünf Abläufe sind offscreen über die echten
  Widgets automatisiert getestet (Buttons, Menüs, Felder, Lineal, Baum-Checkboxen, Tasten).
* Screenshots: offscreen mit echten Windows-Schriften gerendert (`QT_QPA_FONTDIR`),
  echte Widgets, aber kein Abfoto des Desktops.

## 5. Abdeckung der Mindestabläufe

| Ablauf | Status | Test |
|---|---|---|
| A Einfaches Projekt | erfüllt | `test_flow_a_layer_segment_properties_and_the_ring` |
| B Animierte Ebene | erfüllt | `test_flow_b_rotation_play_pause_and_seek` |
| C Mehrere Ebenen | erfüllt | `test_flow_c_two_layers_order_visibility_and_views` |
| D Bearbeitung/Wiederherstellung | erfüllt | `test_flow_d_undo_redo_save_and_load` |
| E LEFX-Export | erfüllt | `test_flow_e_export_validate_reload_and_compare`, `test_the_exported_package_is_accepted_and_renders_the_preview` |

Konzeptfälle aus §7 des Auftrags: 1, 2, 3 und 5 sind mit vorhandenen Bausteinen umsetzbar
(Beispiele). Fall 4 (inneres Farbmuster unabhängig von der Position) nur angenähert:
`color_cycle` verschiebt den Farbton der ganzen Ebene; ein im Segment wanderndes Muster ist
mit den heutigen Bausteinen nicht ausdrückbar. Es wurde **kein** neuer Bausteintyp ergänzt.

## 6. Offene technische Punkte

1. `RingMonitor` zeichnet den Gehäusekreis etwas größer als das Widget (Radius 0,51 der
   Kantenlänge); oben/unten wird er leicht abgeschnitten. Vorbestehend, auch im Player; nicht geändert.
2. „Ausgabe → Alles löschen“ während das Lab sendet entfernt den Feed; das Lab merkt das
   erst beim nächsten Registry-Wechsel oder erneutem Anhaken.
3. Die Lab-Übernahme beendet die Player-Wiedergabe; der Player zeigt danach nicht von
   selbst wieder seinen Effekt.
4. Das Gerät sieht höchstens die Engine-Rate (30 fps); das Lab rendert mit ~60 Hz.
5. Die Vorschau nutzt die Standard-Effektparameter (`speed` 1, `brightness` 1, `color` weiß,
   `reverse` aus). Exportparameter sind im Lab nicht durchspielbar.
6. Öffentliche Parameter (`exposures`) beherrschen Modell und Compiler; das Lab hat noch keine UI dafür.
7. Gruppen werden angezeigt, im Lab aber nicht angelegt. Kein Drag-and-drop im Baum.
8. Schrittpläne lesen die Zeitformeln des aktuellen Kernels nach (nur Zeitpunkte, keine
   Farben). Ändert sich der Kernel, müssen sie mitziehen; Tests sichern den heutigen Stand.
9. Undo-Granularität: Jeder SpinBox-Schritt ist ein eigener Undo-Eintrag.
10. Aus dem Vorgängerbericht bekannt und unverändert: Der bestehende Quelleditor tauscht
    bei seiner Vorschau `library._registry` aus. Das Lab nutzt diesen Weg nicht.
11. `verify_package` schließt die `EffectLibrary`; eine vollständige Freigabe aller vom
    Loader importierten Module wird nicht behauptet.

## 7. Bewusst provisorische Fachannahmen

* Baumreihenfolge wie in Grafikprogrammen: oben = im Bild oben, für Ebenen **und**
  Elemente (im Dokument liegen beide „unten zuerst“).
* „Gesamteffekt“ ist der Ort der Effektmetadaten; er ist weder Runtime-Layer noch Ebene.
* „Ebene isoliert“ zeigt die Ebene auch dann, wenn sie im Gesamteffekt ausgeblendet ist;
  unbedeckte Positionen erscheinen transparent.
* „Ebene hervorgehoben“: übrige Ebenen auf 22 % Helligkeit, reine Anzeige; an das Gerät
  geht in dieser Ansicht dasselbe Bild (was man sieht, leuchtet).
* Die Vorschau-Ringgröße ist eine Ansichtseinstellung, keine Entwurfseigenschaft.
* Schritte sind kein Bausteinvertrag: kein `total_positions`. Physische LED-Zahl,
  Schritte je Zyklus, Zahl verschiedener Bilder und Zeit werden getrennt angezeigt;
  „verschiedene Bilder“ wird auf ganzen gerenderten Frames gezählt.
* Stufenlose Animationen bekommen „Abtastpunkte“ (Standard 8 je Periode), keine Zustände.
* Lab-Ausgabe nur, solange der Lab-Tab sichtbar ist; die Übernahme löscht die Geräteausgabe des Players.
* Ein aus `.lefx` geöffneter Entwurf ist eine Kopie ohne Dateipfad.
* Neue Elemente erhalten reihum Farben aus einer kleinen Palette.

## 8. Ideen für die nächsten UI-Experimente

1. **Filmstreifen der Schritte:** alle Schritte eines Zyklus als Mini-Ringe nebeneinander –
   macht „12 Schritte, 2 Bilder“ auf einen Blick sichtbar.
2. **Direkte Manipulation am Ring:** LED anklicken setzt die Position des gewählten Elements
   (`RingMonitor.led_clicked` existiert bereits), Segmentenden ziehen.
3. **Öffentliche Parameter** per Rechtsklick am Feld freigeben, plus Testpanel für
   `speed`/`brightness`/`color` wie im späteren Player.
4. **Farbkollektionen** als Dialog bzw. Ressourcen-Tab; danach ein Stop-basierter
   Verlaufseditor als alternativer Inspektor für `gradient`.
5. **Spuren in der Zeitleiste** je Ebene mit den Perioden ihrer Animationen
   (Movie-Maker-Spuren), Schleifenbereich markieren.
6. **Experimenteller A/B-Musterbaustein** und ein segmentinternes Musterzyklus-Konzept für
   Konzeptfall 4 – erst nach fachlicher Klärung von Mustergröße vs. Ringposition.
7. Varianten nebeneinander vergleichen (zwei Entwürfe, zwei Ringe).
