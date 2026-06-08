from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout,
    QSpinBox, QDoubleSpinBox, QDialogButtonBox,
)


class ArrayDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Create Array')
        form = QFormLayout()
        self._rows = QSpinBox()
        self._rows.setRange(1, 100)
        self._rows.setValue(2)
        self._cols = QSpinBox()
        self._cols.setRange(1, 100)
        self._cols.setValue(2)
        self._dx = QDoubleSpinBox()
        self._dx.setRange(-10000, 10000)
        self._dx.setDecimals(4)
        self._dx.setSuffix(' um')
        self._dx.setValue(1.0)
        self._dy = QDoubleSpinBox()
        self._dy.setRange(-10000, 10000)
        self._dy.setDecimals(4)
        self._dy.setSuffix(' um')
        self._dy.setValue(1.0)
        form.addRow('Rows:', self._rows)
        form.addRow('Cols:', self._cols)
        form.addRow('DX (col spacing):', self._dx)
        form.addRow('DY (row spacing):', self._dy)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(btns)

    def get_params(self):
        return self._rows.value(), self._cols.value(), self._dx.value(), self._dy.value()
