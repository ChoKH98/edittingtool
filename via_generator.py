"""Via array generator for the IHP SG13G2 layout editor."""
import sys

try:
    from PyQt5.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFormLayout,
        QSpinBox,
        QVBoxLayout,
    )
except ImportError:
    print('Install PyQt5: pip3 install PyQt5')
    sys.exit(1)


VIA_TYPES = {
    'Cont': {
        'layer': 'Cont',
        'lower': 'Activ',
        'upper': 'M1',
        'size': 0.16,
        'spacing': 0.18,
        'enclosure': 0.07,
    },
    'Via1': {
        'layer': 'Via1',
        'lower': 'M1',
        'upper': 'M2',
        'size': 0.19,
        'spacing': 0.22,
        'enclosure': 0.06,
    },
    'Via2': {
        'layer': 'Via2',
        'lower': 'M2',
        'upper': 'M3',
        'size': 0.19,
        'spacing': 0.22,
        'enclosure': 0.06,
    },
    'Via3': {
        'layer': 'Via3',
        'lower': 'M3',
        'upper': 'M4',
        'size': 0.19,
        'spacing': 0.22,
        'enclosure': 0.06,
    },
    'Via4': {
        'layer': 'Via4',
        'lower': 'M4',
        'upper': 'TM2',
        'size': 0.42,
        'spacing': 0.42,
        'enclosure': 0.12,
    },
}


class ViaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Create Via')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.via_type = QComboBox()
        self.via_type.addItems(VIA_TYPES.keys())
        form.addRow('Via type:', self.via_type)

        self.rows = QSpinBox()
        self.rows.setRange(1, 128)
        self.rows.setValue(1)
        form.addRow('Rows:', self.rows)

        self.cols = QSpinBox()
        self.cols.setRange(1, 128)
        self.cols.setValue(1)
        form.addRow('Columns:', self.cols)

        self.x_offset = QDoubleSpinBox()
        self.x_offset.setRange(-100000.0, 100000.0)
        self.x_offset.setDecimals(3)
        self.x_offset.setSingleStep(0.05)
        self.x_offset.setSuffix(' um')
        form.addRow('X offset:', self.x_offset)

        self.y_offset = QDoubleSpinBox()
        self.y_offset.setRange(-100000.0, 100000.0)
        self.y_offset.setDecimals(3)
        self.y_offset.setSingleStep(0.05)
        self.y_offset.setSuffix(' um')
        form.addRow('Y offset:', self.y_offset)

        self.include_enclosure = QCheckBox()
        self.include_enclosure.setChecked(True)
        form.addRow('Include enclosures:', self.include_enclosure)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_shapes(self):
        via_name = self.via_type.currentText()
        spec = VIA_TYPES[via_name]
        rows = self.rows.value()
        cols = self.cols.value()
        x0 = self.x_offset.value()
        y0 = self.y_offset.value()
        size = spec['size']
        pitch = spec['size'] + spec['spacing']

        shapes = []
        for row in range(rows):
            for col in range(cols):
                shapes.append({
                    'type': 'rect',
                    'layer': spec['layer'],
                    'label': via_name,
                    'x': round(x0 + col * pitch, 6),
                    'y': round(y0 + row * pitch, 6),
                    'w': size,
                    'h': size,
                })

        if self.include_enclosure.isChecked():
            enclosure = spec['enclosure']
            width = size + (cols - 1) * pitch
            height = size + (rows - 1) * pitch
            for layer in (spec['lower'], spec['upper']):
                shapes.append({
                    'type': 'rect',
                    'layer': layer,
                    'label': f'{via_name} enclosure',
                    'x': round(x0 - enclosure, 6),
                    'y': round(y0 - enclosure, 6),
                    'w': round(width + 2 * enclosure, 6),
                    'h': round(height + 2 * enclosure, 6),
                })
        return shapes
