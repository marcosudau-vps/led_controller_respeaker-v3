# Release- und Update-Anleitung

Wie Änderungen veröffentlicht werden — einfache Code-Updates (nur GitHub) und
offizielle Releases (mit automatischem PyPI-Upload).

---

## Die beiden Repositories

| Repository | Rolle | Wer schreibt hinein? |
|---|---|---|
| [`marcosudau-vps/led_controller_respeaker-v3`](https://github.com/marcosudau-vps/led_controller_respeaker-v3) | **Entwicklung.** Vollständige Umgebung: Testsuite, Effektquellen, Studio, PyInstaller-Strecke, Dokumentation. | Du. Hier wird gearbeitet und getaggt. |
| [`marcosudau-vps/led-ctrl-v3`](https://github.com/marcosudau-vps/led-ctrl-v3) | **Release.** Nur der Baum, aus dem die PyPI-Pakete gebaut werden. | Ausschließlich der Workflow `sync-release-repo.yml`. |

> ⚠️ **Niemals von Hand ins Release-Repo pushen.** Dessen `main` wird bei jedem
> Release maschinell überschrieben. Ein manueller Push geht verloren oder
> erzeugt einen Konflikt, den nur ein Force-Push auflöst.

Welche Dateien mitwandern, legt die Whitelist in
[`scripts/sync_release_tree.py`](../scripts/sync_release_tree.py) fest. Die
gebauten `.lefxset`-Archive sind hier Ausgabe und dort Quelle — das ist der
einzige Unterschied zwischen den Bäumen, der nicht bloßes Weglassen ist.

---

## Die drei Distributionen

Alle tragen dieselbe Versionsnummer und werden gemeinsam veröffentlicht.
[`tests/architecture/test_versions.py`](../tests/architecture/test_versions.py)
erzwingt das, samt der `==`-Pins zwischen ihnen.

| PyPI-Projekt | Rolle | Installiert durch |
|---|---|---|
| `led-controller-version-3` | Schema, Laufzeit, API/CLI, reSpeaker **und beide Effektkataloge** | Standard |
| `led-controller-version-3-device-simulated-respeaker` | Software-Geräteersatz mit Ringfenster | `[simulated-respeaker]` |
| `led-controller-version-3-effect-creation` | `lefx-pack` und `lefx-studio`, bringt Qt | `[effect-creation]` |

Drei und nicht neun, weil nur Optionales ein eigenes Projekt braucht. Schema,
Engine, Steuerungsoberfläche und Hardware werden immer zusammen installiert —
kein Extra wählt je zwischen ihnen —, und die Kataloge werden zur Laufzeit über
`included_lefxset` gewählt statt beim Installieren. Die Schichtgrenzen bleiben
davon unberührt: `tests/architecture/test_architecture.py` prüft sie jetzt über
Modulverzeichnisse statt über Paketnamen, mit denselben Regeln.

Die PyPI-Namen tragen das Präfix `led-controller-version-3-`, die Importpfade heißen
weiterhin `lefx.*`. Das ist Absicht: `led-controller-version-3` ist ein Arbeitsname für
diesen Stand, und die `lefx-*`-Namen bleiben auf PyPI frei für die spätere
eigenständige Veröffentlichung. Ein Auseinanderfallen von Distributions- und
Importname ist auf PyPI üblich (`opencv-python` importiert sich als `cv2`) und
kostet keine Zeile Anwendungscode.

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
| 2 | Version in alle 4 `pyproject.toml` schreiben — **inklusive der `==`-Pins** |
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
   ein Job **pro Projekt** hoch.
3. Unter [pypi.org/project/led-controller-version-3](https://pypi.org/project/led-controller-version-3/)
   steht die Version bereit: `pip install --upgrade led-controller-version-3`.

Ein Job pro Projekt, weil ein einzelner Upload aller drei bei Trusted
Publishing davon abhinge, wie PyPI ein frisch geprägtes Token über Projekte
hinweg skopiert. Drei getrennte Uploads hängen davon gar nicht ab, und ein
Fehlschlag nennt das Projekt, zu dem er gehört.

### Wenn ein Upload mit 429 scheitert

```
429 Too many new projects created
```

**Die Regel: PyPI erlaubt vier neue Projekte pro Tag und Konto.** Nicht vier pro
Stunde, nicht vier Versuche — vier tatsächlich angelegte Projekte in 24
Stunden. Das Hochladen einer neuen Version in ein **bestehendes** Projekt ist
davon nicht betroffen und geht jederzeit.

Das trifft ausschließlich den allerersten Release einer Namensgebung, und dann
hart: mehr als vier neue Projektnamen sind an einem Tag nicht zu haben, egal
wie langsam man es versucht. `max-parallel: 1` und `skip-existing` in
`release.yml` machen den Lauf wiederholbar, aber sie erzeugen kein Kontingent.

Ein Ausweichen über eine andere IP funktioniert nicht — die Zählung hängt am
Konto. Lokal mit `uv publish` hochladen scheitert genauso.

Kaputt ist dabei nichts: die Artefakte liegen am Workflow-Lauf, und was
durchkam, bleibt. Am Folgetag die fehlgeschlagenen Jobs erneut laufen lassen:

```bash
gh run rerun --repo marcosudau-vps/led-ctrl-v3 <run-id> --failed
```

Welche Projekte fehlen, beantwortet der Index direkt:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/simple/led-controller-version-3-effect-creation/
```

Nicht neu taggen und nicht die Version erhöhen. Ein erfolgreicher Upload lässt
sich nicht wiederholen, ein fehlender fehlt einfach noch.

> Praktische Folge für den Zuschnitt: **jedes zusätzliche PyPI-Projekt ist
> beim ersten Release ein Viertel eines Tageskontingents.** Beim Erstversuch
> dieses Systems standen neun Projekte an; vier entstanden, drei davon für
> Pakete, die es einen Tag später schon nicht mehr gab. Ein Projekt anzulegen
> ist billig, bis man vier davon braucht.

### Wenn CI ausfällt

```bash
uv run python scripts/release.py --skip-ci "GitHub Actions incident #12345"
```

Verlangt eine Begründung und schreibt sie in die Ausgabe. Nur dafür gedacht.

---

## Einrichtung (einmalig)

Alles davon ist erledigt. Es steht hier, damit es nachvollziehbar und
wiederholbar ist — etwa, wenn eines der Repositories neu angelegt wird.

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

### 2. Trusted Publishing auf PyPI

Kein Token, kein Passwort, nichts gespeichert: GitHub prägt pro Lauf ein
kurzlebiges OIDC-Token, PyPI prüft es gegen den für das Projekt hinterlegten
Publisher und gibt ein Upload-Token zurück, das Minuten gilt.

Jedes der drei Projekte hat seinen **eigenen** GitHub-Environment-Namen im
Release-Repo (*Settings → Environments*):

| PyPI-Projekt | Environment name |
|---|---|
| `led-controller-version-3` | `pypi` |
| `led-controller-version-3-effect-creation` | `pypi-effect-creation` |
| `led-controller-version-3-device-simulated-respeaker` | `pypi-simulator` |

Das ist keine Ordnungsliebe, sondern Notwendigkeit: **PyPI lässt pro
Konfiguration nur einen offenen Pending Publisher zu.** Owner, Repository,
Workflow und Environment bilden zusammen den Schlüssel, und drei Projekte, die
vor ihrem ersten Upload registriert werden, brauchen deshalb drei
unterschiedliche Konfigurationen. Das Environment ist das einzige Feld, das
frei wählbar ist.

Es bringt zusätzlich etwas: eine Freigaberegel lässt sich auf ein Projekt legen,
ohne die anderen anzuhalten, und ein Publisher gilt nur für den Job, der ihn
benutzen darf. In `release.yml` kommt der Name aus der Matrix
(`environment: ${{ matrix.environment }}`) — stehen Matrix und Publisher nicht
im Einklang, antwortet PyPI mit einem 403, das nichts über Environments sagt.

Die gemeinsamen Felder für alle drei:

| Feld | Wert |
|---|---|
| Owner | `marcosudau-vps` |
| Repository name | `led-ctrl-v3` |
| Workflow name | `release.yml` |

**Achtung:** Owner und Repository sind die des **Release**-Repos, nicht des
Entwicklungs-Repos — dort läuft `release.yml`.

Wo der Eintrag hingehört, hängt davon ab, ob das Projekt schon existiert:

* **Projekt existiert noch nicht** → *Your account → Publishing → Add a new
  pending publisher*, unter dem Konto, dem das Projekt gehören soll. Der
  Publisher legt das Projekt beim ersten Upload gleich mit an.
* **Projekt existiert bereits** → *Manage project → Publishing → Add a new
  publisher*. Ein Pending Publisher ist hier wirkungslos: er greift nur für
  Namen, die noch frei sind. Anlegen kann ihn nur, wer auf dem Projekt Owner
  ist.

Ein Pending Publisher lässt sich nicht bearbeiten — falscher Name oder falsches
Environment heißt löschen und neu anlegen.

Beides geht ausschließlich über die Weboberfläche; eine API dafür gibt es
nicht.

Die Projekte müssen nicht demselben Konto gehören — der Publisher hängt am
Projekt, nicht am Konto. Zwei Konten sind allerdings auch zwei Stellen, an
denen später jemand Owner sein muss; wer das vermeiden will, lädt das eine
Konto beim anderen als Owner ein (*Manage project → Collaborators*) und
verwaltet danach alles von dort.

---

## Zusammenfassung

```bash
uv run python scripts/release.py
```
