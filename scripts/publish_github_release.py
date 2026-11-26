"""Publish the development GitHub Release from the exact successful main CI run.

Run only after the release tag exists. No compilation or PyPI uploads here.
A failed upload leaves a draft; re-running the workflow can finish it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from release_assets import download, sha256, version

REPOSITORY = "marcosudau-vps/led_controller_respeaker-v3"


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8").strip()


def successful_run(commit: str) -> int:
    runs = json.loads(gh(
        "run", "list", "--repo", REPOSITORY, "--workflow", "ci.yml",
        "--event", "push", "--branch", "main", "--commit", commit,
        "--limit", "20", "--json", "databaseId,headSha,status,conclusion",
    ))
    for run in runs:
        if run["headSha"] == commit and run["status"] == "completed" and run["conclusion"] == "success":
            return int(run["databaseId"])
    raise RuntimeError(f"No successful main CI run for {commit}")


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
    if set(remote) != set(expected):
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


def publish(tag: str, *, verify_only: bool = False) -> None:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or tag != f"v{version()}":
        raise RuntimeError("Tag does not match the checked-out package version")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    tagged_commit = subprocess.check_output(["git", "rev-parse", f"{tag}^{{commit}}"], text=True).strip()
    if commit != tagged_commit:
        raise RuntimeError("Checked-out commit is not the tag's commit")
    run_id = successful_run(commit)
    with tempfile.TemporaryDirectory(prefix="lefx-github-release-") as temp:
        assets = download(run_id, Path(temp), version(), commit, repository=REPOSITORY)
        if verify_only:
            print(f"Verified all pre-tag CI assets for {tag} (run {run_id})")
            return
        record = release_record(tag)
        if record and not record["draft"]:
            verify_uploaded(record, assets)
            print(f"{tag} is already public with the checked assets")
            return
        if not record:
            gh("release", "create", tag, "--repo", REPOSITORY, "--verify-tag",
               "--draft", "--title", f"LEFX {version()}", "--generate-notes")
        gh("release", "upload", tag, *map(str, assets), "--repo", REPOSITORY, "--clobber")
        record = release_record(tag)
        if not record or not record["draft"]:
            raise RuntimeError("Expected the GitHub Release to remain a draft during verification")
        verify_uploaded(record, assets)
        gh("release", "edit", tag, "--repo", REPOSITORY, "--draft=false")
        print(f"Published {tag} from CI run {run_id}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--verify-only"):
        raise SystemExit("usage: publish_github_release.py vX.Y.Z [--verify-only]")
    publish(sys.argv[1], verify_only=len(sys.argv) == 3)
