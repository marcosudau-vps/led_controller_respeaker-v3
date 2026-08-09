"""Repository-wide pytest setup.

One thing only, and it is here rather than in ``tests/`` because it has to run
before the first fixture asks for a temporary directory.

``--basetemp=tests/.cache/tmp`` in the addopts keeps scratch files inside the
checkout, because the system temp directory is not reliably reachable on every
machine this runs on. But pytest creates that directory without creating its
parents, and ``tests/.cache/`` is gitignored — so on a fresh clone, which is
what a CI runner always is, the first test to ask for ``tmp_path`` fails with
FileNotFoundError and takes several hundred others with it. It passes on any
machine that has run the suite before, which is every machine a person
develops on.
"""

from __future__ import annotations

from pathlib import Path

BASETEMP = Path(__file__).resolve().parent / "tests" / ".cache" / "tmp"


def pytest_configure(config) -> None:
    del config
    BASETEMP.mkdir(parents=True, exist_ok=True)
