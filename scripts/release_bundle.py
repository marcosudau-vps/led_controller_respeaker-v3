"""Build the immutable PyPI handoff from already tested distributions.

This module also ships in the release repository. There it downloads the
exact pre-tag files from the public development GitHub Release, verifies
them against the mirrored manifest, and never invokes a build backend.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import tomllib
import urllib.request
import zipfile
from email.parser import BytesParser
from pathlib import Path

from release_contract import (
    CURRENT, DEV_REPO, artifact_filenames, build_projects, canonical_name,
    release_projects, workspace_projects,
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def expected(version: str, commit: str) -> set[str]:
    return artifact_filenames(version, release_projects(version, commit))


def file_record(path: Path) -> dict:
    return {"size": path.stat().st_size, "sha256": sha256(path)}


def verify_file(path: Path, record: dict) -> None:
    if not path.is_file() or file_record(path) != record:
        raise ValueError(f"Missing or damaged release file: {path.name}")


def validate_distribution(path: Path, version: str, projects=CURRENT) -> None:
    if path.name not in artifact_filenames(version, projects):
        raise ValueError(f"Unexpected distribution: {path.name}")
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(members) != 1:
                raise ValueError(f"Invalid wheel metadata: {path.name}")
            data = archive.read(members[0])
    else:
        with tarfile.open(path, "r:gz") as archive:
            members = [m for m in archive.getmembers() if m.isfile()
                       and len(Path(m.name).parts) == 2 and m.name.endswith("/PKG-INFO")]
            if len(members) != 1:
                raise ValueError(f"Invalid sdist metadata: {path.name}")
            with archive.extractfile(members[0]) as stream:
                data = stream.read()
    metadata = BytesParser().parsebytes(data)
    if metadata.get_all("Version") != [version]:
        kind = "Wheel" if path.suffix == ".whl" else "Sdist"
        raise ValueError(f"{kind} version mismatch: {path.name}")
    names = metadata.get_all("Name", [])
    if len(names) != 1 or not re.fullmatch(r"[A-Za-z0-9]+(?:[-_.]+[A-Za-z0-9]+)*", names[0]):
        raise ValueError(f"Invalid distribution name metadata: {path.name}")
    prefix = canonical_name(names[0]).replace("-", "_") + "-" + version
    if path.name not in {prefix + "-py3-none-any.whl", prefix + ".tar.gz"}:
        raise ValueError(f"Incorrect distribution name: {path.name}")


def stage(distributions: Path, tree: Path, destination: Path, version: str, commit: str) -> None:
    projects = build_projects(version, commit)
    wanted = artifact_filenames(version, projects)
    # uv may create a .gitignore in the output directory. It is not a
    # distribution and must not enter the sealed bundle.
    files = sorted(path for path in distributions.iterdir() if path.name != ".gitignore")
    names = {path.name for path in files}
    if names != wanted:
        raise ValueError(f"Distribution set mismatch: missing={sorted(wanted - names)}, extra={sorted(names - wanted)}")
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        validate_distribution(path, version, projects)
        shutil.copyfile(path, destination / path.name)
    shutil.copyfile(tree, destination / "tree.tar.gz")
    manifest = {
        "version": version,
        "commit": commit,
        "files": {p.name: file_record(destination / p.name) for p in files},
        "tree": file_record(destination / "tree.tar.gz"),
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def validate_manifest(manifest: dict, version: str, commit: str) -> None:
    wanted = expected(version, commit)
    if (manifest["version"], manifest["commit"]) != (version, commit):
        raise ValueError("Handoff version or source commit does not match")
    if set(manifest["files"]) != wanted:
        raise ValueError("Wrong set of distribution files in handoff")
    for record in [*manifest["files"].values(), manifest["tree"]]:
        if (set(record) != {"size", "sha256"} or type(record["size"]) is not int or record["size"] <= 0
                or not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
            raise ValueError("Invalid handoff file record")


def load_manifest(path: Path, version: str, commit: str) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest, version, commit)
    return manifest


def verify(bundle: Path, version: str, commit: str) -> tuple[dict, list[Path]]:
    manifest = load_manifest(bundle / "manifest.json", version, commit)
    if {p.name for p in bundle.iterdir()} != expected(version, commit) | {"tree.tar.gz", "manifest.json"}:
        raise ValueError("Unexpected or missing bundle files")
    verify_file(bundle / "tree.tar.gz", manifest["tree"])
    files = []
    projects = release_projects(version, commit)
    for name, record in sorted(manifest["files"].items()):
        path = bundle / name
        verify_file(path, record)
        validate_distribution(path, version, projects)
        files.append(path)
    return manifest, files


def unpack_tree(bundle: Path, destination: Path, version: str, commit: str) -> None:
    manifest, _ = verify(bundle, version, commit)
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(bundle / "tree.tar.gz", "r:gz") as archive:
        members = archive.getmembers()
        if any(not (m.isfile() or m.isdir()) or ".git" in Path(m.name).parts for m in members):
            raise ValueError("Unexpected special file in release tree")
        archive.extractall(destination, filter="data")
    root_version = tomllib.loads((destination / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if root_version != version or not (destination / ".github/workflows/release.yml").is_file():
        raise ValueError("Incorrect release tree")
    if release_projects(version, commit) == CURRENT:
        workspace_projects(destination)
        for name in ("check_release.py", "release_bundle.py", "release_contract.py"):
            if not (destination / "scripts" / name).is_file():
                raise ValueError(f"Missing release script in materialized tree: {name}")
    (destination / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def fetch(manifest_path: Path, destination: Path, version: str, commit: str) -> None:
    manifest = load_manifest(manifest_path, version, commit)
    projects = release_projects(version, commit)
    destination.mkdir(parents=True, exist_ok=False)
    for name, record in sorted(manifest["files"].items()):
        path = destination / name
        url = f"https://github.com/{DEV_REPO}/releases/download/v{version}/{name}"
        with urllib.request.urlopen(url, timeout=60) as response, path.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        verify_file(path, record)
        validate_distribution(path, version, projects)
        print(f"Verified {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("stage")
    p.add_argument("distributions", type=Path)
    p.add_argument("tree", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--version", required=True)
    p.add_argument("--commit", required=True)
    p = sub.add_parser("fetch")
    p.add_argument("manifest", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--version", required=True)
    p.add_argument("--commit", required=True)
    args = parser.parse_args()
    if args.action == "stage":
        stage(args.distributions, args.tree, args.destination, args.version, args.commit)
    else:
        fetch(args.manifest, args.destination, args.version, args.commit)


if __name__ == "__main__":
    main()
