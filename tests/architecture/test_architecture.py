"""The dependency direction, enforced rather than described.

The package layout only means something if the arrows between the packages point
one way. A single ``from lefx.engine import ...`` inside the hardware package
would undo the entire reason the device lives in its own distribution — and it
would do so silently, because everything is installed together in a workspace
and the import would simply work.

So the rule is checked here, over every source file of every distribution, from
the matrix below. There is one matrix, it is the whole rule, and an exception
added to it is an architecture change rather than a test fix.
"""

from __future__ import annotations

import tomllib

import pytest

from .scan import (
    PACKAGES_ROOT,
    REPO_ROOT,
    code_strings_and_names,
    distributions,
    imported_modules,
    parse,
    source_files,
)

# Which import prefix belongs to which distribution. Both namespaces are
# PEP-420, so the distribution is not the top-level name but the one below it.
OWNER_OF_MODULE = {
    "lefx.sdk": "lefx-sdk",
    "lefx.engine": "lefx-engine",
    "lefx.authoring": "lefx-authoring",
    "lefx.interfaces": "lefx-interfaces",
    "lefx.studio": "lefx-studio",
    "respeaker_led.device": "respeaker-led-device",
    "respeaker_led.simulator": "respeaker-led-simulator",
}

# The matrix. Read it as "may import", and note what is *not* there: neither
# device package may reach the engine or the interfaces, and the interfaces may
# not reach either device package — those are found through entry points, which
# is what makes leaving a package uninstalled leave it out of the system.
MAY_IMPORT: dict[str, frozenset[str]] = {
    "lefx-sdk": frozenset(),
    "lefx-engine": frozenset({"lefx-sdk"}),
    "lefx-authoring": frozenset({"lefx-sdk", "lefx-engine"}),
    "lefx-interfaces": frozenset({"lefx-sdk", "lefx-engine"}),
    # An application, and the only package allowed to depend on four others: it
    # reads the schema, renders with the engine, drives a device through the
    # control surface and writes a source back with the authoring tools. Note
    # what is still absent — neither device package. The studio chooses its
    # output from the same entry points the service reads, so installing it
    # does not decide which hardware you have.
    "lefx-studio": frozenset({"lefx-sdk", "lefx-engine", "lefx-authoring", "lefx-interfaces"}),
    "respeaker-led-device": frozenset({"lefx-sdk"}),
    "respeaker-led-simulator": frozenset({"lefx-sdk"}),
}

# Qt is the simulator's optional extra and must stay on the window side. A
# service process that installed the simulator without the extra has to be able
# to import the sink, the provider and the factories they are reached through.
GUI_FREE_SIMULATOR_MODULES = ("registration", "link", "protocol", "sink", "provider", "client")
GUI_ONLY_SIMULATOR_MODULES = frozenset({"ring", "window", "app", "__main__"})

# The studio *is* a window, so Qt is a hard dependency there rather than an
# extra. What still has to hold is that the half describing what the studio
# does — which device it holds, what it plays, how a catalogue is searched —
# stays reachable without one, or it could only ever be tested by clicking.
GUI_FREE_STUDIO_MODULES = (
    "session", "catalogue", "calibrate", "authoring", "blueprint", "project",
)
GUI_ONLY_STUDIO_MODULES = frozenset(
    {
        "ring", "window", "parameters", "app",
        "calibration_page", "preset_dialog", "source_editor",
    }
)


ALL_DISTRIBUTIONS = distributions()


def owner_of(module: str) -> str | None:
    """Which distribution a module name belongs to, or None if it is external."""
    for prefix, distribution in OWNER_OF_MODULE.items():
        if module == prefix or module.startswith(f"{prefix}."):
            return distribution
    return None


def violations(distribution: str) -> list[str]:
    allowed = MAY_IMPORT[distribution] | {distribution}
    found: list[str] = []
    for path in source_files(distribution):
        for module in sorted(imported_modules(parse(path))):
            owner = owner_of(module)
            if owner is None or owner in allowed:
                continue
            found.append(f"{path.relative_to(REPO_ROOT).as_posix()} imports {module} ({owner})")
    return found


# -- the matrix -------------------------------------------------------------


def test_the_matrix_covers_every_distribution_in_the_workspace():
    """A new package must be placed in the matrix, not silently unchecked."""
    assert set(ALL_DISTRIBUTIONS) == set(MAY_IMPORT)
    assert set(OWNER_OF_MODULE.values()) == set(MAY_IMPORT)


@pytest.mark.parametrize("distribution", ALL_DISTRIBUTIONS)
def test_a_distribution_imports_only_what_the_matrix_allows(distribution):
    assert violations(distribution) == []


@pytest.mark.parametrize("distribution", ALL_DISTRIBUTIONS)
def test_the_declared_dependencies_agree_with_the_matrix(distribution):
    """The pyproject and the matrix are two statements of one fact.

    An import the matrix allows but the metadata does not declare would install
    a broken package; a dependency declared beyond the matrix would let the
    import in later without anything noticing.
    """
    text = (PACKAGES_ROOT / distribution / "pyproject.toml").read_bytes()
    declared = tomllib.loads(text.decode("utf-8"))["project"]["dependencies"]
    internal = {
        requirement.split("==")[0].split(">=")[0].strip()
        for requirement in declared
        if requirement.split("==")[0].split(">=")[0].strip() in MAY_IMPORT
    }
    assert internal <= MAY_IMPORT[distribution]


def test_the_sdk_depends_on_nothing_at_all():
    """Every package depends on the SDK, so anything it pulls in reaches all of them."""
    text = (PACKAGES_ROOT / "lefx-sdk" / "pyproject.toml").read_bytes()
    assert tomllib.loads(text.decode("utf-8"))["project"]["dependencies"] == []


# -- the specific rules the matrix exists for -------------------------------


@pytest.mark.parametrize("distribution", ["respeaker-led-device", "respeaker-led-simulator"])
@pytest.mark.parametrize("forbidden", ["lefx.engine", "lefx.interfaces"])
def test_a_device_package_never_reaches_the_engine_or_the_interfaces(distribution, forbidden):
    """The direction that makes a device replaceable.

    A device that imported the engine could not be installed without it, and the
    engine could no longer be embedded without the device. Both hang off the SDK
    ports instead, which is why the simulator can stand in for the hardware.
    """
    offenders = [line for line in violations(distribution) if forbidden in line]
    assert offenders == []


@pytest.mark.parametrize("forbidden", ["respeaker_led.device", "respeaker_led.simulator"])
def test_the_interfaces_never_import_a_device_package(forbidden):
    """Entry points are the mechanism, not a convention.

    An import here would put the hardware package into every installation of the
    control surface, and uninstalling it would stop being how you leave it out.
    """
    offenders = [line for line in violations("lefx-interfaces") if forbidden in line]
    assert offenders == []



def test_the_engine_carries_no_offline_state():
    """The engine renders effects. It has never heard of a cable.

    A connection is either up or down, and what the ring should show when it is
    down is an application's decision, published as a status and mapped outside
    the engine. A state named for the condition, wired in where effects are
    resolved, is the V1 arrangement this generation exists to be rid of.

    That the engine imports nothing from a device package is the matrix's job;
    this is the part a dependency check cannot see, because the V1 version of it
    was a bare string.
    """
    for path in source_files("lefx-engine"):
        used = {item.casefold() for item in code_strings_and_names(parse(path))}
        assert "offline" not in used, f"{path.relative_to(REPO_ROOT).as_posix()} names 'offline'"


# -- Qt stays on the window side --------------------------------------------


@pytest.mark.parametrize("module", GUI_FREE_SIMULATOR_MODULES)
def test_the_service_half_of_the_simulator_carries_no_qt(module):
    """Installing the simulator must not put a GUI toolkit in the service.

    Checked statically rather than by importing, because the toolkit *is*
    installed in this workspace — an import that succeeded here would prove
    nothing about the machine where it is not.
    """
    path = PACKAGES_ROOT / "respeaker-led-simulator/src/respeaker_led/simulator" / f"{module}.py"
    qt = sorted(name for name in imported_modules(parse(path)) if name.split(".")[0] == "PySide6")
    assert qt == []


def test_every_simulator_module_is_either_gui_free_or_declared_gui_only():
    """So a new module cannot quietly become the one that pulls Qt in."""
    directory = PACKAGES_ROOT / "respeaker-led-simulator/src/respeaker_led/simulator"
    modules = {path.stem for path in directory.glob("*.py")} - {"__init__"}
    assert modules == set(GUI_FREE_SIMULATOR_MODULES) | GUI_ONLY_SIMULATOR_MODULES


def test_importing_the_simulator_package_does_not_import_qt():
    """The package's own ``__init__`` is the trap: it is what a factory reaches
    through, and one convenience re-export of the window would undo the extra."""
    path = PACKAGES_ROOT / "respeaker-led-simulator/src/respeaker_led/simulator/__init__.py"
    reached = imported_modules(parse(path))
    assert not any(name.split(".")[0] == "PySide6" for name in reached)
    assert not any(name.rsplit(".", 1)[-1] in GUI_ONLY_SIMULATOR_MODULES for name in reached)


@pytest.mark.parametrize("module", GUI_FREE_STUDIO_MODULES)
def test_the_controller_half_of_the_studio_carries_no_qt(module):
    """What the studio does has to be checkable without a display.

    These two modules hold the device, the catalogue and the playback rules —
    the part with decisions in it. Behind Qt they would only ever be exercised
    by a person clicking, which is the kind of testing that stops happening.
    """
    path = PACKAGES_ROOT / "lefx-studio/src/lefx/studio" / f"{module}.py"
    qt = sorted(name for name in imported_modules(parse(path)) if name.split(".")[0] == "PySide6")
    assert qt == []


def test_every_studio_module_is_either_gui_free_or_declared_gui_only():
    directory = PACKAGES_ROOT / "lefx-studio/src/lefx/studio"
    modules = {path.stem for path in directory.glob("*.py")} - {"__init__"}
    assert modules == set(GUI_FREE_STUDIO_MODULES) | GUI_ONLY_STUDIO_MODULES


def test_importing_the_studio_package_does_not_import_qt():
    """So a test run without a display can still reach the half worth testing."""
    path = PACKAGES_ROOT / "lefx-studio/src/lefx/studio/__init__.py"
    reached = imported_modules(parse(path))
    assert not any(name.split(".")[0] == "PySide6" for name in reached)
    assert not any(name.rsplit(".", 1)[-1] in GUI_ONLY_STUDIO_MODULES for name in reached)
