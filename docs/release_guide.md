# Release- und Update-Anleitung

## Die beiden Repositories

| Repository | Aufgabe | Wer schreibt hinein? |
|---|---|---|
| [led_controller_respeaker-v3](https://github.com/marcosudau-vps/led_controller_respeaker-v3) | Entwicklung, Tests, Effektquellen, Studio, Build und öffentliche GitHub Releases | Entwicklung; Release-Skript und GitHub-Release-Workflow |
| [led-ctrl-v3](https://github.com/marcosudau-vps/led-ctrl-v3) | Ausschließlich der für PyPI benötigte Release-Baum | Automatisch durch sync-release-repo.yml |

Niemals manuell in das Release-Repository pushen oder taggen. Der Sync
materialisiert den Baum anhand von scripts/sync_release_tree.py. Die gebauten
.lefxset-Archive sind im Entwicklungsrepo Ausgabe, im Release-Repo Quelle.
Die Windows-EXE und die GitHub-Release-Assets verbleiben ausschließlich im
Entwicklungsrepo; sie werden nicht über den Release-Baum gespiegelt.

## Die drei Distributionen

Alle tragen dieselbe Versionsnummer und werden gemeinsam veröffentlicht.
tests/architecture/test_versions.py erzwingt die Übereinstimmung der Versionen
und der exakten internen Pins. Nur optionale Komponenten sind eigene Pakete.

| PyPI-Projekt | Rolle | Installation |
|---|---|---|
| led-controller-version-3 | SDK, Engine, API/CLI, reSpeaker und beide Effektkataloge | Standard |
| led-controller-version-3-device-simulated-respeaker | Software-Geräteersatz | [simulated-respeaker] |
| led-controller-version-3-effect-creation | lefx-pack und lefx-studio (Qt) | [effect-creation] |

Python-Importpfade heißen lefx.*. Python 3.12 ist die unterstützte Version.
Schichtgrenzen werden durch die Architekturtests geprüft.

## 1. Normales Code-Update (ohne Veröffentlichung)

```bash
uv run python scripts/build_effects.py
uv run pytest -q -m "not hardware"
git add <betroffene-Dateien>
git commit -m "fix: Beschreibung der Änderung"
git push origin main
```

Alternativ per Feature-Branch und PR. CI baut und prüft bereits die Wheels und
die Windows-Studio-EXE als interne Workflow-Artefakte. Ohne Tag entstehen
weder ein öffentliches GitHub Release noch eine PyPI-Veröffentlichung.

## 2. Offizielles Release

In einem sauberen, aktuellen Main-Checkout, mit uv, git und authentifiziertem gh:

```bash
uv sync
uv run python scripts/release.py
```

Das Skript fragt nach Version und Bestätigung. Ist die aktuelle Version bereits
getaggt, wird die nächste Patchversion vorgeschlagen; andernfalls die noch
unveröffentlichte aktuelle Version. Mit --version X.Y.Z kann sie explizit gewählt
werden. Nur bestätigen, wenn wirklich veröffentlicht werden soll.

### Verbindliche Reihenfolge

| Schritt | Prüfung bzw. Aktion |
|---|---|
| 1 | Sauberer Main-Checkout, HEAD exakt origin/main; Tag in beiden Repos und Version in allen drei PyPI-Projekten frei |
| 2 | Effektkataloge neu bauen |
| 3 | Gesamte hardwarefreie Testsuite |
| 4 | check_release.py: alle Pakete bauen, in eine leere Umgebung installieren und benutzen |
| 5 | Versionsbump in alle vier pyproject.toml inklusive exakter interner Pins, uv.lock synchronisieren |
| 6 | Versionskonsistenz erneut prüfen; Release-Commit und Push |
| 7 | CI des exakten main-Push-Commits abwarten: Linux-Tests, Paket- und Release-Baum-Checks, Windows-PyInstaller-Build, EXE-Self-Checks |
| 8 | Alle drei Wheels und die Studio-EXE aus genau diesem CI-Lauf herunterladen, Versions-/Commit-Zuordnung, Dateinamen und SHA-256 prüfen |
| 9 | origin/main, Arbeitsbaum und freie Version erneut prüfen; erst dann annotierten Tag setzen und pushen |

**Ein Versionsbump im Arbeitsbaum oder ein Release-Commit verbraucht noch
keine PyPI-Version.** Scheitern lokale Prüfungen, CI, Windows-Build oder
Artefaktprüfung, wird kein Tag gesetzt. Nach Behebung kann dieselbe noch
unveröffentlichte Version mit --version X.Y.Z wieder verwendet werden.
Ein Umgehen der CI-Schranke per --skip-ci ist nicht mehr vorgesehen.

Der Linux-CI-Job baut außerdem den materialisierten Release-Baum und prüft
dessen Installierbarkeit. Der Windows-CI-Job baut die Onefile-EXE aus demselben
Commit, prüft den realen eingefrorenen Build, Effektkatalog und Output-Entry-
Points mit --self-check sowie den Qt-Start mit --gui-self-check (null output,
automatisches Schließen). Das ist kein Hardwaretest und keine manuelle UX-Abnahme.
Die Versionsnummer im EXE-Namen stammt aus der Root-Projektversion.

### Vorher hineinsehen

```bash
uv run python scripts/release.py --dry-run --version 3.0.4
```

Prüft Voraussetzungen und führt die lokalen Katalog-, Test- und Paketprüfungen
mit dem aktuellen Versionsstand aus. Schreibt keine neue Version, keinen Commit
und keinen Tag. Der Windows-CI-Build der Zielversion gehört zum regulären
Release-Commit-CI, nicht zum lokalen Dry-Run.

Release-Baum lokal ansehen:

```bash
uv run python scripts/build_effects.py
uv run python scripts/sync_release_tree.py --target ../release_preview
```

Ein manueller Sync ohne Tag spiegelt main ins Release-Repo, ohne PyPI-Publish:

```bash
gh workflow run sync-release-repo.yml --repo marcosudau-vps/led_controller_respeaker-v3 --ref main
```

Das optionale Feld tag leer lassen. Ein solcher Sync verändert bereits das
Release-Repo; für die gewöhnliche Release-Vorprüfung ist er nicht erforderlich.
Bei Wiederholung eines getaggten Sync-Laufs den vorhandenen Entwicklungstag
als Workflow-Ref wählen. Keinen freien Tagname auf main angeben.

## 3. Nach dem Tag: zwei getrennte Veröffentlichungswege

### A. Öffentliches GitHub Release im Entwicklungsrepository

github-release.yml lädt die CI-Artefakte des exakten getaggten Main-Commits
herunter, prüft die Manifeste (Commit, Version, Namen, Größe, SHA-256) erneut
und erzeugt ein GitHub Release als Draft. Die vier Dateien werden hochgeladen
und die Remote-Digests bzw. heruntergeladenen Uploads geprüft. Erst danach
wird der Draft veröffentlicht. Es wird nicht nach dem Tag neu kompiliert.

Beispiel für 3.0.4:

- led_controller_version_3-3.0.4-py3-none-any.whl
- led_controller_version_3_effect_creation-3.0.4-py3-none-any.whl
- led_controller_version_3_device_simulated_respeaker-3.0.4-py3-none-any.whl
- lefx-studio-3.0.4-windows-x64.exe

Die Wheels gehören zusammen und sind auf exakt dieselbe Version gepinnt.
Die Studio-EXE ist der portable PyInstaller-Onefile-Build für Windows x64.
Das vorhandene Studio-Projektmodell gilt weiterhin: mit --project auf den
gewünschten Checkout bzw. Effektkatalog zeigen. Kein Installer, keine
mitgelieferten Projektquellen in der EXE. Automatische GitHub-Quellarchive
sind zusätzlich wie gewohnt vorhanden.

Öffentliche Releases:
https://github.com/marcosudau-vps/led_controller_respeaker-v3/releases

### B. PyPI-Veröffentlichung über das Release-Repository

1. sync-release-repo.yml (Entwicklungsrepo) prüft den getaggten Commit und
   dessen erfolgreiche CI-Artefakte erneut, baut die Kataloge und
   materialisiert den Release-Baum.
2. Via RELEASE_REPO_DEPLOY_KEY wird das Release-Repo ausgecheckt,
   der neue Baum nach main gepusht und derselbe Tag auf dessen eigenen
   Release-Commit gesetzt. Die Commit-SHAs beider Repos sind unterschiedlich.
3. release.yml (Release-Repo) prüft Repository und Tag, baut Wheels und sdists,
   prüft die Installation und stellt die Distributionsartefakte für den Upload
   bereit.
4. Drei getrennte Publish-Jobs veröffentlichen die PyPI-Pakete über Trusted
   Publishing (OIDC). Das Release-Repo erstellt kein GitHub Release mit EXE.
   Ein Job pro Projekt, eigene Environments, max-parallel: 1, skip-existing: true.

Beide Wege sind erst nach ihren erfolgreichen Workflows vollständig
abgeschlossen. Der lokale Release-Befehl bestätigt zunächst den gepushten Tag,
nicht automatisch die abgeschlossenen Veröffentlichungen. Prüfen:

```bash
gh run list --workflow github-release.yml --limit 3
gh run list --workflow sync-release-repo.yml --limit 3
gh run list --repo marcosudau-vps/led-ctrl-v3 --workflow release.yml --limit 3
gh release view v3.0.4
```

Zusätzlich alle drei Versionen auf PyPI prüfen und in einer frischen
Python-3.12-Umgebung installieren. Nicht ungeprüft produktive Installationen
aktualisieren.

## 4. Fehlerbehandlung

- Fehler vor dem Tag: nicht taggen. Beheben, CI erneut ausführen und dieselbe
  noch unveröffentlichte Version verwenden. Wenn der Release-Commit schon
  auf main liegt, den Release-Befehl explizit mit derselben Version starten.
- Fehler beim GitHub-Asset-Upload: Release bleibt Draft; fehlgeschlagenen
  Workflow erneut starten. Ein bereits öffentliches Release wird nicht
  überschrieben, sondern nur verifiziert. CI-Artefakte werden 90 Tage
  aufbewahrt. Nach Ablauf muss derselbe CI-Lauf am selben Commit erneut
  vollständig ausgeführt und geprüft werden.
- Fehler beim Sync: Workflow am bestehenden Entwicklungstag wiederholen.
  Falls der Tag im Release-Repo bereits korrekt gesetzt wurde, dort den
  PyPI-Workflow wiederholen statt erneut zu taggen.
- Fehler bei PyPI: fehlgeschlagene Jobs desselben Release-Laufs erneut
  ausführen; skip-existing schützt bereits hochgeladene Dateien. Keine neue
  Version oder neuen Tag nur für die Wiederholung erzeugen.
- 429 beim Anlegen neuer Projekte: PyPI beschränkt die Anzahl neuer Projekte
  pro Konto und Tag. Bestehende Projekte sind davon nicht betroffen. Bei
  einem solchen Fehler den fehlenden Upload nach Ablauf des Kontingents
  wiederholen; bereits erfolgreiche Uploads bleiben erhalten.
- 403 bei Trusted Publishing: Repository, Workflow und Environment mit den
  Publisher-Einstellungen auf PyPI abgleichen. Keine Tokens als Workaround
  im Repository speichern.

Ein erfolgreicher Testlauf reduziert Buildfehler vor der Tagvergabe. Externe
Dienststörungen, Deploy-Key-, Berechtigungs- oder Uploadfehler nach dem Tag
lassen sich nicht ausschließen; sie sind durch Wiederholung der betroffenen
Workflows zu behandeln, ohne die Version neu zu vergeben.

## 5. Einmalige Einrichtung

### Release-Repository und Deploy-Key

Das Release-Repository benötigt mindestens einen initialen Commit und main.
Der maschinelle Sync überschreibt den Release-Baum. Für ein neues Repository:

1. Initialen README-Commit anlegen.
2. Separates Ed25519-Schlüsselpaar für den Sync erzeugen.
3. Öffentlichen Schlüssel im Release-Repo unter Settings / Deploy keys
   mit Schreibberechtigung hinterlegen.
4. Privaten Schlüssel als Actions-Secret RELEASE_REPO_DEPLOY_KEY im
   Entwicklungsrepo hinterlegen; lokale temporäre Schlüsseldateien sicher
   entfernen. Kein Schlüssel im Repository.
5. Der eingebaute GITHUB_TOKEN reicht für den Cross-Repository-Push nicht aus.

Der GitHub-Release-Workflow schreibt nur in das Entwicklungsrepo und verwendet
dessen eingebauten Token mit contents: write und actions: read; kein zusätzlicher
Deploy-Key oder PyPI-Token erforderlich.

### PyPI Trusted Publishing

Je PyPI-Projekt ein eigenes Environment im Release-Repo:

| PyPI-Projekt | Environment |
|---|---|
| led-controller-version-3 | pypi |
| led-controller-version-3-effect-creation | pypi-effect-creation |
| led-controller-version-3-device-simulated-respeaker | pypi-simulator |

Gemeinsame Publisher-Felder: Owner marcosudau-vps, Repository led-ctrl-v3,
Workflow release.yml. Das Environment muss zur Matrix des Workflows passen.
Bei bestehendem Projekt unter Manage project / Publishing einen Trusted
Publisher einrichten; bei neuem Projektnamen Pending Publisher im Konto.
Ein Pending Publisher gilt nur für einen noch freien Namen und kann nicht
bearbeitet werden (löschen und neu anlegen). Nur der Projekt-Owner kann
Publisher hinzufügen. OIDC verwendet kurzlebige Upload-Tokens, kein
dauerhaftes PyPI-Passwort. Unterschiedliche Projekt-Owner sind möglich;
Publikationsrechte müssen für jedes Projekt separat verwaltet werden.

### Künftige zusätzliche Distributionen

Ein zusätzliches Paket benötigt getrennte Prüfung von Workspace, Lockfile,
Versions-/Architekturtests, check_release.py, Asset-Manifest, Release-Workflow-
Matrix, optionalen Extras und PyPI-Publisher. Die bloße Existenz eines neuen
Paketordners genügt nicht. Der Configurator ist in dieser dreiteiligen
Release-Strecke noch nicht enthalten.
