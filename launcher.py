#!/usr/bin/env python3
"""EDA Suite launcher."""
import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QFileDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._library_manager = None
        self.open_library_manager()

    def open_library_manager(self):
        from library_manager import LibraryManagerWindow
        app = QApplication.instance()
        self._library_manager = LibraryManagerWindow()
        if app is not None:
            app._library_manager_window = self._library_manager
        self._library_manager.show()
        self.close()


class LegacyLauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IHP SG13G2 EDA Suite")
        self.setFixedSize(520, 340)
        self.setStyleSheet("background:#1e1e2e; color:#cdd6f4;")
        self._layout_win = None
        self._schem_win = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(20)

        title = QLabel("IHP SG13G2 EDA Suite")
        title.setFont(QFont("Monospace", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:#cba6f7;")
        root.addWidget(title)

        from pdk_manager import PDK
        self._pdk_label = QLabel(f"PDK: {PDK.name}")
        self._pdk_label.setAlignment(Qt.AlignCenter)
        self._pdk_label.setStyleSheet("color:#a6e3a1; font-size:11px;")
        root.addWidget(self._pdk_label)
        PDK.pdk_changed.connect(lambda name, _layers, _tech: self._pdk_label.setText(f"PDK: {name}"))

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#45475a;")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(24)

        self._btn_layout = QPushButton("Layout Editor")
        self._btn_layout.setMinimumHeight(80)
        self._btn_layout.setFont(QFont("Monospace", 13))
        self._btn_layout.setStyleSheet(
            "QPushButton{background:#313244;border:2px solid #89b4fa;"
            "border-radius:8px;color:#89b4fa;} QPushButton:hover{background:#45475a;}")
        self._btn_layout.clicked.connect(self.open_layout)
        btn_row.addWidget(self._btn_layout)

        self._btn_schem = QPushButton("Schematic Editor")
        self._btn_schem.setMinimumHeight(80)
        self._btn_schem.setFont(QFont("Monospace", 13))
        self._btn_schem.setStyleSheet(
            "QPushButton{background:#313244;border:2px solid #a6e3a1;"
            "border-radius:8px;color:#a6e3a1;} QPushButton:hover{background:#45475a;}")
        self._btn_schem.clicked.connect(self.open_schematic)
        btn_row.addWidget(self._btn_schem)
        root.addLayout(btn_row)

        pdk_btn = QPushButton("Load PDK...")
        pdk_btn.setStyleSheet(
            "QPushButton{background:#313244;border:1px solid #6c7086;"
            "border-radius:4px;color:#9399b2;padding:4px;} QPushButton:hover{background:#45475a;}")
        pdk_btn.clicked.connect(self.load_pdk)
        root.addWidget(pdk_btn)

    def open_layout(self):
        if self._layout_win is None or not self._layout_win.isVisible():
            from main import MainWindow
            self._layout_win = MainWindow()
            self._layout_win.show()
        else:
            self._layout_win.raise_()
            self._layout_win.activateWindow()

    def open_schematic(self):
        if self._schem_win is None or not self._schem_win.isVisible():
            from schematic.schematic_window import SchematicWindow
            self._schem_win = SchematicWindow()
            self._schem_win.show()
        else:
            self._schem_win.raise_()
            self._schem_win.activateWindow()

    def load_pdk(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load PDK", "", "PDK JSON (*.json)")
        if path:
            from pdk_manager import PDK
            name, _ = PDK.load(path)
            self._pdk_label.setText(f"PDK: {name}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        from pdk_manager import load_ihp_pdk
        tech = load_ihp_pdk()
        if tech:
            print(f"[PDK] Loaded IHP SG13G2 from {tech.pdk_root}")
    except Exception as exc:
        print(f"[PDK] Auto-load skipped: {exc}")
    from library_manager import LibraryManagerWindow
    win = LibraryManagerWindow()
    win.show()
    sys.exit(app.exec_())
