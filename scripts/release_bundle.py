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

DEV_REPO = "marcosudau-vps/led_controller_respeaker-v3"
PROJECTS = (
    "led-controller-version-3",
    "led-controller-version-3-effect-creation",
    "led-controller-version-3-device-simulated-respeaker",
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def expected(version: str) -> set[str]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Invalid release version: {version}")
    return {
        f"{project.replace('-', '_')}-{version}{suffix}"
        for project in PROJECTS
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    }


def file_record(path: Path) -> dict:
    return {"size": path.stat().st_size, "sha256": sha256(path)}


def verify_file(path: Path, record: dict) -> None:
    if not path.is_file() or file_record(path) != record:
        raise ValueError(f"Missing or damaged release file: {path.name}")


def validate_distribution(path: Path, version: str) -> None:
    if path.name not in expected(version):
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
    if metadata["Version"] != version or not metadata["Name"]:
        raise ValueError(f"Incorrect distribution version: {path.name}")
    prefix = metadata["Name"].replace("-", "_") + "-" + version
    if path.name not in {prefix + "-py3-none-any.whl", prefix + ".tar.gz"}:
        raise ValueError(f"Incorrect distribution name: {path.name}")


def stage(distributions: Path, tree: Path, destination: Path, version: str, commit: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Full source commit required")
    files = sorted(distributions.iterdir())
    if {p.name for p in files} != expected(version):
        raise ValueError("Expected exactly three wheels and three sdists")
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        validate_distribution(path, version)
        shutil.copyfile(path, destination / path.name)
    shutil.copyfile(tree, destination / "tree.tar.gz")
    manifest = {
        "version": version,
        "commit": commit,
        "files": {p.name: file_record(destination / p.name) for p in files},
        "tree": file_record(destination / "tree.tar.gz"),
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def load_manifest(path: Path, version: str, commit: str | None = None) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (manifest["version"] != version or not re.fullmatch(r"[0-9a-f]{40}", manifest["commit"])
            or (commit is not None and manifest["commit"] != commit)):
        raise ValueError("Handoff version or source commit does not match")
    if set(manifest["files"]) != expected(version):
        raise ValueError("Wrong set of distribution files in handoff")
    for record in [*manifest["files"].values(), manifest["tree"]]:
        if not isinstance(record["size"], int) or record["size"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise ValueError("Invalid handoff file record")
    return manifest


def verify(bundle: Path, version: str, commit: str) -> tuple[dict, list[Path]]:
    manifest = load_manifest(bundle / "manifest.json", version, commit)
    if {p.name for p in bundle.iterdir()} != expected(version) | {"tree.tar.gz", "manifest.json"}:
        raise ValueError("Unexpected or missing bundle files")
    verify_file(bundle / "tree.tar.gz", manifest["tree"])
    files = []
    for name, record in sorted(manifest["files"].items()):
        path = bundle / name
        verify_file(path, record)
        validate_distribution(path, version)
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
    (destination / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def fetch(manifest_path: Path, destination: Path, version: str) -> None:
    manifest = load_manifest(manifest_path, version)
    destination.mkdir(parents=True, exist_ok=False)
    for name, record in sorted(manifest["files"].items()):
        path = destination / name
        url = f"https://github.com/{DEV_REPO}/releases/download/v{version}/{name}"
        with urllib.request.urlopen(url, timeout=60) as response, path.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        verify_file(path, record)
        validate_distribution(path, version)
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
    args = parser.parse_args()
    if args.action == "stage":
        stage(args.distributions, args.tree, args.destination, args.version, args.commit)
    else:
        fetch(args.manifest, args.destination, args.version)


if __name__ == "__main__":
    main()
