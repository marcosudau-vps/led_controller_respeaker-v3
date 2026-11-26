"""Release gates must fail closed, before the version tag is created."""
from __future__ import annotations

import importlib
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SHA = "a" * 40
VERSION = "3.0.4"


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return tuple(importlib.import_module(name) for name in (
        "release_assets", "release", "publish_github_release"
    ))


def create_assets(tmp_path, assets):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    for name in assets.DISTRIBUTIONS:
        normalized = name.replace("-", "_")
        with zipfile.ZipFile(wheels / f"{normalized}-{VERSION}-py3-none-any.whl", "w") as archive:
            archive.writestr(
                f"{normalized}-{VERSION}.dist-info/METADATA",
                f"Metadata-Version: 2.4\nName: {name}\nVersion: {VERSION}\n",
            )
    exe = tmp_path / "studio.exe"
    exe.write_bytes(b"MZ" + b"\x00" * 2048)
    directory = tmp_path / "download"
    assets.stage("release-wheels", wheels, directory / "release-wheels", VERSION, SHA)
    assets.stage("release-studio", exe, directory / "release-studio", VERSION, SHA)
    return directory


def test_all_four_assets_verified(tmp_path, modules):
    assets, _, _ = modules
    directory = create_assets(tmp_path, assets)
    assert {p.name for p in assets.verify(directory, VERSION, SHA)} == (
        assets.wheel_names(VERSION) | {assets.studio_name(VERSION)}
    )


@pytest.mark.parametrize("defect", ["wrong_commit", "wrong_version", "corrupt", "missing", "extra"])
def test_verify_rejects_bad_candidate(tmp_path, modules, defect):
    assets, _, _ = modules
    directory = create_assets(tmp_path, assets)
    studio = directory / "release-studio" / assets.studio_name(VERSION)
    commit, version = SHA, VERSION
    if defect == "wrong_commit":
        commit = "b" * 40
    elif defect == "wrong_version":
        version = "3.0.5"
    elif defect == "corrupt":
        studio.write_bytes(studio.read_bytes()[:-1] + b"X")
    elif defect == "missing":
        studio.unlink()
    else:
        (directory / "release-studio" / "extra.exe").touch()
    with pytest.raises(ValueError):
        assets.verify(directory, version, commit)


def test_wrong_wheel_metadata_is_rejected(tmp_path, modules):
    assets, _, _ = modules
    path = tmp_path / f"led_controller_version_3-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.dist-info/METADATA", "Name: led-controller-version-3\nVersion: 3.0.3\n")
    with pytest.raises(ValueError, match="version mismatch"):
        assets.validate_binary(path, VERSION)


@pytest.mark.parametrize("conclusion,head", [("failure", SHA), ("success", "b" * 40)])
def test_wrong_ci_is_rejected(modules, monkeypatch, conclusion, head):
    _, release, _ = modules
    monkeypatch.setattr(release, "run", lambda *a, **k: json.dumps([{
        "status": "completed", "conclusion": conclusion, "headSha": head,
        "databaseId": 123, "url": "https://example.invalid",
    }]))
    with pytest.raises(release.Abort):
        release.wait_for_ci(SHA)


def test_ci_returns_exact_push_run(modules, monkeypatch):
    _, release, _ = modules
    def run(command, **kwargs):
        assert "--event" in command and command[command.index("--event")+1] == "push"
        assert "--branch" in command and command[command.index("--branch")+1] == "main"
        assert command[command.index("--commit")+1] == SHA
        return json.dumps([{"status": "completed", "conclusion": "success",
                            "headSha": SHA, "databaseId": 123, "url": "https://example.invalid"}])
    monkeypatch.setattr(release, "run", run)
    assert release.wait_for_ci(SHA) == 123


@pytest.mark.parametrize("failure", ["ci", "assets", "moved_main", "dirty", "tag_taken", None])
def test_tag_gate(modules, monkeypatch, failure):
    _, release, _ = modules
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command == ["git", "rev-parse", "HEAD"]:
            return SHA
        if command == ["git", "rev-parse", "origin/main"]:
            return "b" * 40 if failure == "moved_main" else SHA
        if command == ["git", "status", "--porcelain"]:
            return " M unwanted" if failure == "dirty" else ""
        return ""
    monkeypatch.setattr(release, "run", run)
    monkeypatch.setattr(release, "current_version", lambda: VERSION)
    monkeypatch.setattr(release, "check_the_tree_is_ready", lambda version: None)
    monkeypatch.setattr(release, "confirm", lambda *a, **k: None)
    monkeypatch.setattr(release, "write_version", lambda version: [])
    monkeypatch.setattr(release, "check_tag_is_free",
                        Mock(side_effect=release.Abort("tag taken") if failure == "tag_taken" else None))
    monkeypatch.setattr(release, "wait_for_ci",
                        Mock(side_effect=release.Abort("CI failed") if failure == "ci" else None, return_value=123))
    monkeypatch.setattr(release, "download",
                        Mock(side_effect=ValueError("asset failed") if failure == "assets" else None,
                             return_value=[Path("asset.whl")]))
    assert release.main(["--version", VERSION]) == (1 if failure else 0)
    tag = ["git", "tag", "-a", f"v{VERSION}", "-m", f"v{VERSION}"]
    push = ["git", "push", "origin", f"v{VERSION}"]
    assert (tag in calls) == (failure is None)
    assert (push in calls) == (failure is None)


def test_dry_run_never_bumps_or_tags(modules, monkeypatch):
    _, release, _ = modules
    monkeypatch.setattr(release, "current_version", lambda: "3.0.3")
    monkeypatch.setattr(release, "check_the_tree_is_ready", lambda version: None)
    monkeypatch.setattr(release, "run", Mock(return_value=""))
    for name in ("write_version", "download", "wait_for_ci"):
        monkeypatch.setattr(release, name, Mock(side_effect=AssertionError(name)))
    assert release.main(["--dry-run", "--version", VERSION]) == 0
    assert all(call.args[0][0] != "git" for call in release.run.call_args_list)


@pytest.mark.parametrize("existing", [False, True])
def test_upload_failure_never_publishes_draft(tmp_path, modules, monkeypatch, existing):
    _, _, publisher = modules
    monkeypatch.setattr(publisher, "version", lambda: VERSION)
    monkeypatch.setattr(publisher.subprocess, "check_output", lambda *a, **k: SHA)
    monkeypatch.setattr(publisher, "successful_run", lambda commit: 123)
    asset = tmp_path / "example.whl"
    asset.write_bytes(b"wheel")
    monkeypatch.setattr(publisher, "download", lambda *a, **k: [asset])
    monkeypatch.setattr(publisher, "release_record",
                        lambda tag: {"draft": True} if existing else None)
    calls = []
    def gh(*args):
        calls.append(args)
        if args[:2] == ("release", "upload"):
            raise RuntimeError("upload failed")
        return ""
    monkeypatch.setattr(publisher, "gh", gh)
    with pytest.raises(RuntimeError, match="upload failed"):
        publisher.publish(f"v{VERSION}")
    assert not any(c[:2] == ("release", "edit") for c in calls)
    assert any(c[:2] == ("release", "create") for c in calls) != existing


def test_verified_release_publishes_only_after_upload_check(tmp_path, modules, monkeypatch):
    _, _, publisher = modules
    asset = tmp_path / "example.whl"
    asset.write_bytes(b"wheel")
    monkeypatch.setattr(publisher, "version", lambda: VERSION)
    monkeypatch.setattr(publisher.subprocess, "check_output", lambda *a, **k: SHA)
    monkeypatch.setattr(publisher, "successful_run", lambda commit: 123)
    monkeypatch.setattr(publisher, "download", lambda *a, **k: [asset])
    monkeypatch.setattr(publisher, "release_record", Mock(side_effect=[None, {"draft": True}]))
    calls = []
    monkeypatch.setattr(publisher, "gh", lambda *a: calls.append(a[:2]) or "")
    monkeypatch.setattr(publisher, "verify_uploaded", lambda *a: calls.append(("verify", "uploaded")))
    publisher.publish(f"v{VERSION}")
    assert calls == [("release", "create"), ("release", "upload"), ("verify", "uploaded"), ("release", "edit")]


def test_verify_only_never_creates_release(tmp_path, modules, monkeypatch):
    _, _, publisher = modules
    monkeypatch.setattr(publisher, "version", lambda: VERSION)
    monkeypatch.setattr(publisher.subprocess, "check_output", lambda *a, **k: SHA)
    monkeypatch.setattr(publisher, "successful_run", lambda commit: 123)
    monkeypatch.setattr(publisher, "download", Mock(return_value=[]))
    monkeypatch.setattr(publisher, "release_record", Mock(side_effect=AssertionError("release read")))
    monkeypatch.setattr(publisher, "gh", Mock(side_effect=AssertionError("release write")))
    publisher.publish(f"v{VERSION}", verify_only=True)
    publisher.download.assert_called_once()
