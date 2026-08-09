"""Reading source files as structure rather than as text.

Both checks in this package ask a question about what the code *does*, and both
would produce nonsense if asked of the characters in the file: a comment
explaining that a frame may end up on a simulator is not a dependency on one,
and a docstring naming a term precisely because it is forbidden is not that term
coming back.

So imports come from import nodes, and names and values come from the syntax
tree with docstrings left out. Nothing here needs to resolve a name or follow a
call — an AST walk is enough, and anything more would be a second implementation
of the import system living in the test suite.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"


def distributions() -> list[str]:
    return sorted(
        path.name for path in PACKAGES_ROOT.iterdir() if (path / "pyproject.toml").is_file()
    )


def source_files(distribution: str) -> list[Path]:
    return sorted((PACKAGES_ROOT / distribution / "src").rglob("*.py"))


def layers() -> dict[str, Path]:
    """Every module layer in the workspace, by import name.

    A layer is the unit the dependency rules are written about — ``lefx.sdk``,
    ``lefx.engine``, ``lefx.device.respeaker``. It used to be the same thing as
    a distribution, and the rules could be stated in terms of package names.
    They no longer are: four layers and both catalogues ship in one
    distribution now, so a rule phrased as "led-ctrl-v3 may import
    led-ctrl-v3" would permit everything and forbid nothing.

    Found by walking, not listed: a directory under ``src/lefx`` with an
    ``__init__.py`` is a layer, and one without is a PEP 420 namespace to
    descend into — which is exactly how the import system reads the same tree.
    """
    found: dict[str, Path] = {}
    for distribution in distributions():
        root = PACKAGES_ROOT / distribution / "src" / "lefx"
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name == "__pycache__":
                continue
            if (child / "__init__.py").is_file():
                found[f"lefx.{child.name}"] = child
                continue
            for grandchild in sorted(child.iterdir()):
                if grandchild.is_dir() and (grandchild / "__init__.py").is_file():
                    found[f"lefx.{child.name}.{grandchild.name}"] = grandchild
    return found


def distribution_of(layer: str) -> str:
    """Which distribution ships a layer: packages/<here>/src/lefx/..."""
    path = layers()[layer]
    return path.relative_to(PACKAGES_ROOT).parts[0]


def layer_files(layer: str) -> list[Path]:
    return sorted(layers()[layer].rglob("*.py"))


def parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.AST) -> set[str]:
    """Every module name this file names in an import, dotted form kept.

    ``from lefx import engine`` and ``import lefx.engine`` differ only in
    spelling, so both are recorded as ``lefx.engine``. Relative imports stay
    inside their own package by definition and are not interesting here.

    ``importlib.import_module("lefx.engine")`` is picked up as well: naming a
    module in a string rather than in an import statement is still importing it,
    and it is the one form that would otherwise slip past.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
                continue
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            found.update(_dynamic_import_target(node))
    return found


def _dynamic_import_target(node: ast.Call) -> set[str]:
    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
    if name not in {"import_module", "__import__"}:
        return set()
    return {
        argument.value
        for argument in node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    }


def code_strings_and_names(tree: ast.AST) -> set[str]:
    """String values and identifiers a module actually uses, docstrings aside.

    Prose is not code. A file is free to explain what it deliberately does not
    do, and a rule that could not tell the difference would be answered by
    rewording the explanation.
    """
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                found.add(node.value)
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return found


__all__ = [
    "PACKAGES_ROOT",
    "REPO_ROOT",
    "code_strings_and_names",
    "distribution_of",
    "distributions",
    "imported_modules",
    "layer_files",
    "layers",
    "parse",
    "source_files",
]
