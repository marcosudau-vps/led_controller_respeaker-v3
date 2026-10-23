"""The layer panel: "Gesamteffekt", its layers, their elements and animations.

A view and nothing more. It is rebuilt from the editor's document after every
change and never edits that document itself; what the user asks for — add,
rename, hide, reorder, remove — leaves as a ``requested`` intent, and the page
runs it through :class:`lefx.effect_creation.visual.Editor`, whose validation
decides. Selection is kept by object id across rebuilds.

Read top-down like a graphics program's layer list: the topmost row is drawn
last and lies on top. That holds for layers and, inside a layer, for elements —
in the document both are stored bottom first, which is why both are listed
reversed. "Up" here therefore means "later in the document".
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lefx.effect_creation.visual.blocks import BLOCKS

ID_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1
NAME_ROLE = Qt.ItemDataRole.UserRole + 2

BLEND_LABELS = {"over": "überdeckt", "add": "addiert", "max": "Maximum"}


def leds(fraction: float, count: int) -> int:
    """The LED a ring share lands on, with the kernel's own rounding."""
    return int(fraction * count + 0.5)


def describe(item: dict, count: int) -> str:
    """One short line of what a block does, for the Details column."""
    p = item["properties"]
    kind = item["type"]
    if kind == "point":
        return f"LED {leds(p['position'], count) % count} · {p['color']}"
    if kind == "segment":
        return f"ab LED {leds(p['position'], count) % count} · {min(count, leds(p['length'], count))} LEDs · {p['color']}"
    if kind == "fill":
        return p["color"]
    if kind == "gradient":
        return f"{p['color']} → {p['end_color']}"
    if kind == "rotation":
        return f"{p['rate']:g} U/s" + (" · rückwärts" if p["reverse"] else "")
    if kind == "blink":
        return f"{p['frequency']:g} Hz · {p['duty']:.0%} an"
    if kind == "pulse":
        return f"{p['frequency']:g} Hz · {p['minimum']:g} … {p['maximum']:g} %P"
    if kind == "color_cycle":
        return f"{p['rate']:g} Zyklen/s"
    if kind == "sparkle":
        return f"{p['frequency']:g} Hz · {p['density']:.0%} leuchtend"
    return ""


def swatch(*colors: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    width = 12 / len(colors)
    for index, color in enumerate(colors):
        painter.fillRect(int(1 + index * width), 1, int(width + 0.99), 12, QColor(color))
    painter.setPen(QColor(90, 90, 90))
    painter.drawRect(0, 0, 13, 13)
    painter.end()
    return QIcon(pixmap)


class DesignTree(QWidget):
    selected = Signal(object)
    """An object id, or ``None`` for "Gesamteffekt"."""
    requested = Signal(str, dict)
    """An intent for the page: add_layer, add_element, add_animation, duplicate,
    remove, raise, lower, rename, visible."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._document: dict | None = None
        self._led_count = 12
        self._collapsed: set[str] = set()
        self._building = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.setSpacing(2)
        self.add_layer_button = self._button("+ Ebene", "Neue Ebene oben anlegen (Strg+L)",
                                             lambda: self.requested.emit("add_layer", {}))
        self.add_element_button = self._button("+ Element", "Visuelles Element zur Ebene hinzufügen")
        self.add_element_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.element_menu = QMenu(self)
        self.element_menu.aboutToShow.connect(lambda: self._fill_block_menu(self.element_menu, "element"))
        self.add_element_button.setMenu(self.element_menu)
        self.add_animation_button = self._button("+ Animation", "Animation an die Ebene binden")
        self.add_animation_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.animation_menu = QMenu(self)
        self.animation_menu.aboutToShow.connect(lambda: self._fill_block_menu(self.animation_menu, "animation"))
        self.add_animation_button.setMenu(self.animation_menu)
        self.duplicate_button = self._button("⧉", "Duplizieren (Strg+D)", lambda: self.request_current("duplicate"))
        self.raise_button = self._button("▲", "Nach oben (im Bild weiter vorn)", lambda: self.request_current("raise"))
        self.lower_button = self._button("▼", "Nach unten (im Bild weiter hinten)", lambda: self.request_current("lower"))
        self.remove_button = self._button("✕", "Entfernen (Entf)", lambda: self.request_current("remove"))
        for button in (self.add_layer_button, self.add_element_button, self.add_animation_button):
            bar.addWidget(button)
        bar.addStretch(1)
        for button in (self.duplicate_button, self.raise_button, self.lower_button, self.remove_button):
            bar.addWidget(button)
        layout.addLayout(bar)

        hint = QLabel("Oben in der Liste = oben im Bild")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Objekt", "Details"])
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.currentItemChanged.connect(self._on_current)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.itemCollapsed.connect(lambda item: self._collapsed.add(item.data(0, ID_ROLE) or ""))
        self.tree.itemExpanded.connect(lambda item: self._collapsed.discard(item.data(0, ID_ROLE) or ""))
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 170)
        layout.addWidget(self.tree, stretch=1)

    def _button(self, text: str, tip: str, action=None) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        if action is not None:
            button.clicked.connect(action)
        return button

    # -- state --------------------------------------------------------------

    def current_id(self) -> str | None:
        item = self.tree.currentItem()
        return None if item is None else item.data(0, ID_ROLE)

    def current_kind(self) -> str:
        item = self.tree.currentItem()
        return "effect" if item is None else item.data(0, KIND_ROLE)

    def select(self, target: str | None) -> None:
        item = self._find(target)
        if item is not None:
            self.tree.setCurrentItem(item)

    def _find(self, target: str | None) -> QTreeWidgetItem | None:
        def visit(item):
            if item.data(0, ID_ROLE) == target:
                return item
            for index in range(item.childCount()):
                found = visit(item.child(index))
                if found is not None:
                    return found
            return None

        root = self.tree.topLevelItem(0)
        return None if root is None else visit(root)

    def focus_layer(self) -> str | None:
        """The layer the selection belongs to; where new blocks go."""
        item = self.tree.currentItem()
        while item is not None and item.data(0, KIND_ROLE) != "layer":
            item = item.parent()
        return None if item is None else item.data(0, ID_ROLE)

    # -- building -----------------------------------------------------------

    def show_document(self, document: dict, selected: str | None, led_count: int) -> None:
        self._document = document
        self._led_count = led_count
        self._building = True
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            root = QTreeWidgetItem(["Gesamteffekt", document["effect"]["title"]])
            root.setData(0, ID_ROLE, None)
            root.setData(0, KIND_ROLE, "effect")
            font = QFont(root.font(0))
            font.setBold(True)
            root.setFont(0, font)
            root.setToolTip(0, "Das ganze Projekt und seine zusammengesetzte Vorschau — kein Runtime-Layer")
            self.tree.addTopLevelItem(root)
            for layer in reversed(document["layers"]):
                self._add_layer(root, layer, document)
            self._expand(root)
            target = self._find(selected) or root
            self.tree.setCurrentItem(target)
        finally:
            self.tree.blockSignals(False)
            self._building = False
        self._update_buttons()

    def _expand(self, item: QTreeWidgetItem) -> None:
        item.setExpanded((item.data(0, ID_ROLE) or "") not in self._collapsed)
        for index in range(item.childCount()):
            self._expand(item.child(index))

    def _add_layer(self, parent: QTreeWidgetItem, layer: dict, document: dict) -> None:
        props = layer["properties"]
        details = [BLEND_LABELS[layer["blend"]], f"{props['opacity']:.0%}"]
        if props["mask_length"] < 1 or props["mask_invert"]:
            details.append("maskiert")
        item = QTreeWidgetItem([layer["name"], " · ".join(details)])
        item.setData(0, ID_ROLE, layer["id"])
        item.setData(0, KIND_ROLE, "layer")
        item.setData(0, NAME_ROLE, layer["name"])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked if layer["enabled"] else Qt.CheckState.Unchecked)
        item.setToolTip(0, "Häkchen: im Gesamteffekt sichtbar · Doppelklick oder F2: umbenennen")
        if not layer["enabled"]:
            font = QFont(item.font(0))
            font.setItalic(True)
            item.setFont(0, font)
            item.setForeground(0, QColor(130, 130, 130))
        parent.addChild(item)
        self._add_children(item, layer["children"])
        for animation in document["animations"]:
            if animation["target"] == layer["id"]:
                child = QTreeWidgetItem(["⟳ " + BLOCKS[animation["type"]].label,
                                         describe(animation, self._led_count)])
                child.setData(0, ID_ROLE, animation["id"])
                child.setData(0, KIND_ROLE, "animation")
                child.setForeground(1, QColor(140, 140, 140))
                item.addChild(child)

    def _add_children(self, parent: QTreeWidgetItem, children: list[dict]) -> None:
        for child in reversed(children):
            if child.get("type") == "group":
                item = QTreeWidgetItem([child["name"], "Gruppe"])
                item.setData(0, KIND_ROLE, "group")
                item.setData(0, NAME_ROLE, child["name"])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setData(0, ID_ROLE, child["id"])
                parent.addChild(item)
                self._add_children(item, child["children"])
                continue
            item = QTreeWidgetItem([BLOCKS[child["type"]].label, describe(child, self._led_count)])
            item.setData(0, ID_ROLE, child["id"])
            item.setData(0, KIND_ROLE, "element")
            props = child["properties"]
            colors = [props["color"]] + ([props["end_color"]] if "end_color" in props else [])
            item.setIcon(0, swatch(*colors))
            item.setForeground(1, QColor(140, 140, 140))
            parent.addChild(item)

    # -- reacting -----------------------------------------------------------

    def _on_current(self, current, _previous=None) -> None:
        if self._building:
            return
        self._update_buttons()
        self.selected.emit(None if current is None else current.data(0, ID_ROLE))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._building or column != 0:
            return
        kind = item.data(0, KIND_ROLE)
        target = item.data(0, ID_ROLE)
        if kind in ("layer", "group") and item.text(0) != item.data(0, NAME_ROLE):
            intent = ("rename", {"target": target, "name": item.text(0)})
        elif kind == "layer":
            intent = ("visible", {"target": target, "enabled": item.checkState(0) == Qt.CheckState.Checked})
        else:
            return
        # Deferred: the answer rebuilds this tree, which must not happen while
        # Qt is still inside the item's own change notification.
        QTimer.singleShot(0, lambda: self.requested.emit(*intent))

    def _on_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        if item.data(0, KIND_ROLE) in ("layer", "group") and column == 0:
            self.tree.editItem(item, 0)

    def rename_current(self) -> None:
        item = self.tree.currentItem()
        if item is not None and item.data(0, KIND_ROLE) in ("layer", "group"):
            self.tree.editItem(item, 0)

    def request_current(self, name: str) -> None:
        """Ask for ``name`` on the selected object, if one is selected."""
        target = self.current_id()
        if target is not None:
            self.requested.emit(name, {"target": target})

    def _update_buttons(self) -> None:
        kind = self.current_kind()
        movable = kind in ("layer", "element", "group")
        self.raise_button.setEnabled(movable)
        self.lower_button.setEnabled(movable)
        self.remove_button.setEnabled(kind != "effect")
        self.duplicate_button.setEnabled(kind in ("layer", "element", "group"))

    def bound_types(self) -> set[str]:
        layer = self.focus_layer()
        if self._document is None or layer is None:
            return set()
        return {item["type"] for item in self._document["animations"] if item["target"] == layer}

    def _fill_block_menu(self, menu: QMenu, category: str) -> None:
        menu.clear()
        bound = self.bound_types() if category == "animation" else set()
        for name, block in BLOCKS.items():
            if block.category != category:
                continue
            label = block.label + ("  (an dieser Ebene vorhanden)" if name in bound else "")
            action = menu.addAction(label)
            action.setEnabled(name not in bound)
            if name in bound:
                action.setToolTip("Pro Ebene ist jeder Animationstyp nur einmal zulässig.")
            action.triggered.connect(
                lambda _=False, n=name: self.requested.emit(f"add_{category}", {"type": n}))
        menu.setToolTipsVisible(True)

    def _context_menu(self, point: QPoint) -> None:
        item = self.tree.itemAt(point)
        if item is not None:
            self.tree.setCurrentItem(item)
        kind = self.current_kind()
        menu = QMenu(self)
        menu.addAction("Neue Ebene", lambda: self.requested.emit("add_layer", {}))
        elements = menu.addMenu("Element hinzufügen")
        self._fill_block_menu(elements, "element")
        animations = menu.addMenu("Animation hinzufügen")
        self._fill_block_menu(animations, "animation")
        if kind != "effect":
            menu.addSeparator()
            if kind in ("layer", "group"):
                menu.addAction("Umbenennen\tF2", self.rename_current)
            if kind in ("layer", "element", "group"):
                menu.addAction("Duplizieren\tStrg+D", lambda: self.request_current("duplicate"))
                menu.addAction("Nach oben", lambda: self.request_current("raise"))
                menu.addAction("Nach unten", lambda: self.request_current("lower"))
            menu.addAction("Entfernen\tEntf", lambda: self.request_current("remove"))
        menu.exec(self.tree.viewport().mapToGlobal(point))


__all__ = ["DesignTree", "describe", "leds"]
