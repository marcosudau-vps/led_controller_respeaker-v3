# respeaker-led-device

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
