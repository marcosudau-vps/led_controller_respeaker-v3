# led-ctrl-v3-effect-creation

Alles, was mit dem **Erstellen** von Effekten zu tun hat — und nichts, was mit
dem Abspielen zu tun hat. Eine Laufzeitinstallation (`pip install led-ctrl-v3`)
enthält dieses Paket nicht: sie bekommt fertige `.lefx`- und
`.lefxset`-Dateien und braucht die Werkbank nicht, die sie hergestellt hat.

```bash
pip install "led-ctrl-v3[effect-creation]"
```

Das Paket hat zwei Hälften, die dieselbe Sache von zwei Seiten anfassen.

## Die Werkzeughälfte — `lefx-pack`

Ohne Fenster, für Skripte und Build-Strecken:

- Scaffolding für neue Einzelquellen und Sets,
- Quellenvalidierung (Layout, Importgrenzen, Typvertrag, Presets),
- den Smoke-Render gegen mehrere Ringgrößen,
- den Bau von `.lefx` und `.lefxset`,
- Inspektion und Verifikation gebauter Pakete.

Der Build ist eine Qualitätsgrenze, kein Verpackungsschritt: eine Quelle, die
den Vertrag verletzt, wird nicht gebaut.

```bash
lefx-pack validate <quelle>
lefx-pack build <quelle> <ziel.lefx>
lefx-pack verify <ziel.lefx>
```

Qt ist zwar eine harte Abhängigkeit dieses Pakets — das Studio *ist* ein
Fenster, ein Paket mit weggelassener Werkbank wäre eine dritte Sache zum
Erklären —, aber nichts unterhalb von `lefx/effect_creation/` importiert es
außer `lefx/effect_creation/studio/`. Eine Build-Strecke, die `lefx-pack`
aufruft, fasst den Toolkit nie an. Zwei Architekturtests halten diese Grenze.

## Die Fensterhälfte — `lefx-studio`

Für das, was von einer Kommandozeile aus umständlich ist: einen Effekt laufen
sehen, seine Parameter dabei bewegen, ihn ohne Neustart auf echte Hardware oder
auf den Simulator richten, ausmessen wie das Mikrofonarray gegenüber dem Ring
sitzt, und aus dem Ergebnis eine neue Effektquelle schreiben.

```bash
uv run lefx-studio
```

### Als eigenständiges Werkzeug

```bash
uv run --group build python scripts/build_studio.py --onedir
```

```bash
lefx-studio.exe --project C:\pfad\zum\repo
```

Die Exe ist ein echtes Werkzeug, keine Demo: sie liest den Katalog aus einem
Checkout, schreibt Quellen hinein und baut sie. Welcher Checkout ist eine
Laufzeitfrage — `--project`, oder der zuletzt benutzte, oder das
Arbeitsverzeichnis; `Projekt / Projekt öffnen` wechselt jederzeit.

Zwei Dinge verliert ein Bundle stillschweigend, beide behandelt in
`scripts/build_studio.py` und beide abgesichert durch
`tests/studio/test_project.py`: die `.dist-info`-Metadaten, aus denen die
Geräte-Entry-Points gelesen werden, und die Standardbibliotheksmodule, die ein
Effektpaket importieren darf. Ohne das erste bietet die Exe kein Gerät; ohne das
zweite scheitert ein Katalog, der im Checkout lädt, Effekt für Effekt.

```bash
lefx-studio.exe --self-check --project C:\pfad\zum\repo
```

stellt beide Fragen, indem es sie tut — Ausgaben ermitteln, Katalog laden, jede
Definition rendern — und ist der Weg herauszufinden, ob ein Build vollständig
ist.

Das Studio betreibt seine eigene Engine im Prozess. Es ist kein Client von
`lefx serve` — genau das erlaubt ihm, eine noch nicht gebaute Quelle zu
rendern, was der ganze Sinn davon ist, hier eine zu bearbeiten.

Nur ein Prozess kann den reSpeaker gleichzeitig halten. Läuft schon ein Dienst,
sagt das Studio das, statt sich mit ihm um das Gerät zu streiten; wähle
`simulator` oder `null` als Ausgabe, oder halte den Dienst vorher an.

### Die drei Seiten

**Player.** Katalog durchsuchen, Ausgabe wählen, regeln. Die Bedienelemente
entstehen aus dem Parameterschema jeder Definition, ein morgen geschriebener
Effekt bekommt also einen vollständigen Satz, ohne dass dieses Paket sich
ändert. Standardmäßig live, außer bei Events — die wiederholt kein bewegter
Regler.

**Kalibrierung.** Eine bekannte Peilung leuchten lassen, von dort sprechen, und
ausrechnen lassen, wie das Mikrofonarray gegen den Ring verdreht ist. Läuft
gegen das jeweils angeschlossene Gerät; die Antwort landet pro Gerät in
`doa_calibration.json`.

**Neuer Effekt.** Eine Definition entwerfen, sie auf dem echten Gerät rendern
sehen, dann `effect.py` + `effect.yaml` schreiben und ein einzelnes `.lefx`
packen. Ungültiges lässt sich nicht eingeben: Felder, die ein Parametertyp nicht
hat, sind abgeschaltet, reservierte Namen kommen mit festem Typ und Bereich, und
die echte Definition wird bei jeder Änderung konstruiert — Speichern ist
schlicht nicht verfügbar, solange das scheitert.

## Modulübersicht

| Modul | Qt | Zweck |
|---|---|---|
| `scaffold`, `source`, `validate`, `imports`, `build`, `cli` | nein | Die Werkzeughälfte: Gerüst, Prüfung, Importgrenze, Bau |
| `studio/session` | nein | Der eingebettete Controller: Engine, gewählte Ausgabe, Frame-Tap |
| `studio/catalogue` | nein | Durchsuchen und Filtern der geladenen Definitionen |
| `studio/calibrate` | nein | Zirkuläre Statistik und der Fit hinter der Kalibrierseite |
| `studio/authoring` | nein | Ein Quellverzeichnis wiederfinden und ein Preset hineinschreiben |
| `studio/blueprint` | nein | Eine Definition im Entwurf; baut sie, dann druckt sie |
| `studio/parameters` | ja | Editoren, gebaut aus dem Parameterschema einer Definition |
| `studio/ring` | ja | Der Live-Monitor, spiegelt was das Gerät gesendet bekommt |
| `studio/calibration_page` | ja | Den Ring in Halb-LED-Schritten abgehen |
| `studio/source_editor` | ja | Eine neue Definition entwerfen und packen |
| `studio/preset_dialog` | ja | Die Werte auf dem Schirm benennen und behalten |
| `studio/window` | ja | Die drei Seiten und die Ausgabe, die sie teilen |
| `studio/app` | ja | Das Konsolenskript |

Die Qt-freien Module sind so, damit sie ohne Display testbar sind — und in
ihnen steckt jede Entscheidung, die das Studio trifft.
