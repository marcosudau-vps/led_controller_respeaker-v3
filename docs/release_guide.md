# Release- und Update-Anleitung – serverseitiger Patch Release

## Start

Das Entwicklungsrepository ist die einzige Stelle, an der ein neuer Release
gestartet wird:

https://github.com/marcosudau-vps/led_controller_respeaker-v3/actions/workflows/patch-release.yml

Actions → Patch Release → Run workflow → main → Run workflow.
Keine Versionsangabe, keine lokale Umgebung, keine weitere Bestätigung nötig.
Alternativ authentifizierter GitHub CLI:

```bash
gh workflow run patch-release.yml --repo marcosudau-vps/led_controller_respeaker-v3 --ref main
```

Der frühere lokale Einstieg `uv run python scripts/release.py` dispatcht nur
noch diesen Workflow. `--dry-run` ist weiterhin eine optionale lokale
Entwicklerprüfung ohne Veröffentlichung. Die alte lokale Tagvergabe und die
separaten Tag-Push-Workflows im Entwicklungsrepo entfallen.

## Versionsverwaltung

Der Workflow liest die numerisch höchste veröffentlichte Versionsmarke,
prüft, dass main auf dieser Version oder ihrem noch unveröffentlichten
nächsten Patch steht, und erhöht die Patch-Komponente. Beispiel: 3.0.3 →
3.0.4. Minor-/Major-Workflows sind noch nicht Bestandteil der Implementierung.
Root- und Paket-pyproject.toml, exakte interne Pins und uv.lock werden
konsistent aktualisiert. Der Bot pusht zunächst nur einen unveränderlichen
Kandidatencommit unter release-candidate/<run-id>. main bleibt bis zum
bestandenen Gate unverändert.

Der nächste normale Start ist blockiert, falls eine bereits getaggte Version
noch nicht vollständig veröffentlicht wurde. Bei neuen serverseitigen Releases
muss der verknüpfte vorherige Workflow erfolgreich beendet sein oder eine
erfolgreiche, exakt daran gebundene Wiederherstellungsverifikation vorliegen; das GitHub
Release öffentlich sein und alle zum Releasevertrag gehörenden Projekte müssen
auf PyPI exakt die erwarteten Dateien besitzen. Das bereits veröffentlichte v3.0.4 wird anhand der
ursprünglichen Tags, dem Original-Run und drei PyPI-Projekten geprüft. Releases sind serialisiert.

## Verbindlicher Ablauf

| Schritt | Ausführung |
|---|---|
| 1 | GitHub-Runner: main prüfen, nächste Patch-Version ermitteln, freie Version/Tags und vorherigen Release prüfen |
| 2 | Versionsbump, Pins und Lockfile, Kandidatencommit auf temporärem Branch |
| 3 | Reusable CI am exakten Kandidaten-SHA: Linux-Tests, Paketgrenzen, Kataloge, Paketbau und Installationsprüfung |
| 4 | Windows-Runner: hardwarefreie Testsuite, portabler Studio-Onefile-Build, Frozen-Self-Check und automatischer GUI-Start |
| 5 | PyPI-Release-Baum materialisieren, daraus vier Wheels und vier Sdists bauen und installieren; exakt diese geprüften Dateien und den Baum als versiegeltes Bundle sichern |
| 6 | Bundle und Windows-EXE herunterladen; SHA-256, Größe, Version und Commit prüfen; Schreibzugriff auf Release-Repo mit SSH-Deploy-Key und Dry-Run prüfen |
| 7 | Main nochmals auf unveränderten Ausgangsstand prüfen, freie Version erneut prüfen; main und annotierten Versionstag gemeinsam per atomarem Git-Push aktualisieren |
| 8 | Öffentliches GitHub Release: Draft erstellen, vier Wheels, vier Sdists und versionierte Studio-EXE hochladen, Remote-Digests verifizieren, veröffentlichen |
| 9 | Exakt geprüften Release-Baum samt Manifest per SSH in das PyPI-Repository übertragen, dort main und Tag atomar pushen |
| 10 | Release-Repo lädt ausschließlich die acht vorher geprüften Distributionsdateien aus dem öffentlichen Entwicklungs-GitHub-Release herunter, prüft Manifest und lädt sie per Trusted Publishing auf PyPI |
| 11 | Entwicklungsworkflow wartet auf erfolgreichen Workflow am exakten Release-Repo-Tag, prüft Größe und SHA-256 aller acht PyPI-Dateien, installiert die neue Version in frischer Umgebung und erstellt die Abschlusszusammenfassung |

Es gibt keine erneute Kompilierung nach dem Tag. Der normale Release
verwendet keinen lokalen PC und kein --skip-ci. Ein automatisierter
GitHub-Token-Push löst normalerweise keine anderen Push-Workflows desselben
Repos aus: deshalb werden alle Entwicklungsschritte ausdrücklich durch
patch-release.yml orchestriert. Der separate SSH-Push löst release.yml im
Release-Repo aus. Kein zusätzliches persönliches Access-Token notwendig.

Ein Windows-EXE-Build ist keine Hardwareabnahme. Die Studio-EXE ist
portabel, Windows x64, PyInstaller Onefile; das vorhandene Studio-Projektmodell
(--project) bleibt erhalten.

## Download-Artefakte

Das veröffentlichte 3.0.4 enthält sieben Assets:
- lefx-studio-3.0.4-windows-x64.exe
- led_controller_version_3-3.0.4-py3-none-any.whl
- led_controller_version_3_effect_creation-3.0.4-py3-none-any.whl
- led_controller_version_3_device_simulated_respeaker-3.0.4-py3-none-any.whl
- die drei zugehörigen .tar.gz Source-Distributionen

Ab dem ersten gemeinsamen Release mit Configurator kommen
`lefx_config_widget-<version>-py3-none-any.whl` und
`lefx_config_widget-<version>.tar.gz` hinzu. Daraus ergeben sich neun
öffentliche GitHub-Assets. Die Studio-EXE bleibt das einzige Windows-Executable-Asset.

`scripts/release_contract.py` definiert die vier Distributionen, die Dateinamen
und die Publisher-Environments. Der Mirror erhält dieselbe Datei und liest die
Veröffentlichungsmatrix daraus. Seine Tag-Annotation bindet den
Entwicklungscommit an das versiegelte Manifest.

Die sdists sind bewusst ebenfalls öffentliche Release-Assets, damit das
PyPI-Repo dieselben vorab geprüften Bytes statt eines erneuten Builds
verwendet. Der versiegelte Release-Baum und die Manifeste bleiben interne
CI-Artefakte (90 Tage). Das PyPI-Repo enthält nur den erzeugten Quellbaum,
das Manifest und den PyPI-Workflow, keine Studio-EXE und keine GitHub Releases.

## Fehlerbehandlung

Die abschließende PyPI-Installation verwendet keinen uv-Cache, ignoriert
lokale Index-Konfigurationen, nutzt explizit https://pypi.org/simple und
wiederholt Installationsfehler bis zu viermal in frischen Umgebungen.

Wenn der historische Abschlussjob selbst fehlerhaft ist, auf main den
Workflow **Verify Published Release** mit der bereits veröffentlichten
Version starten (z.B. 3.0.4). Er prüft beide Tags, die erfolgreichen
ursprünglichen Prüf-/Publish-Jobs, die exakten Dateien aus dem Original-CI-Lauf
gegen GitHub, das gespiegelte Manifest, den PyPI-Workflow und die Dateihashes.
Danach installiert er frisch und prüft die Einstiegspunkte für den jeweiligen
Releasevertrag. Die neue Distribution wird dabei zusätzlich über
`lefx-config-widget --smoke` gestartet. Für v3.0.4 gilt die fest gebundene
Identität aus Entwicklungs- und Mirror-Commit sowie Original-Run 45854688359.
Der Recovery-Workflow hat reine Leserechte. Ein erfolgreicher Recovery-Job
für exakt Version, Commit und ursprünglichen Run gilt für die nächste
Patch-Freigabe als Abschlussnachweis. Die Original-Artefakte müssen
noch verfügbar sein.


- Vor dem Tag: main/Versionsnummer bleiben unverändert. Fehler beheben,
  Workflow neu starten; dieselbe Patch-Version wird wieder gewählt.
- Nach dem Tag: keine neue Version vergeben, keine Tags verschieben.
  Ausschließlich fehlgeschlagene Jobs des vorhandenen Patch-Release-Runs
  erneut ausführen (Re-run failed jobs, NICHT Re-run all jobs). Ein vollständiger
  Rerun nach dem Tag wird bewusst abgelehnt, damit keine geprüften Dateien
  durch neue Builds ersetzt werden.
- Ein fehlgeschlagener GitHub-Upload bleibt Draft, derselbe Publish-Job
  kann fortgesetzt werden. Ein öffentliches Release wird nur verifiziert,
  nicht überschrieben. SSH-Mirror ist auf Source-SHA und Manifest gebunden.
- Bei PyPI-Fehler den fehlgeschlagenen Job im Release-Repo erneut ausführen,
  danach den Verify-Job des Entwicklungsworkflows wiederholen. Bereits
  publizierte Dateien werden nicht überschrieben (skip-existing); die
  abschließende Digestprüfung erkennt abweichende Dateien.
- Nach Ablauf der internen Artefakte nicht blind neu bauen oder taggen.
  Bereits veröffentlichte unveränderliche Dateien und das Manifest prüfen;
  gegebenenfalls ist eine gezielte Wiederherstellung nötig.
- Candidate-Branches bleiben als Nachweis erhalten und können nach Prüfung
  erfolgreicher Releases bei Bedarf gelöscht werden. Kein Force-Push.

Externe Dienststörungen, Kontingente, Berechtigungsänderungen oder ein
OIDC-Fehler lassen sich nicht vorab vollständig ausschließen. Der Deploy-Key
wird vor dem Tag getestet; tatsächliches Trusted Publishing wird erst im
Veröffentlichungsrepo bestätigt. Der Entwicklungsworkflow meldet erst nach
beiden Publikationswegen und Installation Erfolg.

## Repositorys und Einrichtung

Entwicklung: https://github.com/marcosudau-vps/led_controller_respeaker-v3
Veröffentlichung: https://github.com/marcosudau-vps/led-ctrl-v3

Das Veröffentlichungsrepo wird niemals von Hand verändert. Das
Entwicklungsrepo benötigt den vorhandenen Secret RELEASE_REPO_DEPLOY_KEY
(Schreibzugriff auf das Release-Repo) und für die Release-Jobs
contents: write sowie actions: read des eingebauten GITHUB_TOKEN.
Eventuelle Branch-/Tag-Rulesets müssen diese autorisierte Bot-Aktion
erlauben; keine Schutzregel automatisch abschalten.

Die Trusted Publisher verwenden Owner `marcosudau-vps`, Repository
`led-ctrl-v3` und Workflow-Datei `release.yml`.

| Projekt | Environment |
|---|---|
| led-controller-version-3 | pypi |
| led-controller-version-3-effect-creation | pypi-effect-creation |
| led-controller-version-3-device-simulated-respeaker | pypi-simulator |
| lefx-config-widget | pypi-configurator |

Der Publish-Job verwendet `id-token: write` und `max-parallel: 1`. Die
Kontoinhaber richten den neuen Eintrag einmalig vor der ersten Freigabe ein.

1. Im GitHub-Repository `marcosudau-vps/led-ctrl-v3` unter **Settings → Environments**
   das Environment `pypi-configurator` anlegen und die für Release-Tags vorgesehenen
   Freigabe- und Tagregeln anwenden.
2. Auf PyPI als berechtigter Kontoinhaber unter **Your account → Publishing**
   einen neuen ausstehenden GitHub-Trusted-Publisher anlegen. Ist das Projekt
   bereits im eigenen Besitz, die Publishing-Seite des Projekts verwenden.
   [Neues PyPI-Projekt per Trusted Publishing](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
3. Projektname `lefx-config-widget`, Owner `marcosudau-vps`, Repository
   `led-ctrl-v3`, Workflow-Datei `release.yml`, Environment `pypi-configurator`
   eintragen und die Zuordnung speichern. Der erste erfolgreich autorisierte
   Upload aktiviert den ausstehenden Publisher.
4. Die bestehenden drei Einträge beibehalten. Der Mirror braucht für das neue
   Projekt dieselben OIDC-Rechte wie für die bisherigen Projekte. Die Pipeline
   verwendet keinen dauerhaften Upload-Token.

Der Entwicklungsstand bleibt gemeinsam auf 3.0.4. Ein lokaler Patch-Kandidat
dient der Generalprobe. Über die tatsächliche Versionsnummer und die mögliche
Minor-Einstufung der neuen optionalen Distribution entscheidet die
Releasefreigabe. Der bestehende Workflow unterstützt automatische Patch-Releases.

## Reguläre Entwicklung

Branch und PR verwenden dieselben lesenden CI-Prüfjobs. Ein Release entsteht
über den separat gestarteten Patch-Workflow auf main.

Die Paketprüfung baut die vier Distributionen und installiert sie in getrennten
Umgebungen. Sie prüft Kern-only, Simulator ohne Qt, jedes Extra einzeln, direkte
Configurator-Installation und `[all]`. Bei jeder Installation prüft sie Version
und Herkunft der lokalen Wheels. Die vollständige Root-Testsuite erfasst auch den
Configurator; der Windows-Gate behält beide Studio-Selfchecks bei.
