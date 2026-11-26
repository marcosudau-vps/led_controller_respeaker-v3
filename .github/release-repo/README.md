# led-ctrl-v3 — Release-Repository

> **Hier wird nicht von Hand gepusht.**
>
> Der Inhalt dieses Repositories wird bei jedem Release maschinell erzeugt und
> überschrieben. Ein manueller Commit geht beim nächsten Sync verloren oder
> erzeugt einen Konflikt, den nur ein Force-Push auflöst.

Dies ist der gepr?fte Quellbaum der PyPI-Distributionen. Die zugeh?rigen
Wheels und Source-Distributionen wurden bereits im Entwicklungsrepository
vor der Tagvergabe gebaut, installiert und getestet.

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

1. Patch Release im Entwicklungsrepository erstellt automatisch die n?chste
   Patch-Version und pr?ft den Kandidaten vollst?ndig auf Linux und Windows.
2. Erst nach Artefaktpr?fung werden main und Tag atomar aktualisiert. Das
   ?ffentliche GitHub Release enth?lt die gepr?ften Wheels, sdists und EXE.
3. Der gepr?fte Quellbaum wird samt release-manifest.json per SSH hierher
   ?bertragen. Derselbe Versionstag wird gesetzt.
4. release.yml l?dt ausschlie?lich die sechs gepr?ften Distributionsdateien
   aus dem Entwicklungs-GitHub-Release, verifiziert Gr??e und SHA-256 gegen
   das Manifest und ver?ffentlicht sie per PyPI Trusted Publishing.
5. Der Entwicklungsworkflow pr?ft den erfolgreichen PyPI-Lauf, die dort
   ver?ffentlichten Hashes und eine frische Installation.

Hier wird keine neue EXE gebaut, kein GitHub Release erzeugt und keine
Version manuell vergeben.
