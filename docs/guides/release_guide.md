# LEFX V3 Release & Build Guide

Diese Anleitung beschreibt das Erstellen, Testen und Veröffentlichen von **LEFX V3** Paketen und Effekt-Sets.

---

## 🏗️ Workspace-Struktur

LEFX V3 ist als `uv` Monorepo-Workspace organisiert (`C:\Users\marco\source\repos\respeaker-led-v3`):

```
respeaker-led-v3/
├── pyproject.toml              Workspace-Root (Dependencies & uv Configuration)
├── packages/
│   ├── led-controller-version-3/             Hauptpaket (SDK, Engine, Interfaces, Device & Kataloge)
│   ├── led-controller-version-3-effect-creation/  Authoring & Build-Tools (`lefx-pack`)
│   └── led-controller-version-3-device-simulated-respeaker/ Qt/PySide6 GUI-Simulator
├── effects/
│   ├── core-set/               Quellcode & Quellen für das core-set
│   └── smartspeaker-set/       Quellcode & Quellen für das smartspeaker-set
├── scripts/                    Build- & Release-Skripte
└── tests/                      Vollständige Pytest-Suite (680+ Tests)
```

---

## ⚙️ 1. Entwicklungsumgebung einrichten

```powershell
# Dependencies synchronisieren
uv sync

# Für Simulator- & Distribution-Builds die Build-Gruppe laden:
uv sync --group build
```

---

## 🎨 2. Effekt-Sets bauen (`build_effects.py`)

Die Quellcodes der Effekte liegen unter `effects/core-set` und `effects/smartspeaker-set`. Sie müssen in komprimierte `.lefxset`-Archive kompiliert werden, damit das Hauptpaket sie ausliefern kann:

```powershell
uv run python scripts/build_effects.py
```

Dieses Skript:
1. Validiert alle Python-Effektquellen gegen das Schema V3 (`StateDefinition`, `EventDefinition`, etc.).
2. Prüft die Sandboxing-Regeln (Whitelist an erlaubten Imports: nur `lefx.sdk.*` und `stdlib`).
3. Erzeugt die komprimierten ZIP-Archive:
   - `packages/led-controller-version-3/src/lefx/sets/core_set/core-set.lefxset`
   - `packages/led-controller-version-3/src/lefx/sets/smartspeaker_set/smartspeaker-set.lefxset`

---

## 🧪 3. Testsuite ausführen (`pytest`)

Vor jedem Build oder Commit muss die Pytest-Suite fehlerfrei durchlaufen:

```powershell
uv run pytest -q
```

Die Tests prüfen:
- SDK-Schema, Normalisierung und Farbmathematik
- Engine Layering, Invocation-Lebenszyklen und Timeouts
- CLI- und HTTP REST-API Endpunkte (`/api/v3/*`)
- Hardware- und Simulator-Ports Konformität

---

## 📦 4. Release-Validierung (`check_release.py`)

Vor der Veröffentlichung stellt `check_release.py` sicher, dass alle gebauten Wheels vollständig sind und die `.lefxset`-Archive enthalten:

```powershell
uv run python scripts/check_release.py
```

---

## 🚀 5. PyPI Paketierung & Build

Um ein installierbares Python Wheel für `led-controller-version-3` zu erstellen:

```powershell
uv build --package led-controller-version-3
```

Die gebauten `.whl` und `.tar.gz` Dateien werden im Ordner `dist/` abgelegt.

---

## 📌 Versionsrichtlinien (Semantic Versioning)

- **Version 3.0.x**: Aktuelle Hauptgeneration LEFX V3.
- Versionsänderungen erfolgen in `packages/led-controller-version-3/pyproject.toml`.
