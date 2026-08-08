"""Which checkout the studio works on, and what a frozen build needs to reach it.

Two halves. The first is path arithmetic: one root, everything derived from it,
so a standalone tool started from a Start menu is not left guessing. The second
guards the executable — both ways a PyInstaller bundle silently loses a piece of
this system are checked here rather than discovered on someone else's machine.
"""

from __future__ import annotations

import json

import pytest

from lefx.studio.project import (
    Project,
    iter_paths,
    recalled,
    remember,
    resolve,
    under_a_frozen_build,
)

from tests.architecture.scan import REPO_ROOT


# -- one root, every path -----------------------------------------------------


def test_everything_is_derived_from_the_one_root(tmp_path):
    project = Project.at(tmp_path)
    assert project.catalogue_root == tmp_path / "effects"
    assert project.build_root == tmp_path / "build" / "effects"
    assert project.calibration_file == tmp_path / "doa_calibration.json"
    assert all(project.root in path.parents or path == project.root
               for _, path in iter_paths(project))


def test_the_search_order_is_the_one_the_service_uses():
    """Built catalogue first, then sources — so the studio shows what a service
    would load, not something adjacent to it."""
    project = Project.at(REPO_ROOT)
    assert project.package_search_paths == [project.build_root, project.catalogue_root]


def test_a_relative_path_becomes_an_absolute_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert Project.at(".").root == tmp_path.resolve()


def test_the_scratch_state_stays_out_of_the_way(tmp_path):
    """A studio session must not leave a background state a real service picks up."""
    project = Project.at(tmp_path)
    assert project.build_root in project.state_file.parents or "build" in project.state_file.parts


def test_the_real_checkout_is_recognised_as_a_project():
    project = Project.at(REPO_ROOT)
    assert project.looks_like_a_project is True
    assert {path.name for path in project.sets()} == {"core-set", "smartspeaker-set"}


def test_an_empty_directory_is_not_a_project_but_is_not_an_error(tmp_path):
    """It is where a first effect gets written; the window says so rather than
    presenting an empty list as a finding."""
    project = Project.at(tmp_path)
    assert project.looks_like_a_project is False
    assert project.sets() == []


def test_the_sources_of_a_set_are_found_by_their_manifests():
    project = Project.at(REPO_ROOT)
    core = project.catalogue_root / "core-set"
    sources = project.sources_in(core)
    assert len(sources) == 13
    assert all((path / "effect.yaml").is_file() for path in sources)


# -- remembering --------------------------------------------------------------


def test_the_last_project_is_remembered_and_recalled(tmp_path):
    store = tmp_path / "studio.json"
    project = Project.at(REPO_ROOT)

    remember(project, path=store)
    assert recalled(path=store) == project


def test_a_remembered_project_that_no_longer_exists_is_ignored(tmp_path):
    store = tmp_path / "studio.json"
    store.write_text(json.dumps({"recent": str(tmp_path / "gone")}), encoding="utf-8")
    assert recalled(path=store) is None


def test_nothing_remembered_is_not_an_error(tmp_path):
    assert recalled(path=tmp_path / "absent.json") is None


def test_a_damaged_note_does_not_stop_the_studio(tmp_path):
    store = tmp_path / "studio.json"
    store.write_text("{not json", encoding="utf-8")
    assert recalled(path=store) is None


def test_being_unable_to_remember_is_not_a_reason_to_refuse(tmp_path):
    """Smaller problem than not running."""
    blocked = tmp_path / "file" / "studio.json"
    blocked.parent.write_text("this is a file, not a directory", encoding="utf-8")
    remember(Project.at(REPO_ROOT), path=blocked)  # must not raise


# -- deciding which one -------------------------------------------------------


def test_an_explicit_project_always_wins(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    assert resolve(tmp_path).root == tmp_path.resolve()


def test_a_checkout_started_from_its_own_root_needs_no_flag(monkeypatch, tmp_path):
    monkeypatch.chdir(REPO_ROOT)
    assert resolve(None, path=tmp_path / "none.json").root == REPO_ROOT


def test_started_from_nowhere_it_falls_back_to_the_last_one(tmp_path, monkeypatch):
    """A bundle opened by double-clicking has no useful working directory."""
    store = tmp_path / "studio.json"
    remember(Project.at(REPO_ROOT), path=store)
    monkeypatch.chdir(tmp_path)

    assert resolve(None, path=store).root == REPO_ROOT


def test_with_nothing_to_go_on_it_uses_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve(None, path=tmp_path / "none.json").root == tmp_path.resolve()


def test_a_test_run_is_not_a_frozen_build():
    assert under_a_frozen_build() is False


# -- building from inside the tool -------------------------------------------


def test_a_project_builds_its_own_catalogue(tmp_path):
    """The standalone build has no ``scripts/`` to shell out to."""
    import shutil

    root = tmp_path / "workspace"
    (root / "effects").mkdir(parents=True)
    shutil.copytree(
        REPO_ROOT / "effects/core-set",
        root / "effects/core-set",
        ignore=shutil.ignore_patterns("__pycache__", "effects"),
    )
    project = Project.at(root)

    results = project.build_catalogue()

    assert [item["set_id"] for item in results] == ["core-set"]
    assert (project.build_root / "core-set.lefxset").is_file()
    # And the staging directory is gone, exactly as the script leaves it — it
    # sits inside a directory the service scans.
    assert list((root / "effects/core-set").glob("effects/*.lefx")) == []


def test_building_an_empty_project_reports_nothing_rather_than_failing(tmp_path):
    assert Project.at(tmp_path).build_catalogue() == []


# -- what a frozen build has to carry ----------------------------------------


def build_studio():
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import build_studio as module
    finally:
        sys.path.pop(0)
    return module


def test_the_freeze_recipe_is_complete():
    """Both ways a bundle loses a piece of this, asked before it is built.

    A device whose metadata was not copied is simply not offered, and an effect
    importing a standard library module the bundle lacks fails alone at load
    time. Neither produces an error anyone would connect to packaging.
    """
    assert build_studio().check_recipe() == []


def test_every_entry_point_distribution_travels_with_the_bundle():
    module = build_studio()
    registered = set(module.entry_point_distributions())

    assert {"respeaker-led-device", "respeaker-led-simulator"} <= registered
    assert registered <= set(module.metadata_to_copy())


def test_the_whole_author_whitelist_is_a_hidden_import():
    """PyInstaller cannot see inside a ``.lefx`` that does not exist yet."""
    module = build_studio()
    from lefx.authoring import ALLOWED_STDLIB

    hidden = set(module.hidden_imports())
    assert {name for name in ALLOWED_STDLIB if name != "__future__"} <= hidden


def test_the_registration_modules_are_named_even_though_nothing_imports_them():
    hidden = set(build_studio().hidden_imports())
    assert "respeaker_led.device.registration" in hidden
    assert "respeaker_led.simulator.registration" in hidden


def test_the_studios_own_qt_pages_are_named():
    """They are imported inside ``main`` so a headless self-check needs no Qt;
    that also hides them from the analysis."""
    hidden = set(build_studio().hidden_imports())
    assert {"lefx.studio.window", "lefx.studio.source_editor"} <= hidden
