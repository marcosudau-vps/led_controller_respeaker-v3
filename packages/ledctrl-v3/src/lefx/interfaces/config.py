"""Project-wide settings: one file, one environment convention, one table.

Every knob this system has is a row in ``SETTINGS`` below. A row states the
slug, the type, the default and what the setting means, and everything else
follows from it: the ``config.yaml`` key is the slug, the environment variables
are the slug in upper case with and without a ``LEFX_`` prefix, and the value is
coerced to the declared type wherever it came from. Adding a setting is adding a
row; there is no second place to register it and no way to add one that the
file, the environment and the documentation do not all reach.

Precedence, highest first:

1. ``LEFX_<SLUG>`` in the environment
2. ``<SLUG>`` in the environment
3. the key in ``config.yaml``
4. the default in the table

The prefixed form exists because the bare one is what was asked for and what is
commonly done, and because ``PORT`` and ``SINK`` are words other software also
uses. In a container that runs only this service the bare form is the pleasant
one; in a shared environment the prefixed form is the one that cannot be
misread. Both are supported so neither situation needs a workaround.

Which ``config.yaml``: ``LEFX_CONFIG`` if set, otherwise ``config.yaml`` beside
the working directory, otherwise ``~/.lefx/config.yaml``. The first one that
exists wins outright — configuration files that merge are configuration files
nobody can predict.

The file is cached per path and modification time; the environment is read on
every access. That is the right way round, because the file is a deployment
decision and the environment is how a single run is varied.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger("lefx.interfaces.config")

ENV_CONFIG_FILE = "LEFX_CONFIG"
ENV_PREFIX = "LEFX_"


# -- coercion ---------------------------------------------------------------


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _as_str_list(value: Any) -> list[str]:
    """A list of names from a list, or from the many ways one gets written.

    ``[core, smartspeaker]``, ``core,smartspeaker`` and ``core smartspeaker``
    all mean the same thing to a person, so they mean the same thing here.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.replace(",", " ").split() if item.strip()]


def _as_path_list(value: Any) -> list[str]:
    """Directories, which unlike names may contain spaces.

    So this splits on the platform path separator like ``PATH`` does, and never
    on whitespace — ``C:\\Program Files\\effects`` is one directory.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(os.pathsep) if item.strip()]


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    raise ValueError(f"expected a mapping, got {type(value).__name__}")


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# -- the table --------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Setting:
    slug: str
    coerce: Callable[[Any], Any]
    default: Any
    doc: str

    @property
    def env_names(self) -> tuple[str, str]:
        bare = self.slug.upper()
        return f"{ENV_PREFIX}{bare}", bare


SETTINGS: tuple[Setting, ...] = (
    Setting("led_count", int, 12,
            "How many LEDs the ring has. The renderer checks every frame against it."),
    Setting("fps", float, 30.0,
            "Render loop rate."),
    Setting("host", str, "127.0.0.1",
            "Address 'lefx serve' binds to."),
    Setting("port", int, 8765,
            "Port 'lefx serve' asks for. A busy one falls through to the pool."),
    Setting("sink", str, "null",
            "Which frame sink to use: respeaker, simulator, null, or anything installed."),
    Setting("sink_options", _as_mapping, {},
            "Extra keywords handed to the chosen device's factories, e.g. {port: 8770}."),
    Setting("input_device", _as_optional_str, None,
            "Device whose input providers run. Defaults to the sink's device."),
    Setting("state_root", _as_optional_str, None,
            "Where logs, the instance file and persisted state go. Defaults to a temp directory."),
    Setting("package_path", _as_path_list, [],
            "Extra directories scanned for .lefx and .lefxset files, separated like PATH."),
    Setting("included_lefxset", _as_str_list, [],
            "Which installed effect sets to load, e.g. [core, smartspeaker]. Empty means all."),
    Setting("log_level", str, "INFO",
            "Logging level for the service process."),
)

BY_SLUG: dict[str, Setting] = {setting.slug: setting for setting in SETTINGS}


# -- the file ---------------------------------------------------------------


def config_file() -> Path | None:
    """The configuration file in effect, or None when there is none.

    An explicitly named file that does not exist is an error rather than a
    silent fall-through: someone who sets LEFX_CONFIG has said which file they
    mean, and starting with defaults instead would be the wrong kind of helpful.
    """
    named = os.environ.get(ENV_CONFIG_FILE)
    if named:
        path = Path(named).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"{ENV_CONFIG_FILE} points at {path}, which is not a file")
        return path
    for candidate in (Path.cwd() / "config.yaml", Path.home() / ".lefx" / "config.yaml"):
        if candidate.is_file():
            return candidate
    return None


_FILE_CACHE: dict[tuple[Path, int, int], dict[str, Any]] = {}


def _file_values() -> dict[str, Any]:
    path = config_file()
    if path is None:
        return {}
    stat = path.stat()
    key = (path, stat.st_mtime_ns, stat.st_size)
    cached = _FILE_CACHE.get(key)
    if cached is not None:
        return cached

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a mapping at the top level")

    values = {str(key_): value for key_, value in loaded.items()}
    unknown = sorted(set(values) - set(BY_SLUG))
    if unknown:
        # A warning rather than an error: a typo should be visible, but a file
        # written for a newer version must not stop an older one from starting.
        logger.warning(
            "%s has keys this version does not know: %s (known: %s)",
            path, ", ".join(unknown), ", ".join(sorted(BY_SLUG)),
        )

    _FILE_CACHE.clear()
    _FILE_CACHE[key] = values
    return values


def forget_file() -> None:
    """Drop the cached file. For tests, and for a process that rewrote its own."""
    _FILE_CACHE.clear()


# -- reading ----------------------------------------------------------------


def _from_environment(setting: Setting) -> tuple[bool, Any]:
    for name in setting.env_names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        # YAML first so that [core, smartspeaker], 12 and true arrive as what
        # they look like; the raw string otherwise, because a Windows path is
        # not YAML and should not be treated as though it might be.
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError:
            parsed = raw
        return True, raw if parsed is None and raw.strip() else parsed
    return False, None


def get(slug: str) -> Any:
    """One setting, resolved through the whole precedence chain."""
    setting = BY_SLUG[slug]
    found, raw = _from_environment(setting)
    source = "environment"
    if not found:
        values = _file_values()
        if slug in values:
            found, raw, source = True, values[slug], "config file"
    if not found:
        return setting.default
    try:
        return setting.coerce(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{slug} from the {source} is not usable: {raw!r} ({exc})") from exc


@dataclass(slots=True, frozen=True)
class Settings:
    """Every setting resolved at one moment, so one run cannot disagree with itself."""

    values: dict[str, Any]

    def __getattr__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError:
            raise AttributeError(name) from None

    def __getitem__(self, name: str) -> Any:
        return self.values[name]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.values)


def settings() -> Settings:
    """Read everything now. Cheap enough to call at construction, and only there."""
    return Settings({setting.slug: get(setting.slug) for setting in SETTINGS})


def describe() -> dict[str, Any]:
    """What is set, where each value came from, for 'lefx config' and /status."""
    file_values = _file_values()
    rows = []
    for setting in SETTINGS:
        found, _ = _from_environment(setting)
        if found:
            source = next(name for name in setting.env_names if name in os.environ)
        elif setting.slug in file_values:
            source = "config.yaml"
        else:
            source = "default"
        rows.append(
            {
                "slug": setting.slug,
                "value": get(setting.slug),
                "source": source,
                "env": list(setting.env_names),
                "doc": setting.doc,
            }
        )
    path = config_file()
    return {"file": None if path is None else str(path), "settings": rows}


__all__ = [
    "BY_SLUG",
    "ENV_CONFIG_FILE",
    "ENV_PREFIX",
    "SETTINGS",
    "Setting",
    "Settings",
    "config_file",
    "describe",
    "forget_file",
    "get",
    "settings",
]
