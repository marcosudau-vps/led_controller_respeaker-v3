# Voice STT Client V2

Der Client besitzt den Ereigniskatalog, den Feedback-Reducer und die Persistenz. Leite `EventSpec` aus den tatsächlich angebotenen V2-Ereignissen des Hosts ab. Die Zuordnung unterstützt `set_state`, `clear_state`, zeitgesteuertes `set_overlay`, `emit_event` und `set_output`. Gesteuerte Overlays gehören zur separaten Live-Steuerung des Hosts. Persistente Zustände und einmalige Impulse bleiben als unterschiedliche Aufrufarten erkennbar.

```python
from lefx.config_widget import FeedbackDocument, HostCapabilities, LedFeedbackConfigurator

document = FeedbackDocument(config["feedback_mappings"])
state = {"document": document}
events = [event for event in host_event_specs if event.id not in document.opaque_events()]
widget = LedFeedbackConfigurator(
    events,
    catalogue,
    rules=document.led_rules(),
    capabilities=HostCapabilities.voice_stt(),
)

def apply_led_rules(rules):
    updated_section = state["document"].with_led_rules(rules)
    persist_feedback_section(updated_section)  # Host übernimmt Validierung und Speicherung
    state["document"] = FeedbackDocument(updated_section)

widget.applied.connect(apply_led_rules)
```

`FeedbackDocument` erwartet `schema_version: 2` und `events` als Mapping. Gib an `with_led_rules` den vollständigen LED-Snapshot zurück. Eine geänderte LED-Regel ersetzt ausschließlich ihren `led`-Wert. `sound`, `app`, übrige Daten, Eventreihenfolge, vorhandene Nullwerte und unveränderte Single-/List-Formen bleiben in den Daten erhalten. YAML-Kommentare und Dateiformatierung verwaltet der Host. `opaque_events()` zeigt Event-IDs an, deren gesamte Regel eine unbekannte Form hat. Solche Ereignisse bleiben über den Adapter erhalten.

Die Voice-STT-Fähigkeiten verwenden `primary` für einen ausgelassenen State-Slot und beschränken eine äußere Impulsdauer auf 1–60000 ms. Ob der einzelne Effekt überhaupt eine äußere Dauer gestattet, entscheidet der LEFX-Vertrag.

Die Anpassung an ein anderes Host-Framework erfolgt über dessen Ereignis- und Persistenzadapter. Generische Qt-Widgets können als einzelne Quellen übernommen werden. Das Paket erfordert weder den Voice-STT-Client noch das Dynamic Settings Widget als Abhängigkeit.

Der geprüfte Client-Referenzstand pinnt historisch LEFX 3.0.3. Der Configurator und der LEFX-Kern teilen einen exakten Versions-Pin. Der Entwicklungsstand der Integration ist 3.0.4. Bevor der Client das Wheel integriert, muss seine eigene Abhängigkeitsauflösung eine gemeinsame LEFX-Version vorsehen. [Voice-STT-Referenzcommit](https://github.com/marcosudau-vps/voice-stt-client/tree/0574ba94fd9f0876297288cbcdb55a650b7cee74)
