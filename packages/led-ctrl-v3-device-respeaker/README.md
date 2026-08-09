# led-ctrl-v3-device-respeaker

Die Anbindung an den reSpeaker XVF3800 über USB.

Es enthält:

- `UsbTransport` — Geräteerkennung, automatische Wiederverbindung, Heartbeat
  und thread-sicheres Lesen und Schreiben,
- `ReSpeakerFrameSink` — schreibt den komponierten LED-Frame auf den Ring und
  überspringt unveränderte Frames,
- `ReSpeakerDoaProvider` — liest `DOA_VALUE` und liefert `direction_deg` und
  `detection_state`.

Ausgabe und Eingabe sind getrennte Objekte über einem gemeinsamen Transport.
Sie werden einzeln registriert, damit ein Ausfall der einen Richtung die andere
nicht mitnimmt.

Das Paket hängt nur am SDK. Es kennt weder Engine noch Effektlogik: eine
Definition deklariert lediglich die Fähigkeit `doa` und liest den validierten
Snapshot. Registriert ist der Provider als `respeaker.doa` — der Gerätename hält
ihn vom Simulator getrennt, die Fähigkeit ist das, was ein Effekt benennt.

Die Ringgröße stammt aus der Befehlstabelle der Firmware (`LED_RING_COLOR`) und
steht nirgends als Zahl im Code. Weicht die konfigurierte `led_count` davon ab,
meldet die Senke das über `status()`, statt Frames stillschweigend zu kürzen.

## Wenn das Gerät belegt ist

Ein WinUSB-Handle ist exklusiv. Ein zweiter Prozess reiht sich nicht ein, er
bekommt `Errno 13` — das liest sich wie ein Treiber- oder Rechteproblem und
schickt einen in die falsche Richtung. Meistens läuft schlicht noch ein anderer
Controller.

```bash
lefx-respeaker probe
```

`probe` sagt, ob das Gerät ansprechbar ist, und listet andernfalls die Prozesse,
die ein USB-Gerät halten — mit Kommandozeile, denn erfahrungsgemäß heißen alle
Kandidaten `python.exe`.

```bash
lefx-respeaker claim --dry-run
```

`claim` beendet, was im Weg steht, und prüft danach nach. Zwei Dinge begrenzen
den Schaden:

- **Es wird einzeln beendet und nach jedem Schritt neu geprüft.** Sobald das
  Gerät antwortet, hört es auf. Der Prozess, der wirklich im Weg war, ist damit
  der letzte, den es trifft.
- **Fremde USB-Software wird nicht angefasst.** Maus-, Tastatur- und
  RGB-Software hält dauerhaft offene WinUSB-Handles und taucht in derselben
  Suche auf. Sie wird aufgelistet und in Ruhe gelassen; nur Prozesse, die sich
  als reSpeaker-Software zu erkennen geben, kommen in Frage. `--include-unrelated`
  hebt das auf — bewusst und einzeln.

Im Dienst ist dasselbe als Senken-Option verfügbar:

```bash
uv run lefx serve --sink respeaker --sink-option force_claim=true
```

Es ist eine Senken-Option und kein `lefx`-Schalter, weil `lefx` nichts über
reSpeaker wissen soll. Der Transport ruft es höchstens **einmal pro
Verbindungszyklus** auf, nur bei einem Zugriffsfehler: der Wiederholungsversuch
läuft alle paar Sekunden, und etwas, das in diesem Takt Prozesse beendet, wäre
eine Plage. Ein fehlendes Gerät gilt nicht als Konkurrenz — ein gezogenes Kabel
ist kein fremder Prozess.
