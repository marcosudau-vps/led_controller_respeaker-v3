"""Open a single effect editor and return the accepted overrides to the host."""

from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout,
)

from lefx.config_widget import EffectEditor, LefxCatalogueAdapter


def main():
    app = QApplication([])
    with LefxCatalogueAdapter.installed() as catalogue:
        dialog = QDialog()
        dialog.setWindowTitle("Farbverlauf konfigurieren")
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        editor = EffectEditor(catalogue.resolve("core-set::gradient_ring"))
        scroll.setWidget(editor)
        layout.addWidget(scroll)
        status = QLabel(dialog)
        status.setWordWrap(True)
        layout.addWidget(status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        layout.addWidget(buttons)

        def apply():
            if diagnostics := editor.validate():
                status.setText("\n".join(map(str, diagnostics)))
            else:
                dialog.accept()

        buttons.accepted.connect(apply)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            print("Explizite Parameter:", editor.value())
            print("Aufgelöste Werte:", editor.resolved_config())
    app.quit()


if __name__ == "__main__":
    main()
