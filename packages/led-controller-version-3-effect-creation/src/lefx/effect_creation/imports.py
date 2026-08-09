"""The import boundary that keeps packages self-contained.

A package must build, ship and load on its own. It may use the standard library
and the SDK, and it may import its own local modules — nothing else. Reaching
into the engine, the service, or another package would mean the archive is not
actually the unit it claims to be.

There is deliberately no shared effect library. A ``common.py`` sitting beside
several definitions is the shape this always takes, and it is exactly what makes
packages stop being independently installable.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

ALLOWED_STDLIB: frozenset[str] = frozenset(
    {
        "__future__",
        "abc",
        "bisect",
        "cmath",
        "collections",
        "colorsys",
        "dataclasses",
        "enum",
        "fractions",
        "functools",
        "hashlib",
        "itertools",
        "math",
        "numbers",
        "operator",
        "random",
        "statistics",
        "types",
        "typing",
    }
)

ALLOWED_ROOTS: frozenset[str] = frozenset({"lefx.sdk"})

FORBIDDEN_MODULE_NAMES: frozenset[str] = frozenset({"common", "shared", "utils", "helpers"})


@dataclass(slots=True, frozen=True)
class ImportViolation:
    file: str
    line: int
    module: str
    reason: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.module} — {self.reason}"


def _is_allowed(module: str) -> tuple[bool, str]:
    root = module.split(".", 1)[0]
    if module in ALLOWED_ROOTS or module.startswith("lefx.sdk."):
        return True, ""
    # Every part of this system now lives under ``lefx.``, so one rule covers
    # the engine, the control surface and both device packages: a definition
    # names the authoring contract and nothing else, which is what lets the same
    # source run against hardware, against the simulator, or inside the studio.
    if root == "lefx":
        return False, "only lefx.sdk is available to a package; nothing else in lefx is importable"
    if root in ALLOWED_STDLIB:
        return True, ""
    return False, "not in the allowed standard library subset or the LEFX SDK"


def check_imports(root: Path) -> list[ImportViolation]:
    """Every import in every Python file of the source, checked against the list."""
    violations: list[ImportViolation] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if path.stem in FORBIDDEN_MODULE_NAMES:
            violations.append(
                ImportViolation(
                    file=relative,
                    line=0,
                    module=path.stem,
                    reason=(
                        "generic shared modules are not allowed; give the module a "
                        "concrete name describing what this definition does with it"
                    ),
                )
            )
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(
                ImportViolation(file=relative, line=exc.lineno or 0, module="", reason=str(exc))
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    allowed, reason = _is_allowed(alias.name)
                    if not allowed:
                        violations.append(
                            ImportViolation(relative, node.lineno, alias.name, reason)
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    # Relative imports stay inside the source; that is the point.
                    continue
                module = node.module or ""
                allowed, reason = _is_allowed(module)
                if not allowed:
                    violations.append(ImportViolation(relative, node.lineno, module, reason))
    return violations


def find_effect_classes(path: Path) -> list[str]:
    """Names of classes defined in this file that derive from ``BaseEffect``.

    Read from the syntax tree rather than by importing, so a source with a
    layout problem still gives a useful message instead of an import traceback.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseEffect":
                names.append(node.name)
            elif isinstance(base, ast.Attribute) and base.attr == "BaseEffect":
                names.append(node.name)
    return names


__all__ = [
    "ALLOWED_ROOTS",
    "ALLOWED_STDLIB",
    "ImportViolation",
    "check_imports",
    "find_effect_classes",
]
