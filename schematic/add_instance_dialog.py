import json
import os

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPen
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from library_manager import ANALOG_LIB_DATA, ANALOG_LIB_NAME, DATA_PATH
from schematic.symbols import SYMBOLS

IHP_LIB_NAME = "IHP_SG13G2"


class AddInstanceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Instance")
        self.resize(600, 400)
        self.selected_library = ""
        self.selected_cell = ""
        self.selected_view = "schematic"
        self.selected_comp_type = ""
        self.selected_props = {}
        self.selected_cell_data = {}
        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal, self)
        layout.addWidget(splitter, 1)

        self.tree = QTreeWidget(splitter)
        self.tree.setHeaderLabel("Libraries")
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        splitter.addWidget(self.tree)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        self.cell_label = QLabel("Cell: -", right)
        self.library_label = QLabel("Library: -", right)
        self.description_label = QLabel("", right)
        self.description_label.setWordWrap(True)
        self.params_label = QLabel("", right)
        self.params_label.setWordWrap(True)
        self.preview = QGraphicsView(right)
        self.preview.setMinimumHeight(150)
        self.preview.setScene(QGraphicsScene(self.preview))
        self.view_combo = QComboBox(right)
        self.view_combo.addItems(["schematic", "layout"])
        right_layout.addWidget(self.cell_label)
        right_layout.addWidget(self.library_label)
        right_layout.addWidget(self.description_label)
        right_layout.addWidget(self.params_label)
        right_layout.addWidget(self.preview)
        right_layout.addWidget(QLabel("View:", right))
        right_layout.addWidget(self.view_combo)
        right_layout.addStretch(1)
        splitter.addWidget(right)
        splitter.setSizes([260, 340])

        buttons = QDialogButtonBox(self)
        self.place_button = buttons.addButton("Place", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        self.place_button.setEnabled(False)
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet("""
            QDialog, QWidget { background: #1e1e2e; color: #cdd6f4; }
            QTreeWidget, QGraphicsView, QComboBox {
                background: #181825; color: #cdd6f4; border: 1px solid #45475a;
            }
            QPushButton {
                background: #313244; color: #cdd6f4; border: 1px solid #6c7086;
                border-radius: 4px; padding: 5px 10px;
            }
            QPushButton:hover { background: #45475a; border-color: #89b4fa; }
        """)

    def _populate_tree(self):
        self.tree.clear()
        self._add_library(ANALOG_LIB_NAME, ANALOG_LIB_DATA)
        try:
            from pdk_manager import PDK, load_ihp_pdk
            tech = PDK.tech or load_ihp_pdk()
            if tech:
                self._add_pdk_library_to_tree(tech.get_pdk_library())
        except Exception:
            pass
        for lib_name, lib_data in sorted(self._load_user_libraries().items()):
            if lib_name in (ANALOG_LIB_NAME, IHP_LIB_NAME):
                continue
            self._add_library(lib_name, lib_data)
        self.tree.expandAll()

    def _load_user_libraries(self):
        if not os.path.exists(DATA_PATH):
            return {}
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return data.get("libraries", {}) if isinstance(data, dict) else {}

    def _add_library(self, lib_name, lib_data):
        label = f"{lib_name} (built-in)" if lib_name == ANALOG_LIB_NAME else lib_name
        lib_item = QTreeWidgetItem([label])
        lib_item.setData(0, Qt.UserRole, ("library", lib_name, None, None))
        self.tree.addTopLevelItem(lib_item)
        for cell_name, cell_data in sorted(lib_data.get("cells", {}).items()):
            self._add_cell(lib_item, lib_name, None, cell_name, cell_data)
        for cat_name, cat_data in sorted(lib_data.get("categories", {}).items()):
            cat_item = QTreeWidgetItem([cat_name])
            cat_item.setData(0, Qt.UserRole, ("category", lib_name, cat_name, None))
            font = cat_item.font(0)
            font.setItalic(True)
            cat_item.setFont(0, font)
            lib_item.addChild(cat_item)
            for cell_name, cell_data in sorted(cat_data.get("cells", {}).items()):
                self._add_cell(cat_item, lib_name, cat_name, cell_name, cell_data)

    def _add_pdk_library_to_tree(self, lib_dict):
        lib_name = lib_dict.get("name", IHP_LIB_NAME)
        lib_item = QTreeWidgetItem([lib_name])
        lib_item.setData(0, Qt.UserRole, ("library", lib_name, None, None, lib_dict))
        lib_item.setForeground(0, QColor(lib_dict.get("color", "#a6e3a1")))
        font = lib_item.font(0)
        font.setBold(True)
        lib_item.setFont(0, font)
        self.tree.addTopLevelItem(lib_item)

        categories = {}
        for cell_name, cell_data in lib_dict.get("cells", {}).items():
            categories.setdefault(cell_data.get("category", "Other"), []).append((cell_name, cell_data))
        for cat_name in ("MOS", "Passive", "BJT"):
            cells = categories.pop(cat_name, [])
            if cells:
                self._add_pdk_category(lib_item, lib_name, cat_name, cells)
        for cat_name, cells in sorted(categories.items()):
            self._add_pdk_category(lib_item, lib_name, cat_name, cells)

    def _add_pdk_category(self, parent, lib_name, cat_name, cells):
        cat_item = QTreeWidgetItem([cat_name])
        cat_item.setData(0, Qt.UserRole, ("category", lib_name, cat_name, None))
        font = cat_item.font(0)
        font.setItalic(True)
        cat_item.setFont(0, font)
        parent.addChild(cat_item)
        for cell_name, cell_data in sorted(cells):
            item = QTreeWidgetItem([cell_name])
            item.setData(0, Qt.UserRole, ("cell", lib_name, cat_name, cell_name, cell_data))
            item.setToolTip(0, cell_data.get("description", ""))
            cat_item.addChild(item)

    def _add_cell(self, parent, lib_name, cat_name, cell_name, cell_data):
        item = QTreeWidgetItem([cell_name])
        item.setData(0, Qt.UserRole, ("cell", lib_name, cat_name, cell_name, cell_data.get("views", [])))
        parent.addChild(item)

    def _on_selection_changed(self):
        item = self.tree.currentItem()
        data = item.data(0, Qt.UserRole) if item is not None else None
        if not data or data[0] != "cell":
            self.selected_library = ""
            self.selected_cell = ""
            self.selected_comp_type = ""
            self.selected_props = {}
            self.selected_cell_data = {}
            self.place_button.setEnabled(False)
            self.cell_label.setText("Cell: -")
            self.library_label.setText("Library: -")
            self.description_label.setText("")
            self.params_label.setText("")
            self._draw_empty_preview("No preview available")
            return
        _kind, lib, _cat, cell, payload = data
        cell_data = payload if isinstance(payload, dict) else {}
        views = cell_data.get("views", payload if isinstance(payload, list) else [])
        self.selected_library = lib
        self.selected_cell = cell
        self.selected_cell_data = cell_data
        self.selected_comp_type = cell_data.get("symbol_type", cell)
        self.selected_props = dict(cell_data.get("default_params", {}))
        self.cell_label.setText(f"Cell: {cell}")
        self.library_label.setText(f"Library: {lib}")
        self.description_label.setText(cell_data.get("description", ""))
        params = cell_data.get("default_params", {})
        self.params_label.setText("Params: " + ", ".join(f"{k}={v}" for k, v in params.items()) if params else "")
        self.view_combo.clear()
        self.view_combo.addItems(views or ["schematic"])
        if self.view_combo.findText("schematic") >= 0:
            self.view_combo.setCurrentText("schematic")
        self.place_button.setEnabled(True)
        self._draw_symbol_preview(self.selected_comp_type)

    def _on_item_double_clicked(self, item, _column):
        data = item.data(0, Qt.UserRole)
        if data and data[0] == "cell":
            self._accept_selection()

    def _accept_selection(self):
        if not self.selected_cell:
            return
        self.selected_view = self.view_combo.currentText() or "schematic"
        self.accept()

    def _draw_symbol_preview(self, cell):
        if cell not in SYMBOLS:
            self._draw_empty_preview("No preview available")
            return
        scene = QGraphicsScene(self.preview)
        scene.setBackgroundBrush(QColor("#181825"))
        pen = QPen(QColor("#cdd6f4"), 2)
        scale = 24
        symbol = SYMBOLS[cell]
        for x1, y1, x2, y2 in symbol.get("lines", []):
            line = QGraphicsLineItem(x1 * scale, y1 * scale, x2 * scale, y2 * scale)
            line.setPen(pen)
            scene.addItem(line)
        for cx, cy, r, _sa, _sp in symbol.get("arcs", []):
            ellipse = QGraphicsEllipseItem((cx - r) * scale, (cy - r) * scale, r * 2 * scale, r * 2 * scale)
            ellipse.setPen(pen)
            scene.addItem(ellipse)
        for cx, cy, r in symbol.get("circles", []):
            circle = QGraphicsEllipseItem((cx - r) * scale, (cy - r) * scale, r * 2 * scale, r * 2 * scale)
            circle.setPen(pen)
            scene.addItem(circle)
        rect = scene.itemsBoundingRect()
        scene.setSceneRect(rect.adjusted(-30, -30, 30, 30) if rect.isValid() else QRectF(-80, -60, 160, 120))
        self.preview.setScene(scene)
        self.preview.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)

    def _draw_empty_preview(self, text):
        scene = QGraphicsScene(self.preview)
        scene.setBackgroundBrush(QColor("#181825"))
        msg = QGraphicsTextItem(text)
        msg.setDefaultTextColor(QColor("#a6adc8"))
        msg.setPos(10, 10)
        scene.addItem(msg)
        scene.setSceneRect(0, 0, 260, 120)
        self.preview.setScene(scene)
