"""Writing what the studio produced back into a source tree.

The studio plays *built* packages — that is what the engine loads — but a preset
worth keeping belongs in the source the package was built from, or it survives
only until the next build. So the one thing this has to do is find its way back:
from an effect id in a loaded catalogue to the directory its source lives in.

That link is not recorded anywhere, because nothing in the running system needs
it. It is recovered by looking: a source directory is named after the definition
it contains, and the catalogue tests enforce that. Where the search finds
nothing, the studio asks rather than guesses.

No Qt here. Deciding what to write and writing it are separable from the dialog
that collects it, and only the dialog needs a toolkit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from lefx.effect_creation import SourceError, load_effect_source, validate_effect_source
from lefx.sdk import DefinitionBase, resolve_configuration

DEFAULT_SOURCE_ROOTS = ("effects",)
"""Only a fallback. The studio passes the project's own roots, because a
standalone build has no useful working directory to be relative to."""
PRESET_FILE = "presets.yaml"

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _SLUG.sub("_", text.strip().casefold()).strip("_")


def suggest_preset_id(effect_id: str, label: str) -> str:
    """A preset id derived from a human label.

    Prefixed with the definition's id because presets share one namespace with
    every other source's, and a preset called ``warm`` would be a collision
    waiting for the second catalogue that has one.
    """
    slug = slugify(label)
    if not slug:
        return effect_id
    return slug if slug.startswith(f"{effect_id}_") or slug == effect_id else f"{effect_id}_{slug}"


def find_source_dir(
    effect_id: str, roots: Iterable[str | Path] = DEFAULT_SOURCE_ROOTS
) -> Path | None:
    """Where the source for this definition lives, if it can be found.

    Matched on the directory name and then confirmed by loading the manifest, so
    a directory that merely happens to share a name is not mistaken for it.
    """
    for root in roots:
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        for candidate in sorted(base.rglob(f"sources/**/{effect_id}")):
            if not candidate.is_dir():
                continue
            try:
                load_effect_source(candidate)
            except SourceError:
                continue
            return candidate
    return None


@dataclass(slots=True, frozen=True)
class PresetDraft:
    """A preset as the studio has it, before it is written anywhere."""

    effect_id: str
    preset_id: str
    title: str
    description: str
    params: Mapping[str, Any]

    def to_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"params": dict(self.params)}
        if self.title:
            entry["title"] = self.title
        if self.description:
            entry["description"] = self.description
        return entry


def check_draft(definition: DefinitionBase, draft: PresetDraft) -> list[str]:
    """Everything wrong with a draft, in the words a person can act on.

    Checked here rather than left to the build, because the build happens later
    and somewhere else. The rules are the ones the source validator applies —
    stated twice, but the second statement is the one that catches it while the
    values are still on screen.
    """
    problems: list[str] = []
    if not draft.preset_id:
        problems.append("Ein Preset braucht eine Kennung.")
    elif not draft.preset_id.startswith(definition.id):
        problems.append(
            f"Die Kennung muss mit {definition.id!r} beginnen — Presets teilen sich "
            "einen Namensraum über alle Quellen hinweg."
        )
    elif draft.preset_id != slugify(draft.preset_id):
        problems.append("Nur Kleinbuchstaben, Ziffern und Unterstriche.")

    try:
        resolve_configuration(definition, preset=dict(draft.params))
    except Exception as exc:
        problems.append(f"Die Werte passen nicht zum Schema: {exc}")
    return problems


def read_presets(source_dir: str | Path) -> dict[str, Any]:
    return load_effect_source(source_dir).presets()


def write_preset(source_dir: str | Path, draft: PresetDraft, *, overwrite: bool = False) -> Path:
    """Merge one preset into a source's ``presets.yaml``, leaving the rest alone.

    Rewritten wholesale from the parsed content rather than appended to, so the
    file stays a valid document whatever it looked like before. What that costs
    is comment formatting in a file nobody hand-edits often; what it buys is
    that a half-written append can never produce one that will not load.
    """
    root = Path(source_dir).expanduser().resolve()
    source = load_effect_source(root)
    existing = source.presets()

    if draft.preset_id in existing and not overwrite:
        raise SourceError(f"{draft.preset_id!r} already exists in {root}")

    existing[draft.preset_id] = draft.to_entry()
    target = source.presets_path or (root / PRESET_FILE)
    target.write_text(
        yaml.safe_dump({"presets": dict(sorted(existing.items()))}, allow_unicode=True,
                       sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return target


def write_preset_checked(
    definition: DefinitionBase,
    source_dir: str | Path,
    draft: PresetDraft,
    *,
    overwrite: bool = False,
) -> Path:
    """Write it, then hold the whole source to the validator it will face later.

    A source that stops validating is worse than a preset that was never
    written, so if the result does not pass, the file goes back the way it was.
    """
    root = Path(source_dir).expanduser().resolve()
    source = load_effect_source(root)
    target = source.presets_path or (root / PRESET_FILE)
    before = target.read_text(encoding="utf-8") if target.is_file() else None

    problems = check_draft(definition, draft)
    if problems:
        raise SourceError("; ".join(problems))

    write_preset(root, draft, overwrite=overwrite)
    report = validate_effect_source(root)
    if not report.ok:
        if before is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(before, encoding="utf-8")
        raise SourceError(
            f"{root.name} would no longer validate: " + "; ".join(report.errors)
        )
    return target


__all__ = [
    "DEFAULT_SOURCE_ROOTS",
    "PRESET_FILE",
    "PresetDraft",
    "check_draft",
    "find_source_dir",
    "read_presets",
    "slugify",
    "suggest_preset_id",
    "write_preset",
    "write_preset_checked",
]
