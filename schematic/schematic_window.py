import json
import py_compile

from PyQt5.QtWidgets import QMainWindow, QToolBar, QAction, QStatusBar, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt


class SchematicWindow(QMainWindow):
    def __init__(self, cellname="untitled", lib_data=None, parent=None):
        super().__init__(parent)
        self.cellname = cellname
        self.lib_data = lib_data or {}
        self.setWindowTitle(f"Schematic Editor — {cellname}")
        self.resize(900, 700)
        from schematic.schematic_canvas import SchematicCanvas
        self.canvas = SchematicCanvas(self)
        self._canvas = self.canvas
        self.setCentralWidget(self.canvas)
        self._current_lib = ""
        self._current_cell = ""
        self._last_sim_stdout = ""
        self._last_waveform_viewer = None
        self._ade_window = None
        self._ai_agent_window = None
        self._build_toolbar()
        self._build_menus()
        self.setStatusBar(QStatusBar(self))

    def _build_toolbar(self):
        tb = QToolBar("Tools", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        self._add_tool_action(tb, "Arrow", "Select (Esc)", lambda: self.canvas.start_mode("select"))
        self._add_tool_action(tb, "Wire W", "Wire (W)", lambda: self.canvas.start_mode("wire"))
        self._add_tool_action(tb, "Label L", "Net Label (L)", lambda: self.canvas.start_mode("netlabel"))
        self._add_tool_action(tb, "Port P", "Port (P)", lambda: self.canvas.start_mode("port"))
        self._add_tool_action(tb, "Block B", "Block (B)", lambda: self.canvas.start_mode("block"))
        tb.addSeparator()

        self._add_tool_action(tb, "Add Instance (I)", "Add Instance (I)", self.canvas._add_instance_dialog)
        self._add_tool_action(tb, "VDD", "Place VDD", lambda: self.canvas.add_instance("vdd", "VDD"))
        self._add_tool_action(tb, "GND", "Place GND", lambda: self.canvas.add_instance("gnd", "GND"))
        tb.addSeparator()

        self._add_tool_action(tb, "Copy C", "Copy (C)", self.canvas.copy_selected)
        self._add_tool_action(tb, "Move M", "Move (M)", lambda: self.statusBar().showMessage("Move: drag selected objects", 2000))
        self._add_tool_action(tb, "Rotate R", "Rotate (R)", self.canvas.rotate_selected)
        self._add_tool_action(tb, "Mirror", "Mirror (Shift+M)", self.canvas.mirror_selected)
        self._add_tool_action(tb, "Delete", "Delete (Del)", self.canvas._delete_selected)
        tb.addSeparator()

        self._add_tool_action(tb, "Fit F", "Fit All (F)", self.canvas.fit_all)
        self._add_tool_action(tb, "Zoom In Z", "Zoom In (Z)", lambda: self.canvas.zoom_at_viewport_pos(self.canvas.viewport().rect().center(), 1.2))
        self._add_tool_action(tb, "Zoom Out", "Zoom Out (Shift+Z)", lambda: self.canvas.zoom_at_viewport_pos(self.canvas.viewport().rect().center(), 1 / 1.2))
        tb.addSeparator()

        self._add_tool_action(tb, "SpiceSim", "Launch SpiceSim (F5)", self._open_ade)

    def _add_tool_action(self, toolbar, text, tooltip, slot):
        act = QAction(text, self)
        act.setToolTip(tooltip)
        act.triggered.connect(slot)
        toolbar.addAction(act)
        return act

    def _build_menus(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("File")
        new_act = file_menu.addAction("New", self._new)
        new_act.setShortcut("Ctrl+N")
        open_act = file_menu.addAction("Open", self._load)
        open_act.setShortcut("Ctrl+O")
        import_spice_act = file_menu.addAction("Import SPICE (.cir/.sp)...", self._import_spice)
        import_spice_act.setShortcut("Ctrl+Shift+I")
        save_act = file_menu.addAction("Save", self._save)
        save_act.setShortcut("Ctrl+S")
        check_save = file_menu.addAction("Check && Save", self._check_and_save)
        check_save.setShortcut("Shift+X")
        file_menu.addAction("Close", self.close)

        edit_menu = mb.addMenu("Edit")
        undo_act = edit_menu.addAction("Undo", self.canvas._undo)
        undo_act.setShortcut("Ctrl+Z")
        redo_act = edit_menu.addAction("Redo", self.canvas._redo)
        redo_act.setShortcut("Ctrl+Y")
        edit_menu.addAction("Edit Properties", self.canvas._edit_selected_properties).setShortcut("Q")
        edit_menu.addAction("Delete", self.canvas._delete_selected).setShortcut("Del")

        view_menu = mb.addMenu("View")
        view_menu.addAction("Fit All", self.canvas.fit_all).setShortcut("F")
        view_menu.addAction("Zoom In", lambda: self.canvas.zoom_at_viewport_pos(self.canvas.viewport().rect().center(), 1.2)).setShortcut("Z")
        view_menu.addAction("Zoom Out", lambda: self.canvas.zoom_at_viewport_pos(self.canvas.viewport().rect().center(), 1 / 1.2)).setShortcut("Shift+Z")

        tools_menu = mb.addMenu("Tools")
        tools_menu.addAction("SPICE Export", self._export_spice)
        tools_menu.addAction("Run LVS", self._run_lvs)
        tools_menu.addAction("Descend", lambda: self.statusBar().showMessage("Not implemented", 3000)).setShortcut("E")
        ai_agent_act = tools_menu.addAction("AI Optimization Agent...", self._open_ai_agent)
        ai_agent_act.setShortcut("Ctrl+Shift+A")

        sim_menu = mb.addMenu("Simulation")
        ade_act = sim_menu.addAction("Launch SpiceSim...", self._open_ade)
        run_act = sim_menu.addAction("Run Simulation", self._open_ade)
        run_act.setShortcut("F5")
        sim_menu.addAction("Show Waveform Viewer", self._show_waveform_viewer)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if mods == (Qt.ControlModifier | Qt.ShiftModifier) and key == Qt.Key_A:
            self._open_ai_agent()
        elif key == Qt.Key_F5:
            self._open_ade()
        else:
            super().keyPressEvent(event)

    def _export_spice(self):
        from schematic.netlist_export import NetlistExporter
        netlist = NetlistExporter().export(self.canvas, self.cellname)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SPICE", f"{self.cellname}.sp", "SPICE (*.sp *.spi *.cir)"
        )
        if path:
            with open(path, "w") as f:
                f.write(netlist)

    def _import_spice(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import SPICE",
            "",
            "SPICE Files (*.cir *.sp *.spice);;All Files (*)",
        )
        if not path:
            return
        if not self.canvas.import_from_spice(path):
            return
        self.cellname = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        self.setWindowTitle(f"Schematic Editor — {self.cellname}")

    def save_to_library(self, lib_name: str, cell_name: str):
        """Save current schematic to library folder."""
        from lib_manager_fs import save_view

        data = self._canvas.to_dict()
        data["lib_name"] = lib_name
        data["cell_name"] = cell_name
        save_view(lib_name, cell_name, "schematic", data)
        self._current_lib = lib_name
        self._current_cell = cell_name
        self.cellname = cell_name
        self.setWindowTitle(f"Schematic — {lib_name}/{cell_name}")
        self.statusBar().showMessage(
            f"Saved to libraries/{lib_name}/{cell_name}/schematic/", 3000
        )

    def load_from_library(self, lib_name: str, cell_name: str):
        """Load schematic from library folder."""
        from lib_manager_fs import load_view

        self._current_lib = lib_name
        self._current_cell = cell_name
        self.cellname = cell_name
        data = load_view(lib_name, cell_name, "schematic")
        if data:
            self._canvas.load_dict(data)
            self.setWindowTitle(f"Schematic — {lib_name}/{cell_name}")
            self.statusBar().showMessage(
                f"Loaded libraries/{lib_name}/{cell_name}/schematic/", 3000
            )
        else:
            self.setWindowTitle(f"Schematic — {lib_name}/{cell_name}")
            QMessageBox.information(
                self, "Open", f"No schematic found for {lib_name}/{cell_name}"
            )

    def _save(self):
        if self._current_lib and self._current_cell:
            self.save_to_library(self._current_lib, self._current_cell)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Schematic", f"{self.cellname}.sch.json", "Schematic (*.sch.json);;JSON (*.json)"
        )
        if not path:
            return
        if not path.endswith(".sch.json"):
            path += ".sch.json"
        with open(path, "w") as f:
            json.dump(self.canvas.to_dict(), f, indent=2)
        self.statusBar().showMessage(f"Saved schematic: {path}", 3000)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Schematic",
            "",
            "Schematic (*.sch.json);;JSON (*.json);;SPICE Files (*.cir *.sp *.spice);;All Files (*)",
        )
        if not path:
            return
        lower_path = path.lower()
        if lower_path.endswith((".cir", ".sp", ".spice")):
            if not self.canvas.import_from_spice(path):
                return
            self.cellname = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            self._current_lib = ""
            self._current_cell = ""
            self.setWindowTitle(f"Schematic Editor — {self.cellname}")
            return
        with open(path, "r") as f:
            data = json.load(f)
        self.canvas.load_dict(data)
        self.cellname = path.rsplit("/", 1)[-1].replace(".sch.json", "")
        self._current_lib = ""
        self._current_cell = ""
        self.setWindowTitle(f"Schematic Editor — {self.cellname}")
        self.statusBar().showMessage(f"Loaded schematic: {path}", 3000)

    def _new(self):
        self.canvas.clear_schematic()
        self._current_lib = ""
        self._current_cell = ""
        self.statusBar().showMessage("New schematic", 2000)

    def _check_and_save(self):
        try:
            py_compile.compile("schematic/schematic_canvas.py", doraise=True)
            py_compile.compile("schematic/schematic_window.py", doraise=True)
            py_compile.compile("schematic/ade_window.py", doraise=True)
        except py_compile.PyCompileError as exc:
            QMessageBox.critical(self, "Check & Save", str(exc))
            return
        self.statusBar().showMessage("Check passed", 3000)
        self._save()

    def _run_lvs(self):
        self.statusBar().showMessage("LVS: use Tools → Run LVS from main window", 3000)

    def _open_ade(self):
        from schematic.ade_window import ADEWindow
        if self._ade_window is None or not self._ade_window.isVisible():
            self._ade_window = ADEWindow(schematic_canvas=self._canvas)
            self._ade_window.show()
        else:
            self._ade_window.raise_()
            self._ade_window.activateWindow()

    def _open_ai_agent(self):
        if self._ai_agent_window is None:
            from ai_agent.agent_window import AgentWindow

            self._ai_agent_window = AgentWindow(parent=self)
            self._ai_agent_window.set_schematic_canvas(self._canvas)
            self._ai_agent_window.apply_params_requested.connect(self._apply_agent_params)
        self._ai_agent_window.show()
        self._ai_agent_window.raise_()
        self._ai_agent_window.activateWindow()

    def _apply_agent_params(self, changes):
        """Apply parameter changes suggested by AI agent to schematic components."""
        canvas = self._canvas
        applied = 0
        for item in canvas._scene.items():
            if hasattr(item, "comp_name") and item.comp_name in changes:
                new_params = changes[item.comp_name]
                for k, v in new_params.items():
                    item.props[k] = v
                if hasattr(item, "_update_label"):
                    item._update_label()
                elif hasattr(item, "update"):
                    item.update()
                applied += 1
        canvas._scene.update()
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(f"AI Agent: applied params to {applied} component(s)")

    def _show_waveform_viewer(self):
        if self._last_sim_stdout:
            from schematic.waveform_viewer import WaveformViewer
            self._last_waveform_viewer = WaveformViewer(self._last_sim_stdout)
            self._last_waveform_viewer.show()
        else:
            self.statusBar().showMessage("No simulation results available", 3000)
