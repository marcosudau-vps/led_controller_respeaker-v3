"""GitHub Release asset publication helpers for the gated server workflow."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from release_bundle import sha256
from release_contract import DEV_REPO as REPOSITORY


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8").strip()


def release_record(tag: str) -> dict | None:
    pages = json.loads(gh(
        "api", f"repos/{REPOSITORY}/releases?per_page=100", "--paginate", "--slurp",
    ))
    matches = [item for page in pages for item in page if item["tag_name"] == tag]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple GitHub releases for {tag}")
    return matches[0] if matches else None


def verify_uploaded(record: dict, assets: list[Path]) -> None:
    """Check remote bytes, not just filenames. Existing public releases are immutable here."""
    expected = {p.name: p for p in assets}
    remote = {a["name"]: a for a in record["assets"]}
    if (set(remote) != set(expected) or len(remote) != len(record["assets"])
            or len(expected) != len(assets)):
        raise RuntimeError("GitHub Release asset names differ from the checked CI assets")
    with tempfile.TemporaryDirectory(prefix="lefx-upload-check-") as temp:
        for name, local in expected.items():
            entry = remote[name]
            if entry["size"] != local.stat().st_size:
                raise RuntimeError(f"Upload size mismatch: {name}")
            digest = entry.get("digest")
            if digest:
                if digest != f"sha256:{sha256(local)}":
                    raise RuntimeError(f"Upload digest mismatch: {name}")
            else:
                target = Path(temp) / name
                with target.open("wb") as stream:
                    subprocess.run([
                        "gh", "api", f"repos/{REPOSITORY}/releases/assets/{entry['id']}",
                        "-H", "Accept: application/octet-stream",
                    ], stdout=stream, check=True)
                if sha256(target) != sha256(local):
                    raise RuntimeError(f"Upload content mismatch: {name}")


def publish_assets(tag: str, assets: list[Path]) -> None:
    """Only call after the tag and exact candidate assets have been verified."""
    record = release_record(tag)
    if record and not record["draft"]:
        verify_uploaded(record, assets)
        return
    if not record:
        gh("release", "create", tag, "--repo", REPOSITORY, "--verify-tag",
           "--draft", "--title", f"LEFX {tag[1:]}", "--generate-notes")
    gh("release", "upload", tag, *map(str, assets), "--repo", REPOSITORY, "--clobber")
    record = release_record(tag)
    if not record or not record["draft"]:
        raise RuntimeError("Expected the GitHub Release to remain a draft during verification")
    verify_uploaded(record, assets)
    gh("release", "edit", tag, "--repo", REPOSITORY, "--draft=false")
