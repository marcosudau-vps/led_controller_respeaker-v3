"""The server release gates and exact-file PyPI handoff."""
from __future__ import annotations

import argparse
import importlib
import io
import json
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SHA = "a" * 40
BASE = "b" * 40
VERSION = "3.0.4"


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("release_bundle"), importlib.import_module("server_release")


def make_bundle(tmp_path, bundle):
    dist = tmp_path / "dist"
    dist.mkdir()
    for project in bundle.PROJECTS:
        prefix = project.replace("-", "_") + "-" + VERSION
        metadata = f"Name: {project}\nVersion: {VERSION}\n".encode()
        with zipfile.ZipFile(dist / (prefix + "-py3-none-any.whl"), "w") as archive:
            archive.writestr(prefix + ".dist-info/METADATA", metadata)
        with tarfile.open(dist / (prefix + ".tar.gz"), "w:gz") as archive:
            item = tarfile.TarInfo(prefix + "/PKG-INFO")
            item.size = len(metadata)
            archive.addfile(item, io.BytesIO(metadata))
    tree = tmp_path / "tree.tar.gz"
    with tarfile.open(tree, "w:gz") as archive:
        for name, data in [
            ("pyproject.toml", f'[project]\nversion = "{VERSION}"\n'.encode()),
            (".github/workflows/release.yml", b"name: Release\n"),
        ]:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
    folder = tmp_path / "bundle"
    bundle.stage(dist, tree, folder, VERSION, SHA)
    return folder


def test_sealed_bundle_roundtrip(tmp_path, modules):
    bundle, _ = modules
    folder = make_bundle(tmp_path, bundle)
    manifest, files = bundle.verify(folder, VERSION, SHA)
    assert len(files) == 6
    assert {p.name for p in files} == bundle.expected(VERSION)
    target = tmp_path / "mirror-tree"
    bundle.unpack_tree(folder, target, VERSION, SHA)
    assert json.loads((target / "release-manifest.json").read_text()) == manifest
    assert (target / ".github/workflows/release.yml").is_file()
    assert not list(target.glob("*.whl"))


@pytest.mark.parametrize("defect", ["commit", "version", "wheel", "sdist", "tree", "missing", "extra"])
def test_sealed_bundle_rejects_mismatch(tmp_path, modules, defect):
    bundle, _ = modules
    folder = make_bundle(tmp_path, bundle)
    version, commit = VERSION, SHA
    if defect == "commit":
        commit = BASE
    elif defect == "version":
        version = "3.0.5"
    elif defect == "missing":
        next(folder.glob("*.whl")).unlink()
    elif defect == "extra":
        (folder / "extra.whl").touch()
    else:
        path = (folder / "tree.tar.gz" if defect == "tree" else
                next(folder.glob("*.whl" if defect == "wheel" else "*3.0.4.tar.gz")))
        path.write_bytes(path.read_bytes() + b"bad")
    with pytest.raises(ValueError):
        bundle.verify(folder, version, commit)


def test_pypi_download_uses_the_pre_tag_bytes(tmp_path, modules, monkeypatch):
    bundle, _ = modules
    folder = make_bundle(tmp_path, bundle)
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return (folder / url.rsplit("/", 1)[-1]).open("rb")
    monkeypatch.setattr(bundle.urllib.request, "urlopen", fetch)
    output = tmp_path / "download"
    bundle.fetch(folder / "manifest.json", output, VERSION)
    assert len(calls) == 6
    assert all(f"/releases/download/v{VERSION}/" in url for url in calls)
    assert {p.name for p in output.iterdir()} == bundle.expected(VERSION)


@pytest.mark.parametrize("current,tags,expected", [
    ("3.0.3", ["v3.0.3"], "3.0.4"),
    ("3.0.4", ["v3.0.3"], "3.0.4"),
    ("3.9.9", ["v3.9.8", "v3.9.9", "draft"], "3.9.10"),
    ("3.0.10", ["v3.0.10", "v3.0.9"], "3.0.11"),
])
def test_patch_version(modules, current, tags, expected):
    _, server = modules
    assert server.select_patch(current, tags)[1] == expected


def test_unexpected_version_bump_rejected(modules):
    _, server = modules
    with pytest.raises(RuntimeError):
        server.select_patch("3.1.0", ["v3.0.3"])


@pytest.mark.parametrize("failure", ["wrong_candidate", "bundle", "studio", "main_moved", "version_taken", "mirror", "push", None])
def test_pre_tag_gate(tmp_path, modules, monkeypatch, failure):
    bundle, server = modules
    calls = []
    def fail_or_log(name):
        def callback(*args, **kwargs):
            calls.append(name)
            if failure == name:
                raise RuntimeError(name)
        return callback
    monkeypatch.setattr(server, "verify_candidate", fail_or_log("wrong_candidate"))
    def verify(*args):
        fail_or_log("bundle")()
        return {}, [tmp_path / "wheel.whl"]
    monkeypatch.setattr(bundle, "verify", verify)
    monkeypatch.setattr(bundle, "unpack_tree", Mock())
    def studio(*args):
        fail_or_log("studio")()
        return tmp_path / "studio.exe"
    monkeypatch.setattr(server, "verify_studio", studio)
    monkeypatch.setattr(server, "existing_development_tag", lambda *args: False)
    monkeypatch.setattr(server.legacy, "check_tag_is_free", fail_or_log("version_taken"))
    monkeypatch.setattr(server, "release_record", lambda *args: None)
    def mirror(*args):
        fail_or_log("mirror")()
        return True
    monkeypatch.setattr(server, "make_mirror", mirror)
    def git(*args, **kwargs):
        if args == ("rev-parse", "origin/main"):
            return SHA if failure == "main_moved" else BASE
        if args[0] == "tag":
            calls.append("local_tag")
        if args[:2] == ("push", "--atomic"):
            if kwargs.get("cwd"):
                calls.append("mirror_push")
            else:
                calls.append("tag_push")
                if failure == "push":
                    raise RuntimeError("push")
        return ""
    monkeypatch.setattr(server, "git", git)
    monkeypatch.setattr(server, "publish_assets", fail_or_log("github_release"))
    monkeypatch.setattr(server, "remote_tag", lambda *args: "c" * 40)
    monkeypatch.setattr(server, "output", Mock())
    args = argparse.Namespace(version=VERSION, commit=SHA, base=BASE, run_id="123",
                              artifacts=tmp_path, mirror=tmp_path / "mirror")
    if failure:
        with pytest.raises(RuntimeError):
            server.finalize(args)
        assert "github_release" not in calls
        assert "mirror_push" not in calls
        if failure != "push":
            assert "tag_push" not in calls
    else:
        server.finalize(args)
        assert calls.index("mirror") < calls.index("tag_push")
        assert calls.index("tag_push") < calls.index("github_release") < calls.index("mirror_push")


def test_pypi_wrong_hash_is_not_success(tmp_path, modules, monkeypatch):
    bundle, server = modules
    folder = make_bundle(tmp_path, bundle)
    manifest, _ = bundle.verify(folder, VERSION, SHA)
    def record(project, version):
        return {"urls": [
            {"filename": name, "size": item["size"], "digests": {"sha256": item["sha256"]}, "yanked": False}
            for name, item in manifest["files"].items()
            if name.startswith(project.replace("-", "_") + "-")
        ]}
    monkeypatch.setattr(server, "pypi_record", record)
    assert server.verify_pypi(manifest)
    def damaged(project, version):
        data = record(project, version)
        data["urls"][0]["digests"]["sha256"] = "0" * 64
        return data
    monkeypatch.setattr(server, "pypi_record", damaged)
    with pytest.raises(RuntimeError, match="differs"):
        server.verify_pypi(manifest)
    monkeypatch.setattr(server, "pypi_record", lambda *args: None)
    assert not server.verify_pypi(manifest)


def test_existing_tag_resume_never_retags(tmp_path, modules, monkeypatch):
    bundle, server = modules
    monkeypatch.setattr(server, "verify_candidate", Mock())
    monkeypatch.setattr(bundle, "verify", lambda *a: ({}, []))
    monkeypatch.setattr(bundle, "unpack_tree", Mock())
    monkeypatch.setattr(server, "verify_studio", lambda *a: tmp_path / "studio.exe")
    monkeypatch.setattr(server, "existing_development_tag", lambda *a: True)
    monkeypatch.setattr(server, "make_mirror", lambda *a: False)
    monkeypatch.setattr(server, "publish_assets", Mock())
    monkeypatch.setattr(server, "remote_tag", lambda *a: "c" * 40)
    monkeypatch.setattr(server, "output", Mock())
    monkeypatch.setattr(server, "git", Mock(side_effect=AssertionError("must not write tag")))
    monkeypatch.setattr(server.legacy, "check_tag_is_free", Mock(side_effect=AssertionError("already tagged")))
    server.finalize(argparse.Namespace(version=VERSION, commit=SHA, base=BASE, run_id="123",
                                       artifacts=tmp_path, mirror=tmp_path / "mirror"))
    server.publish_assets.assert_called_once()
