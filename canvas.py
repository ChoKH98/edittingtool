"""QGraphicsView canvas for the IHP SG13G2 layout editor."""
import json
import math
import sys

try:
    from PyQt5.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsPolygonItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QInputDialog,
        QGraphicsView,
        QRubberBand,
        QUndoCommand,
        QUndoStack,
    )
    from PyQt5.QtGui import QBrush, QColor, QKeySequence, QPainter, QPen, QPolygonF
    from PyQt5.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
except ImportError:
    print('Install PyQt5: pip3 install PyQt5')
    sys.exit(1)

try:
    import klayout.db as db
except ImportError:
    db = None

from layer_panel import LAYERS
from ruler_tool import RulerOverlay

SCALE = 1000.0
GRID_MINOR = 0.05   # default minor grid (um)
GRID_MAJOR = 0.5    # default major grid (um)
SNAP = 0.05
MIN_GRID_PIXEL = 4  # skip grid if lines would be closer than this many pixels


def um_to_scene(v):
    return v * SCALE


def scene_to_um(v):
    return v / SCALE


def _shape_rect(shape_dict):
    x = float(shape_dict.get('x', 0.0))
    y = float(shape_dict.get('y', 0.0))
    w = float(shape_dict.get('w', 0.0))
    h = float(shape_dict.get('h', 0.0))
    return QRectF(um_to_scene(x), -um_to_scene(y + h), um_to_scene(w), um_to_scene(h))


def _rect_to_shape(rect, layer, label=''):
    rect = QRectF(rect).normalized()
    return {
        'x': round(scene_to_um(rect.left()), 6),
        'y': round(-scene_to_um(rect.bottom()), 6),
        'w': round(scene_to_um(rect.width()), 6),
        'h': round(scene_to_um(rect.height()), 6),
        'layer': layer,
        'label': label,
    }


def _scene_point_to_um(point):
    return [round(scene_to_um(point.x()), 6), round(-scene_to_um(point.y()), 6)]


def _um_point_to_scene(point):
    return QPointF(um_to_scene(float(point[0])), -um_to_scene(float(point[1])))


class ShapeItem(QGraphicsRectItem):
    """Selectable, movable layout rectangle backed by a shape dictionary."""

    def __init__(self, shape_dict, color_hex, parent=None):
        super().__init__(parent)
        self.shape_dict = dict(shape_dict)
        self._suppress_shape_update = False
        self._base_color = QColor(color_hex)
        self._base_pen = QPen(self._base_color, 1.5)
        fill = QColor(self._base_color)
        fill.setAlpha(100)
        self.setPos(0, 0)
        self.setRect(_shape_rect(self.shape_dict))
        self.setPen(self._base_pen)
        self.setBrush(QBrush(fill))
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setToolTip(self._tooltip())
        self.layer = self.shape_dict.get('layer', '')

    def _tooltip(self):
        label = self.shape_dict.get('label') or self.shape_dict.get('type') or 'shape'
        layer = self.shape_dict.get('layer', '')
        return f'{label} on {layer}' if layer else str(label)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor('white'), 2.0))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self._base_pen)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            if isinstance(value, QPointF):
                step = um_to_scene(SNAP)
                return QPointF(round(value.x() / step) * step, round(value.y() / step) * step)
        if change == QGraphicsItem.ItemPositionHasChanged and not self._suppress_shape_update:
            self.update_shape_dict()
        return super().itemChange(change, value)

    def update_shape_dict(self):
        current = _rect_to_shape(self.mapRectToScene(self.rect()), self.shape_dict.get('layer', 'M1'), self.shape_dict.get('label', ''))
        for key in ('x', 'y', 'w', 'h'):
            self.shape_dict[key] = current[key]
        self.layer = self.shape_dict.get('layer', '')

    def to_shape_dict(self):
        self.update_shape_dict()
        return dict(self.shape_dict)

    def refresh_visuals(self, color_hex):
        self._base_color = QColor(color_hex)
        self._base_pen = QPen(self._base_color, 1.5)
        fill = QColor(self._base_color)
        fill.setAlpha(100)
        self._suppress_shape_update = True
        self.setPos(0, 0)
        self.setRect(_shape_rect(self.shape_dict))
        self._suppress_shape_update = False
        self.setPen(self._base_pen)
        self.setBrush(QBrush(fill))
        self.setToolTip(self._tooltip())
        self.layer = self.shape_dict.get('layer', '')


class PolygonItem(QGraphicsPolygonItem):
    """Selectable, movable polygon backed by a shape dictionary."""

    def __init__(self, shape_dict, color_hex, parent=None):
        super().__init__(parent)
        self.shape_dict = dict(shape_dict)
        self._suppress_shape_update = False
        self.shape_dict['type'] = 'polygon'
        self._base_color = QColor(color_hex)
        self._base_pen = QPen(self._base_color, 1.5)
        fill = QColor(self._base_color)
        fill.setAlpha(90)
        self.setPos(0, 0)
        self.setPolygon(QPolygonF([_um_point_to_scene(p) for p in self.shape_dict.get('points', [])]))
        self.setPen(self._base_pen)
        self.setBrush(QBrush(fill))
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.layer = self.shape_dict.get('layer', '')
        self.setToolTip(self._tooltip())

    def _tooltip(self):
        layer = self.shape_dict.get('layer', '')
        return f'polygon on {layer}' if layer else 'polygon'

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor('white'), 2.0))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self._base_pen)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            if isinstance(value, QPointF):
                step = um_to_scene(SNAP)
                return QPointF(round(value.x() / step) * step, round(value.y() / step) * step)
        if change == QGraphicsItem.ItemPositionHasChanged and not self._suppress_shape_update:
            self.update_shape_dict()
        return super().itemChange(change, value)

    def update_shape_dict(self):
        self.shape_dict['points'] = [_scene_point_to_um(self.mapToScene(p)) for p in self.polygon()]
        self.shape_dict['type'] = 'polygon'
        self.layer = self.shape_dict.get('layer', '')

    def to_shape_dict(self):
        self.update_shape_dict()
        return dict(self.shape_dict)

    def refresh_visuals(self, color_hex):
        self._base_color = QColor(color_hex)
        self._base_pen = QPen(self._base_color, 1.5)
        fill = QColor(self._base_color)
        fill.setAlpha(90)
        self._suppress_shape_update = True
        self.setPos(0, 0)
        self.setPolygon(QPolygonF([_um_point_to_scene(p) for p in self.shape_dict.get('points', [])]))
        self._suppress_shape_update = False
        self.setPen(self._base_pen)
        self.setBrush(QBrush(fill))
        self.layer = self.shape_dict.get('layer', '')
        self.setToolTip(self._tooltip())


class LabelItem(QGraphicsTextItem):
    """Selectable, movable layout label backed by a shape dictionary."""

    def __init__(self, shape_dict, color_hex, parent=None):
        super().__init__(parent)
        self.shape_dict = dict(shape_dict)
        self._suppress_shape_update = False
        self.shape_dict['type'] = 'label'
        self.setPlainText(str(self.shape_dict.get('text', self.shape_dict.get('label', ''))))
        self.setDefaultTextColor(QColor(color_hex))
        self.setPos(um_to_scene(float(self.shape_dict.get('x', 0.0))), -um_to_scene(float(self.shape_dict.get('y', 0.0))))
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.layer = self.shape_dict.get('layer', 'TEXT')
        self.setToolTip(self._tooltip())

    def _tooltip(self):
        return f"label '{self.toPlainText()}' on {self.shape_dict.get('layer', 'TEXT')}"

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            if isinstance(value, QPointF):
                step = um_to_scene(SNAP)
                return QPointF(round(value.x() / step) * step, round(value.y() / step) * step)
        if change == QGraphicsItem.ItemPositionHasChanged and not self._suppress_shape_update:
            self.update_shape_dict()
        return super().itemChange(change, value)

    def update_shape_dict(self):
        pos = self.scenePos()
        self.shape_dict.update({
            'type': 'label',
            'text': self.toPlainText(),
            'label': self.toPlainText(),
            'x': round(scene_to_um(pos.x()), 6),
            'y': round(-scene_to_um(pos.y()), 6),
            'layer': self.shape_dict.get('layer', 'TEXT'),
        })
        self.layer = self.shape_dict.get('layer', 'TEXT')

    def to_shape_dict(self):
        self.update_shape_dict()
        return dict(self.shape_dict)

    def refresh_visuals(self, color_hex):
        self.setPlainText(str(self.shape_dict.get('text', '')))
        self.setDefaultTextColor(QColor(color_hex))
        self._suppress_shape_update = True
        self.setPos(um_to_scene(float(self.shape_dict.get('x', 0.0))), -um_to_scene(float(self.shape_dict.get('y', 0.0))))
        self._suppress_shape_update = False
        self.layer = self.shape_dict.get('layer', 'TEXT')
        self.setToolTip(self._tooltip())



class EditShapePropertiesCommand(QUndoCommand):
    def __init__(self, canvas, item, old_props, new_props):
        super().__init__('Edit properties')
        self._canvas = canvas
        self._item = item
        self._old = dict(old_props)
        self._new = dict(new_props)

    def redo(self):
        self._apply(self._new)

    def undo(self):
        self._apply(self._old)

    def _apply(self, props):
        for k, v in props.items():
            self._item.shape_dict[k] = v
        color = self._canvas._layer_color(props.get('layer', 'M1'))
        self._item.refresh_visuals(color)


class DrcOverlayItem(QGraphicsRectItem):
    """Visual marker for one DRC violation."""

    def __init__(self, violation, parent=None):
        x1, y1, x2, y2 = violation.get('bbox', (0, 0, 0, 0))
        rect = QRectF(um_to_scene(x1), -um_to_scene(y2), um_to_scene(x2 - x1), um_to_scene(y2 - y1)).normalized()
        super().__init__(rect, parent)
        fill = QColor('red')
        fill.setAlpha(80)
        pen = QPen(QColor('red'), 2.0, Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(fill))
        self.setZValue(100)
        rule = violation.get('rule', 'DRC')
        desc = violation.get('description', '')
        self.setToolTip(f'{rule}: {desc}')


class AddShapeCommand(QUndoCommand):
    def __init__(self, canvas, item, text='Add shape'):
        super().__init__(text)
        self.canvas = canvas
        self.item = item

    def redo(self):
        if self.item.scene() is None:
            self.canvas.scene().addItem(self.item)
        if self.item not in self.canvas._shapes:
            self.canvas._shapes.append(self.item)
        self.canvas._sync_item_visibility(self.item)

    def undo(self):
        if self.item in self.canvas._shapes:
            self.canvas._shapes.remove(self.item)
        if self.item.scene() is not None:
            self.canvas.scene().removeItem(self.item)


class DeleteShapeCommand(QUndoCommand):
    def __init__(self, canvas, items, text='Delete shape'):
        super().__init__(text if len(items) == 1 else 'Delete shapes')
        self.canvas = canvas
        self.items = list(items)

    def redo(self):
        for item in self.items:
            if item in self.canvas._shapes:
                self.canvas._shapes.remove(item)
            if item.scene() is not None:
                self.canvas.scene().removeItem(item)

    def undo(self):
        for item in self.items:
            if item.scene() is None:
                self.canvas.scene().addItem(item)
            if item not in self.canvas._shapes:
                self.canvas._shapes.append(item)
            self.canvas._sync_item_visibility(item)


class TransformItemsCommand(QUndoCommand):
    def __init__(self, canvas, items, new_shapes, text):
        super().__init__(text)
        self.canvas = canvas
        self.items = list(items)
        self.old_shapes = [item.to_shape_dict() for item in self.items]
        self.new_shapes = [dict(shape) for shape in new_shapes]

    def redo(self):
        for item, shape in zip(self.items, self.new_shapes):
            self.canvas._apply_shape_to_item(item, shape)

    def undo(self):
        for item, shape in zip(self.items, self.old_shapes):
            self.canvas._apply_shape_to_item(item, shape)


class FlipCommand(TransformItemsCommand):
    def __init__(self, canvas, items, horizontal=True):
        bbox = canvas._items_bbox(items)
        cx = bbox.center().x()
        cy = bbox.center().y()
        new_shapes = []
        for item in items:
            shape = item.to_shape_dict()
            if isinstance(item, ShapeItem):
                rect = item.mapRectToScene(item.rect())
                if horizontal:
                    rect.moveLeft(2 * cx - rect.right())
                else:
                    rect.moveTop(2 * cy - rect.bottom())
                new_shapes.append(_rect_to_shape(rect, shape.get('layer', 'M1'), shape.get('label', '')))
            elif isinstance(item, PolygonItem):
                points = []
                for p in item.polygon():
                    scene_p = item.mapToScene(p)
                    x = 2 * cx - scene_p.x() if horizontal else scene_p.x()
                    y = scene_p.y() if horizontal else 2 * cy - scene_p.y()
                    points.append(_scene_point_to_um(QPointF(x, y)))
                new_shape = dict(shape)
                new_shape.update({'type': 'polygon', 'points': points})
                new_shapes.append(new_shape)
        super().__init__(canvas, items, new_shapes, 'Flip horizontal' if horizontal else 'Flip vertical')


class RotateCommand(TransformItemsCommand):
    def __init__(self, canvas, items, ccw=True):
        bbox = canvas._items_bbox(items)
        center = bbox.center()
        new_shapes = []
        for item in items:
            shape = item.to_shape_dict()
            if isinstance(item, ShapeItem):
                corners = [
                    item.mapRectToScene(item.rect()).topLeft(),
                    item.mapRectToScene(item.rect()).topRight(),
                    item.mapRectToScene(item.rect()).bottomRight(),
                    item.mapRectToScene(item.rect()).bottomLeft(),
                ]
                rotated = [_rotate_scene_point(p, center, ccw) for p in corners]
                rect = QPolygonF(rotated).boundingRect()
                new_shapes.append(_rect_to_shape(rect, shape.get('layer', 'M1'), shape.get('label', '')))
            elif isinstance(item, PolygonItem):
                points = []
                for p in item.polygon():
                    points.append(_scene_point_to_um(_rotate_scene_point(item.mapToScene(p), center, ccw)))
                new_shape = dict(shape)
                new_shape.update({'type': 'polygon', 'points': points})
                new_shapes.append(new_shape)
        super().__init__(canvas, items, new_shapes, 'Rotate CCW' if ccw else 'Rotate CW')


def _rotate_scene_point(point, center, ccw=True):
    dx = point.x() - center.x()
    dy = point.y() - center.y()
    if ccw:
        return QPointF(center.x() - dy, center.y() + dx)
    return QPointF(center.x() + dy, center.y() - dx)


class MergeCommand(QUndoCommand):
    def __init__(self, canvas, old_items, new_items):
        super().__init__('Merge shapes')
        self.canvas = canvas
        self.old_items = list(old_items)
        self.new_items = list(new_items)

    def redo(self):
        for item in self.old_items:
            if item in self.canvas._shapes:
                self.canvas._shapes.remove(item)
            if item.scene() is not None:
                self.canvas.scene().removeItem(item)
        for item in self.new_items:
            if item.scene() is None:
                self.canvas.scene().addItem(item)
            if item not in self.canvas._shapes:
                self.canvas._shapes.append(item)
            self.canvas._sync_item_visibility(item)

    def undo(self):
        for item in self.new_items:
            if item in self.canvas._shapes:
                self.canvas._shapes.remove(item)
            if item.scene() is not None:
                self.canvas.scene().removeItem(item)
        for item in self.old_items:
            if item.scene() is None:
                self.canvas.scene().addItem(item)
            if item not in self.canvas._shapes:
                self.canvas._shapes.append(item)
            self.canvas._sync_item_visibility(item)


class LayoutCanvas(QGraphicsView):
    coord_changed = pyqtSignal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setBackgroundBrush(QBrush(QColor('#1a1a1a')))
        self._scene.setBackgroundBrush(QBrush(QColor('#1a1a1a')))
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        self._undo_stack = QUndoStack(self)
        self._shapes = []
        self._drc_overlays = []
        self._show_grid = True
        self._active_layer = 'M1'
        self._mode = 'select'
        self._layer_panel = None
        self._router = None
        self._clipboard = []

        self._panning = False
        self._pan_start = QPoint()
        self._rubber_origin = None
        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self._rubber_selecting = False
        self._rect_start = None
        self._rect_preview = None
        self._polygon_points = []
        self._polygon_preview = None
        self._last_click_um = None
        self._ruler = RulerOverlay(self._scene)
        self._ruler_active = False

        self._grid_minor = GRID_MINOR
        self._grid_major = GRID_MAJOR

        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(30)
        self._zoom_pending = 1.0
        self._zoom_timer.timeout.connect(self._apply_pending_zoom)

        self.setSceneRect(-500000, -10500000, 11000000, 11000000)  # covers 0-10000 um
        self.fitInView(QRectF(-5000, -5000, 10000, 10000), Qt.KeepAspectRatio)
        self.set_mode('select')

    def set_layer_panel(self, panel):
        self._layer_panel = panel
        if hasattr(panel, 'active_layer'):
            self._active_layer = panel.active_layer()
        panel.layer_selected.connect(self._on_layer_selected)
        panel.layer_visibility_changed.connect(self._on_layer_visibility_changed)
        for item in self._shapes:
            self._sync_item_visibility(item)

    def set_router(self, router):
        self._router = router

    def undo_stack(self):
        return self._undo_stack

    def set_mode(self, mode):
        self._mode = mode
        self.setCursor(Qt.ArrowCursor if mode == 'select' else Qt.CrossCursor)
        if mode != 'wire' and self._router is not None:
            self._router.cancel()
        if mode != 'rectangle':
            self._clear_rect_preview()
        if mode != 'polygon':
            self._clear_polygon_preview()
        if mode != 'ruler':
            self._ruler.clear()
            self._ruler_active = False

    def add_shapes(self, shape_list):
        for shape in shape_list or []:
            layer = shape.get('layer', self._active_layer)
            color = self._layer_color(layer)
            shape_type = shape.get('type', 'rect')
            if shape_type == 'polygon':
                item = PolygonItem(shape, color)
            elif shape_type == 'label':
                item = LabelItem(shape, color)
            else:
                item = ShapeItem(shape, color)
            self._undo_stack.push(AddShapeCommand(self, item))

    def show_drc_violations(self, violations):
        for item in self._drc_overlays:
            if item.scene() is not None:
                self.scene().removeItem(item)
        self._drc_overlays = []
        for violation in violations or []:
            item = DrcOverlayItem(violation)
            self.scene().addItem(item)
            self._drc_overlays.append(item)

    def get_all_shapes(self):
        return [item.to_shape_dict() for item in list(self._shapes) if self._is_layout_item(item)]

    def clear_layout(self):
        self.show_drc_violations([])
        for item in list(self._shapes):
            if item.scene() is not None:
                self.scene().removeItem(item)
        self._shapes = []
        self._undo_stack.clear()

    def clear_drc(self):
        self.show_drc_violations([])

    def toggle_grid(self):
        self._show_grid = not self._show_grid
        self.viewport().update()

    def set_grid_spacing(self, minor_um, major_um):
        self._grid_minor = minor_um
        self._grid_major = major_um
        self.viewport().update()

    def zoom(self, factor):
        current = self.transform().m11()
        target = max(0.001, min(5000.0, current * factor))
        if not math.isclose(current, target):
            actual = target / current
            self.scale(actual, actual)

    def _apply_pending_zoom(self):
        if not math.isclose(self._zoom_pending, 1.0):
            self.zoom(self._zoom_pending)
            self._zoom_pending = 1.0


    def zoom_to_selection(self):
        items = [i for i in self.scene().selectedItems() if self._is_layout_item(i)]
        if not items:
            return
        rect = QRectF()
        for item in items:
            rect = rect.united(item.sceneBoundingRect()) if rect.isValid() else QRectF(item.sceneBoundingRect())
        pad = max(um_to_scene(0.5), rect.width() * 0.1)
        rect.adjust(-pad, -pad, pad, pad)
        self.setSceneRect(self.sceneRect().united(rect))
        self.fitInView(rect, Qt.KeepAspectRatio)

    def fit_view(self):
        items = [item for item in self._shapes if item.scene() is not None]
        if not items:
            self.fitInView(QRectF(-5000, -5000, 10000, 10000), Qt.KeepAspectRatio)
            return
        rect = QRectF()
        for item in items:
            rect = rect.united(item.sceneBoundingRect()) if rect.isValid() else QRectF(item.sceneBoundingRect())
        pad = max(um_to_scene(0.5), rect.width() * 0.05, rect.height() * 0.05)
        rect.adjust(-pad, -pad, pad, pad)
        self.setSceneRect(rect)
        self.fitInView(rect, Qt.KeepAspectRatio)

    def copy_selected(self):
        shapes = [item.to_shape_dict() for item in self.scene().selectedItems() if self._is_layout_item(item)]
        if not shapes:
            return
        self._clipboard = shapes
        QApplication.clipboard().setText(json.dumps(shapes))

    def paste_clipboard(self):
        shapes = list(self._clipboard)
        if not shapes:
            try:
                shapes = json.loads(QApplication.clipboard().text())
            except Exception:
                shapes = []
        pasted = []
        for shape in shapes:
            new_shape = dict(shape)
            if new_shape.get('type') == 'polygon':
                new_shape['points'] = [
                    [round(float(p[0]) + 0.5, 6), round(float(p[1]) + 0.5, 6)]
                    for p in new_shape.get('points', [])
                ]
            else:
                new_shape['x'] = float(new_shape.get('x', 0.0)) + 0.5
                new_shape['y'] = float(new_shape.get('y', 0.0)) + 0.5
            pasted.append(new_shape)
        self.add_shapes(pasted)

    def delete_selected(self):
        items = [item for item in self.scene().selectedItems() if self._is_layout_item(item)]
        if items:
            self._undo_stack.push(DeleteShapeCommand(self, items))

    def flip_selected(self, horizontal=True):
        items = [item for item in self.scene().selectedItems() if isinstance(item, (ShapeItem, PolygonItem))]
        if items:
            self._undo_stack.push(FlipCommand(self, items, horizontal))

    def rotate_selected(self, ccw=True):
        items = [item for item in self.scene().selectedItems() if isinstance(item, (ShapeItem, PolygonItem))]
        if items:
            self._undo_stack.push(RotateCommand(self, items, ccw))

    def merge_selected(self):
        if db is None:
            return
        selected = [item for item in self.scene().selectedItems() if isinstance(item, ShapeItem)]
        if len(selected) < 2:
            return
        by_layer = {}
        for item in selected:
            by_layer.setdefault(item.shape_dict.get('layer', 'M1'), []).append(item)
        new_items = []
        for layer, items in by_layer.items():
            region = db.Region()
            for item in items:
                rect = item.mapRectToScene(item.rect())
                x1 = int(round(scene_to_um(rect.left()) * 1000))
                y1 = int(round(-scene_to_um(rect.bottom()) * 1000))
                x2 = int(round(scene_to_um(rect.right()) * 1000))
                y2 = int(round(-scene_to_um(rect.top()) * 1000))
                region.insert(db.Box(x1, y1, x2, y2))
            for poly in region.merged().each():
                bbox = poly.bbox()
                if poly.is_box():
                    shape = {
                        'type': 'rect',
                        'layer': layer,
                        'x': round(bbox.left / 1000.0, 6),
                        'y': round(bbox.bottom / 1000.0, 6),
                        'w': round(bbox.width() / 1000.0, 6),
                        'h': round(bbox.height() / 1000.0, 6),
                        'label': 'merged',
                    }
                    new_items.append(ShapeItem(shape, self._layer_color(layer)))
                else:
                    points = [
                        [round(poly.point_hull(i).x / 1000.0, 6), round(poly.point_hull(i).y / 1000.0, 6)]
                        for i in range(poly.num_points_hull())
                    ]
                    shape = {'type': 'polygon', 'layer': layer, 'points': points, 'label': 'merged'}
                    new_items.append(PolygonItem(shape, self._layer_color(layer)))
        if new_items:
            self._undo_stack.push(MergeCommand(self, selected, new_items))

    def select_all_on_layer(self, layer):
        self.scene().clearSelection()
        for item in self._shapes:
            item.setSelected(self._is_layout_item(item) and item.shape_dict.get('layer') == layer)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            clicked = self.mapToScene(event.pos())
            self._last_click_um = (scene_to_um(clicked.x()), -scene_to_um(clicked.y()))

        if event.button() == Qt.LeftButton and self._mode == 'select':
            self._rubber_origin = event.pos()
            self._rubber_selecting = self._shape_item_at(event.pos()) is None
            if self._rubber_selecting:
                self._rubber_band.setGeometry(QRect(self._rubber_origin, QSize()))
                self._rubber_band.show()
            super().mousePressEvent(event)
            return

        if event.button() == Qt.LeftButton and self._mode == 'ruler':
            pt = self.mapToScene(event.pos())
            if not self._ruler_active:
                self._ruler.start(pt)
                self._ruler_active = True
            else:
                self._ruler.finish()
                self._ruler_active = False
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._mode == 'rectangle':
            self._rect_start = self._snap_scene_point(self.mapToScene(event.pos()))
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._mode == 'polygon':
            scene_pt = self._snap_scene_point(self.mapToScene(event.pos()))
            if self._polygon_points and self._is_near_polygon_start(scene_pt):
                self._finish_polygon()
            else:
                self._polygon_points.append(scene_pt)
                self._update_polygon_preview(scene_pt)
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._mode == 'label':
            scene_pt = self._snap_scene_point(self.mapToScene(event.pos()))
            text, ok = QInputDialog.getText(self, 'Create Label', 'Text:')
            if ok and text:
                x_um, y_um = _scene_point_to_um(scene_pt)
                self.add_shapes([{
                    'type': 'label',
                    'text': text,
                    'label': text,
                    'x': x_um,
                    'y': y_um,
                    'layer': self._active_layer if self._active_layer in LAYERS else 'TEXT',
                }])
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._mode == 'wire' and self._router is not None:
            self._router.layer = self._active_layer
            scene_pt = self._snap_scene_point(self.mapToScene(event.pos()))
            if not self._router.active:
                self._router.start(scene_pt)
            else:
                self._router.add_waypoint(scene_pt)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pt = self.mapToScene(event.pos())
        x_um = scene_to_um(scene_pt.x())
        y_um = -scene_to_um(scene_pt.y())
        if self._last_click_um is None:
            dx_um = 0.0
            dy_um = 0.0
        else:
            dx_um = x_um - self._last_click_um[0]
            dy_um = y_um - self._last_click_um[1]
        self.coord_changed.emit(x_um, y_um, dx_um, dy_um)

        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return


        if self._mode == 'ruler' and self._ruler_active:
            self._ruler.update_preview(self.mapToScene(event.pos()))
            event.accept()
            return

        if self._mode == 'rectangle' and self._rect_start is not None:
            end = self._snap_scene_point(scene_pt)
            self._update_rect_preview(QRectF(self._rect_start, end).normalized())
            event.accept()
            return

        if self._mode == 'polygon' and self._polygon_points:
            self._update_polygon_preview(self._snap_scene_point(scene_pt))
            event.accept()
            return

        if self._mode == 'wire' and self._router is not None and self._router.active:
            self._router.update_preview(self._snap_scene_point(scene_pt))
            event.accept()
            return

        if self._rubber_selecting and self._rubber_origin is not None:
            self._rubber_band.setGeometry(QRect(self._rubber_origin, event.pos()).normalized())

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor if self._mode == 'select' else Qt.CrossCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._mode == 'rectangle' and self._rect_start is not None:
            end = self._snap_scene_point(self.mapToScene(event.pos()))
            rect = QRectF(self._rect_start, end).normalized()
            self._rect_start = None
            self._clear_rect_preview()
            shape = _rect_to_shape(rect, self._active_layer)
            if shape['w'] > 0 and shape['h'] > 0:
                self.add_shapes([shape])
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._mode == 'select':
            super().mouseReleaseEvent(event)
            clicked = self.mapToScene(event.pos())
            self._last_click_um = (scene_to_um(clicked.x()), -scene_to_um(clicked.y()))
            if self._rubber_selecting and self._rubber_band.isVisible():
                band_rect = self._rubber_band.geometry()
                self._rubber_band.hide()
                if band_rect.width() > 3 and band_rect.height() > 3:
                    scene_rect = self.mapToScene(band_rect).boundingRect()
                    hits = set(self.scene().items(scene_rect, Qt.IntersectsItemShape))
                    for item in self._shapes:
                        item.setSelected(item in hits)
            self._rubber_origin = None
            self._rubber_selecting = False
            return

        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        from PyQt5.QtWidgets import QMenu
        item = self._shape_item_at(event.pos())
        menu = QMenu(self)

        if item is not None:
            if not item.isSelected():
                self.scene().clearSelection()
                item.setSelected(True)
            prop_action = menu.addAction('Properties...')
            prop_action.triggered.connect(lambda: self.open_properties(item))
            menu.addSeparator()

        selected = [i for i in self.scene().selectedItems() if self._is_layout_item(i)]
        if selected:
            del_action = menu.addAction(f'Delete ({len(selected)})')
            del_action.triggered.connect(self.delete_selected)
            copy_action = menu.addAction('Copy')
            copy_action.triggered.connect(self.copy_selected)
            menu.addSeparator()

        sel_all = menu.addAction('Select All')
        sel_all.triggered.connect(lambda: [i.setSelected(True) for i in self._shapes])

        fit_action = menu.addAction('Fit View  [F]')
        fit_action.triggered.connect(self.fit_view)

        menu.exec_(event.globalPos())

    def open_properties(self, item):
        from properties_dialog import PropertiesDialog
        old_props = dict(item.shape_dict)
        dlg = PropertiesDialog(old_props, self)
        if dlg.exec_():
            new_props = dlg.get_props()
            if new_props != {k: old_props.get(k) for k in new_props}:
                merged = dict(old_props)
                merged.update(new_props)
                self._undo_stack.push(
                    EditShapePropertiesCommand(self, item, old_props, merged)
                )

    def mouseDoubleClickEvent(self, event):
        if self._mode == 'polygon' and self._polygon_points:
            self._finish_polygon()
            event.accept()
            return
        if self._mode == 'wire' and self._router is not None and self._router.active:
            self.add_shapes(self._router.finish())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self._router is not None:
                self._router.cancel()
            self._rect_start = None
            self._clear_rect_preview()
            self._clear_polygon_preview()
            self._ruler.clear()
            self._ruler_active = False
            self._rubber_band.hide()
            self.set_mode('select')
            event.accept()
            return
        if event.key() == Qt.Key_Delete:
            self.delete_selected()
            event.accept()
            return
        if event.key() == Qt.Key_G:
            self.toggle_grid()
            event.accept()
            return
        if event.matches(QKeySequence.Copy):
            self.copy_selected()
            event.accept()
            return
        if event.matches(QKeySequence.Paste):
            self.paste_clipboard()
            event.accept()
            return
        if event.matches(QKeySequence.Undo):
            self._undo_stack.undo()
            event.accept()
            return
        if event.matches(QKeySequence.Redo):
            self._undo_stack.redo()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta()
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.2 if delta.y() > 0 else 1.0 / 1.2
            self._zoom_pending *= factor
            if not self._zoom_timer.isActive():
                self._zoom_timer.start()
            event.accept()
            return
        if event.modifiers() & Qt.ShiftModifier:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().wheelEvent(event)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if not self._show_grid:
            return
        painter.save()
        self._draw_grid(painter, rect, um_to_scene(self._grid_minor), QColor('#2a2a2a'))
        self._draw_grid(painter, rect, um_to_scene(self._grid_major), QColor('#3a3a3a'))
        painter.restore()

    def _draw_grid(self, painter, rect, spacing, color):
        if spacing <= 0:
            return
        # Skip if lines would be denser than MIN_GRID_PIXEL pixels apart
        pixel_spacing = spacing * self.transform().m11()
        if pixel_spacing < MIN_GRID_PIXEL:
            return
        lines = []
        left = math.floor(rect.left() / spacing) * spacing
        top = math.floor(rect.top() / spacing) * spacing
        x = left
        while x <= rect.right():
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
            x += spacing
        y = top
        while y <= rect.bottom():
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            y += spacing
        painter.setPen(QPen(color, 0))
        painter.drawLines(lines)

    def _on_layer_selected(self, layer):
        self._active_layer = layer
        if self._router is not None:
            self._router.layer = layer

    def _on_layer_visibility_changed(self, layer, visible):
        for item in self._shapes:
            if item.shape_dict.get('layer') == layer:
                item.setVisible(visible)
                if not visible:
                    item.setSelected(False)

    def _layer_color(self, layer):
        if self._layer_panel is not None and hasattr(self._layer_panel, 'layer_color'):
            return self._layer_panel.layer_color(layer)
        return LAYERS.get(layer, (0, 0, '#FFFFFF'))[2]

    def _sync_item_visibility(self, item):
        if self._layer_panel is not None and hasattr(self._layer_panel, 'is_visible'):
            item.setVisible(self._layer_panel.is_visible(item.shape_dict.get('layer', '')))

    def _snap_scene_point(self, point):
        x_um = round(scene_to_um(point.x()) / SNAP) * SNAP
        y_um = round((-scene_to_um(point.y())) / SNAP) * SNAP
        return QPointF(um_to_scene(x_um), -um_to_scene(y_um))

    def _update_rect_preview(self, rect):
        if self._rect_preview is None:
            self._rect_preview = QGraphicsRectItem()
            self._rect_preview.setPen(QPen(QColor('white'), 1.5, Qt.DashLine))
            self._rect_preview.setBrush(QBrush(Qt.NoBrush))
            self._rect_preview.setZValue(90)
            self.scene().addItem(self._rect_preview)
        self._rect_preview.setRect(rect)

    def _clear_rect_preview(self):
        if self._rect_preview is not None:
            if self._rect_preview.scene() is not None:
                self.scene().removeItem(self._rect_preview)
            self._rect_preview = None
        self._ruler = RulerOverlay(self._scene)
        self._ruler_active = False

    def _update_polygon_preview(self, cursor_point=None):
        points = list(self._polygon_points)
        if cursor_point is not None and points:
            points.append(cursor_point)
        if self._polygon_preview is None:
            self._polygon_preview = QGraphicsPolygonItem()
            self._polygon_preview.setPen(QPen(QColor('white'), 1.5, Qt.DashLine))
            fill = QColor('white')
            fill.setAlpha(20)
            self._polygon_preview.setBrush(QBrush(fill))
            self._polygon_preview.setZValue(90)
            self.scene().addItem(self._polygon_preview)
        self._polygon_preview.setPolygon(QPolygonF(points))

    def _clear_polygon_preview(self):
        if self._polygon_preview is not None:
            if self._polygon_preview.scene() is not None:
                self.scene().removeItem(self._polygon_preview)
            self._polygon_preview = None
        self._polygon_points = []

    def _is_near_polygon_start(self, point):
        if not self._polygon_points:
            return False
        return QLineF(point, self._polygon_points[0]).length() <= um_to_scene(SNAP * 2)

    def _finish_polygon(self):
        if len(self._polygon_points) >= 3:
            shape = {
                'type': 'polygon',
                'layer': self._active_layer,
                'points': [_scene_point_to_um(p) for p in self._polygon_points],
                'label': 'polygon',
            }
            self.add_shapes([shape])
        self._clear_polygon_preview()

    def _shape_item_at(self, view_pos):
        item = self.itemAt(view_pos)
        while item is not None and not self._is_layout_item(item):
            item = item.parentItem()
        return item

    def _is_layout_item(self, item):
        return isinstance(item, (ShapeItem, PolygonItem, LabelItem))

    def _items_bbox(self, items):
        rect = QRectF()
        for item in items:
            item_rect = item.mapRectToScene(item.rect()) if isinstance(item, ShapeItem) else item.sceneBoundingRect()
            rect = rect.united(item_rect) if rect.isValid() else QRectF(item_rect)
        return rect

    def _apply_shape_to_item(self, item, shape):
        item.shape_dict = dict(shape)
        color = self._layer_color(item.shape_dict.get('layer', 'M1'))
        item.refresh_visuals(color)
        self._sync_item_visibility(item)


# ── Real-time DRC integration ─────────────────────────────────────────────────

def _patch_canvas_for_realtime_drc(canvas_instance):
    from PyQt5.QtCore import QTimer
    canvas_instance.realtime_drc_enabled = False
    canvas_instance.drc_overlay_items = []

    def toggle_realtime_drc(enabled):
        canvas_instance.realtime_drc_enabled = enabled
        if enabled:
            _run_deferred(None)

    def _run_deferred(changed_bbox):
        QTimer.singleShot(0, lambda: _run_realtime_drc_deferred(changed_bbox))

    def _run_realtime_drc_deferred(changed_bbox):
        try:
            from drc_engine import run_realtime_drc
            shapes = []
            scene = canvas_instance.scene() if hasattr(canvas_instance, 'scene') else None
            if scene:
                shapes = list(scene.items())
            violations = run_realtime_drc(shapes, changed_bbox)
            _update_drc_overlay(violations)
        except Exception:
            pass

    def _update_drc_overlay(violations):
        from PyQt5.QtWidgets import QGraphicsRectItem
        from PyQt5.QtGui import QColor, QBrush, QPen
        scene = canvas_instance.scene() if hasattr(canvas_instance, 'scene') else None
        if scene is None:
            return
        for item in canvas_instance.drc_overlay_items:
            scene.removeItem(item)
        canvas_instance.drc_overlay_items = []
        for v in violations:
            if v.bbox is None:
                continue
            rect_item = QGraphicsRectItem(v.bbox)
            color = QColor(255, 0, 0, 80)
            rect_item.setBrush(QBrush(color))
            rect_item.setPen(QPen(QColor(255, 0, 0), 1))
            rect_item.setZValue(1000)
            rect_item.setToolTip(f"{v.rule}: {v.message}")
            scene.addItem(rect_item)
            canvas_instance.drc_overlay_items.append(rect_item)

    canvas_instance.toggle_realtime_drc = toggle_realtime_drc
    canvas_instance._run_realtime_drc_deferred = _run_realtime_drc_deferred
    canvas_instance._update_drc_overlay = _update_drc_overlay
