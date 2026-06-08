"""PCell generators for IHP SG13G2 layout editor."""
import sys
try:
    from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout,
                                  QDoubleSpinBox, QSpinBox,
                                  QComboBox, QDialogButtonBox)
    from PyQt5.QtCore import Qt
except ImportError:
    print("PyQt5 required")
    sys.exit(1)

from layer_panel import LAYERS


def NmosPCell(W=1.0, L=0.13, fingers=1):
    shapes = []
    gate_h = W / fingers
    for i in range(fingers):
        fy = i * (gate_h + 0.1)
        shapes.append({"type": "rect", "layer": "Activ", "label": "",
                        "x": 0.0, "y": fy, "w": W * 0.5 + L, "h": gate_h})
        shapes.append({"type": "rect", "layer": "GatPoly", "label": "G",
                        "x": W * 0.25, "y": fy - 0.05, "w": L, "h": gate_h + 0.1})
        shapes.append({"type": "rect", "layer": "M1", "label": "D",
                        "x": 0.0, "y": fy, "w": 0.2, "h": gate_h})
        shapes.append({"type": "rect", "layer": "M1", "label": "S",
                        "x": W * 0.25 + L + 0.05, "y": fy, "w": 0.2, "h": gate_h})
    nw_margin = 0.3
    total_h = fingers * gate_h + (fingers - 1) * 0.1
    shapes.append({"type": "rect", "layer": "NWell", "label": "SUB",
                    "x": -nw_margin, "y": -nw_margin,
                    "w": W * 0.5 + L + 2 * nw_margin,
                    "h": total_h + 2 * nw_margin})
    return shapes


def PmosPCell(W=1.0, L=0.13, fingers=1):
    shapes = NmosPCell(W=W, L=L, fingers=fingers)
    for s in shapes:
        if s["layer"] == "Activ":
            s["layer"] = "PActive"
        elif s["layer"] == "NWell":
            s["layer"] = "NActive"
    return shapes


def ResistorPCell(W=0.5, L=5.0, layer="GatPoly"):
    return [
        {"type": "rect", "layer": layer, "label": "",
         "x": 0.0, "y": 0.0, "w": W, "h": L},
        {"type": "rect", "layer": "M1", "label": "P",
         "x": 0.0, "y": 0.0, "w": W, "h": 0.2},
        {"type": "rect", "layer": "M1", "label": "N",
         "x": 0.0, "y": L - 0.2, "w": W, "h": 0.2},
    ]


def CapacitorPCell(W=5.0, L=5.0):
    return [
        {"type": "rect", "layer": "M1", "label": "P",
         "x": 0.0, "y": 0.0, "w": W, "h": L},
        {"type": "rect", "layer": "M2", "label": "N",
         "x": 0.05, "y": 0.05, "w": W - 0.1, "h": L - 0.1},
    ]


class AddInstanceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add PCell Instance")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._cell_type = QComboBox()
        self._cell_type.addItems(["NMOS", "PMOS", "Resistor", "Capacitor"])
        form.addRow("Cell type:", self._cell_type)
        self._W = QDoubleSpinBox()
        self._W.setRange(0.13, 100.0)
        self._W.setValue(1.0)
        self._W.setSingleStep(0.1)
        self._W.setSuffix(" um")
        form.addRow("Width W:", self._W)
        self._L = QDoubleSpinBox()
        self._L.setRange(0.13, 100.0)
        self._L.setValue(0.13)
        self._L.setSingleStep(0.01)
        self._L.setSuffix(" um")
        form.addRow("Length L:", self._L)
        self._fingers = QSpinBox()
        self._fingers.setRange(1, 32)
        self._fingers.setValue(1)
        form.addRow("Fingers:", self._fingers)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_shapes(self):
        ct = self._cell_type.currentText()
        W = self._W.value()
        L = self._L.value()
        f = self._fingers.value()
        if ct == "NMOS":
            return NmosPCell(W=W, L=L, fingers=f)
        elif ct == "PMOS":
            return PmosPCell(W=W, L=L, fingers=f)
        elif ct == "Resistor":
            return ResistorPCell(W=W, L=L)
        else:
            return CapacitorPCell(W=W, L=L)

