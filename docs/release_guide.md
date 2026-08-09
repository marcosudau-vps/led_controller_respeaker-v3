# Release- und Update-Anleitung

Wie Änderungen veröffentlicht werden — einfache Code-Updates (nur GitHub) und
offizielle Releases (mit automatischem PyPI-Upload).

---

## Die beiden Repositories

| Repository | Rolle | Wer schreibt hinein? |
|---|---|---|
| [`marcosudau-vps/led_controller_respeaker-v3`](https://github.com/marcosudau-vps/led_controller_respeaker-v3) | **Entwicklung.** Vollständige Umgebung: Testsuite, Effektquellen, Studio, PyInstaller-Strecke, Dokumentation. | Du. Hier wird gearbeitet und getaggt. |
| [`marcosudau-vps/led-ctrl-v3`](https://github.com/marcosudau-vps/led-ctrl-v3) | **Release.** Nur der Baum, aus dem die PyPI-Pakete gebaut werden. 105 Dateien statt einigen hundert. | Ausschließlich der Workflow `sync-release-repo.yml`. |

> ⚠️ **Niemals von Hand ins Release-Repo pushen.** Dessen `main` wird bei jedem
> Release maschinell überschrieben. Ein manueller Push geht verloren oder
> erzeugt einen Konflikt, den nur ein Force-Push auflöst.

Welche Dateien mitwandern, legt die Whitelist in
[`scripts/sync_release_tree.py`](../scripts/sync_release_tree.py) fest. Die
gebauten `.lefxset`-Archive sind hier Ausgabe und dort Quelle — das ist der
einzige Unterschied zwischen den Bäumen, der nicht bloßes Weglassen ist.

---

## Die neun Distributionen

Alle tragen dieselbe Versionsnummer und werden gemeinsam veröffentlicht.
[`tests/architecture/test_versions.py`](../tests/architecture/test_versions.py)
erzwingt das, samt der `==`-Pins zwischen ihnen.

Die PyPI-Namen tragen alle das Präfix `led-ctrl-v3-`, die Importpfade heißen
weiterhin `lefx.*`. Das ist Absicht: `led-ctrl-v3` ist ein Arbeitsname für
diesen Stand, und die `lefx-*`-Namen bleiben auf PyPI frei für die spätere
eigenständige Veröffentlichung. Ein Auseinanderfallen von Distributions- und
Importname ist auf PyPI üblich (`opencv-python` importiert sich als `cv2`) und
kostet keine Zeile Anwendungscode.

| PyPI-Projekt | Rolle |
|---|---|
| `led-ctrl-v3` | Der Name, unter dem installiert wird. Enthält keinen Code. |
| `led-ctrl-v3-sdk` | Autorenvertrag |
| `led-ctrl-v3-engine` | Laufzeit |
| `led-ctrl-v3-interfaces` | API, CLI, Konfiguration |
| `led-ctrl-v3-device-respeaker` | Hardware |
| `led-ctrl-v3-device-simulated-respeaker` | Software-Geräteersatz |
| `led-ctrl-v3-effect-creation` | `lefx-pack` und `lefx-studio` |
| `led-ctrl-v3-set-core` | Referenzkatalog |
| `led-ctrl-v3-set-smartspeaker` | Sprachassistenz-Katalog |

---

## Pfad 1: Normales Code-Update (ohne PyPI-Release)

```bash
uv run pytest -q -m "not hardware"
```

```bash
git add . && git commit -m "fix: Beschreibung der Änderung" && git push origin main
```

✅ Entwicklungs-Repo ist aktuell, CI läuft. Release-Repo und PyPI bleiben
unverändert — dorthin gelangt nur, was getaggt wird.

---

## Pfad 2: Offizielles Release

```bash
uv run python scripts/release.py
```

Das ist alles. Das Skript stellt genau zwei Fragen:

```
current version: 3.0.0
release version [3.0.1]:            ← Enter nimmt die nächste Patch-Version

About to release 3.0.1:
  ...
Are you sure? [y/N]
```

Danach läuft es allein durch, und bricht beim ersten Fehler ab:

| # | Schritt |
|---|---|
| 1 | Arbeitsbaum sauber, auf `main`, aktuell zu `origin`, Tag noch frei |
| 2 | Version in alle 10 `pyproject.toml` schreiben — **inklusive der `==`-Pins** |
| 3 | Effektkataloge neu bauen, damit die Wheels die aktuellen Quellen tragen |
| 4 | Gesamte hardwarefreie Testsuite |
| 5 | `check_release.py`: alles bauen, in eine leere Umgebung installieren, benutzen |
| 6 | Committen und pushen |
| 7 | **Auf grünes CI für genau diesen Commit warten** |
| 8 | `vX.Y.Z` taggen und pushen |

Schritt 7 ist der Grund, warum das ein Skript ist und keine Liste in einem
Dokument. Der Tag startet Sync und PyPI-Upload; ein Tag vor grünem CI ist ein
ungeprüftes Release. Hier ist die falsche Reihenfolge nicht möglich.

### Vorher hineinsehen

```bash
uv run python scripts/release.py --dry-run
```

Läuft die Schritte 1, 3, 4 und 5 und hört vor der ersten Änderung auf.

Den Release-Baum lokal ansehen:

```bash
uv run python scripts/build_effects.py && uv run python scripts/sync_release_tree.py --target ../release_preview
```

Probelauf gegen das echte Release-Repo — spiegelt `main` dorthin, **ohne** zu
taggen, sodass dessen `release.yml` untätig bleibt und nichts PyPI erreicht:

```bash
gh workflow run sync-release-repo.yml --repo marcosudau-vps/led_controller_respeaker-v3
```

Das Feld `tag` dabei leer lassen.

### Was nach dem Tag automatisch passiert

1. `sync-release-repo.yml` (Entwicklungs-Repo) baut die Kataloge, materialisiert
   den Release-Baum, committet ihn ins Release-Repo und setzt dort **denselben
   Tag** auf den Release-Commit.
2. Dieser Tag startet dort `release.yml`. Der Guard
   `github.repository == 'marcosudau-vps/led-ctrl-v3'` greift, `uv build
   --all-packages` läuft, `check_release.py` prüft das Gebaute — und dann lädt
   ein Job **pro Projekt** über OIDC Trusted Publishing hoch, ohne Token und
   ohne Passwort.
3. Unter [pypi.org/project/led-ctrl-v3](https://pypi.org/project/led-ctrl-v3/)
   steht die Version bereit: `pip install --upgrade led-ctrl-v3`.

Ein Job pro Projekt, weil ein einzelner Upload aller neun davon abhinge, wie
PyPI ein frisch geprägtes Token über Projekte hinweg skopiert. Neun Uploads
hängen davon gar nicht ab, und ein Fehlschlag nennt das Projekt, zu dem er
gehört.

### Wenn CI ausfällt

```bash
uv run python scripts/release.py --skip-ci "GitHub Actions incident #12345"
```

Verlangt eine Begründung und schreibt sie in die Ausgabe. Nur dafür gedacht.

---

## Einrichtung (einmalig)

Drei Dinge. Nur das letzte lässt sich nicht mit einem GitHub-Token erledigen.

### 0. Das Release-Repo braucht einen ersten Commit

Ein frisch angelegtes Repository hat keinen Default-Branch, und
`actions/checkout` kann dann nichts auschecken — der Sync scheitert mit
`git ls-remote ... failed with exit code 2`. Einmal irgendetwas hineinlegen
genügt; der erste Sync überschreibt es ohnehin:

```bash
gh api -X PUT repos/marcosudau-vps/led-ctrl-v3/contents/README.md -f message="chore: seed" -f content="$(base64 -w0 .github/release-repo/README.md)" -f branch=main
```

### 1. Deploy-Key für den Sync

Der Sync-Workflow pusht in ein fremdes Repository; der eingebaute
`GITHUB_TOKEN` genügt dafür nicht.

```bash
ssh-keygen -t ed25519 -C "led-ctrl-v3-sync" -f led-ctrl-v3-sync -N ""
```

1. Öffentlichen Teil (`led-ctrl-v3-sync.pub`) in **`marcosudau-vps/led-ctrl-v3`**
   unter *Settings → Deploy keys → Add deploy key* eintragen,
   **Allow write access** aktivieren.
2. Privaten Teil (`led-ctrl-v3-sync`) in
   **`marcosudau-vps/led_controller_respeaker-v3`** unter *Settings → Secrets
   and variables → Actions* als `RELEASE_REPO_DEPLOY_KEY` hinterlegen.
3. Beide lokalen Schlüsseldateien danach löschen.

Der Schlüssel gilt nur für dieses eine Repository und läuft nicht ab.

### 2. Trusted Publisher auf PyPI — neunmal (nur von Hand)

Für **jedes** der neun Projekte aus der Tabelle oben, unter
[pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
einen *pending publisher* anlegen (das geht, bevor das Projekt existiert):

| Feld | Wert |
|---|---|
| PyPI Project Name | `led-ctrl-v3`, `led-ctrl-v3-sdk`, … (je einmal) |
| Owner | `marcosudau-vps` |
| Repository name | `led-ctrl-v3` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

**Achtung:** Owner und Repository sind die des **Release**-Repos, nicht des
Entwicklungs-Repos — dort läuft `release.yml`.

Dazu im Release-Repo unter *Settings → Environments* eine Umgebung namens
`pypi` anlegen. Ein Reviewer darauf ist optional und eine gute Idee: dann
verlangt jeder Upload eine Bestätigung.

---

## Zusammenfassung

```bash
uv run python scripts/release.py
```
