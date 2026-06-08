"""DRC engine for IHP SG13G2 layout editor using klayout.db."""
import sys
try:
    import klayout.db as db
except ImportError:
    print('Install klayout: pip3 install klayout')
    sys.exit(1)

from layer_panel import LAYERS

LAYER_NUM = {name: data[0] for name, data in LAYERS.items()}


class DrcEngine:
    def __init__(self):
        self.violations = []

    def run(self, shapes):
        """
        shapes: list of dicts {layer, x, y, w, h} in micrometers.
        Returns list of {rule, bbox:(x1,y1,x2,y2), description}.
        """
        self.violations = []
        layout = db.Layout()
        layout.dbu = 0.001  # 1nm resolution
        cell = layout.create_cell('TOP')

        layer_map = {}
        for name, (gds_l, gds_dt, _) in LAYERS.items():
            li = layout.layer(gds_l, gds_dt)
            layer_map[name] = li

        for s in shapes:
            name = s.get('layer', '')
            if name not in layer_map:
                continue
            li = layer_map[name]
            if s.get('type') == 'polygon':
                points = [
                    db.Point(int(round(float(p[0]) * 1000)), int(round(float(p[1]) * 1000)))
                    for p in s.get('points', [])
                ]
                if len(points) >= 3:
                    cell.shapes(li).insert(db.Polygon(points))
                continue
            if 'x' not in s or 'y' not in s or 'w' not in s or 'h' not in s:
                continue
            x = int(round(float(s['x']) * 1000))
            y = int(round(float(s['y']) * 1000))
            w = int(round(float(s['w']) * 1000))
            h = int(round(float(s['h']) * 1000))
            if w > 0 and h > 0:
                cell.shapes(li).insert(db.Box(x, y, x + w, y + h))

        def region(layer_name):
            if layer_name not in layer_map:
                return db.Region()
            return db.Region(cell.begin_shapes_rec(layer_map[layer_name]))

        dbu = layout.dbu
        nwell = region('NWell')
        pactive = region('PActive')
        nactive = region('NActive')
        m1 = region('M1')
        m4 = region('M4')
        gatpoly = region('GatPoly')

        # R1: PActive inside NWell forbidden
        r1_viol = pactive & nwell
        for shape in r1_viol.each():
            bbox = shape.bbox()
            self.violations.append({
                'rule': 'R1',
                'bbox': (bbox.left * dbu, bbox.bottom * dbu,
                         bbox.right * dbu, bbox.top * dbu),
                'description': 'PActive inside NWell (forbidden)'
            })

        # R2: NWell to PActive spacing >= 500nm
        nwell_grown = nwell.sized(500)
        r2_viol = (nwell_grown & pactive)
        r2_clean = nwell & pactive
        for shape in r2_viol.each():
            bbox = shape.bbox()
            self.violations.append({
                'rule': 'R2',
                'bbox': (bbox.left * dbu, bbox.bottom * dbu,
                         bbox.right * dbu, bbox.top * dbu),
                'description': 'NWell-PActive spacing < 500nm'
            })

        # R3: M1 width >= 200nm (in dbu units, 200nm = 200 dbu)
        for shape in m1.each():
            bbox = shape.bbox()
            w = bbox.right - bbox.left
            h = bbox.top - bbox.bottom
            if min(w, h) < 200:
                self.violations.append({
                    'rule': 'R3',
                    'bbox': (bbox.left * dbu, bbox.bottom * dbu,
                             bbox.right * dbu, bbox.top * dbu),
                    'description': f'M1 width {min(w,h)}dbu < 200nm'
                })

        # R4: M1 spacing >= 200nm
        try:
            m1_space = m1.space_check(200)
            for edge_pair in m1_space.each():
                p = edge_pair.bbox()
                self.violations.append({
                    'rule': 'R4',
                    'bbox': (p.left * dbu, p.bottom * dbu, p.right * dbu, p.top * dbu),
                    'description': 'M1 spacing < 200nm'
                })
        except Exception:
            pass

        # R5: M4 width >= 500nm
        for shape in m4.each():
            bbox = shape.bbox()
            w = bbox.right - bbox.left
            h = bbox.top - bbox.bottom
            if min(w, h) < 500:
                self.violations.append({
                    'rule': 'R5',
                    'bbox': (bbox.left * dbu, bbox.bottom * dbu,
                             bbox.right * dbu, bbox.top * dbu),
                    'description': f'M4 width {min(w,h)}dbu < 500nm'
                })

        # R9: GatPoly width >= 130nm
        for shape in gatpoly.each():
            bbox = shape.bbox()
            w = bbox.right - bbox.left
            h = bbox.top - bbox.bottom
            if min(w, h) < 130:
                self.violations.append({
                    'rule': 'R9',
                    'bbox': (bbox.left * dbu, bbox.bottom * dbu,
                             bbox.right * dbu, bbox.top * dbu),
                    'description': f'GatPoly width {min(w,h)}dbu < 130nm'
                })

        # R13: NWell must contain NActive
        for nw_shape in nwell.each():
            nw_region = db.Region()
            nw_region.insert(nw_shape.polygon)
            inside = nw_region & nactive
            if inside.is_empty():
                bbox = nw_shape.bbox()
                self.violations.append({
                    'rule': 'R13',
                    'bbox': (bbox.left * dbu, bbox.bottom * dbu,
                             bbox.right * dbu, bbox.top * dbu),
                    'description': 'NWell has no NActive inside (missing well tap)'
                })

        return self.violations


# ── Real-time DRC additions ──────────────────────────────────────────────────

class DrcViolation:
    def __init__(self, rule, bbox, message, severity="error"):
        self.rule = rule
        self.bbox = bbox
        self.message = message
        self.severity = severity

    def __repr__(self):
        return f"DrcViolation({self.rule}, {self.message})"


def run_realtime_drc(shapes, changed_bbox=None):
    """Fast incremental DRC. Returns list of DrcViolation."""
    violations = []
    if not shapes:
        return violations
    try:
        from PyQt5.QtCore import QRectF
        # Filter shapes to changed region + 2um margin if provided
        if changed_bbox is not None:
            margin = 2.0
            check_rect = changed_bbox.adjusted(-margin, -margin, margin, margin)
            shapes_to_check = [
                s for s in shapes
                if hasattr(s, "sceneBoundingRect") and
                   s.sceneBoundingRect().intersects(check_rect)
            ]
        else:
            shapes_to_check = shapes

        # Group by layer
        by_layer = {}
        for s in shapes_to_check:
            layer = getattr(s, "layer", None)
            if layer:
                by_layer.setdefault(layer, []).append(s)

        # Basic spacing check: shapes on same layer closer than 0.13um
        MIN_SPACING = 0.13
        for layer, layer_shapes in by_layer.items():
            for i in range(len(layer_shapes)):
                for j in range(i + 1, len(layer_shapes)):
                    ri = layer_shapes[i].sceneBoundingRect()
                    rj = layer_shapes[j].sceneBoundingRect()
                    if ri.intersects(rj):
                        continue  # overlapping, skip spacing check
                    dx = max(0, max(rj.left() - ri.right(), ri.left() - rj.right()))
                    dy = max(0, max(rj.top() - ri.bottom(), ri.top() - rj.bottom()))
                    dist = (dx**2 + dy**2) ** 0.5
                    if dist < MIN_SPACING:
                        union = ri.united(rj)
                        violations.append(DrcViolation(
                            rule="R1",
                            bbox=union,
                            message=f"Spacing violation on {layer}: {dist:.3f}um < {MIN_SPACING}um",
                            severity="error"
                        ))

        # Basic width check: shapes narrower than 0.13um
        MIN_WIDTH = 0.13
        for s in shapes_to_check:
            if hasattr(s, "sceneBoundingRect"):
                r = s.sceneBoundingRect()
                layer = getattr(s, "layer", "")
                if r.width() < MIN_WIDTH or r.height() < MIN_WIDTH:
                    violations.append(DrcViolation(
                        rule="R3",
                        bbox=r,
                        message=f"Width violation on {layer}: min dimension {min(r.width(),r.height()):.3f}um < {MIN_WIDTH}um",
                        severity="error"
                    ))
    except Exception:
        pass
    return violations
