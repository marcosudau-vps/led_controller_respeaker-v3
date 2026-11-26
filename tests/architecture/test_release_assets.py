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

from scripts.release_contract import CURRENT, HISTORIC, HISTORIC_COMMIT


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return tuple(importlib.import_module(name) for name in (
        "release_assets", "release", "publish_github_release"
    ))


def create_assets(tmp_path, assets, commit=SHA, projects=CURRENT):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    for project in projects:
        name, normalized = project.directory, project.stem
        with zipfile.ZipFile(wheels / f"{normalized}-{VERSION}-py3-none-any.whl", "w") as archive:
            archive.writestr(
                f"{normalized}-{VERSION}.dist-info/METADATA",
                f"Metadata-Version: 2.4\nName: {name}\nVersion: {VERSION}\n",
            )
    exe = tmp_path / "studio.exe"
    exe.write_bytes(b"MZ" + b"\x00" * 2048)
    directory = tmp_path / "download"
    assets.stage("release-wheels", wheels, directory / "release-wheels", VERSION, commit)
    assets.stage("release-studio", exe, directory / "release-studio", VERSION, commit)
    return directory


@pytest.mark.parametrize("commit,projects", [(SHA, CURRENT), (HISTORIC_COMMIT, HISTORIC)])
def test_exact_wheels_and_studio_asset_group_verified(tmp_path, modules, commit, projects):
    assets, _, _ = modules
    directory = create_assets(tmp_path, assets, commit, projects)
    assert {p.name for p in assets.verify(directory, VERSION, commit)} == (
        assets.wheel_names(VERSION, projects) | {assets.studio_name(VERSION)}
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


def test_normal_release_dispatches_server_workflow_only(modules, monkeypatch):
    _, release, _ = modules
    monkeypatch.setattr(release, "run", Mock(return_value=""))
    assert release.main([]) == 0
    release.run.assert_called_once_with(
        ["gh", "workflow", "run", "patch-release.yml", "--repo", release.REPOSITORY, "--ref", "main"],
        capture=False,
    )


def test_local_release_cannot_choose_version_without_dry_run(modules):
    _, release, _ = modules
    with pytest.raises(SystemExit) as exc:
        release.main(["--version", VERSION])
    assert exc.value.code == 2


def test_dry_run_never_bumps_or_tags(modules, monkeypatch):
    _, release, _ = modules
    monkeypatch.setattr(release, "current_version", lambda: "3.0.3")
    monkeypatch.setattr(release, "check_the_tree_is_ready", lambda version: None)
    monkeypatch.setattr(release, "run", Mock(return_value=""))
    monkeypatch.setattr(release, "write_version", Mock(side_effect=AssertionError("write version")))
    assert release.main(["--dry-run", "--version", VERSION]) == 0
    assert not any(c.args[0][:2] in (["git", "tag"], ["git", "push"], ["gh", "workflow"])
                   for c in release.run.call_args_list)


@pytest.mark.parametrize("existing", [False, True])
def test_upload_failure_never_publishes_draft(tmp_path, modules, monkeypatch, existing):
    _, _, publisher = modules
    asset = tmp_path / "example.whl"
    asset.write_bytes(b"wheel")
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
        publisher.publish_assets(f"v{VERSION}", [asset])
    assert not any(c[:2] == ("release", "edit") for c in calls)
    assert any(c[:2] == ("release", "create") for c in calls) != existing


def test_verified_release_publishes_only_after_upload_check(tmp_path, modules, monkeypatch):
    _, _, publisher = modules
    asset = tmp_path / "example.whl"
    asset.write_bytes(b"wheel")
    monkeypatch.setattr(publisher, "release_record", Mock(side_effect=[None, {"draft": True}]))
    calls = []
    monkeypatch.setattr(publisher, "gh", lambda *a: calls.append(a[:2]) or "")
    monkeypatch.setattr(publisher, "verify_uploaded", lambda *a: calls.append(("verify", "uploaded")))
    publisher.publish_assets(f"v{VERSION}", [asset])
    assert calls == [("release", "create"), ("release", "upload"), ("verify", "uploaded"), ("release", "edit")]


def test_public_release_is_verified_never_overwritten(tmp_path, modules, monkeypatch):
    _, _, publisher = modules
    asset = tmp_path / "example.whl"
    asset.write_bytes(b"wheel")
    record = {"draft": False}
    monkeypatch.setattr(publisher, "release_record", lambda tag: record)
    monkeypatch.setattr(publisher, "verify_uploaded", Mock())
    monkeypatch.setattr(publisher, "gh", Mock(side_effect=AssertionError("public release must not be modified")))
    publisher.publish_assets(f"v{VERSION}", [asset])
    publisher.verify_uploaded.assert_called_once_with(record, [asset])
