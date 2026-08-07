# lefx-authoring

Entwicklerwerkzeug für Effektquellen und Pakete. Gehört nicht in eine
Laufzeitinstallation.

Es enthält:

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
