class LayoutExtractor:
    def extract(self, canvas):
        result = {}
        if canvas is None:
            return result
        try:
            scene = canvas.scene() if hasattr(canvas, 'scene') else None
            if scene is None:
                return result
            metal_layers = {'M1','M2','M3','M4','M5','M6'}
            via_layers = {'Via1','Via2','Via3','Via4','Via5'}
            metal_shapes = []
            pcell_instances = []
            for item in scene.items():
                layer = getattr(item, 'layer', None)
                if layer in metal_layers:
                    metal_shapes.append(item)
                pcell_data = getattr(item, '_pcell_data', None)
                if pcell_data:
                    pcell_instances.append((item, pcell_data))
            nets = self._assign_nets(metal_shapes)
            for item, data in pcell_instances:
                name = data.get('name', id(item))
                ctype = data.get('type', '')
                entry = {'type': ctype}
                ports = data.get('ports', {})
                item_pos = item.pos() if hasattr(item, 'pos') else None
                for pin_name, rel_pos in ports.items():
                    net = self._find_net_at(rel_pos, item_pos, metal_shapes, nets)
                    entry[pin_name] = net if net else f'unconnected_{name}_{pin_name}'
                result[str(name)] = entry
        except Exception:
            pass
        return result

    def _assign_nets(self, shapes):
        parent = list(range(len(shapes)))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        def union(a, b):
            a, b = find(a), find(b)
            if a != b:
                parent[a] = b
        for i in range(len(shapes)):
            for j in range(i+1, len(shapes)):
                si, sj = shapes[i], shapes[j]
                li = getattr(si, 'layer', None)
                lj = getattr(sj, 'layer', None)
                if li == lj:
                    ri = si.sceneBoundingRect() if hasattr(si,'sceneBoundingRect') else None
                    rj = sj.sceneBoundingRect() if hasattr(sj,'sceneBoundingRect') else None
                    if ri and rj and ri.intersects(rj):
                        union(i, j)
        net_names = {}
        for i, shape in enumerate(shapes):
            root = find(i)
            if root not in net_names:
                net_names[root] = getattr(shape, 'net_name', None) or f'net{root+1}'
        return {i: net_names[find(i)] for i in range(len(shapes))}

    def _find_net_at(self, rel_pos, item_pos, shapes, nets):
        try:
            from PyQt5.QtCore import QPointF
            if item_pos is not None and rel_pos is not None:
                ax = item_pos.x() + rel_pos[0]
                ay = item_pos.y() + rel_pos[1]
            else:
                return None
            for i, shape in enumerate(shapes):
                r = shape.sceneBoundingRect() if hasattr(shape,'sceneBoundingRect') else None
                if r and r.contains(ax, ay):
                    return nets.get(i)
        except Exception:
            pass
        return None
