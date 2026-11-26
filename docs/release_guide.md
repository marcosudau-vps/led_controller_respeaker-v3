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
muss der verknüpfte vorherige Workflow erfolgreich beendet sein, das GitHub
Release öffentlich sein und alle drei Projekte müssen die erwarteten Dateien
auf PyPI besitzen. Historische Releases ohne GitHub Release werden anhand der
beiden Tags und der drei PyPI-Projekte geprüft. Releases sind serialisiert.

## Verbindlicher Ablauf

| Schritt | Ausführung |
|---|---|
| 1 | GitHub-Runner: main prüfen, nächste Patch-Version ermitteln, freie Version/Tags und vorherigen Release prüfen |
| 2 | Versionsbump, Pins und Lockfile, Kandidatencommit auf temporärem Branch |
| 3 | Reusable CI am exakten Kandidaten-SHA: Linux-Tests, Paketgrenzen, Kataloge, Paketbau und Installationsprüfung |
| 4 | Windows-Runner: hardwarefreie Testsuite, portabler Studio-Onefile-Build, Frozen-Self-Check und automatischer GUI-Start |
| 5 | PyPI-Release-Baum materialisieren, daraus drei Wheels und drei sdists bauen und installieren; exakt diese geprüften Dateien und den Baum als versiegeltes Bundle sichern |
| 6 | Bundle und Windows-EXE herunterladen; SHA-256, Größe, Version und Commit prüfen; Schreibzugriff auf Release-Repo mit SSH-Deploy-Key und Dry-Run prüfen |
| 7 | Main nochmals auf unveränderten Ausgangsstand prüfen, freie Version erneut prüfen; main und annotierten Versionstag gemeinsam per atomarem Git-Push aktualisieren |
| 8 | Öffentliches GitHub Release: Draft erstellen, drei Wheels, drei sdists und versionierte Studio-EXE hochladen, Remote-Digests verifizieren, veröffentlichen |
| 9 | Exakt geprüften Release-Baum samt Manifest per SSH in das PyPI-Repository übertragen, dort main und Tag atomar pushen |
| 10 | Release-Repo lädt ausschließlich die sechs vorher geprüften Distributionsdateien aus dem öffentlichen Entwicklungs-GitHub-Release herunter, prüft Manifest und lädt sie per Trusted Publishing auf PyPI |
| 11 | Entwicklungsworkflow wartet auf erfolgreichen Workflow am exakten Release-Repo-Tag, prüft die sechs PyPI-Dateidigestwerte, installiert die neue Version in frischer Umgebung und erstellt die Abschlusszusammenfassung |

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

Beispiel für 3.0.4:
- lefx-studio-3.0.4-windows-x64.exe
- led_controller_version_3-3.0.4-py3-none-any.whl
- led_controller_version_3_effect_creation-3.0.4-py3-none-any.whl
- led_controller_version_3_device_simulated_respeaker-3.0.4-py3-none-any.whl
- die drei zugehörigen .tar.gz Source-Distributionen

Die sdists sind bewusst ebenfalls öffentliche Release-Assets, damit das
PyPI-Repo dieselben vorab geprüften Bytes statt eines erneuten Builds
verwendet. Der versiegelte Release-Baum und die Manifeste bleiben interne
CI-Artefakte (90 Tage). Das PyPI-Repo enthält nur den erzeugten Quellbaum,
das Manifest und den PyPI-Workflow, keine Studio-EXE und keine GitHub Releases.

## Fehlerbehandlung

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

PyPI Trusted Publisher (unverändert): Owner marcosudau-vps, Repository
led-ctrl-v3, Workflow release.yml. Separate Environments:

| Projekt | Environment |
|---|---|
| led-controller-version-3 | pypi |
| led-controller-version-3-effect-creation | pypi-effect-creation |
| led-controller-version-3-device-simulated-respeaker | pypi-simulator |

Je Projekt eigener Publisher, id-token: write nur im Publish-Job,
max-parallel: 1. Keine dauerhaften PyPI-Token. Die bestehenden Publisher
nicht ändern. Ein zusätzlicher Configurator benötigt spätere, gesonderte
Release-Integration (Workspace, Versionen/Pins, Paketprüfungen, Bundle,
Workflow-Matrix, Publisher und Extras); nicht Teil dieses Releases.

## Reguläre Entwicklung

Branch/PR wie bisher; CI verwendet dieselben read-only Prüfjobs. Nur Patch
Release auf main erzeugt einen neuen Release. Kein Tag bei gewöhnlichen
Pushes oder PRs.
