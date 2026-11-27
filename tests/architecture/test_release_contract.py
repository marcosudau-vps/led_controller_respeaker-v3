"""Guard the reviewed project set, version edits and read-only recovery."""
from __future__ import annotations

import argparse
import importlib
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError

import pytest

from scripts.release_contract import (
    CONFIGURATOR, CORE, CURRENT, HISTORIC, HISTORIC_COMMIT, HISTORIC_MIRROR, HISTORIC_RUN,
    canonical_name, release_projects, require_release_identity,
)

from .test_server_release import make_bundle

ROOT = Path(__file__).resolve().parents[2]
SHA = "c" * 40


@pytest.fixture
def release_tools(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return tuple(importlib.import_module(name) for name in (
        "release", "release_assets", "release_bundle", "server_release", "verify_published_release",
    ))


def test_historical_identity_rejects_changed_version_commit_run_and_mirror():
    assert release_projects("3.0.4", HISTORIC_COMMIT) == HISTORIC
    assert release_projects("3.0.5", SHA) == CURRENT
    for version, commit in [("3.0.4", SHA), ("3.0.5", HISTORIC_COMMIT), ("3.0.03", SHA), ("3.0.2", SHA)]:
        with pytest.raises(ValueError):
            release_projects(version, commit)
    for change in ({"mirror": SHA}, {"run_id": "123"}):
        with pytest.raises(ValueError, match="Historical release identity"):
            require_release_identity("3.0.4", HISTORIC_COMMIT, **change)


def test_patch_bump_preserves_normalized_internal_pins(tmp_path, monkeypatch, release_tools):
    release, *_ = release_tools
    for source in release.pyprojects():
        dest = tmp_path / source.relative_to(ROOT)
        dest.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(source, dest)
    monkeypatch.setattr(release, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(release, "PACKAGES_ROOT", tmp_path / "packages")
    target = release.next_patch(release.current_version())
    changed = release.write_version(target)
    assert len(changed) == 5
    assert all(tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"] == target for path in changed)
    core = tomllib.loads((tmp_path / "packages" / CORE.directory / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pin = f"lefx-config-widget=={target}"
    assert core["optional-dependencies"]["configurator"] == [pin]
    assert pin in core["optional-dependencies"]["all"]


def test_configurator_version_collision_stops_candidate(release_tools, monkeypatch):
    release, *_ = release_tools
    monkeypatch.setattr(release, "run", lambda *args: "")
    requested = []

    class Published:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    def urlopen(url, **kwargs):
        project = url.split("/")[-3]
        requested.append(project)
        if project == CONFIGURATOR.name:
            return Published()
        raise HTTPError(url, 404, "Not found", None, None)

    monkeypatch.setattr(release, "urlopen", urlopen)
    with pytest.raises(release.Abort, match="lefx-config-widget"):
        release.check_tag_is_free("3.0.5")
    assert requested == [project.name for project in CURRENT]


def test_mirror_publisher_matrix_is_emitted_from_release_contract():
    script = ROOT / "scripts" / "release_contract.py"
    workflow = (ROOT / ".github/release-repo/release.yml").read_text(encoding="utf-8")
    assert "--commit \"$commit\"" in workflow
    assert "fromJSON(needs.build.outputs.matrix)" in workflow
    for version, commit, projects in [("3.0.4", HISTORIC_COMMIT, HISTORIC), ("3.0.5", SHA, CURRENT)]:
        info = subprocess.check_output([sys.executable, str(script), "--version", version, "--commit", commit], text=True)
        assert json.loads(info) == {"include": [
            {"distribution": project.stem, "environment": project.environment} for project in projects
        ]}
    assert canonical_name("lefx_config_widget") == canonical_name("LEFX.Config-Widget")


@pytest.mark.parametrize("version,commit,mirror,run_id", [
    ("3.0.4", HISTORIC_COMMIT, HISTORIC_MIRROR, HISTORIC_RUN),
    ("3.0.5", SHA, "d" * 40, "168"),
])
def test_recover_uses_only_the_original_run_bundle(tmp_path, release_tools, monkeypatch,
                                                   version, commit, mirror, run_id):
    _, assets, bundle, server, verify = release_tools
    folder = make_bundle(tmp_path, bundle, version, commit)
    portable = tmp_path / "studio.exe"
    portable.write_bytes(b"MZ" + b"x" * 2048)
    studio = tmp_path / "studio"
    assets.stage("release-studio", portable, studio, version, commit)
    manifest, files = bundle.verify(folder, version, commit)
    files.extend(studio.glob("*.exe"))
    record = {"draft": False, "assets": [
        {"name": path.name, "size": path.stat().st_size, "digest": f"sha256:{bundle.sha256(path)}"}
        for path in files
    ]}
    calls = []
    monkeypatch.setattr(server, "remote_tag", lambda remote, tag: commit if remote == "origin" else mirror)

    def git(*args):
        if args[0] == "rev-parse":
            return SHA if args[1] == f"{commit}^" else commit
        if args[0] == "for-each-ref":
            return f"Release run: {run_id}"
        assert args[:2] == ("fetch", "origin")
        return ""

    required = [
        "Select next patch and create immutable candidate",
        "Test and build exact release candidate / Build, test and package",
        "Test and build exact release candidate / Build and verify Windows Studio executable",
        "Verify all artifacts, tag, publish and mirror",
    ]

    def gh(*args):
        if args[0] == "api":
            assert args[1].endswith(f"/actions/runs/{run_id}")
            return json.dumps({"path": ".github/workflows/patch-release.yml", "event": "workflow_dispatch",
                               "head_branch": "main", "status": "completed", "id": int(run_id), "head_sha": SHA})
        if args[:2] == ("run", "view"):
            assert args[2] == run_id
            return json.dumps({"jobs": [{"name": name, "conclusion": "success"} for name in required]})
        assert args[:3] == ("run", "download", run_id)
        group = args[args.index("--name") + 1]
        shutil.copytree(folder if group == "release-pypi" else studio, args[args.index("--dir") + 1])
        calls.append(group)
        return ""

    def wait(args: argparse.Namespace):
        assert (args.version, args.commit, args.mirror_commit) == (version, commit, mirror)
        assert bundle.load_manifest(args.artifacts / "release-pypi/manifest.json", version, commit) == manifest
        calls.append("wait")

    monkeypatch.setattr(server, "git", git)
    monkeypatch.setattr(verify, "gh", gh)
    monkeypatch.setattr(verify, "release_record", lambda _: record)
    monkeypatch.setattr(server, "wait", wait)
    monkeypatch.setattr(verify, "install_published", lambda *args: calls.append(args))
    with pytest.raises(RuntimeError, match="Release identity changed"):
        verify.recover(version, commit, mirror, "333")
    assert calls == []
    verify.recover(version, commit, mirror, run_id)
    assert calls == ["release-pypi", "release-studio", "wait", (version, commit)]
    record["assets"].pop()
    with pytest.raises(RuntimeError, match="asset names differ"):
        verify.recover(version, commit, mirror, run_id)
