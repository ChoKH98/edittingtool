#!/usr/bin/env python3
"""Virtuoso-style library manager for the EDA suite."""
import json
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QSplitter,
    QStatusBar,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QLineEdit,
    QStyle,
    QVBoxLayout,
    QWidget,
)


DATA_PATH = os.path.expanduser("~/.eda_libraries.json")
VIEW_NAMES = ("schematic", "layout", "symbol")
ANALOG_LIB_NAME = "analogLib"
IHP_LIB_NAME = "IHP_SG13G2"
ANALOG_LIB_DATA = {
    "read_only": True,
    "cells": {
        "vdc": {"views": ["schematic"]},
        "vpulse": {"views": ["schematic"]},
        "vsin": {"views": ["schematic"]},
        "vpwl": {"views": ["schematic"]},
        "idc": {"views": ["schematic"]},
        "resistor": {"views": ["schematic"]},
        "capacitor": {"views": ["schematic"]},
        "inductor": {"views": ["schematic"]},
        "vdd": {"views": ["schematic"]},
        "vss": {"views": ["schematic"]},
        "gnd": {"views": ["schematic"]},
        "nmos": {"views": ["schematic", "layout"]},
        "pmos": {"views": ["schematic", "layout"]},
    },
    "categories": {},
}


class NewCellDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Cell")
        self.name = ""
        self.checks = {}

        layout = QFormLayout(self)
        name_widget = QWidget(self)
        name_layout = QVBoxLayout(name_widget)
        name_layout.setContentsMargins(0, 0, 0, 0)

        self._line_edit = QLineEdit(self)
        name_layout.addWidget(self._line_edit)
        layout.addRow("Cell name:", name_widget)

        for view in VIEW_NAMES:
            check = QCheckBox(view, self)
            check.setChecked(view == "schematic")
            self.checks[view] = check
            layout.addRow("", check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def selected_views(self):
        return [view for view, check in self.checks.items() if check.isChecked()]

    def cell_name(self):
        return self._line_edit.text().strip()


class LibraryManagerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Library Manager")
        self.resize(800, 600)
        self._data_path = DATA_PATH
        self._data = {"libraries": {}}
        self._open_windows = []

        self._load_data()
        self._build_ui()
        self._autoload_pdk()
        self._ihp_lib = None
        self._try_load_ihp_library()
        self._populate_tree()
        self._show_library_status()

    def _build_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1e1e2e; color: #cdd6f4; }
            QTreeWidget, QListWidget {
                background: #181825; color: #cdd6f4; border: 1px solid #45475a;
                selection-background-color: #313244;
            }
            QToolBar { background: #181825; border-bottom: 1px solid #45475a; spacing: 4px; }
            QToolButton, QPushButton {
                background: #313244; color: #cdd6f4; border: 1px solid #6c7086;
                border-radius: 4px; padding: 4px 8px;
            }
            QToolButton:hover, QPushButton:hover { background: #45475a; border-color: #89b4fa; }
            QMenuBar, QMenu { background: #181825; color: #cdd6f4; }
            QMenu::item:selected { background: #313244; }
            QStatusBar { background: #181825; color: #a6adc8; }
        """)

        self._build_menus()
        self._build_toolbar()

        splitter = QSplitter(Qt.Horizontal, self)
        self.tree = QTreeWidget(splitter)
        self._tree = self.tree
        self.tree.setHeaderLabel("Libraries")
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setMinimumWidth(300)

        details = QWidget(splitter)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(10, 10, 10, 10)
        self.cell_name_label = QLabel("Select a cell", details)
        self.cell_name_label.setStyleSheet("font-weight: bold; color: #cdd6f4;")
        self.cell_library_label = QLabel("", details)
        self.views = QListWidget(details)
        self.views.itemDoubleClicked.connect(lambda item: self._open_selected_cell(item.text()))
        buttons = QHBoxLayout()
        self.open_button = QPushButton("Open", details)
        self.open_button.clicked.connect(self._open_selected_cell)
        self.add_instance_button = QPushButton("Add to Schematic", details)
        self.add_instance_button.clicked.connect(self._add_selected_to_schematic)
        self.open_button.setEnabled(False)
        self.add_instance_button.setEnabled(False)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.add_instance_button)
        details_layout.addWidget(self.cell_name_label)
        details_layout.addWidget(self.cell_library_label)
        details_layout.addWidget(QLabel("Available views:", details))
        details_layout.addWidget(self.views, 1)
        details_layout.addLayout(buttons)

        splitter.addWidget(self.tree)
        splitter.addWidget(details)
        splitter.setSizes([300, 500])
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar(self))
        self._pdk_status_label = QLabel(self)
        self.statusBar().addPermanentWidget(self._pdk_status_label)
        try:
            from pdk_manager import PDK
            PDK.pdk_changed.connect(lambda _name, _layers, _tech: self._update_pdk_status())
        except Exception:
            pass
        self._update_pdk_status()

    def _build_toolbar(self):
        tb = QToolBar("Library", self)
        self.addToolBar(tb)
        for text, slot in (
            ("New Library", self._new_library),
            ("New Category", self._new_category_for_selection),
            ("New Cell", self._new_cell_for_selection),
            ("Open", self._open_selected_cell),
            ("Delete", self._delete_selected),
        ):
            action = QAction(text, self)
            action.triggered.connect(slot)
            tb.addAction(action)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("New Library", self._new_library)
        file_menu.addAction("Open Library File...", self._open_library_file)
        file_menu.addAction("Save", self._save_data)
        file_menu.addAction("Exit", self.close)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction("Open Layout Editor", self._open_layout_editor)
        tools_menu.addAction("Open Schematic Editor", self._open_schematic_editor)

        pdk_menu = self.menuBar().addMenu("PDK")
        pdk_menu.addAction("Load PDK...", self._load_pdk_dialog)

    def _load_data(self):
        if not os.path.exists(self._data_path):
            self._data = {"libraries": {}}
            return
        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._data = data if isinstance(data, dict) else {"libraries": {}}
            self._data.setdefault("libraries", {})
        except (OSError, json.JSONDecodeError):
            self._data = {"libraries": {}}

    def _save_data(self):
        self._data.get("libraries", {}).pop(ANALOG_LIB_NAME, None)
        self._data.get("libraries", {}).pop(IHP_LIB_NAME, None)
        with open(self._data_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        self.statusBar().showMessage("Saved library data", 3000)

    def _populate_tree(self):
        self.tree.clear()
        self._add_library_item(ANALOG_LIB_NAME, ANALOG_LIB_DATA, built_in=True)
        if self._ihp_lib is not None:
            self._add_pdk_library_item(self._ihp_lib)
        for lib_name, lib_data in sorted(self._data.get("libraries", {}).items()):
            if lib_name in (ANALOG_LIB_NAME, IHP_LIB_NAME):
                continue
            self._add_library_item(lib_name, lib_data)
        self.tree.expandAll()

    def _add_pdk_library_item(self, lib_data):
        lib_name = lib_data.get("name", IHP_LIB_NAME)
        lib_item = QTreeWidgetItem([f"{lib_name} (PDK)"])
        lib_item.setData(0, Qt.UserRole, ("library", lib_name, None, None, lib_data))
        lib_item.setToolTip(0, "read-only PDK library")
        lib_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirHomeIcon))
        font = lib_item.font(0)
        font.setBold(True)
        lib_item.setFont(0, font)
        lib_item.setForeground(0, QColor(lib_data.get("color", "#a6e3a1")))
        self.tree.addTopLevelItem(lib_item)

        categories = {}
        for cell_name, cell_data in lib_data.get("cells", {}).items():
            categories.setdefault(cell_data.get("category", "Other"), []).append((cell_name, cell_data))
        for cat_name in ("MOS", "Passive", "BJT"):
            cells = categories.pop(cat_name, [])
            if cells:
                self._add_pdk_category_item(lib_item, lib_name, cat_name, cells)
        for cat_name, cells in sorted(categories.items()):
            self._add_pdk_category_item(lib_item, lib_name, cat_name, cells)

    def _add_pdk_category_item(self, parent, lib_name, cat_name, cells):
        cat_item = QTreeWidgetItem([cat_name])
        cat_item.setData(0, Qt.UserRole, ("category", lib_name, cat_name, None))
        cat_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
        font = cat_item.font(0)
        font.setItalic(True)
        cat_item.setFont(0, font)
        cat_item.setForeground(0, QColor("#f9e2af"))
        parent.addChild(cat_item)
        for cell_name, cell_data in sorted(cells):
            cell_item = QTreeWidgetItem([cell_name])
            cell_item.setData(0, Qt.UserRole, ("cell", lib_name, cat_name, cell_name, cell_data))
            cell_item.setToolTip(0, cell_data.get("description", ""))
            cell_item.setIcon(0, self.style().standardIcon(QStyle.SP_FileIcon))
            cat_item.addChild(cell_item)
            for view in cell_data.get("views", []):
                view_item = QTreeWidgetItem([view])
                view_item.setData(0, Qt.UserRole, ("view", lib_name, cat_name, cell_name, view, cell_data))
                view_item.setForeground(0, QColor("#a6e3a1"))
                cell_item.addChild(view_item)

    def _add_library_item(self, lib_name, lib_data, built_in=False):
        title = f"{lib_name} (built-in)" if built_in else lib_name
        lib_item = QTreeWidgetItem([title])
        lib_item.setData(0, Qt.UserRole, ("library", lib_name, None, None))
        lib_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirHomeIcon))
        font = lib_item.font(0)
        font.setBold(True)
        lib_item.setFont(0, font)
        lib_item.setForeground(0, QColor("#fab387" if built_in else "#89b4fa"))
        self.tree.addTopLevelItem(lib_item)

        for cell_name, cell_data in sorted(lib_data.get("cells", {}).items()):
            self._add_cell_item(lib_item, lib_name, None, cell_name, cell_data, built_in)

        for cat_name, cat_data in sorted(lib_data.get("categories", {}).items()):
            cat_item = QTreeWidgetItem([cat_name])
            cat_item.setData(0, Qt.UserRole, ("category", lib_name, cat_name, None))
            cat_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
            cat_font = cat_item.font(0)
            cat_font.setItalic(True)
            cat_item.setFont(0, cat_font)
            cat_item.setForeground(0, QColor("#f9e2af"))
            lib_item.addChild(cat_item)
            for cell_name, cell_data in sorted(cat_data.get("cells", {}).items()):
                self._add_cell_item(cat_item, lib_name, cat_name, cell_name, cell_data, built_in)

    def _add_cell_item(self, parent, lib_name, cat_name, cell_name, cell_data, built_in=False):
        label = f"[{cell_name}] {cell_name}" if built_in else cell_name
        cell_item = QTreeWidgetItem([label])
        cell_item.setData(0, Qt.UserRole, ("cell", lib_name, cat_name, cell_name))
        cell_item.setIcon(0, self.style().standardIcon(QStyle.SP_FileIcon))
        parent.addChild(cell_item)
        for view in cell_data.get("views", []):
            view_item = QTreeWidgetItem([view])
            view_item.setData(0, Qt.UserRole, ("view", lib_name, cat_name, cell_name, view))
            view_item.setForeground(0, QColor("#a6e3a1"))
            cell_item.addChild(view_item)

    def _new_library(self):
        name, ok = QInputDialog.getText(self, "New Library", "Library name:")
        name = name.strip()
        if not ok or not name:
            return
        libraries = self._data.setdefault("libraries", {})
        if name in libraries:
            QMessageBox.warning(self, "Library Exists", f"Library '{name}' already exists.")
            return
        libraries[name] = {"cells": {}, "categories": {}}
        self._save_data()
        self._populate_tree()

    def _new_category(self, lib_name):
        if self._is_read_only(lib_name):
            self._read_only_message()
            return
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        name = name.strip()
        if not ok or not name:
            return
        categories = self._data["libraries"][lib_name].setdefault("categories", {})
        if name in categories:
            QMessageBox.warning(self, "Category Exists", f"Category '{name}' already exists.")
            return
        categories[name] = {"cells": {}}
        self._save_data()
        self._populate_tree()

    def _new_cell(self, lib_name, cat_name):
        if self._is_read_only(lib_name):
            self._read_only_message()
            return
        dlg = NewCellDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        name = dlg.cell_name()
        views = dlg.selected_views()
        if not name or not views:
            return
        lib_data = self._data["libraries"][lib_name]
        if cat_name:
            cells = lib_data.setdefault("categories", {}).setdefault(cat_name, {"cells": {}}).setdefault("cells", {})
        else:
            cells = lib_data.setdefault("cells", {})
        if name in cells:
            QMessageBox.warning(self, "Cell Exists", f"Cell '{name}' already exists.")
            return
        cells[name] = {"views": views}
        self._save_data()
        self._populate_tree()

    def _delete_node(self, lib=None, cat=None, cell=None):
        if self._is_read_only(lib):
            self._read_only_message()
            return
        libraries = self._data.get("libraries", {})
        if lib and cat and cell:
            del libraries[lib]["categories"][cat]["cells"][cell]
            label = f"Deleted cell {cell}"
        elif lib and cell:
            del libraries[lib].setdefault("cells", {})[cell]
            label = f"Deleted cell {cell}"
        elif lib and cat:
            del libraries[lib]["categories"][cat]
            label = f"Deleted category {cat}"
        elif lib:
            del libraries[lib]
            label = f"Deleted library {lib}"
        else:
            return
        self._save_data()
        self._populate_tree()
        self.statusBar().showMessage(label, 3000)

    def _open_cell(self, lib, cat, cell, view):
        cell_data = self._get_cell_data(lib, cat, cell)
        if view == "schematic":
            from schematic.schematic_window import SchematicWindow
            win = SchematicWindow(cellname=cell, lib_data=cell_data)
        elif view == "layout":
            from main import MainWindow
            win = MainWindow()
        else:
            self.statusBar().showMessage(f"No editor registered for {view}", 3000)
            return
        self._open_windows.append(win)
        win.show()
        path = f"{lib}/{cat}/{cell}/{view}" if cat else f"{lib}/{cell}/{view}"
        self.statusBar().showMessage(f"Opened {path}", 3000)

    def _on_item_double_clicked(self, item, _column=0):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, lib, cat, cell, *rest = data
        if kind == "cell":
            cell_data = self._get_cell_data(lib, cat, cell)
            views = cell_data.get("views", [])
            if views:
                self._open_cell(lib, cat, cell, views[0])
        elif kind == "view":
            self._open_cell(lib, cat, cell, rest[0])

    def _show_context_menu(self, point):
        item = self.tree.itemAt(point)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, lib, cat, cell, *rest = data
        menu = QMenu(self)
        if lib == IHP_LIB_NAME and kind in ("library", "category", "cell"):
            action = menu.addAction("(read-only PDK library)")
            action.setEnabled(False)
            if kind == "cell":
                menu.addAction("Open Schematic", lambda: self._open_cell(lib, cat, cell, "schematic"))
                menu.addAction("Add to Schematic", self._add_selected_to_schematic)
            menu.exec_(self.tree.viewport().mapToGlobal(point))
            return
        if kind == "library":
            menu.addAction("New Cell", lambda: self._new_cell(lib, None)).setEnabled(not self._is_read_only(lib))
            menu.addAction("New Category", lambda: self._new_category(lib)).setEnabled(not self._is_read_only(lib))
            menu.addAction("Delete Library", lambda: self._delete_node(lib=lib)).setEnabled(not self._is_read_only(lib))
        elif kind == "category":
            menu.addAction("New Cell", lambda: self._new_cell(lib, cat)).setEnabled(not self._is_read_only(lib))
            menu.addAction("Delete Category", lambda: self._delete_node(lib=lib, cat=cat)).setEnabled(not self._is_read_only(lib))
        elif kind == "cell":
            menu.addAction("Open Schematic", lambda: self._open_cell(lib, cat, cell, "schematic"))
            menu.addAction("Open Layout", lambda: self._open_cell(lib, cat, cell, "layout"))
            menu.addAction("Add to Schematic", self._add_selected_to_schematic)
            menu.addAction("Delete Cell", lambda: self._delete_node(lib=lib, cat=cat, cell=cell)).setEnabled(not self._is_read_only(lib))
        menu.exec_(self.tree.viewport().mapToGlobal(point))

    def _on_selection_changed(self):
        self.views.clear()
        self.cell_name_label.setText("Select a cell")
        self.cell_library_label.setText("")
        self.open_button.setEnabled(False)
        self.add_instance_button.setEnabled(False)
        selected = self.tree.currentItem()
        if selected is None:
            return
        data = selected.data(0, Qt.UserRole)
        if not data:
            return
        kind, lib, cat, cell, *rest = data
        if kind == "view":
            cell = cell
        elif kind != "cell":
            return
        cell_data = self._get_cell_data(lib, cat, cell)
        self.cell_name_label.setText(cell)
        self.cell_library_label.setText(f"Library: {lib}")
        self.views.addItems(cell_data.get("views", []))
        self.open_button.setEnabled(bool(cell_data.get("views", [])))
        self.add_instance_button.setEnabled(True)

    def _new_category_for_selection(self):
        data = self._current_context()
        if data:
            lib, _cat, _cell = data
            self._new_category(lib)

    def _new_cell_for_selection(self):
        data = self._current_context()
        if data:
            lib, cat, _cell = data
            self._new_cell(lib, cat)

    def _delete_selected(self):
        data = self._current_item_data()
        if not data:
            return
        kind, lib, cat, cell, *rest = data
        if kind == "view":
            return
        self._delete_node(lib=lib, cat=cat, cell=cell)

    def _open_selected_cell(self, view=None):
        data = self._current_item_data()
        if not data:
            return
        kind, lib, cat, cell, *rest = data
        if kind == "view":
            self._open_cell(lib, cat, cell, rest[0])
        elif kind == "cell":
            selected_view = view if isinstance(view, str) else self._selected_view(cell, lib, cat)
            if selected_view:
                self._open_cell(lib, cat, cell, selected_view)

    def _selected_view(self, cell, lib, cat):
        item = self.views.currentItem()
        if item is not None:
            return item.text()
        views = self._get_cell_data(lib, cat, cell).get("views", [])
        return views[0] if views else ""

    def _get_lib_data(self, lib):
        if lib == ANALOG_LIB_NAME:
            return ANALOG_LIB_DATA
        if lib == IHP_LIB_NAME:
            return self._ihp_lib or {}
        return self._data.get("libraries", {}).get(lib, {})

    def _get_cell_data(self, lib, cat, cell):
        lib_data = self._get_lib_data(lib)
        if lib == IHP_LIB_NAME:
            return lib_data.get("cells", {}).get(cell, {})
        if cat:
            return lib_data.get("categories", {}).get(cat, {}).get("cells", {}).get(cell, {})
        return lib_data.get("cells", {}).get(cell, {})

    def _is_read_only(self, lib):
        return lib in (ANALOG_LIB_NAME, IHP_LIB_NAME)

    def _read_only_message(self):
        QMessageBox.information(self, "Read-only Library", "This library is built in or generated from the PDK and cannot be modified.")

    def _add_selected_to_schematic(self):
        data = self._current_item_data()
        if not data:
            return
        kind, lib, cat, cell, *rest = data
        if kind == "view":
            view = rest[0]
        elif kind == "cell":
            view = self._selected_view(cell, lib, cat) or "schematic"
        else:
            return
        for widget in QApplication.topLevelWidgets():
            if widget is self:
                continue
            canvas = getattr(widget, "canvas", None)
            if canvas is not None and callable(getattr(canvas, "enter_instance_mode", None)):
                widget.raise_()
                widget.activateWindow()
                cell_data = self._get_cell_data(lib, cat, cell)
                if lib == IHP_LIB_NAME:
                    canvas.enter_instance_mode(
                        cell_data.get("symbol_type", cell),
                        library=lib,
                        view=view,
                        props=dict(cell_data.get("default_params", {})),
                        cell_name_display=cell,
                    )
                else:
                    canvas.enter_instance_mode(cell, library=lib, view=view)
                self.statusBar().showMessage(f"Place instance: {lib}/{cell}", 3000)
                return
        self.statusBar().showMessage("No open SchematicWindow found", 3000)

    def _current_item_data(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def _current_context(self):
        data = self._current_item_data()
        if not data:
            return None
        kind, lib, cat, cell, *rest = data
        if kind == "library":
            return lib, None, None
        if kind == "category":
            return lib, cat, None
        if kind in ("cell", "view"):
            return lib, cat, cell
        return None

    def _open_library_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Library File", "", "JSON (*.json)")
        if not path:
            return
        self._data_path = path
        self._load_data()
        self._populate_tree()
        self.statusBar().showMessage(f"Opened library data: {path}", 3000)

    def _open_layout_editor(self):
        from main import MainWindow
        win = MainWindow()
        self._open_windows.append(win)
        win.show()

    def _open_schematic_editor(self):
        from schematic.schematic_window import SchematicWindow
        win = SchematicWindow()
        self._open_windows.append(win)
        win.show()

    def _autoload_pdk(self):
        try:
            from pdk_manager import PDK, load_ihp_pdk
            if PDK.tech is None:
                tech = load_ihp_pdk()
                if tech:
                    print(f"[PDK] Loaded IHP SG13G2 from {tech.pdk_root}")
        except Exception as exc:
            print(f"[PDK] Auto-load skipped: {exc}")
        self._update_pdk_status()

    def _try_load_ihp_library(self):
        try:
            from pdk_manager import PDK, load_ihp_pdk
            tech = PDK.tech
            if tech is None:
                tech = load_ihp_pdk()
            if tech is not None:
                self._ihp_lib = tech.get_pdk_library()
        except Exception as e:
            print(f"[LibraryManager] Could not load IHP PDK library: {e}")

    def _load_pdk_dialog(self):
        root = QFileDialog.getExistingDirectory(self, "Load PDK Root", "")
        if not root:
            return
        try:
            from pdk_manager import PDK
            tech_json = os.path.join(root, "libs.tech/klayout/python/sg13g2_pycell_lib/sg13g2_tech.json")
            PDK.load(tech_json if os.path.exists(tech_json) else root)
            self._try_load_ihp_library()
            self._populate_tree()
            self._update_pdk_status()
            self._show_library_status()
        except Exception as exc:
            QMessageBox.warning(self, "Load PDK", f"Could not load PDK: {exc}")

    def _update_pdk_status(self):
        label = getattr(self, "_pdk_status_label", None)
        if label is None:
            return
        try:
            from pdk_manager import PDK
            tech = PDK.tech
        except Exception:
            tech = None
        if tech is None:
            label.setText("● PDK: none")
            label.setStyleSheet("color: #f38ba8;")
            return
        params = tech.tech_params
        version = params.get("relName") or ".".join(str(params.get(key, "")) for key in ("majorVersion", "minorVersion", "bugfixVersion")).strip(".")
        label.setText(f"PDK: IHP SG13G2 v{version}".rstrip())
        label.setStyleSheet("color: #a6e3a1;")

    def _show_library_status(self):
        if self._ihp_lib:
            self.statusBar().showMessage(f"Library data: {self._data_path} | PDK: IHP SG13G2 v{self._ihp_lib.get('version', 'SG13G2')}")
        else:
            self.statusBar().showMessage(f"Library data: {self._data_path}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = LibraryManagerWindow()
    win.show()
    sys.exit(app.exec_())
