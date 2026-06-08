"""GDS/OASIS import and export helpers for the layout editor."""
import sys

try:
    import klayout.db as db
except ImportError:
    print('Install klayout: pip3 install klayout')
    sys.exit(1)

from layer_panel import LAYERS

DBU_PER_UM = 1000


def _build_layout(shapes):
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell('TOP')
    layer_map = {name: layout.layer(gds_layer, gds_dt) for name, (gds_layer, gds_dt, _) in LAYERS.items()}
    for shape in shapes or []:
        layer = shape.get('layer')
        if layer not in layer_map:
            continue
        if shape.get('type') == 'polygon':
            points = [
                db.Point(int(round(float(p[0]) * DBU_PER_UM)), int(round(float(p[1]) * DBU_PER_UM)))
                for p in shape.get('points', [])
            ]
            if len(points) >= 3:
                top.shapes(layer_map[layer]).insert(db.Polygon(points))
            continue
        if shape.get('type') == 'label':
            text = str(shape.get('text', shape.get('label', '')))
            x = int(round(float(shape.get('x', 0.0)) * DBU_PER_UM))
            y = int(round(float(shape.get('y', 0.0)) * DBU_PER_UM))
            if text:
                top.shapes(layer_map[layer]).insert(db.Text(text, db.Trans(x, y)))
            continue
        x1 = int(round(float(shape.get('x', 0.0)) * DBU_PER_UM))
        y1 = int(round(float(shape.get('y', 0.0)) * DBU_PER_UM))
        x2 = int(round((float(shape.get('x', 0.0)) + float(shape.get('w', 0.0))) * DBU_PER_UM))
        y2 = int(round((float(shape.get('y', 0.0)) + float(shape.get('h', 0.0))) * DBU_PER_UM))
        if x2 > x1 and y2 > y1:
            top.shapes(layer_map[layer]).insert(db.Box(x1, y1, x2, y2))
    return layout


def save_gds(path, shapes):
    layout = _build_layout(shapes)
    layout.write(str(path))


def save_oasis(path, shapes):
    layout = _build_layout(shapes)
    layout.write(str(path))


def load_gds(path):
    layout = db.Layout()
    layout.read(str(path))
    top = layout.top_cell()
    if top is None:
        return []
    shapes = []
    for name, (gds_layer, gds_dt, _) in LAYERS.items():
        layer_index = layout.layer(gds_layer, gds_dt)
        it = top.begin_shapes_rec(layer_index)
        while not it.at_end():
            shape = it.shape()
            if shape.is_text():
                text = shape.text.transformed(it.trans())
                shapes.append({
                    'type': 'label',
                    'layer': name,
                    'text': text.string,
                    'label': text.string,
                    'x': round(text.trans.disp.x * layout.dbu, 6),
                    'y': round(text.trans.disp.y * layout.dbu, 6),
                })
                it.next()
                continue
            if shape.is_box():
                bbox = shape.bbox().transformed(it.trans())
            elif shape.is_polygon():
                poly = shape.polygon.transformed(it.trans())
                shapes.append({
                    'type': 'polygon',
                    'layer': name,
                    'points': [
                        [round(poly.point_hull(i).x * layout.dbu, 6), round(poly.point_hull(i).y * layout.dbu, 6)]
                        for i in range(poly.num_points_hull())
                    ],
                    'label': 'imported',
                })
                it.next()
                continue
            else:
                bbox = shape.bbox().transformed(it.trans())
            if bbox.width() > 0 and bbox.height() > 0:
                shapes.append({
                    'type': 'rect',
                    'layer': name,
                    'x': round(bbox.left * layout.dbu, 6),
                    'y': round(bbox.bottom * layout.dbu, 6),
                    'w': round(bbox.width() * layout.dbu, 6),
                    'h': round(bbox.height() * layout.dbu, 6),
                    'label': 'imported',
                })
            it.next()
    return shapes
