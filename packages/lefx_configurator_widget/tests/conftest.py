import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from lefx.configurator_widget import LefxCatalogueAdapter


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app
    app.processEvents()


@pytest.fixture(scope="session")
def catalogue():
    with LefxCatalogueAdapter.installed() as adapter:
        yield adapter
