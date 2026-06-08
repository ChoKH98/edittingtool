from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QStatusBar, QToolBar, QAction
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np


class WaveformViewer(QMainWindow):
    def __init__(self, data_text, title="Simulation Results"):
        super().__init__()
        self.setWindowTitle("Waveform Viewer")
        self.resize(900, 600)
        self._nav_toolbar = None

        self.figure = Figure(facecolor="#1e1e2e")
        self.canvas = FigureCanvas(self.figure)
        self.setCentralWidget(self.canvas)

        self._build_toolbar()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage(title)

        data = self._parse_ngspice_output(data_text)
        self._plot_data(data)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)

    def _build_toolbar(self):
        self._nav_toolbar = NavigationToolbar(self.canvas, self)
        self._nav_toolbar.hide()

        toolbar = QToolBar("Waveform Tools", self)
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        zoom_in = QAction("Zoom In", self)
        zoom_in.triggered.connect(lambda: self._zoom(0.8))
        toolbar.addAction(zoom_in)

        zoom_out = QAction("Zoom Out", self)
        zoom_out.triggered.connect(lambda: self._zoom(1.25))
        toolbar.addAction(zoom_out)

        pan = QAction("Pan", self)
        pan.setCheckable(True)
        pan.triggered.connect(self._toggle_pan)
        toolbar.addAction(pan)

        reset = QAction("Reset", self)
        reset.triggered.connect(self._reset_view)
        toolbar.addAction(reset)

    def _parse_ngspice_output(self, text):
        lines = text.splitlines()
        best = {}
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            parts = line.split()
            if parts and parts[0].lower() == "index" and len(parts) > 2:
                columns = parts[1:]
                table = {name: [] for name in columns}
                index += 1
                while index < len(lines):
                    row = lines[index].strip()
                    if not row:
                        break
                    values = row.split()
                    if len(values) < len(columns) + 1:
                        break
                    try:
                        floats = [float(value) for value in values[1:len(columns) + 1]]
                    except ValueError:
                        break
                    for name, value in zip(columns, floats):
                        table[name].append(value)
                    index += 1
                if table and any(table.values()):
                    best = table
            index += 1
        return best

    def _plot_data(self, data):
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.set_facecolor("#181825")
        axes.grid(True, color="#313244", linewidth=0.8)
        axes.tick_params(colors="#cdd6f4")
        for spine in axes.spines.values():
            spine.set_color("#cdd6f4")

        if not data:
            axes.text(
                0.5,
                0.5,
                "No plottable ngspice data found",
                ha="center",
                va="center",
                color="#cdd6f4",
                transform=axes.transAxes,
            )
            axes.set_xlabel("X", color="#cdd6f4")
            axes.set_ylabel("Y", color="#cdd6f4")
            self.figure.tight_layout()
            self.canvas.draw_idle()
            return

        columns = list(data.keys())
        x_name = columns[0]
        x = np.array(data[x_name], dtype=float)
        colors = ["#89b4fa", "#a6e3a1", "#f38ba8", "#fab387", "#f9e2af"]

        for idx, name in enumerate(columns[1:]):
            y = np.array(data[name], dtype=float)
            axes.plot(x, y, label=name, color=colors[idx % len(colors)], linewidth=1.6)

        if len(columns) == 1:
            axes.plot(np.arange(len(x)), x, label=x_name, color=colors[0], linewidth=1.6)

        axes.set_xlabel(self._x_label(x_name), color="#cdd6f4")
        axes.set_ylabel("Signal", color="#cdd6f4")
        axes.legend(facecolor="#181825", edgecolor="#313244", labelcolor="#cdd6f4")
        axes.set_title("Simulation Results", color="#cdd6f4")
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _x_label(self, x_name):
        name = x_name.lower()
        if "freq" in name:
            return "Frequency (Hz)"
        if "time" in name:
            return "Time (s)"
        if "v-" in name or "sweep" in name or "voltage" in name:
            return "Voltage (V)"
        return x_name

    def _zoom(self, factor):
        axes = self.figure.axes[0] if self.figure.axes else None
        if axes is None:
            return
        for getter, setter in ((axes.get_xlim, axes.set_xlim), (axes.get_ylim, axes.set_ylim)):
            low, high = getter()
            center = (low + high) / 2.0
            half = (high - low) * factor / 2.0
            setter(center - half, center + half)
        self.canvas.draw_idle()

    def _toggle_pan(self):
        if self._nav_toolbar is not None:
            self._nav_toolbar.pan()

    def _reset_view(self):
        axes = self.figure.axes[0] if self.figure.axes else None
        if axes is None:
            return
        axes.relim()
        axes.autoscale_view()
        self.canvas.draw_idle()

    def _on_motion(self, event):
        if event.inaxes and event.xdata is not None and event.ydata is not None:
            self.statusBar().showMessage(f"x={event.xdata:.6g}, y={event.ydata:.6g}")
