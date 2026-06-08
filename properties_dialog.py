"""Properties dialog for layout shape editing."""
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout,
    QComboBox, QDoubleSpinBox, QLineEdit, QLabel,
)
from PyQt5.QtCore import Qt

from layer_panel import LAYERS


class PropertiesDialog(QDialog):
    def __init__(self, shape_dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Properties')
        self.setMinimumWidth(320)
        self._build_ui(shape_dict)

    def _build_ui(self, s):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Layer
        self._layer = QComboBox()
        self._layer.addItems(list(LAYERS.keys()))
        current_layer = s.get('layer', 'M1')
        idx = self._layer.findText(current_layer)
        if idx >= 0:
            self._layer.setCurrentIndex(idx)
        form.addRow('Layer:', self._layer)

        # Label
        self._label = QLineEdit(str(s.get('label', '')))
        form.addRow('Label:', self._label)

        # X
        self._x = QDoubleSpinBox()
        self._x.setRange(-100000, 100000)
        self._x.setDecimals(4)
        self._x.setSuffix(' um')
        self._x.setValue(float(s.get('x', 0.0)))
        form.addRow('X:', self._x)

        # Y
        self._y = QDoubleSpinBox()
        self._y.setRange(-100000, 100000)
        self._y.setDecimals(4)
        self._y.setSuffix(' um')
        self._y.setValue(float(s.get('y', 0.0)))
        form.addRow('Y:', self._y)

        # Width
        self._w = QDoubleSpinBox()
        self._w.setRange(0.001, 100000)
        self._w.setDecimals(4)
        self._w.setSuffix(' um')
        self._w.setValue(float(s.get('w', 1.0)))
        form.addRow('Width (W):', self._w)

        # Height / Length
        self._h = QDoubleSpinBox()
        self._h.setRange(0.001, 100000)
        self._h.setDecimals(4)
        self._h.setSuffix(' um')
        self._h.setValue(float(s.get('h', 1.0)))
        form.addRow('Height (H):', self._h)

        # Info row (read-only area)
        area_label = QLabel()
        area_label.setStyleSheet('color: #888;')
        self._area_label = area_label
        self._update_area()
        self._w.valueChanged.connect(self._update_area)
        self._h.valueChanged.connect(self._update_area)
        form.addRow('Area:', self._area_label)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_area(self):
        area = self._w.value() * self._h.value()
        self._area_label.setText(f'{area:.4f} um²')

    def get_props(self):
        return {
            'layer': self._layer.currentText(),
            'label': self._label.text(),
            'x': round(self._x.value(), 6),
            'y': round(self._y.value(), 6),
            'w': round(self._w.value(), 6),
            'h': round(self._h.value(), 6),
        }
