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
VERSION = "3.0.5"

from scripts.release_contract import HISTORIC_COMMIT, HISTORIC_VERSION


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("release_bundle"), importlib.import_module("server_release")


def make_bundle(tmp_path, bundle, version=VERSION, commit=SHA):
    dist = tmp_path / "dist"
    dist.mkdir()
    projects = bundle.release_projects(version, commit)
    for project in projects:
        prefix = f"{project.stem}-{version}"
        # The Configurator's metadata spelling differs from its index name.
        metadata = f"Name: {project.directory}\nVersion: {version}\n".encode()
        with zipfile.ZipFile(dist / (prefix + "-py3-none-any.whl"), "w") as archive:
            archive.writestr(prefix + ".dist-info/METADATA", metadata)
        with tarfile.open(dist / (prefix + ".tar.gz"), "w:gz") as archive:
            item = tarfile.TarInfo(prefix + "/PKG-INFO")
            item.size = len(metadata)
            archive.addfile(item, io.BytesIO(metadata))
    tree = tmp_path / "tree.tar.gz"
    with tarfile.open(tree, "w:gz") as archive:
        files = {
            "pyproject.toml": f'[project]\nversion = "{version}"\n'.encode(),
            ".github/workflows/release.yml": b"name: Release\n",
            **{f"packages/{p.directory}/pyproject.toml": f'[project]\nname = "{p.directory}"\n'.encode()
               for p in projects},
            **{f"scripts/{name}.py": b"# release script\n"
               for name in ("check_release", "release_bundle", "release_contract")},
        }
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
    (dist / ".gitignore").write_text("*\n", encoding="utf-8")
    folder = tmp_path / "bundle"
    bundle.stage(dist, tree, folder, version, commit)
    return folder


@pytest.mark.parametrize("version,commit,count", [(VERSION, SHA, 8), (HISTORIC_VERSION, HISTORIC_COMMIT, 6)])
def test_sealed_bundle_roundtrip(tmp_path, modules, version, commit, count):
    bundle, _ = modules
    folder = make_bundle(tmp_path, bundle, version, commit)
    manifest, files = bundle.verify(folder, version, commit)
    assert len(files) == count
    assert {p.name for p in files} == bundle.expected(version, commit)
    target = tmp_path / "mirror-tree"
    bundle.unpack_tree(folder, target, version, commit)
    assert json.loads((target / "release-manifest.json").read_text()) == manifest
    assert (target / ".github/workflows/release.yml").is_file()
    assert not list(target.glob("*.whl"))


@pytest.mark.parametrize("defect", ["commit", "version", "wheel", "sdist", "tree", "missing", "extra",
                                    "metadata", "missing-configurator"])
def test_sealed_bundle_rejects_mismatch(tmp_path, modules, defect):
    bundle, _ = modules
    folder = make_bundle(tmp_path, bundle)
    version, commit = VERSION, SHA
    if defect == "commit":
        commit = BASE
    elif defect == "version":
        version = "3.0.6"
    elif defect == "missing":
        next(folder.glob("*.whl")).unlink()
    elif defect == "extra":
        (folder / "extra.whl").touch()
    elif defect == "missing-configurator":
        (folder / f"lefx_config_widget-{VERSION}.tar.gz").unlink()
    elif defect == "metadata":
        path = folder / f"lefx_config_widget-{VERSION}-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("wrong.dist-info/METADATA", f"Name: wrong\nVersion: {VERSION}\n")
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"][path.name] = bundle.file_record(path)
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        path = (folder / "tree.tar.gz" if defect == "tree" else
                next(folder.glob("*.whl" if defect == "wheel" else f"*{VERSION}.tar.gz")))
        path.write_bytes(path.read_bytes() + b"bad")
    with pytest.raises(ValueError):
        bundle.verify(folder, version, commit)


@pytest.mark.parametrize("version,commit,count", [(VERSION, SHA, 8), (HISTORIC_VERSION, HISTORIC_COMMIT, 6)])
def test_pypi_download_uses_the_pre_tag_bytes(tmp_path, modules, monkeypatch, version, commit, count):
    bundle, _ = modules
    folder = make_bundle(tmp_path, bundle, version, commit)
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return (folder / url.rsplit("/", 1)[-1]).open("rb")
    monkeypatch.setattr(bundle.urllib.request, "urlopen", fetch)
    output = tmp_path / "download"
    bundle.fetch(folder / "manifest.json", output, version, commit)
    assert len(calls) == count
    assert all(f"/releases/download/v{version}/" in url for url in calls)
    assert {p.name for p in output.iterdir()} == bundle.expected(version, commit)


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
    assert server.verify_pypi(manifest, VERSION, SHA)
    def damaged(project, version):
        data = record(project, version)
        data["urls"][0]["digests"]["sha256"] = "0" * 64
        return data
    monkeypatch.setattr(server, "pypi_record", damaged)
    with pytest.raises(RuntimeError, match="differs"):
        server.verify_pypi(manifest, VERSION, SHA)
    monkeypatch.setattr(server, "pypi_record", lambda *args: None)
    assert not server.verify_pypi(manifest, VERSION, SHA)


def test_historical_bundle_refuses_a_fourth_project_or_wrong_commit(tmp_path, modules):
    bundle, _ = modules
    folder = make_bundle(tmp_path, bundle, HISTORIC_VERSION, HISTORIC_COMMIT)
    path = folder / "manifest.json"
    with pytest.raises(ValueError, match="No release contract"):
        bundle.load_manifest(path, HISTORIC_VERSION, SHA)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"]["lefx_config_widget-3.0.4.tar.gz"] = manifest["tree"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Wrong set"):
        bundle.load_manifest(path, HISTORIC_VERSION, HISTORIC_COMMIT)


@pytest.mark.parametrize("version,commit", [(VERSION, SHA), (HISTORIC_VERSION, HISTORIC_COMMIT)])
def test_wait_and_previous_gate_use_the_exact_contract(tmp_path, modules, monkeypatch, version, commit):
    bundle, server = modules
    folder = make_bundle(tmp_path, bundle, version, commit)
    manifest, _ = bundle.verify(folder, version, commit)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    folder.rename(artifacts / "release-pypi")
    tag, mirror = f"v{version}", "f6bd3823170820b123a061d2609c8008bfae708a"
    monkeypatch.setattr(server, "remote_tag", lambda repo, name: (
        (commit if repo == "origin" else mirror) if name == tag else None
    ))
    monkeypatch.setattr(server, "public_runs", lambda *_: [
        {"status": "completed", "conclusion": "success", "html_url": "https://example.invalid"}
    ])
    monkeypatch.setattr(server, "published_mirror_manifest", lambda _: manifest)
    monkeypatch.setattr(server, "git", lambda *args: commit if args[0] == "rev-parse"
                        else "Release run: 45854688359")
    monkeypatch.setattr(server, "gh", lambda *args: json.dumps({
        "status": "completed", "conclusion": "success", "headSha": commit
    }))
    names = set(manifest["files"]) | server.expected_names("release-studio", version)
    monkeypatch.setattr(server, "release_record", lambda _: {
        "draft": False, "assets": [{"name": name} for name in names]
    })

    def pypi(project, release):
        assert release == version
        distribution = next(d for d in bundle.release_projects(version, commit) if d.name == project)
        return {"urls": [
            {"filename": name, "size": manifest["files"][name]["size"], "yanked": False,
             "digests": {"sha256": manifest["files"][name]["sha256"]}}
            for name in (distribution.wheel(version), distribution.sdist(version))
        ]}

    monkeypatch.setattr(server, "pypi_record", pypi)
    args = argparse.Namespace(version=version, commit=commit, mirror_commit=mirror, artifacts=artifacts)
    server.require_previous_complete(version)
    server.wait(args)
    monkeypatch.setattr(server, "published_mirror_manifest", lambda _: {**manifest, "commit": BASE})
    with pytest.raises(RuntimeError, match="Mirrored manifest differs"):
        server.wait(args)
    assert not server.remote_tag("origin", "v9.0.0")
    monkeypatch.setattr(server, "pypi_record", lambda name, ver: {"urls": [
        *pypi(name, ver)["urls"], {"filename": "unexpected.tar.gz", "yanked": False}
    ]})
    with pytest.raises(RuntimeError, match="Unexpected files"):
        server.verify_pypi(manifest, version, commit)
    with pytest.raises(RuntimeError, match="incorrect PyPI files"):
        server.require_previous_complete(version)


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
