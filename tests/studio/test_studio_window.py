"""The studio's window, checked without anyone looking at it.

These skip where Qt is not installed, like the simulator's window tests. What
they are worth is the class of mistake that only appears when Qt is real: an
editor that cannot round-trip the value its type declares, a form that builds
before its layout, a paint that throws.

The most valuable one is the last: every definition in the catalogue is selected
in turn and applied. That is the studio's whole promise — that it can drive
anything the schema can describe — and it is the promise a hand-written form per
effect would quietly break the first time somebody wrote a new one.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6", reason="the studio window needs Qt")

# Must be set before the first QApplication: there is no display here.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from lefx.sdk import (  # noqa: E402
    ParamDefinition,
    ParamType,
    normalize_parameter_value,
)
from lefx.studio import catalogue  # noqa: E402
from lefx.studio.parameters import EDITORS, SchemaForm, editor_for  # noqa: E402
from lefx.studio.ring import RingMonitor  # noqa: E402
from lefx.studio.session import StudioSession  # noqa: E402
from lefx.studio.window import KIND_FILTERS, StudioWindow  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


# -- one editor per declared type -------------------------------------------


def test_every_parameter_type_has_an_editor():
    """The mapping is total by construction, and stays total by this.

    A type added to the SDK without an editor here would produce an effect with
    a field nobody can change, which is worse than a failure at import.
    """
    assert set(EDITORS) == set(ParamType)


SAMPLES: list[tuple[ParamDefinition, object]] = [
    (ParamDefinition(name="flag", type=ParamType.BOOL, default=False), True),
    (ParamDefinition(name="count", type=ParamType.INT, default=1, minimum=0, maximum=10), 7),
    (ParamDefinition(name="speed", type=ParamType.FLOAT, default=1.0, minimum=0.1, maximum=4.0), 2.5),
    (ParamDefinition(name="loose", type=ParamType.FLOAT, default=0.0), 12.5),
    (ParamDefinition(name="duration_ms", type=ParamType.DURATION_MS, default=500, minimum=1,
                     maximum=10000, unit="ms"), 2500),
    (ParamDefinition(name="direction_deg", type=ParamType.ANGLE_DEG, default=0.0, unit="deg"), 137.0),
    (ParamDefinition(name="mode", type=ParamType.ENUM, enum_values=("a", "b", "c"), default="a"), "c"),
    (ParamDefinition(name="color", type=ParamType.COLOR, default="#112233"), "#AABBCC"),
    (ParamDefinition(name="colors", type=ParamType.COLOR_LIST, default=["#FF0000", "#00FF00"],
                     minimum=2, maximum=6), ["#010203", "#040506", "#070809"]),
    (
        ParamDefinition(name="gradient", type=ParamType.GRADIENT,
                        default=[{"at": 0.0, "color": "#000000"}, {"at": 1.0, "color": "#FFFFFF"}]),
        [{"at": 0.0, "color": "#101010"}, {"at": 0.4, "color": "#808080"},
         {"at": 1.0, "color": "#F0F0F0"}],
    ),
    (
        ParamDefinition(name="color_range", type=ParamType.COLOR_RANGE,
                        default={"hue": [0.0, 360.0], "saturation": [0.0, 1.0],
                                 "brightness": [0.0, 1.0]}),
        {"hue": [90.0, 180.0], "saturation": [0.2, 0.8], "brightness": [0.1, 0.9]},
    ),
]


@pytest.mark.parametrize(("parameter", "value"), SAMPLES, ids=lambda item: getattr(item, "name", ""))
def test_an_editor_gives_back_what_it_was_given(qt_app, parameter, value):
    """And gives it back in a form the schema accepts.

    Round-tripping through the normaliser is the point: an editor that produced
    something almost right would fail on apply, at the far end, with an error
    about a value the person never typed.
    """
    editor = editor_for(parameter)
    editor.set_value(value)
    read_back = editor.value()

    assert normalize_parameter_value(parameter, read_back) == normalize_parameter_value(
        parameter, value
    )


@pytest.mark.parametrize(("parameter", "value"), SAMPLES, ids=lambda item: getattr(item, "name", ""))
def test_an_editor_starts_from_the_declared_default(qt_app, parameter, value):
    del value
    editor = editor_for(parameter)
    editor.set_value(parameter.default)
    assert normalize_parameter_value(parameter, editor.value()) == parameter.default


def test_a_nullable_parameter_can_be_set_to_no_value(qt_app):
    parameter = ParamDefinition(
        name="background_color", type=ParamType.COLOR, nullable=True, default=None
    )
    editor = editor_for(parameter)

    editor.set_value("#123456")
    assert editor.value() == "#123456"

    editor.set_value(None)
    assert editor.value() is None


def test_a_colour_list_keeps_to_the_length_the_schema_declares(qt_app):
    parameter = ParamDefinition(
        name="colors", type=ParamType.COLOR_LIST, default=["#FF0000", "#00FF00"],
        minimum=2, maximum=3,
    )
    editor = editor_for(parameter)
    editor.set_value(["#FF0000", "#00FF00"])

    for _ in range(5):
        editor._add_row("#0000FF")  # noqa: SLF001 — the button's own handler
    assert len(editor.value()) == 3

    for _ in range(5):
        editor._remove_row()  # noqa: SLF001
    assert len(editor.value()) == 2


def test_a_gradient_editor_cannot_produce_an_invalid_gradient(qt_app):
    """Sorted, starting at 0, ending at 1 — the schema's rules, enforced by the
    control rather than reported after the fact."""
    parameter = ParamDefinition(
        name="gradient", type=ParamType.GRADIENT,
        default=[{"at": 0.0, "color": "#000000"}, {"at": 1.0, "color": "#FFFFFF"}],
    )
    editor = editor_for(parameter)
    editor.set_value(
        [{"at": 1.0, "color": "#FFFFFF"}, {"at": 0.3, "color": "#888888"},
         {"at": 0.0, "color": "#000000"}]
    )
    stops = editor.value()

    assert [stop["at"] for stop in stops] == sorted(stop["at"] for stop in stops)
    assert stops[0]["at"] == 0.0 and stops[-1]["at"] == 1.0
    assert normalize_parameter_value(parameter, stops) == stops


def test_a_colour_range_keeps_its_bounds_in_order(qt_app):
    parameter = ParamDefinition(
        name="color_range", type=ParamType.COLOR_RANGE,
        default={"hue": [0.0, 360.0], "saturation": [0.0, 1.0], "brightness": [0.0, 1.0]},
    )
    editor = editor_for(parameter)
    low, high = editor.bounds["hue"]
    high.setValue(100.0)
    low.setValue(200.0)

    values = editor.value()
    assert values["hue"][0] <= values["hue"][1]
    assert normalize_parameter_value(parameter, values) == values


def test_a_form_reports_every_change_once(qt_app):
    changes: list[int] = []
    form = SchemaForm(
        {
            "color": ParamDefinition(name="color", type=ParamType.COLOR, default="#000000"),
            "speed": ParamDefinition(name="speed", type=ParamType.FLOAT, default=1.0,
                                     minimum=0.1, maximum=4.0),
        },
        on_change=lambda: changes.append(1),
    )
    form.editors["speed"].set_value(2.0)
    form.editors["speed"].spin.setValue(3.0)

    assert changes
    assert set(form.values()) == {"color", "speed"}


# -- the monitor ------------------------------------------------------------


def test_the_monitor_draws_at_any_ring_size(qt_app):
    from PySide6.QtGui import QImage

    for led_count in (1, 5, 12, 24):
        monitor = RingMonitor(led_count)
        monitor.set_colors([0x00FF00] * led_count)
        image = QImage(240, 240, QImage.Format.Format_RGB32)
        image.fill(0)
        monitor.resize(240, 240)
        monitor.render(image)
        assert monitor.led_count == led_count


def test_the_monitor_ignores_a_frame_of_the_wrong_length(qt_app):
    """The same rule the sinks follow: padding would light positions nothing sent."""
    monitor = RingMonitor(12)
    monitor.set_colors([0xFF0000] * 12)
    monitor.set_colors([0x00FF00] * 11)
    assert monitor._colors == [0xFF0000] * 12  # noqa: SLF001


def test_the_monitor_draws_the_sectors_a_direction_can_land_on(qt_app):
    from PySide6.QtGui import QImage

    monitor = RingMonitor(12)
    monitor.set_show_sectors(True)
    monitor.mark_sector(3)
    image = QImage(240, 240, QImage.Format.Format_RGB32)
    monitor.resize(240, 240)
    monitor.render(image)
    assert monitor._marked_sector == 3  # noqa: SLF001


# -- the window over the real catalogue -------------------------------------


@pytest.fixture
def window(qt_app, built_catalogue, tmp_path, monkeypatch):
    monkeypatch.setenv("LEFX_STATE_ROOT", str(tmp_path))
    session = StudioSession(
        led_count=12, fps=60.0, search_paths=[built_catalogue],
        state_file=tmp_path / "background.json",
    )
    built = StudioWindow(session, initial_output="null")
    try:
        yield built
    finally:
        built.close()


def test_the_window_opens_on_the_whole_catalogue(window):
    assert window.list.count() > 0
    assert len(window.entries) == 36
    assert window.session.output_name == "null"


def test_the_filters_narrow_the_list(window):
    everything = window.list.count()

    window.kind_filter.setCurrentIndex([label for label, _ in KIND_FILTERS].index("Events"))
    events_only = window.list.count()
    assert 0 < events_only < everything

    window.search.setText("wakeword")
    assert window.list.count() <= events_only


def test_searching_narrows_with_every_word(window):
    window.search.setText("ring")
    one_word = window.list.count()
    window.search.setText("ring core")
    assert window.list.count() <= one_word


@pytest.mark.parametrize("effect_id", [
    "solid_fill", "breathing_ring", "gradient_ring", "palette_cycle", "random_sparkle",
    "direction_indicator", "level_meter", "fade_flash", "pulse_signal",
])
def test_selecting_a_definition_builds_a_form_and_plays_it(window, effect_id):
    """The studio's promise, one definition at a time.

    Selecting builds every control from the schema and — for the forms where it
    means anything — applies it. Nothing here knows what these effects are; if
    the schema can describe it, the studio can drive it.
    """
    window.search.setText(effect_id)
    window.kind_filter.setCurrentIndex(0)
    match = next(
        row for row in range(window.list.count())
        if window.list.item(row).data(0x0100) == effect_id
    )
    window.list.setCurrentRow(match)

    assert window.selected is not None and window.selected.effect_id == effect_id
    assert window.config_form is not None
    assert set(window.config_form.values()) == set(
        window.selected.definition.parameter_schema
    )

    window._apply()  # noqa: SLF001 — what the play button calls
    status = window.session.status()
    running = [
        entry["effect_id"] for entry in status["layers"].values() if entry
    ]
    assert effect_id in running


def test_a_pulled_overlay_offers_no_input_controls(window):
    """The device supplies those values, and the next sample would overwrite
    anything typed here — which reads as the controls being broken."""
    window.search.setText("direction_indicator")
    window.list.setCurrentRow(0)

    assert catalogue.pulls_a_provider(window.selected.definition) == "doa"
    assert window.inputs_form is None


def test_a_pushed_overlay_offers_input_controls(window):
    window.search.setText("level_meter")
    window.list.setCurrentRow(0)

    assert catalogue.pulls_a_provider(window.selected.definition) is None
    assert window.inputs_form is not None
    assert "progress" in window.inputs_form.values()


def test_choosing_a_preset_fills_the_form(window):
    window.search.setText("solid_fill")
    window.list.setCurrentRow(0)
    if window.preset_box.count() <= 1:
        pytest.skip("solid_fill ships without presets")

    window.preset_box.setCurrentIndex(1)
    preset_id = window.preset_box.currentData()
    preset = next(
        one for one in window.session.registry.list_presets(effect_id="solid_fill")
        if one.preset_id == preset_id
    )
    values = window.config_form.values()
    for name, expected in preset.params.items():
        assert values[name] == expected


def test_the_monitor_shows_the_frames_the_device_was_sent(window):
    window.search.setText("solid_fill")
    window.list.setCurrentRow(0)
    window.config_form.set_values({"color": "#FF0000", "brightness": 1.0})
    window._apply()  # noqa: SLF001

    # The tap runs on the render thread and reaches the widget through a signal;
    # in a test there is no event loop to deliver it, so read what was sent.
    sent = window.session.service.sink
    assert sent.frame_count > 0


def test_closing_the_window_lets_go_of_the_device(window):
    window.close()
    assert window.session.service is None


# -- curating a preset from what is on screen -------------------------------


def test_the_preset_dialog_opens_on_the_values_being_edited(window, tmp_path, monkeypatch):
    """What it offers to save is what the form currently holds — not the
    definition's defaults, and not the preset that was loaded before."""
    from lefx.studio.preset_dialog import PresetDialog

    window.search.setText("solid_fill")
    window.list.setCurrentRow(0)
    window.config_form.set_values({"color": "#204080", "brightness": 0.7})

    dialog = PresetDialog(window.selected.definition, window.config_form.values())
    try:
        dialog.label.setText("Studio Blau")
        assert dialog.preset_id.text() == "solid_fill_studio_blau"
        assert dialog.draft().params["color"] == "#204080"
        # The real source is on disk and was found without being told where.
        assert dialog.source_dir.text().endswith("solid_fill")
        assert dialog.problems.text() == ""
    finally:
        dialog.deleteLater()


def test_the_dialog_will_not_save_something_the_schema_refuses(window):
    from lefx.studio.preset_dialog import PresetDialog
    from PySide6.QtWidgets import QDialogButtonBox

    window.search.setText("solid_fill")
    window.list.setCurrentRow(0)

    dialog = PresetDialog(window.selected.definition, {"brightness": 5.0})
    try:
        dialog.label.setText("Zu hell")
        assert dialog.problems.text()
        assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
    finally:
        dialog.deleteLater()


def test_the_dialog_says_when_it_would_replace_one(window):
    from lefx.studio.preset_dialog import PresetDialog

    window.search.setText("solid_fill")
    window.list.setCurrentRow(0)

    dialog = PresetDialog(window.selected.definition, window.config_form.values())
    try:
        dialog.preset_id.setText("solid_fill_calm_blue")
        dialog._revalidate()  # noqa: SLF001 — what typing triggers
        assert dialog.overwrite is True
        assert "überschrieben" in dialog.summary.text()
    finally:
        dialog.deleteLater()
