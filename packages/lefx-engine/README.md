# lefx-engine

Die generische Ausführung. Sie kennt Typen, Lebenszyklen und Layer — aber
niemals eine konkrete Definition-ID.

Es enthält:

- den Layer-Stapel und die Komposition zu einem LED-Frame,
- Lebenszyklen für States, kontrollierte und zeitgesteuerte Overlays und Events,
- die Event-Warteschlange mit Priorität und FIFO,
- Runtime-Eingaben mit Push/Pull-Bezug und Input-Health,
- die Registry mit ID-Auflösung,
- das Laden und Prüfen von `lefx/3`- und `lefxset/3`-Paketen,
- die Renderschleife (headless und einbettbar).

Die Engine hängt ausschließlich am SDK. Hardwarezugriff, HTTP und CLI liegen
außerhalb.
