"""Regression coverage for the read-only post-publication recovery."""
from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.release_contract import HISTORIC_COMMIT, HISTORIC_MIRROR, HISTORIC_RUN

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SHA = "a" * 40
MIRROR = "b" * 40


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("verify_published_release"), importlib.import_module("server_release")


@pytest.mark.parametrize("version,commit", [("3.0.4", HISTORIC_COMMIT), ("3.0.5", SHA)])
def test_clean_install_retries_without_cache_or_foreign_index(modules, monkeypatch, version, commit):
    verify, _ = modules
    monkeypatch.setenv("UV_INDEX_URL", "https://wrong.invalid")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://wrong.invalid")
    monkeypatch.setenv("GH_TOKEN", "test-token")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        env = kwargs["env"]
        assert not any(key.startswith(("UV_", "PIP_")) for key in env)
        assert "GH_TOKEN" not in env
        assert kwargs["check"] is True
        if "pip" in command:
            assert "--no-cache" in command and "--no-config" in command
            assert "https://pypi.org/simple" in command
            assert f"led-controller-version-3[all]=={version}" in command
            if len([c for c in calls if "pip" in c]) == 1:
                raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(verify.subprocess, "run", run)
    monkeypatch.setattr(verify.time, "sleep", Mock())
    verify.install_published(version, commit)
    installs = [c for c in calls if "pip" in c]
    assert len(installs) == 2 and installs[0] != installs[1]
    assert sum(c[-1] == "--help" for c in calls) == 5
    assert any(c[-1] == "--smoke" and "lefx-configurator-widget" in c[0] for c in calls) == (version == "3.0.5")
    check = next(c[-1] for c in calls if "-c" in c)
    assert ("lefx-configurator-widget" in check) == (version == "3.0.5")


def test_permanent_install_failure_is_not_success(modules, monkeypatch):
    verify, _ = modules
    def run(command, **kwargs):
        if "pip" in command:
            raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(verify.subprocess, "run", run)
    monkeypatch.setattr(verify.time, "sleep", Mock())
    with pytest.raises(subprocess.CalledProcessError):
        verify.install_published("3.0.4", HISTORIC_COMMIT)


@pytest.mark.parametrize("conclusion,job_name,ancestor,expected", [
    ("success", f"Verify published v3.0.4 at {SHA} (run 123)", True, True),
    ("failure", f"Verify published v3.0.4 at {SHA} (run 123)", True, False),
    ("success", f"Verify published v3.0.4 at {SHA} (run 999)", True, False),
    ("success", f"Verify published v3.0.4 at {MIRROR} (run 123)", True, False),
    ("success", f"Verify published v3.0.4 at {SHA} (run 123)", False, False),
])
def test_recovery_proof_bound_to_exact_release(modules, monkeypatch, conclusion, job_name, ancestor, expected):
    _, server = modules
    def gh(*args):
        if args[:2] == ("run", "list"):
            assert "--workflow" in args and "verify-release.yml" in args
            assert "--branch" in args and "main" in args
            return json.dumps([{"databaseId": 99, "headSha": SHA,
                                "status": "completed", "conclusion": "success"}])
        return json.dumps({"jobs": [{"name": job_name, "conclusion": conclusion}]})
    monkeypatch.setattr(server, "gh", gh)
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **k: Mock(returncode=0 if ancestor else 1))
    assert server.verified_recovery("v3.0.4", SHA, "123") is expected


def test_resolve_refuses_failed_prerequisites(modules, monkeypatch):
    verify, server = modules
    monkeypatch.setattr(server, "remote_tag", lambda remote, tag: HISTORIC_COMMIT if remote == "origin" else HISTORIC_MIRROR)
    monkeypatch.setattr(server, "git", lambda *a: HISTORIC_COMMIT if a[0] == "rev-parse" else f"Release run: {HISTORIC_RUN}")
    def gh(*args):
        if args[0] == "api":
            return json.dumps({"path": ".github/workflows/patch-release.yml",
                               "event": "workflow_dispatch", "head_branch": "main", "status": "completed", "id": int(HISTORIC_RUN), "head_sha": HISTORIC_COMMIT})
        return json.dumps({"jobs": [{"name": "Verify all artifacts, tag, publish and mirror", "conclusion": "failure"}]})
    monkeypatch.setattr(verify, "gh", gh)
    with pytest.raises(RuntimeError, match="prerequisite"):
        verify.resolve("3.0.4")
