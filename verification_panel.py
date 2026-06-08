"""RF Verification Panel - DRC, LVS, PEX, Post-Layout Simulation."""
from pathlib import Path
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QFormLayout, QLineEdit, QPushButton, QTextEdit, QLabel, QFileDialog,
    QComboBox, QSizePolicy)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont

RFIC_ROOT = Path.home() / "rfic_project"
PDK_ROOT = Path.home() / "tools" / "IHP-Open-PDK" / "ihp-sg13g2"
KLAYOUT_DRC = PDK_ROOT / "libs.tech" / "klayout" / "tech" / "drc" / "ihp-sg13g2.drc"
KLAYOUT_LVS = PDK_ROOT / "libs.tech" / "klayout" / "tech" / "lvs" / "ihp-sg13g2.lvs"
NGSPICE_MODELS = PDK_ROOT / "libs.tech" / "ngspice" / "models"


class RunWorker(QObject):
    output = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, cmd, cwd=None):
        super().__init__()
        self.cmd = cmd
        self.cwd = str(cwd) if cwd else None

    def run(self):
        import subprocess
        try:
            proc = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.cwd)
            for line in proc.stdout:
                self.output.emit(line.rstrip())
            proc.wait()
            self.finished.emit(proc.returncode)
        except Exception as exc:
            self.output.emit(f"ERROR: {exc}")
            self.finished.emit(1)


class VerificationPanel(QWidget):
    gds_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget{background:#1a1a1a;}"
            "QTabBar::tab{background:#2a2a2a;color:#ccc;padding:6px 14px;}"
            "QTabBar::tab:selected{background:#005577;color:#fff;}")
        layout.addWidget(tabs)

        self._drc_gds, drc_tab = self._make_drc_tab()
        self._lvs_gds, self._lvs_sp, lvs_tab = self._make_lvs_tab()
        self._sim_sp, sim_tab = self._make_sim_tab()
        self._pex_src, self._pex_out, pex_tab = self._make_pex_tab()

        tabs.addTab(drc_tab, "DRC")
        tabs.addTab(lvs_tab, "LVS")
        tabs.addTab(pex_tab, "PEX")
        tabs.addTab(sim_tab, "Post-Sim")

        self.gds_changed.connect(self._drc_gds.setText)
        self.gds_changed.connect(self._lvs_gds.setText)

    def set_gds(self, path):
        self.gds_changed.emit(path)

    def _output_widget(self):
        w = QTextEdit()
        w.setReadOnly(True)
        w.setFont(QFont("Monospace", 9))
        w.setStyleSheet("background:#0d0d0d; color:#00ff88;")
        w.setMinimumHeight(120)
        return w

    def _browse(self, edit, title, filt):
        path, _ = QFileDialog.getOpenFileName(self, title, "", filt)
        if path:
            edit.setText(path)

    def _run(self, cmd, cwd, out_widget, status_lbl):
        out_widget.clear()
        status_lbl.setText("Running...")
        status_lbl.setStyleSheet("color:#FFD700;")
        worker = RunWorker(cmd, cwd)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.output.connect(lambda line: out_widget.append(line))
        def on_done(rc):
            if rc == 0:
                status_lbl.setText("PASS")
                status_lbl.setStyleSheet("color:#00ff88;")
            else:
                status_lbl.setText(f"FAIL (exit {rc})")
                status_lbl.setStyleSheet("color:#ff5555;")
            thread.quit()
        worker.finished.connect(on_done)
        thread.finished.connect(thread.deleteLater)
        self._threads.append((worker, thread))
        thread.start()

    def _field_row(self, form, label, default="", browse_title=None, browse_filt=""):
        edit = QLineEdit(str(default))
        if browse_title:
            row = QHBoxLayout()
            row.addWidget(edit)
            btn = QPushButton("...")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda: self._browse(edit, browse_title, browse_filt))
            row.addWidget(btn)
            container = QWidget()
            container.setLayout(row)
            form.addRow(label, container)
        else:
            form.addRow(label, edit)
        return edit

    def _make_drc_tab(self):
        tab = QWidget()
        vl = QVBoxLayout(tab)
        form = QFormLayout()
        gds_e = self._field_row(form, "GDS:", "", "GDS file", "GDS (*.gds *.gdsii)")
        cell_e = self._field_row(form, "Top cell:", "LC_DCO_NMOS")
        drc_e = self._field_row(form, "DRC script:", str(KLAYOUT_DRC),
                               "DRC script", "DRC (*.drc *.rb)")
        vl.addLayout(form)
        status = QLabel("Idle")
        status.setStyleSheet("color:#888;")
        out = self._output_widget()
        run_btn = QPushButton("Run DRC")
        run_btn.setStyleSheet("background:#005577;color:#fff;padding:6px;border-radius:4px;")

        def do_run():
            gds = gds_e.text().strip()
            cell = cell_e.text().strip()
            drc = drc_e.text().strip()
            if not gds:
                status.setText("Set GDS path first")
                return
            run_dir = RFIC_ROOT / "results" / "drc_run"
            run_dir.mkdir(parents=True, exist_ok=True)
            lyrdb = str(run_dir / "out.lyrdb")
            cmd = ["klayout", "-b", "-r", drc,
                   "-rd", f"input={gds}",
                   "-rd", f"topcell={cell}",
                   "-rd", f"report={lyrdb}",
                   "-rd", "run_mode=flat",
                   "-rd", "no_feol=true",
                   "-rd", "no_density=true"]
            self._run(cmd, None, out, status)

        run_btn.clicked.connect(do_run)
        vl.addWidget(run_btn)
        vl.addWidget(status)
        vl.addWidget(out)
        return gds_e, tab

    def _make_lvs_tab(self):
        tab = QWidget()
        vl = QVBoxLayout(tab)
        form = QFormLayout()
        gds_e = self._field_row(form, "GDS:", "", "GDS file", "GDS (*.gds)")
        sp_e = self._field_row(form, "Schematic SPICE:", "", "SPICE netlist", "SPICE (*.sp *.spi *.cir)")
        cell_e = self._field_row(form, "Top cell:", "LC_DCO_NMOS")
        lvs_e = self._field_row(form, "LVS script:", str(KLAYOUT_LVS), "LVS script", "LVS (*.lvs *.rb)")
        vl.addLayout(form)
        status = QLabel("Idle")
        status.setStyleSheet("color:#888;")
        out = self._output_widget()
        run_btn = QPushButton("Run LVS")
        run_btn.setStyleSheet("background:#005577;color:#fff;padding:6px;border-radius:4px;")

        def do_run():
            gds = gds_e.text().strip()
            sp = sp_e.text().strip()
            cell = cell_e.text().strip()
            lvs = lvs_e.text().strip()
            if not gds or not sp:
                status.setText("Set GDS and SPICE paths")
                return
            run_dir = RFIC_ROOT / "results" / "lvs_run"
            run_dir.mkdir(parents=True, exist_ok=True)
            lvsdb = str(run_dir / "out.lvsdb")
            cmd = ["klayout", "-b", "-r", lvs,
                   "-rd", f"input={gds}",
                   "-rd", f"schematic={sp}",
                   "-rd", f"topcell={cell}",
                   "-rd", f"report={lvsdb}"]
            self._run(cmd, None, out, status)

        run_btn.clicked.connect(do_run)
        vl.addWidget(run_btn)
        vl.addWidget(status)
        vl.addWidget(out)
        return gds_e, sp_e, tab

    def _make_pex_tab(self):
        tab = QWidget()
        vl = QVBoxLayout(tab)
        form = QFormLayout()
        src_e = self._field_row(form, "Source SPICE:",
            str(RFIC_ROOT / "circuits" / "lc_dco_nmos_top.cir"),
            "Source SPICE", "SPICE (*.sp *.spi *.cir)")
        out_e = self._field_row(form, "Output SPICE:",
            str(RFIC_ROOT / "results" / "lc_dco_nmos_extracted.spice"))
        vl.addLayout(form)
        status = QLabel("Idle")
        status.setStyleSheet("color:#888;")
        log = self._output_widget()
        run_btn = QPushButton("Run PEX")
        run_btn.setStyleSheet("background:#005577;color:#fff;padding:6px;border-radius:4px;")

        def do_run():
            script = Path("/home/whqkrel/rfic_project/scripts/run_pex.py")
            if not script.exists():
                status.setText("run_pex.py not found")
                return
            cmd = ["python3", str(script)]
            self._run(cmd, None, log, status)
            self._sim_sp.setText(out_e.text())

        run_btn.clicked.connect(do_run)
        vl.addWidget(run_btn)
        vl.addWidget(status)
        vl.addWidget(log)
        return src_e, out_e, tab

    def _make_sim_tab(self):
        tab = QWidget()
        vl = QVBoxLayout(tab)
        form = QFormLayout()
        sp_e = self._field_row(form, "Extracted SPICE:",
            str(RFIC_ROOT / "results" / "lc_dco_nmos_extracted.spice"),
            "SPICE", "SPICE (*.sp *.spi *.spice)")
        vl.addLayout(form)
        status = QLabel("Idle")
        status.setStyleSheet("color:#888;")
        log = self._output_widget()
        run_btn = QPushButton("Run Post-Layout Simulation")
        run_btn.setStyleSheet("background:#005577;color:#fff;padding:6px;border-radius:4px;")

        def do_run():
            script = Path("/home/whqkrel/rfic_project/scripts/post_layout_sim.py")
            if not script.exists():
                status.setText("post_layout_sim.py not found")
                return
            cmd = ["python3", str(script)]
            self._run(cmd, str(NGSPICE_MODELS) if NGSPICE_MODELS.exists() else None, log, status)

        run_btn.clicked.connect(do_run)
        vl.addWidget(run_btn)
        vl.addWidget(status)
        vl.addWidget(log)
        return sp_e, tab
