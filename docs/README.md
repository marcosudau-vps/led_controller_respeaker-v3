# Dokumentation — Gliederung

> **Status: Vorschlag.** Diese Seite ist die geplante Struktur, noch nicht die
> fertige Doku. Geschrieben ist bisher nur [index.md](index.md). Die Tabellen
> unten sagen pro Kapitel, was neu entsteht und was aus der V2-Doku übernommen
> werden kann.

Die V2-Doku war ein flacher Lauf aus zwölf Kapiteln, weil es *ein* System gab.
V3 zerfällt in Dinge, die verschiedene Leute an verschiedenen Tagen tun:
Effekte schreiben, den Dienst betreiben, darauf aufbauen, am System selbst
arbeiten. Die Gliederung folgt diesen Tätigkeiten — und weil die Paketgrenzen
genau entlang dieser Tätigkeiten geschnitten sind, deckt sie die Pakete
nebenbei mit ab.

---

## Einstieg

| | Seite | Inhalt |
|---|---|---|
| — | [index.md](index.md) | Das System auf einen Blick: sieben Pakete, ihre Rollen, die Pfade eines Frames und einer Richtung. **Fertig.** |

---

## Teil I — Konzepte

*Das mentale Modell. Paketunabhängig, einmal lesen und dann selten wieder.*

| # | Kapitel | Inhalt | Herkunft |
|---|---|---|---|
| 01 | `konzepte/01-grundidee.md` | Warum die Effektlogik von der Anwendung getrennt ist, was ein Effekt kennt und was nicht, das Grundmodell in fünf Absätzen | V2 `01_overview` — kürzen, der Systemüberblick steht jetzt in `index.md` |
| 02 | `konzepte/02-layer-und-komposition.md` | LED-Frame, der Fünferstapel, Prioritäten, opaque/transparent, `None` ≠ Schwarz, Kompositionsablauf | V2 `03` — **weitgehend übernehmbar**, nur die Scene/Visual-Indirektion streichen |
| 03 | `konzepte/03-lebenszyklusformen.md` | State, Controlled Overlay, Timed Overlay, Event: Vergleich, Entscheidungshilfe, Verläufe | V2 `04` — Substanz bleibt, Mechanik neu (der Typ *ist* jetzt die Klasse) |

---

## Teil II — Effekte schreiben

*Der Autorenpfad und der meistgelesene Teil. Dokumentiert `lefx-sdk` und `lefx-authoring`.*

| # | Kapitel | Inhalt | Herkunft |
|---|---|---|---|
| 04 | `effekte/04-definitionsschema.md` | Die vier typspezifischen Definitionsklassen, `slots`/`restorable`, `duration_field`, `sampling`. Warum `layer_rules` und `capabilities` weg sind. **Die Zulässigkeitsmatrix als Tabelle.** Validierung in `__post_init__` | V2 `05` — **größter Umbau**, das Objektmodell ist ein anderes |
| 05 | `effekte/05-parameter-und-werte.md` | Wertetypen, Normalisierung, freundliche Eingabeformen, Farbmodelle, Aliase, reservierte Namen, Grenzen und Fehler | V2 `06` — **fast unverändert übernehmbar**, die Normalisierung wurde 1:1 portiert |
| 06 | `effekte/06-runtime-eingaben.md` | Konfiguration vs. Laufzeitwerte, Channel, Push und Pull, `provider_id` als *Fähigkeit*, Health, Karenzzeit, `None` | V2 `07` — übernehmen, DoA-Teil wandert nach Kapitel 13 |
| 07 | `effekte/07-effekt-schreiben.md` | Durchgehendes Beispiel: Gerüst, Definition, `render`, Presets, prüfen, bauen. Mit `lefx-pack` und mit dem Studio | **neu** (in V2 lag das in einem eigenen Ordner `effect-development/`) |
| 08 | `effekte/08-pakete-und-sets.md` | Quelle vs. Paket, Anatomie, `lefx/3` und `lefxset/3`, ID-Arten, globale Eindeutigkeit, Presets, Registry und Discovery, Integrität | V2 `08` — übernehmen, Stempel und Import-Whitelist aktualisieren |
| 09 | `effekte/09-validieren-und-bauen.md` | Die Qualitätskette, Quellenvalidierung, Import-Autarkie, Smoke-Render, Set-Build, typische harte Fehler | V2 `10` — übernehmen, Werkzeugnamen anpassen |

---

## Teil III — Betreiben

*Den Dienst laufen lassen und steuern. Dokumentiert `lefx-interfaces` und die beiden Gerätepakete.*

| # | Kapitel | Inhalt | Herkunft |
|---|---|---|---|
| 10 | `betrieb/10-cli-und-api.md` | Verben und Endpunkte vollständig, Aktivierungsmodi, Lesen, **Ausgabeeinstellungen, Statusabfrage und Paketquellen-Verwaltung** | V2 `09` — übernehmen und **deutlich erweitern**, drei Bereiche fehlten komplett |
| 11 | `betrieb/11-status-und-lebenszyklus.md` | Was `/status` sagt, Input-Health, Sink-Verfügbarkeit, Service-Events, Persistenz des Background-States, Start und Stopp, Instanzdatei | **neu** |
| 12 | `betrieb/12-geraete.md` | Die SDK-Ports, Entry Points, Gerätewahl, Hardware und Simulator im Vergleich, Verbindungsverlust und Wiederkehr, warum die Engine kein Gerät kennt | **neu** |
| 13 | `betrieb/13-richtung-und-kalibrierung.md` | DoA von der Messung zum Marker, Fähigkeitsname `doa`, Halb-LED-Sektoren, Montagewinkel, `doa_calibration.json`, Kalibrieren mit dem Studio | **neu** (Reste aus V2 `07`) |

---

## Teil IV — Einbetten und erweitern

*Auf dem System aufbauen, statt es zu bedienen. Das Zielszenario für eine Veröffentlichung.*

| # | Kapitel | Inhalt | Herkunft |
|---|---|---|---|
| 14 | `einbetten/14-controllerservice.md` | `ControllerService` als Bibliothek: Konstruktion, eigener Sink als Objekt, Frames mitlesen, Renderloop, Statusereignisse, was Vertrag ist und was nicht | **neu** |
| 15 | `einbetten/15-eigenes-geraet.md` | Ein drittes Gerät anbinden: Ports erfüllen, Entry Points deklarieren, die gemeinsame Konformitätssuite bestehen | **neu** |

---

## Teil V — Studio

| # | Kapitel | Inhalt | Herkunft |
|---|---|---|---|
| 16 | `studio/16-studio.md` | Die drei Seiten, Projektbegriff, Ausgabewahl, Presets kuratieren, neue Quellen entwerfen, Standalone-Build | **neu** |

---

## Teil VI — Am System selbst arbeiten

*Für Beitragende.*

| # | Kapitel | Inhalt | Herkunft |
|---|---|---|---|
| 17 | `entwicklung/17-paketgrenzen.md` | Die Abhängigkeitsmatrix, warum Entry Points die Mechanik sind, wie der Architekturtest sie erzwingt, Prüffragen für neue Logik | V2 `11` — Substanz neu (Distributionen statt Module) |
| 18 | `entwicklung/18-tests.md` | Die Ebenen: Schema, Katalog, Runtime, API, Gerätevertrag über beide Geräte, Architektur, Legacy. Hardware-Marker | **neu** |
| 19 | `entwicklung/19-release-und-versionierung.md` | Paket-Build, Installations-Smoke-Test, CI, **Versionierungs- und Deprecation-Regel: kein stiller Kompatibilitätsmodus** | **neu** |

---

## Referenz

| # | Kapitel | Inhalt | Herkunft |
|---|---|---|---|
| 20 | `referenz/20-fehler.md` | Fehlerformat, Fehlercodes (`target_not_found`, `ambiguous_target`, `validation_failed`, …), die Ausnahmehierarchie, HTTP-Zuordnung | **neu** |
| 21 | `referenz/21-glossar.md` | Alle Begriffe an einer Stelle | V2 `02` — umbauen zum Nachschlagewerk statt Lesekapitel |

---

## Was aus V2 nicht mitkommt

- **`12_status_and_outlook`** — die V1-Altlastenliste ist mit dem Fork erledigt,
  und ein Ausblick gehört in `PLAN.md`, nicht in eine Referenz.
- **Die Trennung `effect-system/` und `effect-development/`** — die
  Schritt-für-Schritt-Anleitung wird Kapitel 07 und steht damit dort, wo man
  sie sucht.
- **Alle `src.core.*`-Importpfade** — heißen jetzt `lefx.sdk.*`.

## Zwei Konventionen

**Durchlaufende Nummern über Ordnergrenzen.** Damit „siehe Kapitel 12" eindeutig
bleibt und die Lesereihenfolge im Dateinamen steht. Preis: ein eingeschobenes
Kapitel nummeriert die folgenden um.

**Deutsche Prosa, englischer Code.** Wie `index.md`, `PLAN.md` und `HANDOFF.md`
es schon halten. Bezeichner, Fehlermeldungen und Docstrings bleiben englisch.
