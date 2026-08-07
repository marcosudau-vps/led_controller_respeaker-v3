# lefx-interfaces

Transport und Darstellung. CLI und HTTP-API tragen dieselben
Steuerungskommandos; keine der beiden besitzt eigene Fachlogik.

Es enthält:

- die HTTP-API unter `/api/v3/`,
- die CLI mit den Verben `list`, `show`, `set`, `clear`, `update`, `emit`,
  `output`, `sources`, `serve`, `status`,
- den Client für lokale Aufrufe,
- das Prozess-Hosting (Portwahl, Instanzverwaltung, Lebenszyklus),
- die Serialisierung der Antworten.

Frame-Senken und Input-Provider werden über Entry Points entdeckt. Dieses Paket
importiert weder die Hardware- noch die Simulator-Distribution.

```bash
lefx serve --sink simulator
lefx list states
lefx set state ready_state --config '{"color":"green"}'
```
