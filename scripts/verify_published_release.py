"""Read-only verification of published LEFX releases; no build or upload."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import release_bundle as bundle
import server_release as server
from publish_github_release import gh, release_record, verify_uploaded
from release_contract import CONFIGURATOR, CORE, release_projects, require_release_identity, version_key


# The v3.0.5 tag contains the original, failing workflow. Only the reviewed
# recovery definition on Mirror main can substitute for its tag-triggered run.
RECOVERY_305 = (
    "3.0.5", "6bfca277079d5e957811405ef5cbff25f9c71ad8",
    "f1f6931628f39cb2031c85d1664b1d1e7b785755", "45918385311",
)
RECOVERY_WORKFLOW_COMMIT = "ea79b074abe30df42255884dce529fe94a4c28fb"
RECOVERY_MANIFEST_SHA = "f1e0bc5f76ebde618f71377c69793ee9892f9c28695dbb9bf07caab7bedf0e86"
RECOVERY_TAG_OBJECTS = (
    ("origin", "576a86e98caa302ffde5ad28c8f1663a9626a473"),
    (server.MIRROR, "5e4008dd64efbce209c54505d11c3597ecfce697"),
)


def clean_index_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("UV_", "PIP_", "LEFX_"))
            and k not in ("GH_TOKEN", "GITHUB_TOKEN", "PYTHONPATH", "PYTHONHOME")}


def install_published(version: str, commit: str) -> None:
    projects = release_projects(version, commit)
    env = clean_index_env()
    env["QT_QPA_PLATFORM"] = "offscreen"
    with tempfile.TemporaryDirectory(prefix="lefx-published-") as directory:
        root = Path(directory)
        config = root / "config.yaml"
        config.write_text("{}\n", encoding="utf-8")
        env["LEFX_CONFIG"] = str(config)
        env["LEFX_STATE_ROOT"] = str(root)
        for attempt in range(1, 5):
            venv = root / f"venv-{attempt}"
            subprocess.run(["uv", "--no-config", "venv", "--python", "3.12", str(venv)],
                           env=env, cwd=root, check=True, timeout=120)
            bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
            python = bin_dir / ("python.exe" if os.name == "nt" else "python")
            try:
                subprocess.run([
                    "uv", "--no-cache", "--no-config", "pip", "install",
                    "--python", str(python), "--default-index", "https://pypi.org/simple",
                    f"{CORE.name}[all]=={version}",
                ], env=env, cwd=root, check=True, timeout=240)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if attempt == 4:
                    raise
                print(f"Fresh PyPI installation attempt {attempt} failed; retrying without cache", flush=True)
                time.sleep(20 * attempt)
                continue
            break
        check = (
            "from importlib.metadata import version; "
            f"names={tuple(project.name for project in projects)!r}; "
            f"assert all(version(n)=={version!r} for n in names); "
            "print({n:version(n) for n in names})"
        )
        subprocess.run([str(python), "-c", check], env=env, cwd=root, check=True, timeout=60)
        entries = [(entry, "--help") for entry in ("lefx", "lefx-respeaker", "lefx-pack", "lefx-studio", "lefx-simulator")]
        if CONFIGURATOR in projects:
            entries.append(("lefx-config-widget", "--smoke"))
        for entry, option in entries:
            executable = bin_dir / (entry + (".exe" if os.name == "nt" else ""))
            subprocess.run([str(executable), option], env=env, cwd=root, check=True, timeout=60)
        print(f"Fresh PyPI installation and entry point checks successful for {version}", flush=True)


def resolve(version: str) -> tuple[str, str, str]:
    version_key(version)
    tag = f"v{version}"
    commit = server.remote_tag("origin", tag)
    mirror = server.remote_tag(server.MIRROR, tag)
    if not commit or not mirror:
        raise RuntimeError("Both published tags must exist")
    release_projects(version, commit)
    server.git("fetch", "origin", "main", "--tags")
    if server.git("rev-parse", f"{tag}^{{commit}}") != commit:
        raise RuntimeError("Development tag changed")
    note = server.git("for-each-ref", "--format=%(contents)", f"refs/tags/{tag}")
    match = re.search(r"^Release run: (\d+)$", note, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("No original server-side release run in the tag")
    run_id = match[1]
    require_release_identity(version, commit, mirror=mirror, run_id=run_id)
    run = json.loads(gh("api", f"repos/{server.DEV}/actions/runs/{run_id}"))
    if (run["path"].split("@")[0] != ".github/workflows/patch-release.yml"
            or run["event"] != "workflow_dispatch" or run["head_branch"] != "main"
            or run["status"] != "completed" or str(run["id"]) != run_id
            or run["head_sha"] != server.git("rev-parse", f"{commit}^")):
        raise RuntimeError("Original release run is not a completed main Patch Release")
    jobs = json.loads(gh("run", "view", run_id, "--repo", server.DEV, "--json", "jobs"))["jobs"]
    required = {
        "Select next patch and create immutable candidate",
        "Test and build exact release candidate / Build, test and package",
        "Test and build exact release candidate / Build and verify Windows Studio executable",
        "Verify all artifacts, tag, publish and mirror",
    }
    succeeded = {job["name"] for job in jobs if job["conclusion"] == "success"}
    if not required <= succeeded:
        raise RuntimeError(f"Original release prerequisite jobs not successful: {required - succeeded}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9a-f]{40}", mirror):
        raise RuntimeError("Invalid tag target")
    return commit, mirror, run_id


def mirror_recovery_proof(identity: tuple[str, str, str, str], manifest: Path, publication: str) -> dict:
    if identity != RECOVERY_305 or not re.fullmatch(r"[1-9][0-9]*", publication):
        raise RuntimeError("Unexpected v3.0.5 Mirror recovery identity")
    if bundle.sha256(manifest) != RECOVERY_MANIFEST_SHA:
        raise RuntimeError("Original v3.0.5 manifest digest differs")
    ref = "refs/tags/v3.0.5"
    for remote, tag_object in RECOVERY_TAG_OBJECTS:
        if server.git("ls-remote", "--refs", remote, ref) != f"{tag_object}\t{ref}":
            raise RuntimeError(f"Annotated v3.0.5 tag differs on {remote}")

    api_path = f"actions/runs/{publication}"
    run = server.public_mirror_api(api_path)
    expected = {
        "id": int(publication), "path": ".github/workflows/release.yml",
        "event": "workflow_dispatch", "head_branch": "main",
        "head_sha": RECOVERY_WORKFLOW_COMMIT, "display_title": "Recovery v3.0.5 (publish)",
        "status": "completed", "conclusion": "success",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Mirror run is not a successful publication by the reviewed v3.0.5 recovery")
    jobs = server.public_mirror_api(f"{api_path}/jobs?per_page=100")["jobs"]
    version, commit, _, _ = identity
    required = {"Verify the exact pre-tag distributions"}
    required.update(f"{project.stem} to PyPI" for project in release_projects(version, commit))
    if not required <= {job["name"] for job in jobs if job["conclusion"] == "success"}:
        raise RuntimeError("Mirror recovery verification or publisher job did not succeed")
    return run


def recover(version: str, commit: str, mirror: str, run_id: str, mirror_recovery_run: str = "") -> None:
    if resolve(version) != (commit, mirror, run_id):
        raise RuntimeError("Release identity changed")
    with tempfile.TemporaryDirectory(prefix="lefx-recovery-") as directory:
        root = Path(directory)
        for name in ("release-pypi", "release-studio"):
            gh("run", "download", run_id, "--repo", server.DEV,
               "--name", name, "--dir", str(root / name))
        _, assets = bundle.verify(root / "release-pypi", version, commit)
        assets.append(server.verify_studio(root / "release-studio", version, commit))
        record = release_record(f"v{version}")
        if not record or record["draft"]:
            raise RuntimeError("GitHub Release is not public")
        verify_uploaded(record, assets)
        args = argparse.Namespace(artifacts=root, version=version, commit=commit, mirror_commit=mirror)
        if mirror_recovery_run:
            proof = mirror_recovery_proof(
                (version, commit, mirror, run_id), root / "release-pypi" / "manifest.json", mirror_recovery_run,
            )
            server.wait(args, recovery_run=proof)
        else:
            server.wait(args)
        install_published(version, commit)
    print(f"Recovered verification for v{version}, commit {commit}, original run {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("install", "resolve", "recover"):
        p = sub.add_parser(name)
        p.add_argument("--version", required=True)
        if name == "install":
            p.add_argument("--commit", required=True)
        if name == "recover":
            for key in ("commit", "mirror", "run-id"):
                p.add_argument("--" + key, required=True)
            p.add_argument("--mirror-recovery-run", default="")
    args = parser.parse_args()
    if args.action == "install":
        version_key(args.version)
        if server.remote_tag("origin", f"v{args.version}") != args.commit:
            raise RuntimeError("Development tag does not match installation request")
        install_published(args.version, args.commit)
    elif args.action == "resolve":
        commit, mirror, run_id = resolve(args.version)
        server.output(commit=commit, mirror=mirror, run_id=run_id)
    else:
        recover(args.version, args.commit, args.mirror, args.run_id, args.mirror_recovery_run)


if __name__ == "__main__":
    main()
