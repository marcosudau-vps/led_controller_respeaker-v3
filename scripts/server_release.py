"""Orchestrate the patch release on GitHub runners, never on a developer PC."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import release as legacy
import release_bundle as bundle
from release_assets import expected_names, validate_binary
from publish_github_release import gh, release_record, publish_assets
from release_contract import DEV_REPO as DEV, MIRROR_REPO as PYPI_REPO
from release_contract import release_projects, require_release_identity

ROOT = Path(__file__).resolve().parents[1]
MIRROR = f"https://github.com/{PYPI_REPO}.git"


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, encoding="utf-8").strip()


def output(**values: str) -> None:
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError("Invalid output")
            print(f"{key}={value}", file=stream)


def remote_tag(remote: str, tag: str) -> str | None:
    refs = git("ls-remote", "--tags", remote, f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}")
    records = dict(line.split("\t")[::-1] for line in refs.splitlines() if line)
    return records.get(f"refs/tags/{tag}^{{}}") or records.get(f"refs/tags/{tag}")


def pypi_record(project: str, version: str) -> dict | None:
    try:
        with urlopen(f"https://pypi.org/pypi/{project}/{version}/json", timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def select_patch(current: str, tags: list[str]) -> tuple[str | None, str]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", current):
        raise ValueError("Expected MAJOR.MINOR.PATCH")
    known = sorted(
        (tuple(map(int, tag[1:].split("."))), tag[1:])
        for tag in tags if re.fullmatch(r"v\d+\.\d+\.\d+", tag)
    )
    if not known:
        return None, current
    last = known[-1][1]
    version = legacy.next_patch(last)
    if current not in (last, version):
        raise RuntimeError(f"Main version {current} does not match latest tag {last} or its next patch")
    return last, version


def verified_recovery(tag: str, commit: str, original_run: str) -> bool:
    """Accept only a successful main recovery job bound to the exact tag and run."""
    runs = json.loads(gh(
        "run", "list", "--repo", DEV, "--workflow", "verify-release.yml",
        "--branch", "main", "--event", "workflow_dispatch", "--status", "success",
        "--limit", "100", "--json", "databaseId,headSha,status,conclusion",
    ))
    expected = f"Verify published {tag} at {commit} (run {original_run})"
    for run in runs:
        if run["status"] != "completed" or run["conclusion"] != "success":
            continue
        head = run["headSha"]
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            continue
        if subprocess.run(["git", "merge-base", "--is-ancestor", head, "origin/main"],
                          cwd=ROOT, check=False).returncode:
            continue
        jobs = json.loads(gh("run", "view", str(run["databaseId"]), "--repo", DEV,
                             "--json", "jobs"))["jobs"]
        if any(job["name"] == expected and job["conclusion"] == "success" for job in jobs):
            print(f"Previous release {tag} verified by recovery run {run['databaseId']}")
            return True
    return False


def require_previous_complete(current: str) -> None:
    tag = f"v{current}"
    commit = remote_tag("origin", tag)
    if not commit:
        raise RuntimeError(f"Previous release tag {tag} is missing from origin")
    projects = release_projects(current, commit)
    mirror = remote_tag(MIRROR, tag)
    if not mirror:
        raise RuntimeError(f"Previous release {tag} has not been mirrored")
    require_release_identity(current, commit, mirror=mirror)
    for project in projects:
        record = pypi_record(project.name, current)
        files = (record or {}).get("urls", [])
        names = {item["filename"] for item in files}
        if (len(files) != 2 or names != {project.wheel(current), project.sdist(current)}
                or any(item["yanked"] for item in files)):
            raise RuntimeError(f"Previous release {tag} has incorrect PyPI files: {project.name}")
    if git("rev-parse", f"{tag}^{{commit}}") != commit:
        raise RuntimeError(f"Previous release tag {tag} differs locally")
    annotation = git("for-each-ref", "--format=%(contents)", f"refs/tags/{tag}")
    match = re.search(r"^Release run: (\d+)$", annotation, flags=re.MULTILINE)
    if match:
        require_release_identity(current, commit, run_id=match[1])
        run = json.loads(gh("run", "view", match[1], "--repo", DEV, "--json", "status,conclusion,headSha"))
        if run["headSha"] != git("rev-parse", f"{commit}^"):
            raise RuntimeError(f"Previous release run {match[1]} belongs to a different main commit")
        if (run["status"], run["conclusion"]) != ("completed", "success"):
            if run["status"] != "completed" or not verified_recovery(tag, commit, match[1]):
                raise RuntimeError(f"Previous release run {match[1]} not verified; rerun failed jobs or Verify Published Release, do not bump")
        record = release_record(tag)
        if not record or record["draft"]:
            raise RuntimeError(f"Previous GitHub Release {tag} is not public")
        names = bundle.expected(current, commit) | expected_names("release-studio", current)
        if {asset["name"] for asset in record["assets"]} != names or len(record["assets"]) != len(names):
            raise RuntimeError(f"Incorrect GitHub assets for previous release {tag}")
    else:
        raise RuntimeError(f"Previous release {tag} has no original release run")


def prepare(run_id: str) -> None:
    if os.environ.get("GITHUB_REF") != "refs/heads/main" or os.environ.get("GITHUB_REPOSITORY") != DEV:
        raise RuntimeError("Patch release may only run on the development main branch")
    if not run_id.isdigit():
        raise ValueError("Invalid run ID")
    git("fetch", "origin", "main", "--tags")
    base = git("rev-parse", "HEAD")
    if base != git("rev-parse", "origin/main") or git("status", "--porcelain"):
        raise RuntimeError("Main moved or checkout is dirty; start again on current main")
    current = legacy.current_version()
    for note in git("for-each-ref", "--format=%(contents)", "refs/tags").splitlines():
        if note == f"Release run: {run_id}":
            raise RuntimeError("This workflow already tagged a release. Rerun failed jobs only.")
    last, version = select_patch(current, git("tag", "--list", "v*").splitlines())
    if last:
        require_previous_complete(last)
    # If a previous attempt has already tagged this workflow's candidate, do
    # not let a full workflow rerun create different binaries for that tag.
    # Rerun failed jobs only; their validated artifacts remain available.
    if remote_tag("origin", f"v{version}"):
        raise RuntimeError("Version is already tagged; recover the existing run")
    legacy.check_tag_is_free(version)
    ref = f"refs/heads/release-candidate/{run_id}"
    existing = git("ls-remote", "--heads", "origin", ref)
    if existing:
        git("fetch", "origin", ref)
        candidate = git("rev-parse", "FETCH_HEAD")
        if git("rev-parse", f"{candidate}^") != base:
            raise RuntimeError("Existing candidate no longer matches main")
        git("checkout", "--detach", candidate)
        if legacy.current_version() != version:
            raise RuntimeError("Existing candidate version differs")
    else:
        legacy.write_version(version)
        subprocess.run(["uv", "lock"], cwd=ROOT, check=True)
        allowed = {str(path.relative_to(ROOT).as_posix()) for path in legacy.pyprojects()} | {"uv.lock"}
        changes = set(git("diff", "--name-only").splitlines())
        if not changes <= allowed:
            raise RuntimeError(f"Unexpected version changes: {changes - allowed}")
        git("config", "user.name", "lefx release bot")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        git("add", "--", *sorted(allowed))
        git("commit", "--allow-empty", "-m", f"release: v{version}")
        candidate = git("rev-parse", "HEAD")
        git("push", "origin", f"{candidate}:{ref}")
    output(version=version, commit=candidate, base=base)
    print(f"Candidate {version}: {candidate} based on {base}; no main change or tag yet")


def verify_studio(directory: Path, version: str, commit: str) -> Path:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    release_projects(version, commit)
    names = expected_names("release-studio", version)
    if (manifest["group"], manifest["version"], manifest["commit"]) != ("release-studio", version, commit):
        raise ValueError("Studio manifest source mismatch")
    if set(manifest["files"]) != names or {p.name for p in directory.iterdir()} != names | {"manifest.json"}:
        raise ValueError("Wrong set of Studio files")
    name = next(iter(names))
    path = directory / name
    bundle.verify_file(path, manifest["files"][name])
    validate_binary(path, version)
    return path


def verify_candidate(version: str, commit: str, base: str) -> None:
    if git("rev-parse", "HEAD") != commit or legacy.current_version() != version:
        raise RuntimeError("Wrong candidate checkout")
    if git("rev-parse", f"{commit}^") != base:
        raise RuntimeError("Candidate not based on selected main")
    allowed = {path.relative_to(ROOT).as_posix() for path in legacy.pyprojects()} | {"uv.lock"}
    changed = set(git("diff", "--name-only", base, commit).splitlines())
    if not changed <= allowed:
        raise RuntimeError("Candidate contains non-version changes")


def existing_development_tag(version: str, commit: str, run_id: str) -> bool:
    tag = f"v{version}"
    git("fetch", "origin", "main", "--tags")
    found = remote_tag("origin", tag)
    if found is None:
        return False
    annotation = git("for-each-ref", "--format=%(contents)", f"refs/tags/{tag}")
    if found != commit or f"Release run: {run_id}" not in annotation.splitlines():
        raise RuntimeError("Existing development tag belongs to another release")
    return True


def make_mirror(tree: Path, checkout: Path, version: str, commit: str) -> bool:
    """Stage exact tested source and check write access without publishing."""
    tag = f"v{version}"
    git("fetch", "origin", "main", "--tags", cwd=checkout)
    existing = remote_tag(MIRROR, tag)
    if existing:
        note = git("for-each-ref", "--format=%(contents)", f"refs/tags/{tag}", cwd=checkout)
        if f"Development commit: {commit}" not in note.splitlines():
            raise RuntimeError("Existing mirror tag belongs to another source")
        actual = git("show", f"{tag}:release-manifest.json", cwd=checkout)
        if json.loads(actual) != json.loads((tree / "release-manifest.json").read_text(encoding="utf-8")):
            raise RuntimeError("Existing mirror tag has a different manifest")
        return False
    git("checkout", "-B", "main", "origin/main", cwd=checkout)
    for path in checkout.iterdir():
        if path.name != ".git":
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    shutil.copytree(tree, checkout, dirs_exist_ok=True)
    git("config", "user.name", "lefx release bot", cwd=checkout)
    git("config", "user.email", "noreply@github.com", cwd=checkout)
    git("add", "-A", cwd=checkout)
    if git("status", "--porcelain", cwd=checkout):
        git("commit", "-m", f"release: sync from {commit} ({tag})", cwd=checkout)
    git("tag", "-a", tag, "-m", tag, "-m", f"Development commit: {commit}", cwd=checkout)
    git("push", "--dry-run", "--atomic", "origin", "HEAD:refs/heads/main", f"refs/tags/{tag}", cwd=checkout)
    return True


def finalize(args: argparse.Namespace) -> None:
    version, commit, base, run_id = args.version, args.commit, args.base, args.run_id
    verify_candidate(version, commit, base)
    tag = f"v{version}"
    _, assets = bundle.verify(args.artifacts / "release-pypi", version, commit)
    studio = verify_studio(args.artifacts / "release-studio", version, commit)
    assets.append(studio)
    tree = args.artifacts / "unpacked-tree"
    bundle.unpack_tree(args.artifacts / "release-pypi", tree, version, commit)
    already_tagged = existing_development_tag(version, commit, run_id)
    if not already_tagged:
        if git("rev-parse", "origin/main") != base:
            raise RuntimeError("Main advanced during validation; start again without consuming a version")
        legacy.check_tag_is_free(version)
        if release_record(tag):
            raise RuntimeError("GitHub Release already exists for untagged version")
    # Verify both write paths before the irreversible tag; the release repo
    # commit/tag remain local to this runner until the public assets exist.
    needs_mirror = make_mirror(tree, args.mirror, version, commit)
    if not already_tagged:
        git("config", "user.name", "lefx release bot")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        git("tag", "-a", tag, commit, "-m", tag, "-m", f"Release run: {run_id}")
        refs = (f"{commit}:refs/heads/main", f"refs/tags/{tag}")
        git("push", "--dry-run", "--atomic", "origin", *refs)
        git("fetch", "origin", "main")
        if git("rev-parse", "origin/main") != base:
            raise RuntimeError("Main advanced immediately before tag")
        # No force: a concurrent main update or taken tag rejects the entire push.
        git("push", "--atomic", "origin", *refs)
    publish_assets(tag, assets)
    if needs_mirror:
        git("push", "--atomic", "origin", "HEAD:refs/heads/main", f"refs/tags/{tag}", cwd=args.mirror)
    mirror_commit = remote_tag(MIRROR, tag)
    if not mirror_commit:
        raise RuntimeError("Mirror tag missing after push")
    output(mirror_commit=mirror_commit)
    print(f"Published GitHub assets and mirrored {tag}; waiting for PyPI is the next job")


def public_mirror_api(path: str) -> dict:
    url = f"https://api.github.com/repos/{PYPI_REPO}/{path}"
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "LEFX-release-verifier"})
    token = os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        if not token or exc.code not in (401, 403, 404):
            raise
        request.remove_header("Authorization")
        with urlopen(request, timeout=20) as response:
            return json.load(response)


def public_runs(tag: str, commit: str) -> list[dict]:
    runs = public_mirror_api(
        f"actions/workflows/release.yml/runs?event=push&head_sha={commit}&per_page=20"
    )["workflow_runs"]
    return [r for r in runs if r["head_sha"] == commit and r["head_branch"] in (tag, f"refs/tags/{tag}")]


def verify_pypi(manifest: dict, version: str, commit: str) -> bool:
    bundle.validate_manifest(manifest, version, commit)
    for project in release_projects(version, commit):
        record = pypi_record(project.name, version)
        if record is None:
            return False
        actual = {item["filename"]: item for item in record["urls"]}
        names = {project.wheel(version), project.sdist(version)}
        if actual.keys() - names or len(actual) != len(record["urls"]):
            raise RuntimeError(f"Unexpected files on PyPI for {project.name}: {sorted(actual)}")
        if not names <= actual.keys():
            return False
        for name in names:
            expected = manifest["files"][name]
            item = actual[name]
            if item["yanked"] or item["size"] != expected["size"] or item["digests"]["sha256"] != expected["sha256"]:
                raise RuntimeError(f"PyPI file differs from tested file: {name}")
    return True


def published_mirror_manifest(commit: str) -> dict:
    return json.loads(gh("api", f"repos/{PYPI_REPO}/contents/release-manifest.json?ref={commit}",
                         "-H", "Accept: application/vnd.github.raw+json"))


def wait(args: argparse.Namespace, *, recovery_run: dict | None = None) -> None:
    manifest = bundle.load_manifest(args.artifacts / "release-pypi" / "manifest.json", args.version, args.commit)
    tag = f"v{args.version}"
    if remote_tag("origin", tag) != args.commit:
        raise RuntimeError("Development tag missing or changed")
    mirror_commit = remote_tag(MIRROR, tag)
    if not mirror_commit or mirror_commit != args.mirror_commit:
        raise RuntimeError("Release-repository tag missing or changed")
    require_release_identity(args.version, args.commit, mirror=mirror_commit)
    if published_mirror_manifest(mirror_commit) != manifest:
        raise RuntimeError("Mirrored manifest differs from original CI")
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        try:
            runs = [recovery_run] if recovery_run is not None else public_runs(tag, mirror_commit)
            if runs:
                run = runs[0]
                print(f"PyPI workflow {run['status']} {run['html_url']}", flush=True)
                if run["status"] == "completed":
                    if run["conclusion"] != "success":
                        raise RuntimeError(f"PyPI workflow failed: {run['html_url']}; rerun its failed jobs")
                    if verify_pypi(manifest, args.version, args.commit):
                        print(f"All {len(manifest['files'])} PyPI files match the verified pre-tag artifacts for {tag}")
                        return
        except (URLError, TimeoutError) as exc:
            print(f"Temporary verification error: {exc}", flush=True)
        time.sleep(45)
    raise RuntimeError("Timed out verifying PyPI publication; rerun this job, not the release with a new version")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--run-id", required=True)
    p = sub.add_parser("finalize")
    for name in ("version", "commit", "base", "run-id"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--artifacts", type=Path, required=True)
    p.add_argument("--mirror", type=Path, required=True)
    p = sub.add_parser("wait")
    for name in ("version", "commit", "mirror-commit"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.run_id)
    elif args.action == "finalize":
        finalize(args)
    else:
        wait(args)


if __name__ == "__main__":
    main()
