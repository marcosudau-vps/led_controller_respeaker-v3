# led-ctrl-v3-set-core

Der kuratierte Referenzsatz. Deckt alle vier Lebenszyklusformen und alle
Farbmodelle ab und ist zugleich als Lesestoff geschrieben: jede Definition
zeigt, wie ein Vertrag deklariert und wie ein Frame erzeugt wird, ohne eine
Abkürzung, die ein echtes Paket nicht auch nehmen dürfte.

```bash
pip install "led-ctrl-v3[core-set]"
```

Das Paket enthält genau eine gebaute `core-set.lefxset` und die Zeilen, die
sagen, wo sie liegt. Gefunden wird sie über den Entry-Point-Group
`lefx.effect_sets` — derselbe Mechanismus, über den der Dienst auch Geräte
findet. Deinstallieren entfernt den Satz; es gibt keine Liste, die man dabei
vergessen könnte.

Welche installierten Sätze geladen werden, entscheidet `INCLUDED_LEFXSET` in
der `config.yaml` oder als Umgebungsvariable:

```yaml
included_lefxset: [core, smartspeaker]
```

Ohne Angabe wird jeder installierte Satz geladen.

Die Quellen liegen im Entwicklungs-Repository unter `effects/core-set/sources/`.
Das Archiv hier ist gebaute Ausgabe und entsteht bei
`python scripts/build_effects.py`.
