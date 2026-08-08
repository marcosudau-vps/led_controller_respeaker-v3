"""Shared setup for the studio tests."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def built_catalogue(tmp_path_factory):
    """The shipped sets, built once, so the studio meets the real thing."""
    import sys

    from tests.architecture.scan import REPO_ROOT

    output = tmp_path_factory.mktemp("catalogue")
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from build_effects import build_set
    finally:
        sys.path.pop(0)

    for name in ("core-set", "smartspeaker-set"):
        build_set(REPO_ROOT / "effects" / name, output_root=output)
    return output
