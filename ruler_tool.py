from PyQt5.QtWidgets import QGraphicsLineItem, QGraphicsTextItem, QGraphicsEllipseItem
from PyQt5.QtGui import QPen, QColor, QFont
from PyQt5.QtCore import Qt, QPointF, QLineF
import math

SCALE = 1000.0


class RulerOverlay:
    def __init__(self, scene):
        self._scene = scene
        self._items = []
        self._start = None

    def start(self, scene_pt):
        self.clear()
        self._start = scene_pt
        dot = QGraphicsEllipseItem(scene_pt.x() - 4, scene_pt.y() - 4, 8, 8)
        dot.setBrush(QColor('#FFFF00'))
        dot.setPen(QPen(Qt.NoPen))
        dot.setZValue(500)
        self._scene.addItem(dot)
        self._items.append(dot)

    def update_preview(self, scene_pt):
        for item in self._items[1:]:
            self._scene.removeItem(item)
        self._items = self._items[:1]
        if self._start is None:
            return
        line = QGraphicsLineItem(QLineF(self._start, scene_pt))
        line.setPen(QPen(QColor('#FFFF00'), 1.5, Qt.DashLine))
        line.setZValue(500)
        self._scene.addItem(line)
        self._items.append(line)
        dx = (scene_pt.x() - self._start.x()) / SCALE
        dy = (scene_pt.y() - self._start.y()) / SCALE
        dist = math.hypot(dx, dy)
        txt = QGraphicsTextItem(
            f'{dist * 1000:.1f} nm  ({dx * 1000:.1f}, {dy * 1000:.1f})'
        )
        txt.setDefaultTextColor(QColor('#FFFF00'))
        txt.setFont(QFont('Monospace', 9))
        txt.setZValue(501)
        mid = QPointF(
            (self._start.x() + scene_pt.x()) / 2,
            (self._start.y() + scene_pt.y()) / 2 - 20,
        )
        txt.setPos(mid)
        self._scene.addItem(txt)
        self._items.append(txt)

    def finish(self):
        self._start = None

    def clear(self):
        for item in self._items:
            self._scene.removeItem(item)
        self._items = []
        self._start = None
