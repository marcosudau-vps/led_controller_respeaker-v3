"""The dependency direction, enforced rather than described.

The layout only means something if the arrows between the layers point one way.
A single ``from lefx.engine import ...`` inside the hardware layer would undo
the reason the device is replaceable at all — and it would do so silently,
because everything is installed together and the import would simply work.

The rules are written about **layers** rather than distributions. They used to
be the same thing, and for a while the matrix could be phrased in package
names. It cannot any more: the schema, the engine, the control surface, the
hardware and both catalogues ship in one distribution, so "led-ctrl-v3 may
import led-ctrl-v3" would permit everything and forbid nothing. What is worth
protecting was never the packaging — it is that the engine knows no device and
the device knows no engine.

The distribution boundary still exists where it is load-bearing, and one
section here holds it: what a package declares must match what its layers
actually reach for.
"""

from __future__ import annotations

import tomllib

import pytest

from .scan import (
    PACKAGES_ROOT,
    REPO_ROOT,
    code_strings_and_names,
    distribution_of,
    distributions,
    imported_modules,
    layer_files,
    layers,
    parse,
)

# The matrix. Read it as "may import", and note what is *not* there: neither
# device layer may reach the engine or the interfaces, the interfaces may not
# reach a device — those are found through entry points, which is what makes
# leaving a package uninstalled leave it out of the system — and a catalogue
# imports nothing at all.
MAY_IMPORT: dict[str, frozenset[str]] = {
    "lefx.sdk": frozenset(),
    "lefx.engine": frozenset({"lefx.sdk"}),
    "lefx.interfaces": frozenset({"lefx.sdk", "lefx.engine"}),
    # The one layer allowed three, because the studio is inside it: it reads
    # the schema, renders with the engine and drives a device through the
    # control surface. Note what is still absent — neither device. The studio
    # picks its output from the same entry points the service reads, so
    # installing it does not decide which hardware you have.
    "lefx.effect_creation": frozenset({"lefx.sdk", "lefx.engine", "lefx.interfaces"}),
    "lefx.device.respeaker": frozenset({"lefx.sdk"}),
    "lefx.device.simulated_respeaker": frozenset({"lefx.sdk"}),
    # A catalogue is data. It ships one archive and a function that says where
    # the archive is, so it imports nothing — not even the SDK, because a
    # package format is not an import.
    "lefx.sets.core_set": frozenset(),
    "lefx.sets.smartspeaker_set": frozenset(),
}

# Which distribution may depend on which. Three, and the direction is the one
# the layers have: the optional packages sit on the runtime, never the reverse.
DISTRIBUTION_MAY_DEPEND: dict[str, frozenset[str]] = {
    "led-ctrl-v3": frozenset(),
    "led-ctrl-v3-effect-creation": frozenset({"led-ctrl-v3"}),
    "led-ctrl-v3-device-simulated-respeaker": frozenset({"led-ctrl-v3"}),
}

CREATION_ROOT = PACKAGES_ROOT / "led-ctrl-v3-effect-creation/src/lefx/effect_creation"
STUDIO_ROOT = CREATION_ROOT / "studio"
SIMULATOR_ROOT = (
    PACKAGES_ROOT
    / "led-ctrl-v3-device-simulated-respeaker/src/lefx/device/simulated_respeaker"
)

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


ALL_LAYERS = sorted(layers())


def owner_of(module: str) -> str | None:
    """Which layer a module name belongs to, or None if it is external.

    Longest prefix first, so ``lefx.device.respeaker`` is not mistaken for a
    shorter one that happens to be a prefix of it.
    """
    for prefix in sorted(MAY_IMPORT, key=len, reverse=True):
        if module == prefix or module.startswith(f"{prefix}."):
            return prefix
    return None


def violations(layer: str) -> list[str]:
    allowed = MAY_IMPORT[layer] | {layer}
    found: list[str] = []
    for path in layer_files(layer):
        for module in sorted(imported_modules(parse(path))):
            owner = owner_of(module)
            if owner is None or owner in allowed:
                continue
            found.append(f"{path.relative_to(REPO_ROOT).as_posix()} imports {module} ({owner})")
    return found


# -- the matrix -------------------------------------------------------------


def test_the_matrix_covers_every_layer_in_the_workspace():
    """A new layer must be placed in the matrix, not silently unchecked."""
    assert set(ALL_LAYERS) == set(MAY_IMPORT)


def test_the_matrix_covers_every_distribution_in_the_workspace():
    assert set(distributions()) == set(DISTRIBUTION_MAY_DEPEND)


@pytest.mark.parametrize("layer", ALL_LAYERS)
def test_a_layer_imports_only_what_the_matrix_allows(layer):
    assert violations(layer) == []


def test_the_sdk_depends_on_nothing_at_all():
    """Every layer sits on the SDK, so anything it pulled in would reach all."""
    assert MAY_IMPORT["lefx.sdk"] == frozenset()
    assert violations("lefx.sdk") == []


# -- the specific rules the matrix exists for -------------------------------


@pytest.mark.parametrize("layer", ["lefx.device.respeaker", "lefx.device.simulated_respeaker"])
@pytest.mark.parametrize("forbidden", ["lefx.engine", "lefx.interfaces"])
def test_a_device_never_reaches_the_engine_or_the_interfaces(layer, forbidden):
    """The direction that makes a device replaceable.

    A device that imported the engine could not be used without it, and the
    engine could no longer be embedded without the device. Both hang off the
    SDK ports instead, which is why the simulator can stand in for hardware.

    Worth stating separately now that the hardware and the engine ship in one
    wheel: nothing at install time stops that import any more, only this.
    """
    offenders = [line for line in violations(layer) if forbidden in line]
    assert offenders == []


@pytest.mark.parametrize("forbidden", ["lefx.device.respeaker", "lefx.device.simulated_respeaker"])
def test_the_interfaces_never_import_a_device(forbidden):
    """Entry points are the mechanism, not a convention.

    An import here would put a device into every path that reaches the control
    surface, and uninstalling a package would stop being how you leave it out.
    """
    offenders = [line for line in violations("lefx.interfaces") if forbidden in line]
    assert offenders == []


def test_the_engine_carries_no_offline_state():
    """The engine renders effects. It has never heard of a cable.

    A connection is either up or down, and what the ring should show when it is
    down is an application's decision, published as a status and mapped outside
    the engine. A state named for the condition, wired in where effects are
    resolved, is the V1 arrangement this generation exists to be rid of.

    That the engine imports nothing from a device is the matrix's job; this is
    the part a dependency check cannot see, because the V1 version of it was a
    bare string.
    """
    for path in layer_files("lefx.engine"):
        used = {item.casefold() for item in code_strings_and_names(parse(path))}
        assert "offline" not in used, f"{path.relative_to(REPO_ROOT).as_posix()} names 'offline'"


# -- the distribution boundary, where there still is one --------------------


def test_every_layer_is_in_the_distribution_it_belongs_to():
    """Three packages, and which layer lives in which is not incidental.

    The runtime layers and both catalogues ship together because nothing ever
    installs a subset of them — no extra selects between the schema, the
    engine, the control surface and the hardware. The two optional ones are
    separate because something does select them: an installation without
    effect creation must not have effect creation.
    """
    expected = {
        "lefx.sdk": "led-ctrl-v3",
        "lefx.engine": "led-ctrl-v3",
        "lefx.interfaces": "led-ctrl-v3",
        "lefx.device.respeaker": "led-ctrl-v3",
        "lefx.sets.core_set": "led-ctrl-v3",
        "lefx.sets.smartspeaker_set": "led-ctrl-v3",
        "lefx.effect_creation": "led-ctrl-v3-effect-creation",
        "lefx.device.simulated_respeaker": "led-ctrl-v3-device-simulated-respeaker",
    }
    assert {layer: distribution_of(layer) for layer in ALL_LAYERS} == expected


@pytest.mark.parametrize("distribution", sorted(DISTRIBUTION_MAY_DEPEND))
def test_the_declared_dependencies_agree_with_what_the_layers_reach(distribution):
    """The pyproject and the imports are two statements of one fact.

    An import across a package boundary that the metadata does not declare
    installs broken; a dependency declared that nothing reaches for is a
    boundary that has quietly stopped meaning anything.
    """
    text = (PACKAGES_ROOT / distribution / "pyproject.toml").read_bytes()
    declared = tomllib.loads(text.decode("utf-8"))["project"]["dependencies"]
    internal = {
        requirement.split("==")[0].split("[")[0].strip()
        for requirement in declared
        if requirement.split("==")[0].split("[")[0].strip() in DISTRIBUTION_MAY_DEPEND
    }

    reached = {
        distribution_of(target)
        for layer in ALL_LAYERS
        if distribution_of(layer) == distribution
        for target in MAY_IMPORT[layer]
        if distribution_of(target) != distribution
    }

    assert internal <= DISTRIBUTION_MAY_DEPEND[distribution]
    assert internal == reached


# -- Qt stays on the window side --------------------------------------------


@pytest.mark.parametrize("module", GUI_FREE_SIMULATOR_MODULES)
def test_the_service_half_of_the_simulator_carries_no_qt(module):
    """Installing the simulator must not put a GUI toolkit in the service.

    Checked statically rather than by importing, because the toolkit *is*
    installed in this workspace — an import that succeeded here would prove
    nothing about the machine where it is not.
    """
    path = SIMULATOR_ROOT / f"{module}.py"
    qt = sorted(name for name in imported_modules(parse(path)) if name.split(".")[0] == "PySide6")
    assert qt == []


def test_every_simulator_module_is_either_gui_free_or_declared_gui_only():
    """So a new module cannot quietly become the one that pulls Qt in."""
    modules = {path.stem for path in SIMULATOR_ROOT.glob("*.py")} - {"__init__"}
    assert modules == set(GUI_FREE_SIMULATOR_MODULES) | GUI_ONLY_SIMULATOR_MODULES


def test_importing_the_simulator_package_does_not_import_qt():
    """The package's own ``__init__`` is the trap: it is what a factory reaches
    through, and one convenience re-export of the window would undo the extra."""
    reached = imported_modules(parse(SIMULATOR_ROOT / "__init__.py"))
    assert not any(name.split(".")[0] == "PySide6" for name in reached)
    assert not any(name.rsplit(".", 1)[-1] in GUI_ONLY_SIMULATOR_MODULES for name in reached)


@pytest.mark.parametrize("module", GUI_FREE_STUDIO_MODULES)
def test_the_controller_half_of_the_studio_carries_no_qt(module):
    """What the studio does has to be checkable without a display.

    These modules hold the device, the catalogue and the playback rules — the
    part with decisions in it. Behind Qt they would only ever be exercised by a
    person clicking, which is the kind of testing that stops happening.
    """
    path = STUDIO_ROOT / f"{module}.py"
    qt = sorted(name for name in imported_modules(parse(path)) if name.split(".")[0] == "PySide6")
    assert qt == []


def test_every_studio_module_is_either_gui_free_or_declared_gui_only():
    modules = {path.stem for path in STUDIO_ROOT.glob("*.py")} - {"__init__"}
    assert modules == set(GUI_FREE_STUDIO_MODULES) | GUI_ONLY_STUDIO_MODULES


def test_importing_the_studio_package_does_not_import_qt():
    """So a test run without a display can still reach the half worth testing."""
    reached = imported_modules(parse(STUDIO_ROOT / "__init__.py"))
    assert not any(name.split(".")[0] == "PySide6" for name in reached)
    assert not any(name.rsplit(".", 1)[-1] in GUI_ONLY_STUDIO_MODULES for name in reached)


def test_the_authoring_half_of_effect_creation_carries_no_qt():
    """The line that makes Qt a hard dependency bearable.

    Merging the studio into the authoring package put a 150 MB toolkit into
    every installation that wanted ``lefx-pack``. That is acceptable only while
    the toolkit stays unreached: a build pipeline runs the packer, and the
    packer must not import a window to do it. Everything directly under
    lefx/effect_creation/ is that half; only studio/ is allowed to draw.
    """
    offenders = []
    for path in sorted(CREATION_ROOT.glob("*.py")):
        qt = [name for name in imported_modules(parse(path)) if name.split(".")[0] == "PySide6"]
        if qt:
            offenders.append(f"{path.name} imports {', '.join(sorted(qt))}")
    assert offenders == []


def test_the_authoring_half_never_imports_the_studio():
    """One direction, and it is the one that keeps the packer headless.

    The studio reaches down into the authoring functions; nothing reaches up.
    A single convenience import here — a scaffolder that offers to open the
    window it just wrote — would pull Qt into ``lefx-pack`` through the back
    door and undo the rule above without tripping it.
    """
    offenders = []
    for path in sorted(CREATION_ROOT.glob("*.py")):
        reached = sorted(
            name for name in imported_modules(parse(path))
            if name == "lefx.effect_creation.studio"
            or name.startswith("lefx.effect_creation.studio.")
        )
        if reached:
            offenders.append(f"{path.name} imports {', '.join(reached)}")
    assert offenders == []
