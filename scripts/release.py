"""Cut a release: ask twice, then do the whole thing.

    uv run python scripts/release.py

Two questions and no others. Which version — the next patch is offered and
Enter takes it. Then "are you sure", spelled out, because everything after it
is automatic and the last step is a tag that cannot be taken back once a build
has gone to PyPI under it.

What runs after that, in order, stopping at the first failure:

 1. the working tree is clean and on the release branch, up to date with origin
 2. the version is written into every pyproject file at once
 3. the effect catalogues are rebuilt, so the wheels carry the current sources
 4. the whole hardware-free test suite
 5. scripts/check_release.py — build every distribution, install them into an
    empty environment, and use them
 6. commit and push
 7. wait for the CI run on that commit to go green
 8. tag and push the tag

Step 7 is the one that matters and the reason this is a script rather than a
list in a document. The tag is what triggers the sync to the release repository
and the upload to PyPI, so a tag pushed before CI has spoken is a release
nobody checked. Here it is not possible to do them in the wrong order.

    --dry-run     do everything up to the first thing that changes state
    --skip-ci     tag without waiting for CI (needs a reason; prints a warning)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
RELEASE_BRANCH = "main"
CI_WORKFLOW = "ci.yml"
CI_TIMEOUT_S = 45 * 60
CI_POLL_S = 20

VERSION_LINE = re.compile(r'^version\s*=\s*"(\d+\.\d+\.\d+)"\s*$', re.MULTILINE)


class Abort(RuntimeError):
    """Something is not as it must be. The message is for a person."""


# -- shell ------------------------------------------------------------------


def run(command: list[str], *, capture: bool = True, check: bool = True) -> str:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=capture,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() if capture else ""
        raise Abort(f"{' '.join(command)} failed:\n{detail}")
    return (result.stdout or "") if capture else ""


def step(text: str) -> None:
    print(f"\n=== {text}", flush=True)


# -- versions ---------------------------------------------------------------


def pyprojects() -> list[Path]:
    """The workspace root first, then every package. All of them get the version."""
    return [REPO_ROOT / "pyproject.toml", *sorted(PACKAGES_ROOT.glob("*/pyproject.toml"))]


def current_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_bytes().decode("utf-8")
    return tomllib.loads(text)["project"]["version"]


def next_patch(version: str) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def write_version(version: str) -> list[Path]:
    """Set the version everywhere it appears, including the internal pins.

    Both in one pass, because they are one fact. A bump that moved the versions
    and left ``ledctrl-v3==3.0.0`` behind in the optional packages would
    produce wheels that cannot be installed together, and every one of them
    would build.
    """
    internal = {path.parent.name for path in PACKAGES_ROOT.glob("*/pyproject.toml")}
    # Longest name first, so that "ledctrl-v3" does not shadow
    # "ledctrl-v3-effect-creation" in the alternation.
    ordered = sorted(map(re.escape, internal), key=len, reverse=True)
    pin = re.compile(r'"(' + "|".join(ordered) + r')(\[[^\]]*\])?==\d+\.\d+\.\d+"')

    touched = []
    for path in pyprojects():
        text = path.read_text(encoding="utf-8")
        updated = VERSION_LINE.sub(f'version = "{version}"', text, count=1)
        updated = pin.sub(lambda match: f'"{match[1]}{match[2] or ""}=={version}"', updated)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            touched.append(path)
    return touched


# -- asking -----------------------------------------------------------------


def ask_version(current: str) -> str:
    suggested = next_patch(current)
    print(f"current version: {current}")
    answer = input(f"release version [{suggested}]: ").strip() or suggested
    if not re.fullmatch(r"\d+\.\d+\.\d+", answer):
        raise Abort(f"{answer!r} is not a version of the form MAJOR.MINOR.PATCH")
    if answer == current:
        # Allowed, because the first release of a generation is exactly this:
        # the tree already says 3.0.0 and nothing has been published under it.
        # What stops a second attempt at an already-published version is the
        # tag check, which is the honest test — PyPI will not take a version
        # twice, and a tag is what says it went.
        print(f"note: {answer} is what the tree already says; releasing it as-is")
    return answer


def confirm(version: str, *, remote: str, branch: str) -> None:
    print(
        f"\nAbout to release {version}:"
        f"\n  * write {version} into {len(pyprojects())} pyproject files"
        f"\n  * rebuild the catalogues, run the tests and the release check"
        f"\n  * commit and push to {remote}/{branch}"
        f"\n  * wait for CI, then push the tag v{version}"
        f"\n\nThe tag starts the sync to the release repository and the upload to"
        f"\nPyPI. A version on PyPI cannot be replaced, only yanked."
    )
    if input("\nAre you sure? [y/N] ").strip().casefold() not in {"y", "yes", "j", "ja"}:
        raise Abort("nothing was changed")


# -- preconditions ----------------------------------------------------------


def check_the_tree_is_ready(version: str) -> None:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if branch != RELEASE_BRANCH:
        raise Abort(f"on branch {branch!r}; releases are cut from {RELEASE_BRANCH!r}")

    if run(["git", "status", "--porcelain"]).strip():
        raise Abort("the working tree has changes; commit or stash them first")

    if run(["git", "tag", "--list", f"v{version}"]).strip():
        raise Abort(f"tag v{version} already exists")

    run(["git", "fetch", "origin", RELEASE_BRANCH, "--tags"])
    behind = run(["git", "rev-list", "--count", f"HEAD..origin/{RELEASE_BRANCH}"]).strip()
    if behind != "0":
        raise Abort(f"{behind} commits behind origin/{RELEASE_BRANCH}; pull first")


# -- CI ---------------------------------------------------------------------


def wait_for_ci(sha: str) -> None:
    """Watch the run for this exact commit, not the newest one.

    Asking for "the latest run" would accept a green run of the commit before
    this one, which is the whole thing this step exists to prevent.
    """
    deadline = time.monotonic() + CI_TIMEOUT_S
    reported = None
    while time.monotonic() < deadline:
        raw = run(
            ["gh", "run", "list", "--workflow", CI_WORKFLOW, "--commit", sha,
             "--limit", "1", "--json", "status,conclusion,url"],
            check=False,
        )
        runs = json.loads(raw) if raw.strip().startswith("[") else []
        if not runs:
            if reported != "queued":
                print("  waiting for a CI run to appear...", flush=True)
                reported = "queued"
        else:
            info = runs[0]
            if info["status"] != reported:
                print(f"  CI {info['status']}  {info['url']}", flush=True)
                reported = info["status"]
            if info["status"] == "completed":
                if info["conclusion"] == "success":
                    return
                raise Abort(f"CI concluded {info['conclusion']}: {info['url']}")
        time.sleep(CI_POLL_S)
    raise Abort(f"CI did not finish within {CI_TIMEOUT_S // 60} minutes")


# -- the sequence -----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run every check and stop before anything is written",
    )
    parser.add_argument(
        "--skip-ci", metavar="REASON",
        help="Tag without waiting for CI. Only for a CI outage; say why.",
    )
    parser.add_argument("--version", help="Skip the prompt and use this version")
    args = parser.parse_args(argv)

    try:
        current = current_version()
        version = args.version or ask_version(current)
        check_the_tree_is_ready(version)
        if not args.dry_run:
            confirm(version, remote="origin", branch=RELEASE_BRANCH)

        step("rebuilding the effect catalogues")
        run([sys.executable, "scripts/build_effects.py"], capture=False)

        step("running the hardware-free test suite")
        run([sys.executable, "-m", "pytest", "-q", "-m", "not hardware"], capture=False)

        step("building every distribution and installing it")
        run([sys.executable, "scripts/check_release.py"], capture=False)

        if args.dry_run:
            print(f"\ndry run: everything passed; {current} would have become {version}")
            return 0

        step(f"writing version {version}")
        for path in write_version(version):
            print(f"  {path.relative_to(REPO_ROOT).as_posix()}")

        # After the bump, because the pins moved with it and a stale one would
        # have passed every check above and failed only on a user's machine.
        step("re-checking the version agreement")
        run([sys.executable, "-m", "pytest", "-q", "tests/architecture/test_versions.py"],
            capture=False)

        step("committing and pushing")
        run(["git", "add", "-A"])
        if run(["git", "diff", "--cached", "--name-only"]).strip():
            run(["git", "commit", "-m", f"release: v{version}"])
            run(["git", "push", "origin", RELEASE_BRANCH], capture=False)
        else:
            # The first release of a generation: the tree already carries the
            # version, so writing it changed nothing and there is nothing to
            # commit. Tag what is there. Committing an empty change to have
            # something to tag would be a commit that says nothing.
            print("  nothing changed; tagging the commit that is already here")
        sha = run(["git", "rev-parse", "HEAD"]).strip()

        if args.skip_ci:
            print(f"\n!! skipping the CI gate: {args.skip_ci}")
        else:
            step(f"waiting for CI on {sha[:8]}")
            wait_for_ci(sha)

        step(f"tagging v{version}")
        run(["git", "tag", "-a", f"v{version}", "-m", f"v{version}"])
        run(["git", "push", "origin", f"v{version}"], capture=False)

        print(
            f"\nv{version} is tagged and pushed."
            f"\nThe sync workflow now mirrors the release tree and tags it there,"
            f"\nwhich starts the upload to PyPI. Watch it with:"
            f"\n\n    gh run list --workflow sync-release-repo.yml --limit 1"
        )
        return 0
    except Abort as exc:
        print(f"\nstopped: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
