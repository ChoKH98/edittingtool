from PyQt5.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QFormLayout,
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QDialogButtonBox,
    QGraphicsView, QGraphicsScene, QGraphicsLineItem, QGraphicsEllipseItem,
    QGraphicsTextItem, QLabel, QSizePolicy)
from PyQt5.QtGui import QPen, QBrush, QColor, QPainter, QFont
from PyQt5.QtCore import Qt, QRectF

SCALE = 8
CELL_TYPES = ['NMOS', 'PMOS', 'Resistor', 'Capacitor']

TYPE_MAP = {
    'NMOS': 'nmos', 'PMOS': 'pmos', 'Resistor': 'resistor', 'Capacitor': 'capacitor'
}

PREFIX_MAP = {
    'NMOS': 'M', 'PMOS': 'M', 'Resistor': 'R', 'Capacitor': 'C'
}


def _auto_name(prefix, used):
    i = 1
    while f'{prefix}{i}' in used:
        i += 1
    return f'{prefix}{i}'


class PreviewCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QBrush(QColor('#1e1e1e')))
        self.setScene(self._scene)
        self.setFixedSize(200, 200)
        self.setRenderHint(QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def draw_symbol(self, sym_key, label=''):
        self._scene.clear()
        try:
            from schematic.symbols import SYMBOLS
            sym = SYMBOLS.get(sym_key, {})
        except ImportError:
            return
        pen = QPen(QColor('#ffffff'), 1.5)
        pin_pen = QPen(QColor('#00FF88'), 1.5)
        for x1, y1, x2, y2 in sym.get('lines', []):
            line = QGraphicsLineItem(x1*SCALE, y1*SCALE, x2*SCALE, y2*SCALE)
            line.setPen(pen)
            self._scene.addItem(line)
        for cx, cy, r, sa, sp in sym.get('arcs', []):
            ellipse = QGraphicsEllipseItem(
                (cx-r)*SCALE, (cy-r)*SCALE, r*2*SCALE, r*2*SCALE)
            ellipse.setPen(pen)
            ellipse.setBrush(QBrush(Qt.NoBrush))
            self._scene.addItem(ellipse)
        for pin_name, (px, py) in sym.get('pins', {}).items():
            dot = QGraphicsEllipseItem(px*SCALE-3, py*SCALE-3, 6, 6)
            dot.setPen(pin_pen)
            dot.setBrush(QBrush(QColor('#00FF88')))
            self._scene.addItem(dot)
            txt = QGraphicsTextItem(pin_name)
            txt.setDefaultTextColor(QColor('#00FF88'))
            txt.setFont(QFont('Monospace', 6))
            txt.setPos(px*SCALE+4, py*SCALE-6)
            self._scene.addItem(txt)
        if label:
            lbl = QGraphicsTextItem(label)
            lbl.setDefaultTextColor(QColor('#aaaaaa'))
            lbl.setFont(QFont('Monospace', 7))
            nx, ny = sym.get('name_offset', (0, -3))
            lbl.setPos(nx*SCALE, ny*SCALE)
            self._scene.addItem(lbl)
        self.fitInView(self._scene.itemsBoundingRect().adjusted(-10,-10,10,10),
                       Qt.KeepAspectRatio)


class PcellDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Place PCell')
        self._used_names = set()
        self._place_callback = None
        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # Left: parameter form
        form_widget = QVBoxLayout()
        form = QFormLayout()

        self._type_combo = QComboBox()
        self._type_combo.addItems(CELL_TYPES)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addRow('Cell type:', self._type_combo)

        self._w_spin = QDoubleSpinBox()
        self._w_spin.setRange(0.1, 100.0)
        self._w_spin.setValue(2.0)
        self._w_spin.setSingleStep(0.1)
        self._w_spin.setSuffix(' um')
        self._w_spin.valueChanged.connect(self._update_preview)
        form.addRow('W:', self._w_spin)

        self._l_spin = QDoubleSpinBox()
        self._l_spin.setRange(0.13, 1.0)
        self._l_spin.setValue(0.13)
        self._l_spin.setSingleStep(0.01)
        self._l_spin.setSuffix(' um')
        self._l_spin.valueChanged.connect(self._update_preview)
        form.addRow('L:', self._l_spin)

        self._fingers_spin = QSpinBox()
        self._fingers_spin.setRange(1, 32)
        self._fingers_spin.setValue(1)
        self._fingers_spin.valueChanged.connect(self._update_preview)
        form.addRow('Fingers:', self._fingers_spin)

        self._name_edit = QLineEdit('M1')
        form.addRow('Name:', self._name_edit)

        form_widget.addLayout(form)
        form_widget.addStretch()

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Cancel)
        btns.rejected.connect(self.reject)
        place_btn = btns.addButton('Place', QDialogButtonBox.AcceptRole)
        place_btn.clicked.connect(self._on_place)
        form_widget.addWidget(btns)

        left_container = QVBoxLayout()
        left_container.addLayout(form_widget)
        main_layout.addLayout(left_container)

        # Right: preview
        self._preview = PreviewCanvas(self)
        main_layout.addWidget(self._preview)

    def _on_type_changed(self, ctype):
        prefix = PREFIX_MAP.get(ctype, 'X')
        is_mos = ctype in ('NMOS', 'PMOS')
        self._w_spin.setEnabled(is_mos)
        self._l_spin.setEnabled(is_mos)
        self._fingers_spin.setEnabled(is_mos)
        name = _auto_name(prefix, self._used_names)
        self._name_edit.setText(name)
        self._update_preview()

    def _update_preview(self):
        ctype = self._type_combo.currentText()
        sym_key = TYPE_MAP.get(ctype, 'nmos')
        label = self._name_edit.text()
        self._preview.draw_symbol(sym_key, label)

    def _on_place(self):
        name = self._name_edit.text()
        self._used_names.add(name)
        props = self.get_props()
        if self._place_callback:
            self._place_callback(props)
        # Auto-increment name
        prefix = PREFIX_MAP.get(self._type_combo.currentText(), 'X')
        new_name = _auto_name(prefix, self._used_names)
        self._name_edit.setText(new_name)
        self._update_preview()

    def get_props(self):
        return {
            'type': TYPE_MAP.get(self._type_combo.currentText(), 'nmos'),
            'name': self._name_edit.text(),
            'W': self._w_spin.value(),
            'L': self._l_spin.value(),
            'fingers': self._fingers_spin.value(),
        }

    def set_place_callback(self, callback):
        self._place_callback = callback

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self._on_place()
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
