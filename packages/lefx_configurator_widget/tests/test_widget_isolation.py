import os
from pathlib import Path
from shutil import copyfile
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "src/lefx/configurator_widget/widgets"
LOADER = """
import importlib.abc
import importlib.util
import os
import sys
class NoProject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "lefx" or fullname.startswith("lefx."):
            raise ModuleNotFoundError(fullname)
if os.environ.get("LEFX_QT_ONLY_PYTHON"):
    assert importlib.util.find_spec("lefx") is None
sys.meta_path.insert(0, NoProject())
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit
import shiboken6
source = Path(sys.argv[1])
assert list(source.parent.iterdir()) == [source]
spec = importlib.util.spec_from_file_location("isolated_editor", source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
app = QApplication([])
"""
SCENARIOS = {
    "angle_editor.py": """
w = module.AngleEditor(value=45.123456789, decimals=2)
changed, edited = QSignalSpy(w.value_changed), QSignalSpy(w.value_edited)
w.set_value(725.123456789)
assert abs(w.value() - 5.123456789) < 1e-12 and edited.count() == 0
w.show()
w.field.selectAll()
QTest.keyClicks(w.field, "-45")
assert w.value() == 315 and not w.error()
assert changed.count() == edited.count() > 0
w.set_read_only(True)
QTest.keyClicks(w.field, "7")
assert w.value() == 315 and not w.dial.isEnabled()
""",
    "range_editor.py": """
w = module.RangeEditor(number_type=float, value=(.12, .87654321),
                       minimum=0, maximum=1, step=.1, decimals=5, unit="ratio")
spy = QSignalSpy(w.value_edited)
w.set_value((.123456789, .87654321))
assert w.value() == (.123456789, .87654321) and spy.count() == 0
w.show()
w.fields[0].selectAll()
QTest.keyClicks(w.fields[0], ".99")
assert "Maximum" in w.error() and spy.count() > 0
w.fields[0].selectAll()
QTest.keyClicks(w.fields[0], ".2")
assert w.value() == (.2, .87654321)
w.set_read_only(True)
assert all(field.isReadOnly() for field in w.fields)
integer = module.RangeEditor(number_type=int, value=(-12, 75000000000), step=2)
assert integer.value() == (-12, 75000000000)
integer._controls[1].click()
assert integer.value() == (-10, 75000000000)
""",
    "color_list_editor.py": """
w = module.ColorListEditor(value=("#FF0000", "#123456", "#FF0000"),
                           minimum=2, maximum=4)
spy = QSignalSpy(w.value_edited)
w.set_value(w.value())
assert not w.error() and spy.count() == 0
w.show()
w.open_detail()
app.processEvents()
dialog = w.findChild(QDialog)
full = dialog.findChild(module.ColorListEditor)
full.list.setCurrentRow(1)
full.up_button.click()
full.add_color("#AABBCC")
full.add_color("#DDFFFF")
assert full.value() == ["#123456", "#FF0000", "#FF0000", "#AABBCC"]
assert w.value()[0] == "#FF0000" and spy.count() == 0
dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
assert w.value() == full.value() and spy.count() == 1
full = w.create_detail()
full.remove_color()
full.remove_color()
full.remove_color()
assert len(full.value()) == 2
w.set_read_only(True)
assert not w.commit_detail(full)
w.set_value(["#FF0000"] * 5)
assert len(w.value()) == 5 and w.error() and spy.count() == 1
""",
    "gradient_editor.py": """
w = module.GradientEditor()
spy = QSignalSpy(w.value_edited)
detail = w.create_detail()
detail.add_button.click()
detail.table.item(1, 0).setText("0.1234567890123")
detail.table.item(1, 1).setText("#FF6622")
assert detail.value()[1]["at"] == .1234567890123
assert not detail.error() and spy.count() == 0
detail.table.setCurrentCell(0, 0)
assert not detail.remove_button.isEnabled()
assert w.commit_detail(detail) and spy.count() == 1
w.show()
assert w.grab().width() > 0
detail = w.create_detail()
detail.table.setCurrentCell(1, 0)
detail.remove_button.click()
assert len(detail.value()) == 2 and len(w.value()) == 3
bad = [{"at": 0, "color": "#123456"}] * 17
w.set_value(bad)
assert w.value() == bad and w.error()
w.set_read_only(True)
assert not w.commit_detail(detail)
generic = module.GradientEditor(minimum=1, maximum=3, require_endpoints=False,
                                value=[{"at": .25, "color": "#123456"}])
assert not generic.error()
""",
    "color_range_editor.py": """
w = module.ColorRangeEditor(value={"hue":[20, 160], "saturation":[.2, 1], "brightness":[.1, .8]})
spy = QSignalSpy(w.value_edited)
detail = w.create_detail()
field = detail.fields["brightness"][0]
field.selectAll()
QTest.keyClicks(field, ".987654321")
assert detail.error() and not w.commit_detail(detail)
field.selectAll()
QTest.keyClicks(field, ".123456789")
assert not detail.error() and w.commit_detail(detail)
assert w.value()["brightness"][0] == .123456789 and spy.count() == 1
w.show()
assert w.grab().width() > 0
w.set_read_only(True)
detail = w.create_detail()
assert all(field.isReadOnly() for fields in detail.fields.values() for field in fields)
""",
    "repeatable_container.py": """
class Field(QLineEdit):
    value_edited = Signal(object)
    def __init__(self, value, parent):
        super().__init__(value, parent)
        self.textEdited.connect(self.value_edited.emit)
w = module.RepeatableContainer(Field, lambda child: child.text(), lambda: "neu", maximum=2)
spy = QSignalSpy(w.value_edited)
assert w.ids() == () and w.value() == []
first, second = w.add(), w.add()
assert first != second and w.add() is None and w.ids() == (first, second)
assert w.move(second, -1) and w.ids() == (second, first)
child = w._rows[0].editor
child.selectAll()
QTest.keyClicks(child, "edit")
assert w.value() == ["edit", "neu"] and spy.count() >= 4
w.set_read_only(True)
assert not w.remove(second) and not w.move(second, 1) and w.add() is None
w.set_read_only(False)
assert w.remove(second) and w.ids() == (first,)
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
assert not shiboken6.isValid(child)
count = spy.count()
w.set_value(["a", "a", "b"])
assert w.error() and w.value() == ["a", "a", "b"] and spy.count() == count
""",
    "led_ring_preview.py": """
w = module.LedRingPreview(led_count=3, diameter=140, clockwise=False)
w.set_value([0x00C066, None, "#FF4400"])
assert w.value()[0] == QColor("#00C066") and w.value()[1] is None
w.show()
assert w.grab().size().width() > 0
try:
    w.set_value([0xABCDEF])
except ValueError:
    assert w.value()[0] == QColor("#00C066")
else:
    raise AssertionError("Invalid frame length was accepted")
w.configure(led_count=1, start_angle=45)
assert w.value() == (None,)
w.set_value([0])
assert w.value()[0] == QColor("#000000")
""",
}


@pytest.mark.parametrize("filename", SCENARIOS)
def test_copy_one_file_into_a_clean_process(filename, tmp_path):
    copied = tmp_path / filename
    copyfile(SOURCE / filename, copied)
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    python = os.environ.get("LEFX_QT_ONLY_PYTHON", sys.executable)
    process = subprocess.run(
        [python, "-I", "-B", "-c", LOADER + SCENARIOS[filename], str(copied)],
        cwd=tmp_path, env=env, text=True, encoding="utf-8",
        capture_output=True, timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr
