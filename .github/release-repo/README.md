# led-ctrl-v3 — Release-Repository

Der Patch-Release-Workflow erzeugt diesen Quellbaum im Entwicklungsrepository.
Dort werden Änderungen, Issues und Pull Requests bearbeitet. [LEFX-Entwicklungsrepository](https://github.com/marcosudau-vps/led_controller_respeaker-v3)

## Distributionen

| PyPI-Projekt | Rolle | Kern-Extra |
|---|---|---|
| `led-controller-version-3` | SDK, Engine, Schnittstellen, reSpeaker und beide Effektkataloge | Standard |
| `led-controller-version-3-device-simulated-respeaker` | Software-Geräteersatz mit Ringfenster | `simulated-respeaker` |
| `led-controller-version-3-effect-creation` | Effekte erstellen mit `lefx-pack` und `lefx-studio` | `effect-creation` |
| `lefx-config-widget` | Effektparameter und LED-Aufrufe konfigurieren | `configurator` |

```bash
pip install led-controller-version-3
pip install "led-controller-version-3[configurator]"
pip install "led-controller-version-3[all]"
```

## Ablauf

1. Die Entwicklungs-CI testet den exakten Patch-Kandidaten unter Linux und Windows.
2. Nach bestandenem Gate werden der Entwicklungscommit und sein Tag veröffentlicht. Das GitHub Release erhält die geprüften Wheels, Sdists und die Studio-EXE.
3. Der Patch-Workflow spiegelt den geprüften Quellbaum samt Manifest. Der annotierte Release-Tag benennt den Entwicklungscommit.
4. `release.yml` ermittelt die Publisher-Matrix aus `scripts/release_contract.py`. Das Skript prüft die Dateien vom Entwicklungs-GitHub-Release anhand der Dateimenge, Version, Größe und SHA-256 und übergibt sie je Projekt an Trusted Publishing.
5. Der Entwicklungsworkflow kontrolliert die PyPI-Dateien und installiert den Release frisch.

Bei vier Distributionen umfasst das Manifest acht Python-Dateien. Das bestehende
v3.0.4 bleibt über seine ursprünglichen Tags und drei Distributionen verifizierbar.
Die Studio-EXE wird im Entwicklungsrepository gebaut und veröffentlicht.
