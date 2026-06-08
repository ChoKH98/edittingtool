"""Interactive wire routing helpers for the layout editor."""
import sys

try:
    from PyQt5.QtWidgets import QGraphicsLineItem
    from PyQt5.QtGui import QColor, QPen
    from PyQt5.QtCore import QLineF, Qt
except ImportError:
    print('Install PyQt5: pip3 install PyQt5')
    sys.exit(1)

from layer_panel import LAYERS
from canvas import scene_to_um


class RouterState:
    def __init__(self, canvas):
        self.canvas = canvas
        self.active = False
        self._waypoints = []
        self._preview_items = []
        self._committed_items = []
        self.layer = 'M1'
        self.width_um = 0.2

    def start(self, scene_pt):
        self.cancel()
        self.active = True
        self._waypoints = [scene_pt]

    def add_waypoint(self, scene_pt):
        if not self.active:
            self.start(scene_pt)
            return
        last = self._waypoints[-1]
        self._waypoints.append(scene_pt)
        item = QGraphicsLineItem(QLineF(last, scene_pt))
        item.setPen(QPen(QColor('#3399ff'), 1.5))
        item.setZValue(60)
        self.canvas.scene().addItem(item)
        self._committed_items.append(item)

    def update_preview(self, scene_pt):
        self._remove_items(self._preview_items)
        self._preview_items = []
        if not self.active or not self._waypoints:
            return
        item = QGraphicsLineItem(QLineF(self._waypoints[-1], scene_pt))
        item.setPen(QPen(QColor('white'), 1.2, Qt.DashLine))
        item.setZValue(61)
        self.canvas.scene().addItem(item)
        self._preview_items.append(item)

    def cancel(self):
        self._remove_items(self._preview_items)
        self._remove_items(self._committed_items)
        self._preview_items = []
        self._committed_items = []
        self.active = False
        self._waypoints = []

    def finish(self):
        self._remove_items(self._preview_items)
        self._remove_items(self._committed_items)
        self._preview_items = []
        self._committed_items = []
        shapes = []
        half = self.width_um / 2.0
        for p1, p2 in zip(self._waypoints, self._waypoints[1:]):
            x1, y1 = self._scene_to_um_point(p1)
            x2, y2 = self._scene_to_um_point(p2)
            shapes.append({
                'type': 'wire',
                'layer': self.layer if self.layer in LAYERS else 'M1',
                'x': round(min(x1, x2) - half, 6),
                'y': round(min(y1, y2) - half, 6),
                'w': round(abs(x2 - x1) + self.width_um, 6),
                'h': round(abs(y2 - y1) + self.width_um, 6),
                'label': 'wire',
            })
        self.active = False
        self._waypoints = []
        return shapes

    def _scene_to_um_point(self, point):
        return scene_to_um(point.x()), -scene_to_um(point.y())

    def _remove_items(self, items):
        for item in list(items):
            if item.scene() is not None:
                item.scene().removeItem(item)
