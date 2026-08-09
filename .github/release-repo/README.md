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
pip install led-ctrl-v3
```

| Distribution | Rolle |
|---|---|
| `led-ctrl-v3` | Der Name, unter dem installiert wird. Enthält selbst keinen Code. |
| `lefx-sdk` | Der Autorenvertrag: Definitionsschema, Wertnormalisierung, Ports |
| `lefx-engine` | Layer, Komposition, Lebenszyklen, Registry, `lefx/3`-Loader |
| `lefx-interfaces` | HTTP-API v3, CLI, Client, Prozess-Hosting, Konfiguration |
| `lefx-device-respeaker` | reSpeaker XVF3800: USB-Transport, LED-Senke, DoA-Provider |
| `lefx-device-simulated-respeaker` | Software-Geräteersatz mit Ringfenster |
| `lefx-effect-creation` | Effekte erstellen: `lefx-pack` und `lefx-studio` |
| `lefxset-core-set` | Referenzkatalog |
| `lefxset-smartspeaker-set` | Sprachassistenz-Katalog |

Die vier ersten sind die Normalversion; der Rest sind Extras von
`led-ctrl-v3` — siehe die README dieses Pakets.

## Wie ein Release hierher kommt

1. Im Entwicklungs-Repository läuft `scripts/release.py`: Version schreiben,
   Kataloge bauen, Tests, `check_release.py`, committen, pushen.
2. Das Skript wartet auf grünes CI **für genau diesen Commit** und setzt erst
   dann den Tag `vX.Y.Z`.
3. Der Tag startet dort `sync-release-repo.yml`, das diesen Baum erzeugt,
   hierher committet und hier denselben Tag setzt.
4. Dieser Tag startet hier `release.yml`: bauen, das Gebaute in einer leeren
   Umgebung installieren und benutzen, dann pro Projekt über OIDC Trusted
   Publishing nach PyPI hochladen — ohne Token und ohne Passwort.

Ein Tag hier bedeutet also: drüben geprüft.
