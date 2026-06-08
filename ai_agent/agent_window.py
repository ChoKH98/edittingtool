"""AI Optimization Agent window for EDA tool."""

from PyQt5.QtCore import QSettings, QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai_agent.optimization_agent import ANTHROPIC_AVAILABLE, OptimizationAgent

DARK_STYLE = """
QWidget { background-color: #1e1e2e; color: #cdd6f4; font-family: monospace; }
QGroupBox { border: 1px solid #45475a; border-radius: 4px; margin-top: 8px; padding-top: 8px; }
QGroupBox::title { color: #89b4fa; }
QLineEdit, QTextEdit, QComboBox {
    background: #181825; border: 1px solid #45475a; border-radius: 3px;
    color: #cdd6f4; padding: 3px;
}
QPushButton {
    background: #313244; border: 1px solid #45475a; border-radius: 4px;
    color: #cdd6f4; padding: 5px 12px;
}
QPushButton:hover { background: #45475a; }
QPushButton#run_btn { background: #89b4fa; color: #1e1e2e; font-weight: bold; }
QPushButton#run_btn:hover { background: #b4befe; }
QPushButton#apply_btn { background: #a6e3a1; color: #1e1e2e; font-weight: bold; }
QPushButton#apply_btn:hover { background: #94e2d5; }
QPushButton#reset_btn { background: #f38ba8; color: #1e1e2e; }
QComboBox::drop-down { border: none; }
QScrollBar:vertical { background: #181825; width: 8px; }
QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; }
"""


class AgentWorker(QThread):
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, agent, netlist, goals, params, sim_results, iteration):
        super().__init__()
        self.agent = agent
        self.netlist = netlist
        self.goals = goals
        self.params = params
        self.sim_results = sim_results
        self.iteration = iteration

    def run(self):
        try:
            result = self.agent.get_suggestions(
                self.netlist,
                self.goals,
                self.params,
                self.sim_results,
                self.iteration,
            )
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class AgentWindow(QWidget):
    """Floating window for AI optimization agent."""

    apply_params_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Optimization Agent")
        self.setWindowFlags(Qt.Window)
        self.resize(600, 750)
        self.setStyleSheet(DARK_STYLE)

        self._agent = OptimizationAgent()
        self._pending_suggestions = []
        self._iteration = 0
        self._settings = QSettings("EDATool", "AIAgent")
        self._canvas = None
        self._worker = None

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        api_box = QGroupBox("Anthropic API Key")
        api_lay = QHBoxLayout(api_box)
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setPlaceholderText("sk-ant-...")
        self._key_edit.textChanged.connect(self._on_key_changed)
        api_lay.addWidget(self._key_edit)
        self._key_status = QLabel("*")
        self._key_status.setFixedWidth(20)
        self._key_status.setStyleSheet("color: #f38ba8;")
        api_lay.addWidget(self._key_status)
        root.addWidget(api_box)

        mode_box = QGroupBox("Optimization Mode")
        mode_lay = QHBoxLayout(mode_box)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Off", "Suggest (manual apply)", "Auto (apply directly)"])
        self._mode_combo.setCurrentIndex(1)
        mode_lay.addWidget(QLabel("Mode:"))
        mode_lay.addWidget(self._mode_combo)
        mode_lay.addStretch()
        root.addWidget(mode_box)

        goals_box = QGroupBox("Design Goals")
        goals_lay = QVBoxLayout(goals_box)
        self._goals_edit = QTextEdit()
        self._goals_edit.setMaximumHeight(100)
        self._goals_edit.setPlaceholderText(
            "Describe what you want to achieve:\n"
            "e.g., Gain > 40dB, BW > 100MHz, Vout_swing > 1V, "
            "phase margin > 60deg, power < 5mW"
        )
        goals_lay.addWidget(self._goals_edit)
        root.addWidget(goals_box)

        sim_box = QGroupBox("Simulation Results (optional - paste from SpiceSim)")
        sim_lay = QVBoxLayout(sim_box)
        self._sim_edit = QTextEdit()
        self._sim_edit.setMaximumHeight(80)
        self._sim_edit.setPlaceholderText("Paste ngspice output or measured values here...")
        sim_lay.addWidget(self._sim_edit)
        root.addWidget(sim_box)

        ctrl_lay = QHBoxLayout()
        self._run_btn = QPushButton("Optimize ->")
        self._run_btn.setObjectName("run_btn")
        self._run_btn.clicked.connect(self._run_optimization)
        self._reset_btn = QPushButton("Reset History")
        self._reset_btn.setObjectName("reset_btn")
        self._reset_btn.clicked.connect(self._reset)
        ctrl_lay.addWidget(self._run_btn)
        ctrl_lay.addWidget(self._reset_btn)
        ctrl_lay.addStretch()
        root.addLayout(ctrl_lay)

        sugg_box = QGroupBox("Agent Suggestions")
        sugg_lay = QVBoxLayout(sugg_box)
        self._sugg_display = QTextEdit()
        self._sugg_display.setReadOnly(True)
        self._sugg_display.setMinimumHeight(180)
        self._sugg_display.setStyleSheet("QTextEdit { background: #11111b; font-size: 12px; }")
        sugg_lay.addWidget(self._sugg_display)

        apply_lay = QHBoxLayout()
        self._apply_btn = QPushButton("Apply Suggestions to Schematic")
        self._apply_btn.setObjectName("apply_btn")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_suggestions)
        apply_lay.addWidget(self._apply_btn)
        apply_lay.addStretch()
        sugg_lay.addLayout(apply_lay)
        root.addWidget(sugg_box)

        self._status_label = QLabel("Ready. Set API key and design goals to begin.")
        self._status_label.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        root.addWidget(self._status_label)

        if not ANTHROPIC_AVAILABLE:
            warn = QLabel("anthropic not installed. Run: pip install anthropic")
            warn.setStyleSheet("color: #fab387; font-size: 11px;")
            root.addWidget(warn)

    def _on_key_changed(self, key):
        has_key = bool(key.strip())
        self._key_status.setStyleSheet("color: #a6e3a1;" if has_key else "color: #f38ba8;")
        self._agent.set_api_key(key.strip())

    def _load_settings(self):
        key = self._settings.value("api_key", "")
        if key:
            self._key_edit.setText(key)
        mode = self._settings.value("mode", 1, type=int)
        self._mode_combo.setCurrentIndex(mode)

    def _save_settings(self):
        self._settings.setValue("api_key", self._key_edit.text())
        self._settings.setValue("mode", self._mode_combo.currentIndex())

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    def _get_mode(self):
        return self._mode_combo.currentIndex()

    def _run_optimization(self):
        mode = self._get_mode()
        if mode == 0:
            self._status("AI is Off. Change mode to use optimization.")
            return
        if not self._agent.api_key:
            self._status("Enter your Anthropic API key first.")
            return
        goals = self._goals_edit.toPlainText().strip()
        if not goals:
            self._status("Enter design goals first.")
            return

        netlist, params = self._get_netlist_and_params()

        self._run_btn.setEnabled(False)
        self._status(f"Asking Claude (iteration {self._iteration + 1})...")

        self._worker = AgentWorker(
            self._agent,
            netlist,
            goals,
            params,
            self._sim_edit.toPlainText().strip(),
            self._iteration,
        )
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result):
        self._run_btn.setEnabled(True)
        if "error" in result:
            self._on_error(result["error"])
            return

        suggestions = result.get("suggestions", [])
        summary = result.get("summary", "")
        next_step = result.get("next_step", "")

        text = f"=== Iteration {self._iteration + 1} ===\n\n"
        if suggestions:
            text += "PARAMETER CHANGES:\n"
            for s in suggestions:
                text += (
                    f"  {s.get('component', '?')}.{s.get('parameter', '?')}: "
                    f"{s.get('old_value', '?')} -> {s.get('new_value', '?')}\n"
                    f"  Reason: {s.get('reason', '')}\n\n"
                )
        text += f"SUMMARY:\n{summary}\n"
        if next_step:
            text += f"\nNEXT STEP: {next_step}\n"

        self._sugg_display.setPlainText(text)
        self._pending_suggestions = suggestions
        self._iteration += 1

        mode = self._get_mode()
        if mode == 2 and suggestions:
            self._apply_suggestions()
            self._status(f"Auto-applied {len(suggestions)} changes (iter {self._iteration})")
        elif mode == 1 and suggestions:
            self._apply_btn.setEnabled(True)
            self._status("Suggest mode: review and click 'Apply' to update schematic")
        else:
            self._status("Done. No changes suggested.")

    def _on_error(self, msg):
        self._run_btn.setEnabled(True)
        self._sugg_display.setPlainText(f"Error: {msg}")
        self._status(f"Error: {msg[:80]}")

    def _apply_suggestions(self):
        if not self._pending_suggestions:
            return
        changes = {}
        for s in self._pending_suggestions:
            comp = s.get("component", "")
            param = s.get("parameter", "")
            val = s.get("new_value", "")
            if comp and param and val:
                changes.setdefault(comp, {})[param] = val
        if changes:
            self.apply_params_requested.emit(changes)
            self._status(f"Applied changes to {len(changes)} component(s).")
        self._apply_btn.setEnabled(False)
        self._pending_suggestions = []

    def _reset(self):
        self._agent.reset_history()
        self._iteration = 0
        self._sugg_display.clear()
        self._pending_suggestions = []
        self._apply_btn.setEnabled(False)
        self._status("History cleared. Ready for new optimization run.")

    def _get_netlist_and_params(self):
        """Try to get netlist from parent schematic window."""
        netlist = "(no schematic connected)"
        params = {}
        canvas = self._canvas

        parent = self.parent()
        while canvas is None and parent is not None:
            if hasattr(parent, "_canvas"):
                canvas = parent._canvas
                break
            parent = parent.parent() if hasattr(parent, "parent") else None

        if canvas is not None:
            try:
                from schematic.netlist_export import NetlistExporter

                try:
                    netlist = NetlistExporter(canvas._scene).export_string()
                except TypeError:
                    netlist = NetlistExporter().export(canvas, "ai_agent")
                for item in canvas._scene.items():
                    if hasattr(item, "comp_name") and hasattr(item, "props"):
                        params[item.comp_name] = dict(item.props)
            except Exception:
                pass

        return netlist, params

    def set_schematic_canvas(self, canvas):
        """Connect to a schematic canvas for reading netlist."""
        self._canvas = canvas

    def _status(self, msg):
        self._status_label.setText(msg)
