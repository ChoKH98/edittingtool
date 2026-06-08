import json

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QToolBar, QVBoxLayout, QWidget, QDialogButtonBox
)

from schematic.netlist_export import export_netlist
from schematic.simulation_panel import SimWorker
from schematic.waveform_viewer import WaveformViewer


class ADEWindow(QMainWindow):
    sim_done = pyqtSignal(str, int, str)

    def __init__(self, schematic_canvas=None):
        super().__init__()
        self._canvas = schematic_canvas
        self._thread = None
        self._worker = None
        self._viewer = None
        self.setWindowTitle("SpiceSim — Circuit Simulator")
        self.resize(900, 700)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1e1e2e; color: #cdd6f4; }
            QTableWidget, QTextEdit, QLineEdit, QComboBox {
                background: #181825; color: #cdd6f4; border: 1px solid #313244;
            }
            QHeaderView::section { background: #313244; color: #cdd6f4; border: 0; }
            QPushButton { background: #313244; color: #cdd6f4; padding: 5px 10px; }
        """)
        self._build_menus()
        self._build_toolbar()
        self._build_ui()
        self.sim_done.connect(self._on_sim_done)

    def _build_menus(self):
        mb = self.menuBar()
        session = mb.addMenu("Session")
        session.addAction("Save State", self._save_state_dialog)
        session.addAction("Load State", self._load_state_dialog)
        session.addAction("Exit", self.close)

        setup = mb.addMenu("Setup")
        setup.addAction("Model Libraries", lambda: self._log("Model Libraries setup is not implemented."))
        corner_menu = setup.addMenu("Corner")
        for corner in ("tt", "ff", "ss", "hv_tt"):
            corner_menu.addAction(corner, lambda _checked=False, c=corner: self.corner_combo.setCurrentText(c))
        setup.addAction("Simulator Options", lambda: self._log("Simulator Options setup is not implemented."))

        analyses = mb.addMenu("Analyses")
        analyses.addAction("Choose...", self._edit_current_analysis)

        simulation = mb.addMenu("Simulation")
        net_run = simulation.addAction("Netlist and Run", self._run_simulation)
        net_run.setShortcut("F5")
        run = simulation.addAction("Run", self._run_simulation)
        run.setShortcut("Ctrl+R")
        simulation.addAction("Stop", self._stop_simulation)
        simulation.addAction("Netlist Only", self._netlist_only)

        results = mb.addMenu("Results")
        results.addAction("Print...", lambda: self._log("Print results is not implemented."))
        results.addAction("Plot Outputs", lambda: self._log("Plot Outputs uses the waveform viewer after a run."))
        results.addAction("Calculator", lambda: self._log("Calculator is not implemented."))

        help_menu = mb.addMenu("Help")
        help_menu.addAction("About SpiceSim", lambda: QMessageBox.information(
            self, "About SpiceSim", "SpiceSim is a SPICE simulation frontend for ngspice"
        ))

    def _build_toolbar(self):
        tb = QToolBar("SpiceSim", self)
        tb.setMovable(False)
        self.addToolBar(tb)
        choose = QAction("Choose Analyses...", self)
        choose.triggered.connect(self._edit_current_analysis)
        tb.addAction(choose)
        tb.addAction("Choose Outputs...", lambda: self.tabs.setCurrentWidget(self.outputs_page))
        run = QAction("Run", self)
        run.setShortcut("F5")
        run.triggered.connect(self._run_simulation)
        tb.addAction(run)
        stop = QAction("Stop", self)
        stop.triggered.connect(self._stop_simulation)
        tb.addAction(stop)
        tb.addSeparator()
        tb.addWidget(QLabel("Corner: "))
        self.corner_combo = QComboBox(self)
        self.corner_combo.addItems(["tt", "ff", "ss", "hv_tt"])
        tb.addWidget(self.corner_combo)
        tb.addSeparator()
        tb.addAction("Design Variables", lambda: self.tabs.setCurrentWidget(self.vars_page))
        tb.addWidget(QLabel("  Simulator: ngspice  "))
        self.status_label = QLabel("Status: idle")
        tb.addWidget(self.status_label)

    def _build_ui(self):
        splitter = QSplitter(Qt.Vertical, self)
        self.setCentralWidget(splitter)

        self.analysis_table = QTableWidget(0, 4)
        self.analysis_table.setHorizontalHeaderLabels(["Enabled", "Analysis", "Arguments", "Status"])
        self.analysis_table.doubleClicked.connect(self._edit_current_analysis)
        splitter.addWidget(self.analysis_table)
        for analysis, args, enabled in (
            ("Tran", "10p 10n 0", True),
            ("DC", "V1 0 1.8 0.01", False),
            ("AC", "DEC 10 1k 10G", False),
            ("PSS", "1G 20", False),
            ("Pnoise", "V1 1k 10G 100", False),
        ):
            self._add_analysis_row(analysis, args, enabled)

        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)

        self.outputs_page = QWidget()
        outputs_layout = QVBoxLayout(self.outputs_page)
        self.outputs_table = QTableWidget(0, 4)
        self.outputs_table.setHorizontalHeaderLabels(["Type", "Name", "Value/Expression", "Save"])
        outputs_layout.addWidget(self.outputs_table)
        add_out = QPushButton("Add Row")
        add_out.clicked.connect(lambda: self._add_output_row("voltage", "out", "v(out)", True))
        outputs_layout.addWidget(add_out)
        self._add_output_row("voltage", "out", "v(out)", True)
        self.tabs.addTab(self.outputs_page, "Outputs")

        self.vars_page = QWidget()
        vars_layout = QVBoxLayout(self.vars_page)
        self.vars_table = QTableWidget(0, 2)
        self.vars_table.setHorizontalHeaderLabels(["Name", "Value"])
        vars_layout.addWidget(self.vars_table)
        var_buttons = QHBoxLayout()
        add_var = QPushButton("Add")
        remove_var = QPushButton("Remove")
        add_var.clicked.connect(lambda: self._add_var_row("freq", "1G"))
        remove_var.clicked.connect(self._remove_selected_var)
        var_buttons.addWidget(add_var)
        var_buttons.addWidget(remove_var)
        vars_layout.addLayout(var_buttons)
        self._add_var_row("freq", "1G")
        self._add_var_row("vdd", "1.8")
        self.tabs.addTab(self.vars_page, "Design Variables")

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.tabs.addTab(self.log_edit, "Log")
        splitter.setSizes([320, 360])

    def _add_analysis_row(self, analysis, args, enabled):
        row = self.analysis_table.rowCount()
        self.analysis_table.insertRow(row)
        chk = QCheckBox()
        chk.setChecked(enabled)
        self.analysis_table.setCellWidget(row, 0, chk)
        self.analysis_table.setItem(row, 1, QTableWidgetItem(analysis))
        self.analysis_table.setItem(row, 2, QTableWidgetItem(args))
        self.analysis_table.setItem(row, 3, QTableWidgetItem("idle"))

    def _add_output_row(self, typ="voltage", name="", expr="", save=True):
        row = self.outputs_table.rowCount()
        self.outputs_table.insertRow(row)
        for col, value in enumerate((typ, name, expr)):
            self.outputs_table.setItem(row, col, QTableWidgetItem(value))
        chk = QCheckBox()
        chk.setChecked(save)
        self.outputs_table.setCellWidget(row, 3, chk)

    def _add_var_row(self, name="", value=""):
        row = self.vars_table.rowCount()
        self.vars_table.insertRow(row)
        self.vars_table.setItem(row, 0, QTableWidgetItem(name))
        self.vars_table.setItem(row, 1, QTableWidgetItem(value))

    def _remove_selected_var(self):
        rows = sorted({idx.row() for idx in self.vars_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.vars_table.removeRow(row)

    def _edit_current_analysis(self):
        row = self.analysis_table.currentRow()
        if row < 0:
            row = 0
            self.analysis_table.selectRow(row)
        analysis = self._table_text(self.analysis_table, row, 1)
        args = self._table_text(self.analysis_table, row, 2)
        new_args = self._edit_analysis_dialog(analysis, args)
        if new_args:
            self.analysis_table.setItem(row, 2, QTableWidgetItem(new_args))

    def _edit_analysis_dialog(self, analysis, args=""):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Analysis: {analysis}")
        layout = QFormLayout(dlg)
        fields = []
        parts = args.split()

        def add_field(label, default):
            field = QLineEdit(default)
            layout.addRow(label + ":", field)
            fields.append(field)

        if analysis == "Tran":
            labels = ["Stop Time", "Step", "Start"]
            defaults = ["10n", "10p", "0"]
            order = [1, 0, 2]
        elif analysis == "DC":
            labels = ["Source", "Start", "Stop", "Step"]
            defaults = ["V1", "0", "1.8", "0.01"]
            order = [0, 1, 2, 3]
        elif analysis == "AC":
            labels = ["Type (DEC/OCT/LIN)", "Points", "Fstart", "Fstop"]
            defaults = ["DEC", "10", "1k", "10G"]
            order = [0, 1, 2, 3]
        elif analysis == "PSS":
            labels = ["Fundamental Freq", "Periods"]
            defaults = ["1G", "20"]
            order = [0, 1]
        else:
            labels = ["Reference", "Fstart", "Fstop", "Points"]
            defaults = ["V1", "1k", "10G", "100"]
            order = [0, 1, 2, 3]

        for idx, label in enumerate(labels):
            source_idx = order[idx] if idx < len(order) else idx
            add_field(label, parts[source_idx] if source_idx < len(parts) else defaults[idx])

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addRow(btns)
        if dlg.exec_() != QDialog.Accepted:
            return ""
        values = [field.text().strip() for field in fields]
        if analysis == "Tran":
            return f"{values[1]} {values[0]} {values[2]}"
        return " ".join(values)

    def _run_simulation(self):
        netlist_file = self._write_netlist()
        if not netlist_file:
            return
        self.status_label.setText("Status: running")
        self._log(f"Running ngspice: {netlist_file}")
        self._thread = QThread(self)
        self._worker = SimWorker(netlist_file, "/tmp/ade_sim.raw")
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self.sim_done)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker_refs)
        self._thread.start()

    def _write_netlist(self):
        if self._canvas is None:
            QMessageBox.warning(self, "SpiceSim", "No schematic canvas is available.")
            return ""
        analyses = self._enabled_analyses()
        if not analyses:
            QMessageBox.warning(self, "SpiceSim", "Enable at least one analysis.")
            return ""
        netlist = export_netlist(self._canvas, "top_circuit", corner=self.corner_combo.currentText())
        lines = [netlist]
        lines.extend(self._param_lines())
        lines.extend(self._analysis_lines(analyses))
        lines.extend(self._output_lines(analyses))
        lines.append(".control")
        lines.append("run")
        lines.append("write /tmp/ade_sim.raw")
        lines.append(".endc")
        lines.append(".end")
        path = "/tmp/ade_sim.sp"
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def _netlist_only(self):
        path = self._write_netlist()
        if path:
            self._log(f"Wrote netlist: {path}")

    def _enabled_analyses(self):
        rows = []
        for row in range(self.analysis_table.rowCount()):
            chk = self.analysis_table.cellWidget(row, 0)
            if chk and chk.isChecked():
                rows.append((self._table_text(self.analysis_table, row, 1),
                             self._table_text(self.analysis_table, row, 2)))
        return rows

    def _analysis_lines(self, analyses):
        lines = []
        for name, args in analyses:
            lower = name.lower()
            if name == "Pnoise":
                parts = args.split()
                if len(parts) >= 4:
                    lines.append(f".noise V(out) {parts[0]} DEC {parts[3]} {parts[1]} {parts[2]}")
            elif name == "PSS":
                lines.append(f"* .pss {args} stabilize")
            else:
                lines.append(f".{lower} {args}")
        return lines

    def _param_lines(self):
        lines = []
        for row in range(self.vars_table.rowCount()):
            name = self._table_text(self.vars_table, row, 0)
            value = self._table_text(self.vars_table, row, 1)
            if name and value:
                lines.append(f".param {name}={value}")
        return lines

    def _output_lines(self, analyses):
        if not analyses:
            return []
        first = analyses[0][0].lower()
        outputs = []
        for row in range(self.outputs_table.rowCount()):
            chk = self.outputs_table.cellWidget(row, 3)
            if chk and not chk.isChecked():
                continue
            expr = self._table_text(self.outputs_table, row, 2)
            if expr:
                outputs.append(expr)
        if not outputs:
            outputs = ["v(out)"]
        return [f".print {first} " + " ".join(outputs), ".probe " + " ".join(outputs)]

    def _stop_simulation(self):
        if self._worker is not None:
            self._worker.stop()
            self.status_label.setText("Status: stopping")

    def _on_sim_done(self, _rawfile, returncode, stdout):
        self._show_results(stdout, returncode)

    def _show_results(self, stdout, returncode):
        self._log(stdout)
        if returncode == 0:
            self.status_label.setText("Status: done")
            self._viewer = WaveformViewer(stdout)
            self._viewer.show()
        else:
            self.status_label.setText("Status: error")
            self.tabs.setCurrentWidget(self.log_edit)

    def _clear_worker_refs(self):
        self._thread = None
        self._worker = None

    def _save_state_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save SpiceSim State", "spicesim_state.json", "JSON (*.json)")
        if path:
            self._save_state(path)

    def _load_state_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load SpiceSim State", "", "JSON (*.json)")
        if path:
            self._load_state(path)

    def _save_state(self, path):
        data = {
            "analyses": [
                {
                    "enabled": bool(self.analysis_table.cellWidget(row, 0).isChecked()),
                    "analysis": self._table_text(self.analysis_table, row, 1),
                    "arguments": self._table_text(self.analysis_table, row, 2),
                    "status": self._table_text(self.analysis_table, row, 3),
                }
                for row in range(self.analysis_table.rowCount())
            ],
            "outputs": [
                {
                    "type": self._table_text(self.outputs_table, row, 0),
                    "name": self._table_text(self.outputs_table, row, 1),
                    "expression": self._table_text(self.outputs_table, row, 2),
                    "save": bool(self.outputs_table.cellWidget(row, 3).isChecked()),
                }
                for row in range(self.outputs_table.rowCount())
            ],
            "variables": [
                {
                    "name": self._table_text(self.vars_table, row, 0),
                    "value": self._table_text(self.vars_table, row, 1),
                }
                for row in range(self.vars_table.rowCount())
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_state(self, path):
        with open(path, "r") as f:
            data = json.load(f)
        self.analysis_table.setRowCount(0)
        for row in data.get("analyses", []):
            self._add_analysis_row(row.get("analysis", "Tran"), row.get("arguments", ""), row.get("enabled", False))
        self.outputs_table.setRowCount(0)
        for row in data.get("outputs", []):
            self._add_output_row(row.get("type", ""), row.get("name", ""), row.get("expression", ""), row.get("save", True))
        self.vars_table.setRowCount(0)
        for row in data.get("variables", []):
            self._add_var_row(row.get("name", ""), row.get("value", ""))

    def _table_text(self, table, row, col):
        item = table.item(row, col)
        return item.text().strip() if item is not None else ""

    def _log(self, text):
        if text:
            self.log_edit.append(str(text))


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = ADEWindow()
    win.show()
    sys.exit(app.exec_())
