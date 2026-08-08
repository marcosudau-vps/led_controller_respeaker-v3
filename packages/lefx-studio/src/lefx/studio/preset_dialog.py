"""Turning what is on screen into a preset in the source tree.

The values are already there — somebody just spent ten minutes arriving at them.
What is missing is a name, a sentence about when to use it, and somewhere to put
it, and only the last of those is a question the studio can partly answer for
itself.

Everything the dialog decides is checked before it is offered: the id it
proposes, whether it collides, whether the values still satisfy the schema. A
dialog that accepted and then failed on write would have collected the same
information twice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lefx.authoring import SourceError
from lefx.sdk import DefinitionBase

from .authoring import (
    PresetDraft,
    check_draft,
    find_source_dir,
    read_presets,
    suggest_preset_id,
    write_preset_checked,
)


class PresetDialog(QDialog):
    """Name the current parameters and write them into the effect's source."""

    def __init__(
        self,
        definition: DefinitionBase,
        params: Mapping[str, Any],
        parent: QWidget | None = None,
        *,
        source_roots: "list[Path] | None" = None,
    ) -> None:
        super().__init__(parent)
        self.definition = definition
        self.params = dict(params)
        self.source_roots = source_roots
        self.written: Path | None = None
        self.overwrite = False

        self.setWindowTitle("Als Preset sichern")
        self.setMinimumWidth(520)
        self._build()
        found = find_source_dir(definition.id, source_roots or ("effects",))
        self.source_dir.setText(str(found or ""))
        self._revalidate()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.label = QLineEdit()
        self.label.setPlaceholderText("z. B. Ruhiges Blau")
        self.label.textChanged.connect(self._on_label_changed)
        form.addRow("Bezeichnung", self.label)

        self.preset_id = QLineEdit()
        self.preset_id.setPlaceholderText(f"{self.definition.id}_…")
        self.preset_id.textEdited.connect(self._revalidate)
        form.addRow("Kennung", self.preset_id)

        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("Wofür ist das gedacht?")
        self.description.setMaximumHeight(72)
        form.addRow("Beschreibung", self.description)

        row = QHBoxLayout()
        self.source_dir = QLineEdit()
        self.source_dir.setPlaceholderText("Quellverzeichnis des Effekts")
        self.source_dir.textChanged.connect(self._revalidate)
        browse = QPushButton("…")
        browse.setFixedWidth(32)
        browse.clicked.connect(self._browse)
        row.addWidget(self.source_dir, stretch=1)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Quelle", holder)
        layout.addLayout(form)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.problems = QLabel("")
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet("color: #d76;")
        layout.addWidget(self.problems)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    # -- keeping the dialog honest -----------------------------------------

    def _on_label_changed(self, text: str) -> None:
        # The id follows the label until somebody types one, then it is theirs.
        if not self.preset_id.isModified():
            self.preset_id.setText(suggest_preset_id(self.definition.id, text))
        self._revalidate()

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Quellverzeichnis wählen")
        if chosen:
            self.source_dir.setText(chosen)

    def draft(self) -> PresetDraft:
        return PresetDraft(
            effect_id=self.definition.id,
            preset_id=self.preset_id.text().strip(),
            title=self.label.text().strip(),
            description=self.description.toPlainText().strip(),
            params=self.params,
        )

    def _revalidate(self) -> None:
        draft = self.draft()
        problems = check_draft(self.definition, draft)

        directory = self.source_dir.text().strip()
        existing: dict[str, Any] = {}
        if not directory:
            problems.append(
                f"Kein Quellverzeichnis für {self.definition.id!r} gefunden — bitte auswählen."
            )
        else:
            try:
                existing = read_presets(directory)
            except SourceError as exc:
                problems.append(str(exc))

        self.overwrite = draft.preset_id in existing
        if self.overwrite:
            self.summary.setText(
                f"{len(self.params)} Parameter · {draft.preset_id} ist vorhanden "
                "und wird überschrieben."
            )
        else:
            self.summary.setText(
                f"{len(self.params)} Parameter · {len(existing)} Presets bereits in dieser Quelle."
            )

        self.problems.setText("\n".join(problems))
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(not problems)

    def _save(self) -> None:
        try:
            self.written = write_preset_checked(
                self.definition,
                self.source_dir.text().strip(),
                self.draft(),
                overwrite=self.overwrite,
            )
        except SourceError as exc:
            # The source was put back the way it was; say what happened and let
            # the values stay on screen rather than closing over the problem.
            self.problems.setText(str(exc))
            return
        self.accept()


__all__ = ["PresetDialog"]
