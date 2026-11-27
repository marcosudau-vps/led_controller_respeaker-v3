"""Example settings host that retains drafts until Apply or Cancel."""

from PySide6.QtWidgets import (
    QApplication, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from lefx.config_widget import (
    EventSpec, LedFeedbackConfigurator, LefxCatalogueAdapter, PreviewSession,
)


class SettingsHost(QStackedWidget):
    def __init__(self, catalogue):
        super().__init__()
        self.setWindowTitle("Host-Einstellungen")
        self.saved_rules = {"sync.done": {"emit_event": "pulse_signal"}}
        host = QWidget(self)
        layout = QVBoxLayout(host)
        self.summary = QLabel("Ein LED-Ereignis konfiguriert.", host)
        layout.addWidget(self.summary)
        button = QPushButton("LED-Effekte konfigurieren", host)
        layout.addWidget(button)
        layout.addStretch()
        self.configurator = LedFeedbackConfigurator(
            [EventSpec("sync.done", "Synchronisierung abgeschlossen"),
             EventSpec("sync.failed", "Synchronisierung fehlgeschlagen")],
            catalogue, self, rules=self.saved_rules,
            preview_factory=lambda: lambda: PreviewSession(catalogue.registry),
        )
        self.addWidget(host)
        self.addWidget(self.configurator)
        button.clicked.connect(lambda: self.setCurrentWidget(self.configurator))
        self.configurator.back_requested.connect(lambda: self.setCurrentWidget(host))
        self.configurator.applied.connect(self._applied)
        self.configurator.cancelled.connect(lambda: self.summary.setText("Entwurf verworfen."))

    def _applied(self, rules):
        self.saved_rules = rules
        self.summary.setText(f"{len(rules)} LED-Regeln übernommen.")


def main():
    app = QApplication([])
    with LefxCatalogueAdapter.installed() as catalogue:
        host = SettingsHost(catalogue)
        host.show()
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
