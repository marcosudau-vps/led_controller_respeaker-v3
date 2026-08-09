# led-ctrl-v3 — Release-Repository

> **Hier wird nicht von Hand gepusht.**
>
> Der Inhalt dieses Repositories wird bei jedem Release maschinell erzeugt und
> überschrieben. Ein manueller Commit geht beim nächsten Sync verloren oder
> erzeugt einen Konflikt, den nur ein Force-Push auflöst.

Dies ist der Baum, aus dem die PyPI-Pakete gebaut werden — nur das, was
`uv build --all-packages` braucht, damit ein Release lesbar und zwischen
Versionen vergleichbar bleibt.

Entwickelt wird in
**[marcosudau-vps/led_controller_respeaker-v3](https://github.com/marcosudau-vps/led_controller_respeaker-v3)**.
Dort liegen Effektquellen, Testsuite, Dokumentation und die Werkzeuge; dort
werden auch Issues und Pull Requests aufgemacht.

## Was hier veröffentlicht wird

```bash
pip install led-controller-version-3
```

| Distribution | Rolle |
|---|---|
| `led-controller-version-3` | Die Normalversion: Autorenvertrag (`lefx.sdk`), Laufzeit (`lefx.engine`), Steuerungsoberfläche (`lefx.interfaces`), reSpeaker-Anbindung und beide Effektkataloge. |
| `led-controller-version-3-device-simulated-respeaker` | Software-Geräteersatz mit Ringfenster. |
| `led-controller-version-3-effect-creation` | Effekte erstellen: `lefx-pack` und `lefx-studio`. |

Die erste ist die Normalversion; die anderen beiden sind Extras von
`led-controller-version-3` (`[simulated-respeaker]`, `[effect-creation]`, `[all]`) — siehe
die README dieses Pakets.

## Wie ein Release hierher kommt

1. Im Entwicklungs-Repository läuft `scripts/release.py`: Version schreiben,
   Kataloge bauen, Tests, `check_release.py`, committen, pushen.
2. Das Skript wartet auf grünes CI **für genau diesen Commit** und setzt erst
   dann den Tag `vX.Y.Z`.
3. Der Tag startet dort `sync-release-repo.yml`, das diesen Baum erzeugt,
   hierher committet und hier denselben Tag setzt.
4. Dieser Tag startet hier `release.yml`: bauen, das Gebaute in einer leeren
   Umgebung installieren und benutzen, dann pro Projekt nach PyPI hochladen.

Ein Tag hier bedeutet also: drüben geprüft.
