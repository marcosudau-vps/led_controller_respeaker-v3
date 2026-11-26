"""Release entry point and shared version helpers.

Normal execution dispatches the server-side Patch Release workflow.
Only --dry-run performs local, non-publishing checks.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from release_assets import DISTRIBUTIONS

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
RELEASE_BRANCH = "main"
REPOSITORY = "marcosudau-vps/led_controller_respeaker-v3"
RELEASE_REPOSITORY = "https://github.com/marcosudau-vps/led-ctrl-v3.git"

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
    and left ``led-controller-version-3==3.0.0`` behind in the optional packages would
    produce wheels that cannot be installed together, and every one of them
    would build.
    """
    internal = {path.parent.name for path in PACKAGES_ROOT.glob("*/pyproject.toml")}
    # Longest name first, so that "led-controller-version-3" does not shadow
    # "led-controller-version-3-effect-creation" in the alternation.
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


# -- preconditions ----------------------------------------------------------


def check_the_tree_is_ready(version: str) -> None:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if branch != RELEASE_BRANCH:
        raise Abort(f"on branch {branch!r}; releases are cut from {RELEASE_BRANCH!r}")

    if run(["git", "status", "--porcelain"]).strip():
        raise Abort("the working tree has changes; commit or stash them first")

    run(["git", "fetch", "origin", RELEASE_BRANCH, "--tags"])
    check_tag_is_free(version)
    head = run(["git", "rev-parse", "HEAD"]).strip()
    remote = run(["git", "rev-parse", f"origin/{RELEASE_BRANCH}"]).strip()
    if head != remote:
        raise Abort("HEAD must exactly match origin/main; reconcile the branch first")


def check_tag_is_free(version: str) -> None:
    tag = f"v{version}"
    if run(["git", "tag", "--list", tag]).strip():
        raise Abort(f"tag {tag} already exists locally")
    for remote in ("origin", RELEASE_REPOSITORY):
        if run(["git", "ls-remote", "--tags", remote, f"refs/tags/{tag}"]).strip():
            raise Abort(f"tag {tag} already exists on {remote}")
    for distribution in DISTRIBUTIONS:
        try:
            with urlopen(f"https://pypi.org/pypi/{distribution}/{version}/json", timeout=15):
                raise Abort(f"{distribution} {version} already exists on PyPI")
        except HTTPError as exc:
            if exc.code != 404:
                raise Abort(f"Could not check PyPI availability for {distribution}: {exc}") from exc
        except (URLError, TimeoutError) as exc:
            raise Abort(f"Could not check PyPI availability for {distribution}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the server-side Patch Release workflow.")
    parser.add_argument("--dry-run", action="store_true", help="Run local preflight without publishing")
    parser.add_argument("--version", help="Optional target for a local dry run only")
    args = parser.parse_args(argv)
    try:
        if not args.dry_run:
            if args.version:
                parser.error("Patch Release selects its next version automatically; --version is only for --dry-run")
            run(["gh", "workflow", "run", "patch-release.yml", "--repo", REPOSITORY, "--ref", "main"], capture=False)
            print(f"Patch Release dispatched: https://github.com/{REPOSITORY}/actions/workflows/patch-release.yml")
            return 0
        current = current_version()
        tagged = run(["git", "ls-remote", "--tags", "origin", f"refs/tags/v{current}"]).strip()
        version = args.version or (next_patch(current) if tagged else current)
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise Abort("Version must be MAJOR.MINOR.PATCH")
        check_the_tree_is_ready(version)
        step("rebuilding the effect catalogues")
        run([sys.executable, "scripts/build_effects.py"], capture=False)
        step("running the hardware-free test suite")
        run([sys.executable, "-m", "pytest", "-q", "-m", "not hardware"], capture=False)
        step("building every distribution and installing it")
        run([sys.executable, "scripts/check_release.py"], capture=False)
        print(f"Local dry run passed on {current}; proposed version {version}; nothing published.")
        return 0
    except Abort as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
