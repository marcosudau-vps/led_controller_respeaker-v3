"""Atomic design storage and data-only, bounded package re-opening."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

from lefx.engine.packages import HASHES_NAME

from .blocks import DesignError
from .model import validate

PROJECT_MEMBER = "payload/studio/project.json"
MAX_DESIGN_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024


def canonical(document):
    return json.dumps(validate(document), sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def digest(document):
    return hashlib.sha256(canonical(document)).hexdigest()


def _pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise DesignError(f"Doppeltes JSON-Feld {name!r}.")
        result[name] = value
    return result


def decode(data):
    if len(data) > MAX_DESIGN_BYTES:
        raise DesignError("Studio-Entwurf ist zu groß (maximal 2 MiB).")
    try:
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(DesignError(f"Ungültige Zahl {value}.")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise DesignError(f"Ungültiges Studio-JSON: {exc}") from exc


def atomic_write(path, data):
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def save(document, path):
    data = canonical(document)
    if len(data) > MAX_DESIGN_BYTES:
        raise DesignError("Studio-Entwurf ist zu groß (maximal 2 MiB).")
    return atomic_write(path, data)


def load(path):
    target = Path(path)
    try:
        if target.suffix.lower() == ".lefx":
            return load_package_design(target)
        with target.open("rb") as stream:
            return validate(decode(stream.read(MAX_DESIGN_BYTES + 1)))
    except (OSError, TypeError, KeyError, RecursionError) as exc:
        raise DesignError(f"Entwurf konnte nicht gelesen werden: {exc}") from exc


def load_package_design(path):
    """Never import or extract executable package contents to read a design."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) > 4096 or len(names) != len(set(names)):
                raise DesignError("Paket enthält zu viele oder doppelte ZIP-Einträge.")
            if sum(entry.file_size for entry in entries) > MAX_PACKAGE_BYTES:
                raise DesignError("Paket ist zu groß für den Studioimport (32 MiB).")
            if PROJECT_MEMBER not in names:
                raise DesignError("Dieses LEFX-Paket enthält keinen bearbeitbaren Studio-Entwurf.")
            if archive.getinfo(PROJECT_MEMBER).file_size > MAX_DESIGN_BYTES:
                raise DesignError("Studio-Entwurf ist zu groß.")
            hashes = decode(archive.read(HASHES_NAME))
            if not isinstance(hashes, dict) or not isinstance(hashes.get("files"), dict):
                raise DesignError("Ungültiges Pakethash-Verzeichnis.")
            recorded = hashes["files"]
            if set(recorded) != set(names) - {HASHES_NAME}:
                raise DesignError("Pakethash-Verzeichnis ist unvollständig.")
            for name, expected in recorded.items():
                if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                    raise DesignError(f"Pakethash stimmt nicht: {name}.")
            return validate(decode(archive.read(PROJECT_MEMBER)))
    except (OSError, zipfile.BadZipFile, KeyError, TypeError, RecursionError) as exc:
        raise DesignError(f"Studio-Entwurf konnte nicht aus dem Paket gelesen werden: {exc}") from exc
