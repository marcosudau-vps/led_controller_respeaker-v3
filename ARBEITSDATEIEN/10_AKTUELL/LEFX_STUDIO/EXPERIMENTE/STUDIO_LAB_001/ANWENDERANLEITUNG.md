# Studio Lab – Kurzanleitung

Start: `uv run lefx-studio --project . --output null`, dann Tab **„Studio Lab (experimentell)“**.

```text
┌ Neu · Öffnen · Speichern · Export · Rückgängig · Wiederholen · Beispiele ────── Dateiname ┐
│ Baum                 │ Ansicht: Gesamt | Isoliert | Hervorgehoben │ Inspektor              │
│ + Ebene + Element    │            LED-Ring                        │ Felder des gewählten   │
│ + Animation ⧉ ▲ ▼ ✕  │ LEDs · Unbedeckte zeigen · Ausgabe         │ Objekts                │
├ ▶ ⏹ 00:01.300 / 00:10.000 ──────────── Gehe zu · Zeitraum · Tempo · Schleife ──────────────┤
│ ═════════════ Zeitachse (klicken/ziehen) ════════════════════════════════════════════════ │
│ Schritte [Quelle] ◀ ▶  Versatz 3 von 12 LEDs · Zyklus: 12 Schritte, 2 verschiedene Bilder │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## Beispiel 1 – zwei gegenläufige Segmente (der Abnahmeweg)

1. **Neu**. Im Baum steht nur „Gesamteffekt“; dort lassen sich Titel und Effekt-ID setzen.
2. **+ Ebene**, dann **+ Element → Segment**. Im Inspektor bei *Länge* das LED-Feld auf **5**
   stellen (ergibt 5/12 eines Zwölferrings), Farbe über das Farbfeld oder `#FF0000` tippen.
3. **+ Animation → Rotation**. *Umdrehungen / Sekunde* z. B. 0,25.
4. **▶** (oder Leertaste): Der Ring dreht, die Zeitleiste läuft mit. **⏸** pausiert; ein Klick
   auf die Zeitachse springt dorthin, „Gehe zu“ erlaubt exakte Zeitpunkte.
5. **+ Ebene**, wieder **Segment** (3 LEDs, blau) und **Rotation** mit **Rückwärts**.
   Mischmodus der Ebene im Inspektor z. B. auf *Addieren*: Wo sich beide treffen, mischen sie sich.
6. Reihenfolge mit **▲/▼**, Sichtbarkeit mit dem Häkchen vor der Ebene.
   **Ebene isoliert** zeigt nur die gewählte Ebene, **Gesamteffekt** wieder alles.
7. **Speichern** (`.lefx-design.json`), **Neu**, **Öffnen** – alles ist wieder da.
8. **Als .lefx exportieren**: Das Paket wird gebaut, vom LEFX-Loader geladen und an
   mehreren Zeitpunkten mit der Vorschau verglichen; das Ergebnis steht unten in der Meldungszeile.

Abkürzung: **Beispiele → Zwei Segmente, gegenläufig auf zwei Ebenen**.

## Beispiel 2 – Schritte statt Zeit: das A/B-Muster

1. **Beispiele → A/B-Muster über den ganzen Ring**.
2. Im Baum die Animation **⟳ Rotation** anklicken. Die Schrittquelle springt auf
   „LED-Versätze (12 je Umdrehung)“.
3. Mit **▶** in der Schrittzeile (oder `.`) Schritt für Schritt weiter, `,` zurück.
   Die Anzeige sagt: 12 Schritte bei 12 LEDs, aber nur **2 verschiedene Bilder** –
   physische LED-Zahl, Schrittzahl und Zustandszahl sind verschiedene Dinge.
4. Bei *Pulsieren* oder *Farbwechsel* heißen die Punkte ausdrücklich „Abtastpunkte“:
   Diese Animationen haben keine natürlichen Zustände.

## Auf dem ReSpeaker ansehen

Unter **Ausgabe** `respeaker` wählen und **An Ausgabe senden** anhaken. Das Gerät zeigt
genau, was der Lab-Ring zeigt – auch pausiert, gescrubbt oder schrittweise. Mit
„Ring zeigt Gerätesignal“ zeigt der Ring die tatsächlich gesendeten Werte (inkl. globaler
Helligkeit aus dem Player-Tab). Beim Wechsel in einen anderen Tab wird das Gerät freigegeben.
Ist die Vorschau-Ringgröße nicht 12, wird nichts gesendet.

## Legende

* farbiger Punkt: gerendert · schwarzer Punkt: deckend schwarz
* gestrichelter Kreis: keine Ebene trägt bei (transparent; ein deckender Effekt sendet dort Schwarz)

## Tasten (nur im Lab-Tab)

| Taste | Wirkung |
|---|---|
| Leertaste | Abspielen / Pausieren |
| `,` / `.` | vorheriger / nächster Schritt |
| Strg+Z, Strg+Y | Rückgängig, Wiederholen |
| Strg+L | neue Ebene |
| Strg+D | Duplizieren |
| Entf, F2 (im Baum) | Entfernen, Umbenennen |
| Strg+N, Strg+Umschalt+O, Strg+S, Strg+Umschalt+S, Strg+E | Neu, Öffnen, Speichern, Speichern unter, Export |
