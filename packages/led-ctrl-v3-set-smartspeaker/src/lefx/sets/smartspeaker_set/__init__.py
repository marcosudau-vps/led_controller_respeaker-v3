"""Where the smartspeaker set's archive is, and nothing else.

A catalogue distribution carries one file and answers one question. The
question has to be answerable without unpacking anything, because the service
asks it before it has decided to load the set at all — so this is a path, not a
reader.

The archive sits beside this module rather than in a data directory: an
installed wheel and an editable checkout then look the same, and the checkout
needs no second search path for built output.
"""

from __future__ import annotations

from pathlib import Path

SET_ID = "smartspeaker-set"
ARCHIVE_NAME = "smartspeaker-set.lefxset"


def package_file() -> Path:
    """The ``.lefxset`` this distribution ships.

    Returned whether or not it exists. In a checkout it does not until
    ``scripts/build_effects.py`` has run, and reporting a missing catalogue is
    the caller's job — a set that silently disappears is worse than one that
    says it has not been built.
    """
    return Path(__file__).resolve().parent / ARCHIVE_NAME


__all__ = ["ARCHIVE_NAME", "SET_ID", "package_file"]
