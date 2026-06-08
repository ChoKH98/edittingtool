"""Layer Selection Window for IHP SG13G2 layout editor."""
import sys
try:
    from PyQt5.QtWidgets import (QWidget, QListWidget, QListWidgetItem,
                                  QVBoxLayout, QLabel, QColorDialog, QMenu, QAction)
    from PyQt5.QtGui import QColor, QPixmap, QIcon
    from PyQt5.QtCore import Qt, pyqtSignal
except ImportError:
    print('Install PyQt5: pip3 install PyQt5')
    sys.exit(1)

from pdk_manager import PDK
LAYERS = PDK.layers

LAYER_NAMES = list(LAYERS.keys())


def make_color_icon(color_hex, size=16):
    pix = QPixmap(size, size)
    pix.fill(QColor(color_hex))
    return QIcon(pix)


class LayerPanel(QWidget):
    layer_selected = pyqtSignal(str)
    layer_visibility_changed = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self._colors = {name: data[2] for name, data in LAYERS.items()}
        self._visible = {name: True for name in LAYERS}
        self._locked = {name: False for name in LAYERS}
        self._active_layer = 'M1'

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        label = QLabel('Layers (LSW)')
        label.setStyleSheet('color: #ccc; font-weight: bold;')
        layout.addWidget(label)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            'QListWidget { background: #2a2a2a; color: #eee; }'
            'QListWidget::item:selected { background: #005577; }'
        )
        layout.addWidget(self.list_widget)

        self._populate()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        PDK.pdk_changed.connect(self.reload_layers)

        # Select M1 by default
        self._select_layer('M1')

    def reload_layers(self, pdk_name, layers, _tech_data=None):
        global LAYERS, LAYER_NAMES
        LAYERS = layers
        LAYER_NAMES = list(LAYERS.keys())
        self._colors = {name: data[2] for name, data in LAYERS.items()}
        self._visible = {name: True for name in LAYERS}
        self._locked = {name: False for name in LAYERS}
        if self._active_layer not in LAYERS and LAYERS:
            self._active_layer = next(iter(LAYERS))
        self._populate()

    def _populate(self):
        self.list_widget.clear()
        for name, (gds_layer, gds_dt, _) in LAYERS.items():
            item = QListWidgetItem()
            item.setText(f'  {name}  [{gds_layer}:{gds_dt}]')
            item.setIcon(make_color_icon(self._colors[name]))
            item.setData(Qt.UserRole, name)
            if not self._visible[name]:
                item.setForeground(QColor('#555'))
            if self._locked[name]:
                item.setForeground(QColor('#886'))
            # Checkbox via flags
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self._visible[name] else Qt.Unchecked)
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        name = item.data(Qt.UserRole)
        if self._locked.get(name):
            return
        vis = item.checkState() == Qt.Checked
        if self._visible[name] != vis:
            self._visible[name] = vis
            self.layer_visibility_changed.emit(name, vis)
        self._active_layer = name
        self.layer_selected.emit(name)

    def _on_item_double_clicked(self, item):
        name = item.data(Qt.UserRole)
        color = QColorDialog.getColor(QColor(self._colors[name]), self, f'Color for {name}')
        if color.isValid():
            self._colors[name] = color.name()
            item.setIcon(make_color_icon(color.name()))

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        name = item.data(Qt.UserRole)
        menu = QMenu(self)
        vis_action = QAction('Hide layer' if self._visible[name] else 'Show layer', self)
        lock_action = QAction('Unlock layer' if self._locked[name] else 'Lock layer', self)
        menu.addAction(vis_action)
        menu.addAction(lock_action)
        action = menu.exec_(self.list_widget.mapToGlobal(pos))
        if action == vis_action:
            self._visible[name] = not self._visible[name]
            item.setCheckState(Qt.Checked if self._visible[name] else Qt.Unchecked)
            self.layer_visibility_changed.emit(name, self._visible[name])
            self._populate()
        elif action == lock_action:
            self._locked[name] = not self._locked[name]
            self._populate()

    def _select_layer(self, name):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == name:
                self.list_widget.setCurrentItem(item)
                break

    def active_layer(self):
        return self._active_layer

    def layer_color(self, name):
        return self._colors.get(name, '#FFFFFF')

    def is_visible(self, name):
        return self._visible.get(name, True)

    def is_locked(self, name):
        return self._locked.get(name, False)
