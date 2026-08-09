# led-ctrl-v3-sdk

Der Vertrag zwischen Effektpaketen und der Engine. Dieses Paket ist das
einzige, das ein Effektautor importiert.

Es enthält:

- die typ-spezifischen Definitionsklassen (`StateDefinition`,
  `ControlledOverlayDefinition`, `TimedOverlayDefinition`, `EventDefinition`),
- die Parametertypen und ihre Zulässigkeitsregeln,
- die kanonische Wertnormalisierung (Farben, Dauern, Winkel, Boolesche Werte),
- generische Farbmathematik,
- `RenderContext` und `InputContext`,
- die Ports `FrameSink` und `InputProvider`.

Das SDK hat bewusst keine Abhängigkeiten. Eine ungültige Definition ist nicht
konstruierbar — die Prüfungen laufen im Konstruktor, nicht in einem separaten
Validierungsschritt.
