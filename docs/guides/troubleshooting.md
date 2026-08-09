# LEFX V3 Troubleshooting & Diagnose-Leitfaden

Dieser Leitfaden hilft bei der Behebung typischer Probleme bei der Verbindung, Treiberinstallation, Parameter-Validierung und Ausführung des LEFX V3 LED-Controllers.

---

## ❓ 1. Service nicht erreichbar

### Symptom:
`lefx status` meldet `cannot reach the service at http://127.0.0.1:8765`.

### Lösungsschritte:
1. **Prüfen, ob der Service läuft**:
   ```powershell
   lefx status
   ```
2. **Service im Terminal starten**:
   ```powershell
   lefx serve --sink null
   ```
3. **Port-Kollisionen prüfen**:
   Falls Port `8765` von einer anderen Anwendung belegt ist, nutze `--port` oder `--port-pool`:
   ```powershell
   lefx serve --port 8766 --port-pool 8766-8770
   ```
4. **Aktive Service-Datei prüfen**:
   Beim Start schreibt der Service seine effektive Portnummer in die Datei `active_service.json`.

---

## 🔌 2. reSpeaker Hardware wird nicht erkannt (`respeaker` Sink)

### Symptom:
`lefx status` zeigt `"sink_available": false` oder meldet USB-Verbindungsfehler.

### Ursachen & Behebung:

#### A) Windows Treiber-Setup (WinUSB via Zadig)
Auf Windows benötigt der reSpeaker XVF3800 den WinUSB-Treiber für die direkte USB-Steuerung:

1. Lade das kostenlose Tool **[Zadig](https://zadig.akeo.ie/)** herunter.
2. Schließe den reSpeaker XVF3800 per USB an.
3. Öffne Zadig und aktiviere im Menü *Options → List All Devices*.
4. Wähle **reSpeaker XVF3800** (oder Interface 0) aus der Liste.
5. Wähle als Ziel-Treiber **WinUSB (v6.x.x.x)** aus.
6. Klicke auf **Replace Driver** (oder *Reinstall Driver*).
7. Starte `lefx serve --sink respeaker` neu.

#### B) Linux USB-Berechtigungen (udev rules)
Unter Linux erfordert der Zugriff auf USB-Geräte ohne `root`-Rechte eine udev-Regel:

1. Erstelle die Datei `/etc/udev/rules.d/99-respeaker.rules`:
   ```text
   SUBSYSTEM=="usb", ATTR{idVendor}=="2886", ATTR{idProduct}=="0018", MODE="0666"
   ```
2. Lade die udev-Regeln neu:
   ```bash
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```

---

## 🖥️ 3. GUI-Simulator startet nicht

### Symptom:
`lefx serve --sink simulator` bricht ab mit `ImportError: PySide6`.

### Lösung:
Installiere das `simulated-respeaker` Extra-Paket, welches PySide6 beinhaltet:

```powershell
pip install led-controller-version-3[simulated-respeaker]
```

---

## ❌ 4. Parameter-Validierungsfehler (HTTP 422)

### Symptom:
Beim Ausführen von `lefx set` oder einem HTTP POST-Aufruf wird ein HTTP Status 422 zurückgegeben.

### Erklärung:
LEFX V3 unterscheidet strikt zwischen statischer Konfiguration (`--config`) und dynamischen Live-Eingaben (`--inputs`):

- **`config`**: Parameter, die im `parameter_schema` des Effekts definiert sind (z. B. `color`, `brightness`, `speed`).
- **`inputs`**: Dynamic Runtime Inputs, die im `runtime_input_schema` definiert sind (z. B. `progress` bei `level_meter` oder `direction_deg` bei `direction_indicator`).

### Häufige Fehlerbeispiele & Korrekturen:

#### FALSCH:
```powershell
# Fehler: 'progress' gehört in --inputs, nicht in --config!
lefx set overlay level_meter --channel volume --config '{"progress": 0.75}'
```

#### RICHTIG:
```powershell
lefx set overlay level_meter --channel volume --config '{"color": "green"}' --inputs '{"progress": 0.75}'
```

#### UNBEKANNTE FARBE:
LEFX V3 akzeptiert Hex-Farbcodes (`#FF0000`, `#00FFCC`) oder englische/deutsche Farbnamen (`red`, `rot`, `blue`, `blau`, `green`, `grün`, `yellow`, `gelb`, `cyan`, `white`, `weiss`, `black`, `schwarz`).

---

## 🚦 5. Effekt ist auf den LEDs nicht sichtbar

1. **Ausgabe stummgeschaltet?**
   Prüfe mit `lefx status`, ob `output.enabled` auf `true` steht. Falls nicht:
   ```powershell
   lefx output --enabled true
   ```
2. **Helligkeit auf 0%?**
   ```powershell
   lefx output --brightness 0.8
   ```
3. **Überlagernde Schicht aktiv?**
   Prüfe, ob ein höheres Event oder Overlay den State verdeckt:
   ```powershell
   lefx clear all
   ```
