"""The settings layer: one table, one file, one environment convention.

What is worth checking here is not that a value can be read — it is that the
four sources agree on an order, that every setting is reachable from all of
them, and that a value written the way a person writes it arrives as the type
the code expects.
"""

from __future__ import annotations

import pytest

from lefx.interfaces import config, discovery


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """No stray LEFX_* or bare slug from the developer's shell.

    Deleting both spellings of every slug, because a machine that happens to
    export PORT would otherwise make these tests pass or fail for a reason that
    has nothing to do with the code.
    """
    for setting in config.SETTINGS:
        for name in setting.env_names:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(config.ENV_CONFIG_FILE, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path / "nowhere"))
    config.forget_file()
    yield
    config.forget_file()


def write_config(tmp_path, text: str):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    config.forget_file()
    return path


# -- the table is the whole of it -------------------------------------------


def test_every_setting_has_a_distinct_slug_and_two_environment_names():
    slugs = [setting.slug for setting in config.SETTINGS]
    assert len(slugs) == len(set(slugs))
    names = [name for setting in config.SETTINGS for name in setting.env_names]
    assert len(names) == len(set(names))
    assert config.BY_SLUG.keys() == set(slugs)


def test_every_setting_is_documented():
    """The table is what the example file and the guide are written from."""
    assert all(setting.doc.strip() for setting in config.SETTINGS)


def test_the_example_file_covers_every_setting():
    """A setting nobody can discover is a setting nobody uses."""
    from tests.architecture.scan import REPO_ROOT

    text = (REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8")
    missing = [setting.slug for setting in config.SETTINGS if f"\n{setting.slug}:" not in text]
    assert missing == []


def test_defaults_apply_when_there_is_nothing_else():
    assert config.config_file() is None
    assert config.get("led_count") == 12
    assert config.get("port") == 8765
    assert config.get("included_lefxset") == []


# -- precedence -------------------------------------------------------------


def test_the_file_beats_the_default(tmp_path):
    write_config(tmp_path, "led_count: 5\n")
    assert config.get("led_count") == 5


def test_the_bare_environment_name_beats_the_file(tmp_path, monkeypatch):
    write_config(tmp_path, "led_count: 5\n")
    monkeypatch.setenv("LED_COUNT", "24")
    assert config.get("led_count") == 24


def test_the_prefixed_environment_name_beats_the_bare_one(tmp_path, monkeypatch):
    """Because PORT and SINK are words other software uses too.

    In a shared environment the prefixed form is the one that cannot be
    misread, so it has to be the one that wins.
    """
    monkeypatch.setenv("LED_COUNT", "24")
    monkeypatch.setenv("LEFX_LED_COUNT", "60")
    assert config.get("led_count") == 60


def test_describe_says_where_each_value_came_from(tmp_path, monkeypatch):
    write_config(tmp_path, "fps: 15\n")
    monkeypatch.setenv("LEFX_PORT", "9000")
    rows = {row["slug"]: row for row in config.describe()["settings"]}
    assert rows["port"]["source"] == "LEFX_PORT"
    assert rows["fps"]["source"] == "config.yaml"
    assert rows["led_count"]["source"] == "default"


# -- values arriving the way people write them ------------------------------


@pytest.mark.parametrize(
    "raw",
    ["[core, smartspeaker]", "core,smartspeaker", "core smartspeaker", "core, smartspeaker"],
)
def test_a_list_setting_accepts_every_spelling_of_a_list(monkeypatch, raw):
    monkeypatch.setenv("INCLUDED_LEFXSET", raw)
    assert config.get("included_lefxset") == ["core", "smartspeaker"]


def test_a_list_setting_from_the_file_is_a_yaml_list(tmp_path):
    write_config(tmp_path, "included_lefxset: [core, smartspeaker]\n")
    assert config.get("included_lefxset") == ["core", "smartspeaker"]


def test_a_mapping_setting_survives_both_routes(tmp_path, monkeypatch):
    write_config(tmp_path, "sink_options:\n  port: 8770\n")
    assert config.get("sink_options") == {"port": 8770}
    monkeypatch.setenv("SINK_OPTIONS", "{port: 9999, angle_offset_deg: 129.1}")
    assert config.get("sink_options") == {"port": 9999, "angle_offset_deg": 129.1}


def test_a_path_list_splits_on_the_path_separator_and_not_on_spaces(monkeypatch):
    """Because a directory may contain a space and a set name may not.

    Written with os.pathsep rather than a literal, and with directories that
    contain no colon: on Linux the separator *is* a colon, so a Windows path
    spelled out here would split down the middle and the test would be about
    the machine rather than about the code.
    """
    import os

    entries = ["/opt/effect packages", "/srv/fx"]
    monkeypatch.setenv("PACKAGE_PATH", os.pathsep.join(entries))
    assert config.get("package_path") == entries


def test_an_unusable_value_names_the_setting_and_the_source(monkeypatch):
    monkeypatch.setenv("LED_COUNT", "twelve")
    with pytest.raises(ValueError, match="led_count from the environment"):
        config.get("led_count")


# -- the file itself --------------------------------------------------------


def test_an_explicitly_named_file_that_is_missing_is_an_error(tmp_path, monkeypatch):
    """Someone who set LEFX_CONFIG said which file they meant.

    Falling back to defaults would be the wrong kind of helpful: the service
    would start, and every setting in the file they thought they were using
    would silently not apply.
    """
    monkeypatch.setenv(config.ENV_CONFIG_FILE, str(tmp_path / "absent.yaml"))
    with pytest.raises(FileNotFoundError, match="absent.yaml"):
        config.config_file()


def test_an_unknown_key_warns_rather_than_refusing_to_start(tmp_path, caplog):
    """A typo should be visible; a file written for a newer version should still boot."""
    write_config(tmp_path, "led_count: 5\nled_kount: 9\n")
    with caplog.at_level("WARNING"):
        assert config.get("led_count") == 5
    assert "led_kount" in caplog.text


def test_a_file_that_is_not_a_mapping_is_refused(tmp_path):
    write_config(tmp_path, "- one\n- two\n")
    with pytest.raises(ValueError, match="mapping"):
        config.get("led_count")


def test_a_rewritten_file_is_noticed(tmp_path):
    """The file is cached, so the cache has to key on the file changing."""
    write_config(tmp_path, "led_count: 5\n")
    assert config.get("led_count") == 5
    (tmp_path / "config.yaml").write_text("led_count: 60\n", encoding="utf-8")
    config.forget_file()
    assert config.get("led_count") == 60


# -- effect sets, which is what the selection is for ------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("core", "core"),
        ("core-set", "core"),
        ("Core_Set", "core"),
        ("  smartspeaker-set ", "smartspeaker"),
        ("smartspeaker", "smartspeaker"),
    ],
)
def test_a_set_name_reduces_to_one_form(written, expected):
    assert discovery.normalize_set_id(written) == expected


def test_an_empty_selection_means_every_installed_set():
    """A fresh install with no config file should play what it installed."""
    installed = set(discovery.available_effect_sets())
    assert set(discovery.installed_effect_sets([])) == installed
    assert {"core-set", "smartspeaker-set"} <= installed


def test_the_selection_narrows_and_takes_either_spelling():
    assert set(discovery.installed_effect_sets(["core"])) == {"core-set"}
    assert set(discovery.installed_effect_sets(["core-set"])) == {"core-set"}
    assert set(discovery.installed_effect_sets(["smartspeaker"])) == {"smartspeaker-set"}


def test_the_selection_is_read_from_the_environment(monkeypatch):
    """The whole point of the setting: the user's own example, verbatim."""
    monkeypatch.setenv("INCLUDED_LEFXSET", "[core, smartspeaker]")
    assert set(discovery.installed_effect_sets()) == {"core-set", "smartspeaker-set"}
    monkeypatch.setenv("INCLUDED_LEFXSET", "[core]")
    assert set(discovery.installed_effect_sets()) == {"core-set"}


def test_naming_a_set_that_is_not_installed_warns_and_carries_on(caplog):
    with caplog.at_level("WARNING"):
        found = discovery.installed_effect_sets(["core", "nonexistent"])
    assert set(found) == {"core-set"}
    assert "nonexistent" in caplog.text


def test_an_installed_set_is_found_through_its_entry_point_and_nothing_else():
    """No import of lefx.sets anywhere in the interfaces — metadata only."""
    for set_id, path in discovery.installed_effect_sets().items():
        assert path.is_file(), f"{set_id} archive missing at {path}"
        assert path.suffix == ".lefxset"
        assert path.stem == set_id


def test_the_search_paths_contain_every_enabled_set(monkeypatch):
    from lefx.interfaces import paths

    monkeypatch.setenv("INCLUDED_LEFXSET", "core")
    found = paths.package_search_paths()
    assert discovery.installed_effect_sets()["core-set"].parent in found
    assert all("smartspeaker" not in path.name for path in found)


def test_package_path_adds_to_the_installed_sets_rather_than_replacing_them(monkeypatch, tmp_path):
    """The old behaviour turned the shipped catalogue off by accident."""
    from lefx.interfaces import paths

    extra = tmp_path / "extra-effects"
    extra.mkdir()
    monkeypatch.setenv("PACKAGE_PATH", str(extra))
    found = paths.package_search_paths()
    assert extra in found
    assert discovery.installed_effect_sets()["core-set"].parent in found
