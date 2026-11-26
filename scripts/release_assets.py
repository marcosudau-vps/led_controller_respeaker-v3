"""Stage and verify the exact CI-built assets for the development GitHub Release.

No builds or publication take place here. The manifests bind assets to a
version and a commit and detect missing, stale or damaged downloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("release-wheels", "release-studio")
DISTRIBUTIONS = (
    "led-controller-version-3",
    "led-controller-version-3-effect-creation",
    "led-controller-version-3-device-simulated-respeaker",
)


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def studio_name(release_version: str) -> str:
    return f"lefx-studio-{release_version}-windows-x64.exe"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def wheel_names(release_version: str) -> set[str]:
    return {f"{name.replace('-', '_')}-{release_version}-py3-none-any.whl" for name in DISTRIBUTIONS}


def expected_names(group: str, release_version: str) -> set[str]:
    if group == GROUPS[0]:
        return wheel_names(release_version)
    if group == GROUPS[1]:
        return {studio_name(release_version)}
    raise ValueError(f"Unknown asset group {group}")


def validate_binary(path: Path, release_version: str) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as wheel:
            metadata = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise ValueError(f"Invalid wheel metadata: {path.name}")
            msg = BytesParser().parsebytes(wheel.read(metadata[0]))
            if msg["Version"] != release_version:
                raise ValueError(f"Wheel version mismatch: {path.name}")
            name = msg["Name"].replace("-", "_") if msg["Name"] else ""
            if path.name != f"{name}-{release_version}-py3-none-any.whl":
                raise ValueError(f"Wheel name mismatch: {path.name}")
    elif path.suffix == ".exe":
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ" or path.stat().st_size < 1024:
                raise ValueError(f"Not a Windows executable: {path.name}")
    else:
        raise ValueError(f"Unexpected asset: {path.name}")


def stage(group: str, source: Path, destination: Path, release_version: str, commit: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full Git commit SHA is required")
    if destination.exists():
        raise ValueError(f"Asset destination must be new: {destination}")
    if group == GROUPS[0]:
        paths = {path.name: path for path in source.glob("*.whl")}
        if set(paths) != expected_names(group, release_version):
            raise ValueError(f"Wrong set of wheels: {sorted(paths)}")
    elif group == GROUPS[1]:
        paths = {studio_name(release_version): source}
    else:
        raise ValueError(f"Unknown asset group {group}")
    destination.mkdir(parents=True)
    files = {}
    for name, path in sorted(paths.items()):
        target = destination / name
        shutil.copyfile(path, target)
        validate_binary(target, release_version)
        files[name] = {"size": target.stat().st_size, "sha256": sha256(target)}
    (destination / "manifest.json").write_text(
        json.dumps({"group": group, "version": release_version, "commit": commit, "files": files}, indent=2) + "\n",
        encoding="utf-8",
    )


def verify(directory: Path, release_version: str, commit: str) -> list[Path]:
    assets = []
    for group in GROUPS:
        folder = directory / group
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if (manifest["group"], manifest["version"], manifest["commit"]) != (group, release_version, commit):
            raise ValueError(f"Stale or mismatched CI manifest: {group}")
        names = expected_names(group, release_version)
        if set(manifest["files"]) != names or {p.name for p in folder.iterdir()} != names | {"manifest.json"}:
            raise ValueError(f"Unexpected or missing assets: {group}")
        for name in sorted(names):
            path = folder / name
            recorded = manifest["files"][name]
            if not path.is_file() or path.stat().st_size != recorded["size"] or sha256(path) != recorded["sha256"]:
                raise ValueError(f"Asset integrity check failed: {name}")
            validate_binary(path, release_version)
            assets.append(path)
    return assets


def download(run_id: int, directory: Path, release_version: str, commit: str, *, repository: str) -> list[Path]:
    for group in GROUPS:
        subprocess.run(
            ["gh", "run", "download", str(run_id), "--repo", repository, "--name", group,
             "--dir", str(directory / group)], check=True,
        )
    return verify(directory, release_version, commit)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("stage")
    p.add_argument("group", choices=GROUPS)
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--commit", required=True)
    p = sub.add_parser("verify")
    p.add_argument("directory", type=Path)
    p.add_argument("--commit", required=True)
    args = parser.parse_args()
    if args.action == "stage":
        stage(args.group, args.source, args.destination, version(), args.commit)
    else:
        for path in verify(args.directory, version(), args.commit):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
