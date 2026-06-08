import os
import shutil
import subprocess

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from schematic import netlist_export
from schematic.waveform_viewer import WaveformViewer


class SimWorker(QObject):
    finished = pyqtSignal(str, int, str)

    def __init__(self, netlist_file, rawfile, parent=None):
        super().__init__(parent)
        self.netlist_file = netlist_file
        self.rawfile = rawfile
        self._process = None

    @pyqtSlot()
    def run(self):
        exe = shutil.which("ngspice") or "/usr/bin/ngspice"
        try:
            self._process = subprocess.Popen(
                [exe, "-b", self.netlist_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            stdout, _ = self._process.communicate()
            self.finished.emit(self.rawfile, self._process.returncode, stdout or "")
        except Exception as exc:
            self.finished.emit(self.rawfile, 1, str(exc))
        finally:
            self._process = None

    def stop(self):
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()


class SimulationPanel(QDockWidget):
    sim_done = pyqtSignal(str, int, str)

    def __init__(self, parent_window):
        super().__init__("Simulation", parent_window)
        self.parent_window = parent_window
        self._thread = None
        self._worker = None
        self._last_viewer = None
        self._last_stdout = ""
        self._last_rawfile = ""

        self._build_ui()
        self.sim_done.connect(self._on_sim_done)

    def _build_ui(self):
        root = QWidget(self)
        layout = QVBoxLayout(root)

        self.tabs = QTabWidget(root)
        layout.addWidget(self.tabs)

        self.tran_stop = QLineEdit("10n")
        self.tran_step = QLineEdit("10p")
        self.tran_start = QLineEdit("0")
        tran_form = QFormLayout()
        tran_form.addRow("Stop Time", self.tran_stop)
        tran_form.addRow("Step Time", self.tran_step)
        tran_form.addRow("Start Time", self.tran_start)
        self.tabs.addTab(self._form_page(tran_form), "Tran")

        self.dc_source = QLineEdit("V1")
        self.dc_start = QLineEdit("0")
        self.dc_stop = QLineEdit("1.8")
        self.dc_step = QLineEdit("0.01")
        dc_form = QFormLayout()
        dc_form.addRow("Source Name", self.dc_source)
        dc_form.addRow("Start", self.dc_start)
        dc_form.addRow("Stop", self.dc_stop)
        dc_form.addRow("Step", self.dc_step)
        self.tabs.addTab(self._form_page(dc_form), "DC")

        self.ac_type = QComboBox()
        self.ac_type.addItems(["DEC", "OCT", "LIN"])
        self.ac_pts = QLineEdit("10")
        self.ac_start = QLineEdit("1k")
        self.ac_stop = QLineEdit("10G")
        ac_form = QFormLayout()
        ac_form.addRow("Type", self.ac_type)
        ac_form.addRow("Points/Decade", self.ac_pts)
        ac_form.addRow("Start Freq", self.ac_start)
        ac_form.addRow("Stop Freq", self.ac_stop)
        self.tabs.addTab(self._form_page(ac_form), "AC")

        self.pss_freq = QLineEdit("1G")
        self.pss_periods = QLineEdit("20")
        pss_form = QFormLayout()
        pss_form.addRow("Fundamental Freq", self.pss_freq)
        pss_form.addRow("Periods", self.pss_periods)
        self.tabs.addTab(self._form_page(pss_form), "PSS")

        self.pnoise_ref = QLineEdit("V1")
        self.pnoise_start = QLineEdit("1k")
        self.pnoise_stop = QLineEdit("10G")
        self.pnoise_pts = QLineEdit("100")
        pnoise_form = QFormLayout()
        pnoise_form.addRow("Ref Source", self.pnoise_ref)
        pnoise_form.addRow("Start Freq", self.pnoise_start)
        pnoise_form.addRow("Stop Freq", self.pnoise_stop)
        pnoise_form.addRow("Points", self.pnoise_pts)
        self.tabs.addTab(self._form_page(pnoise_form), "Pnoise")

        layout.addWidget(QLabel("Probe Nodes:", root))
        self.probe_nodes = QLineEdit()
        self.probe_nodes.setPlaceholderText("e.g. out, in, net1")
        layout.addWidget(self.probe_nodes)

        self.run_button = QPushButton("Run Simulation")
        self.run_button.setStyleSheet("background: #40a02b; color: white; font-weight: bold;")
        self.run_button.clicked.connect(self.run_simulation)
        layout.addWidget(self.run_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet("background: #d20f39; color: white; font-weight: bold;")
        self.stop_button.clicked.connect(self.stop_simulation)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.setWidget(root)

    def _form_page(self, form):
        page = QWidget()
        page.setLayout(form)
        return page

    def _get_analysis_string(self):
        tab = self.tabs.tabText(self.tabs.currentIndex())
        if tab == "Tran":
            return f".tran {self.tran_step.text()} {self.tran_stop.text()} {self.tran_start.text()}"
        if tab == "DC":
            return f".dc {self.dc_source.text()} {self.dc_start.text()} {self.dc_stop.text()} {self.dc_step.text()}"
        if tab == "AC":
            return f".ac {self.ac_type.currentText()} {self.ac_pts.text()} {self.ac_start.text()} {self.ac_stop.text()}"
        if tab == "PSS":
            return f".pss {self.pss_freq.text()} {self.pss_periods.text()} stabilize"
        if tab == "Pnoise":
            return f".noise V(out) {self.pnoise_ref.text()} DEC {self.pnoise_pts.text()} {self.pnoise_start.text()} {self.pnoise_stop.text()}"
        return ""

    def run_simulation(self):
        canvas = getattr(self.parent_window, "_canvas", None) or getattr(self.parent_window, "canvas", None)
        if canvas is None:
            QMessageBox.warning(self, "Simulation", "No schematic canvas is available.")
            return

        tab = self.tabs.tabText(self.tabs.currentIndex())
        if tab in ("PSS", "Pnoise"):
            QMessageBox.warning(
                self,
                "Simulation",
                f"{tab} is not supported by standard ngspice in this flow. Running may fail.",
            )

        netlist = netlist_export.export_netlist(canvas, getattr(self.parent_window, "cellname", "top_circuit"))
        probes = self._probe_list()
        lines = [netlist, self._get_analysis_string()]
        lines.extend(self._print_lines(tab, probes))
        if probes:
            lines.append(".probe " + " ".join(probes))
        lines.append(".control")
        lines.append("run")
        lines.append("write /tmp/sim_out.raw")
        lines.append(".endc")
        lines.append(".end")

        netlist_file = "/tmp/eda_sim.sp"
        rawfile = "/tmp/sim_out.raw"
        with open(netlist_file, "w") as f:
            f.write("\n".join(lines) + "\n")

        self._start_worker(netlist_file, rawfile)

    def _probe_list(self):
        return [node.strip() for node in self.probe_nodes.text().split(",") if node.strip()]

    def _print_lines(self, tab, probes):
        if not probes:
            probes = ["out"]
        if tab == "Tran":
            return [".print tran " + " ".join(f"v({node})" for node in probes)]
        if tab == "DC":
            return [".print dc " + " ".join(f"v({node})" for node in probes)]
        if tab == "AC":
            return [".print ac " + " ".join(f"vdb({node}) vp({node})" for node in probes)]
        if tab == "Pnoise":
            return [".print noise onoise_spectrum"]
        return []

    def _start_worker(self, netlist_file, rawfile):
        self.progress.show()
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Running ngspice...")

        self._thread = QThread(self)
        self._worker = SimWorker(netlist_file, rawfile)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self.sim_done)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker_refs)
        self._thread.start()

    def stop_simulation(self):
        if self._worker is not None:
            self._worker.stop()
            self.status_label.setText("Stopping...")

    def _clear_worker_refs(self):
        self._thread = None
        self._worker = None

    def _on_sim_done(self, rawfile, returncode, stdout):
        self.progress.hide()
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._last_rawfile = rawfile
        self._last_stdout = stdout

        if returncode == 0:
            self.status_label.setText("Simulation complete")
            self._last_viewer = WaveformViewer(stdout)
            self._last_viewer.show()
            if hasattr(self.parent_window, "_last_sim_stdout"):
                self.parent_window._last_sim_stdout = stdout
                self.parent_window._last_waveform_viewer = self._last_viewer
        else:
            self.status_label.setText("Simulation failed")
            QMessageBox.critical(self, "ngspice Error", stdout or "ngspice failed without output.")

    def show_last_results(self):
        if self._last_stdout:
            self._last_viewer = WaveformViewer(self._last_stdout)
            self._last_viewer.show()
            return True
        return False
