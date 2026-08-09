# lefxset-smartspeaker-set

States, Overlays und Events für ein Sprachassistenzgerät — der Satz, für den
dieses System ursprünglich gebaut wurde: Zuhören, Denken, Sprechen, Fehler,
Lautstärke, Stummschaltung, Richtungsanzeige.

```bash
pip install "led-ctrl-v3[smartspeaker-set]"
```

Das Paket enthält genau eine gebaute `smartspeaker-set.lefxset` und die Zeilen,
die sagen, wo sie liegt. Gefunden wird sie über den Entry-Point-Group
`lefx.effect_sets` — derselbe Mechanismus, über den der Dienst auch Geräte
findet. Deinstallieren entfernt den Satz; es gibt keine Liste, die man dabei
vergessen könnte.

Welche installierten Sätze geladen werden, entscheidet `INCLUDED_LEFXSET` in
der `config.yaml` oder als Umgebungsvariable:

```yaml
included_lefxset: [core, smartspeaker]
```

Ohne Angabe wird jeder installierte Satz geladen.

Die Quellen liegen im Entwicklungs-Repository unter
`effects/smartspeaker-set/sources/`. Das Archiv hier ist gebaute Ausgabe und
entsteht bei `python scripts/build_effects.py`.
