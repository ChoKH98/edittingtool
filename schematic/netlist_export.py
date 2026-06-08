import os

from PyQt5.QtCore import QLineF, QPointF
from PyQt5.QtWidgets import QGraphicsTextItem

from schematic.spice_units import normalize_spice_value


MODEL_LIB = "/usr/share/pdk/ihp-sg13g2/libs.tech/ngspice/models/sg13g2.lib"


def _export_value(value):
    text = str(value).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    return normalize_spice_value(text)


def export_netlist(items_or_canvas=None, cellname=None, corner="tt"):
    return NetlistExporter().export(items_or_canvas, cellname or "top_circuit", corner=corner)


class NetlistExporter:
    def export(self, canvas, cellname="top_circuit", corner="tt"):
        cellname = cellname or "top_circuit"
        nets, components = self._extract(canvas)
        ports = self._ports(components, nets)
        lines = ["* Schematic netlist -- exported from layout_editor"]

        has_model_device = any(
            comp.get("type", "") in ("nmos", "pmos", "resistor", "capacitor", "npn")
            for comp in components.values()
        )
        if has_model_device:
            model_include = self._pdk_model_include(corner)
            if model_include:
                lines.append(model_include)
            elif any(comp.get("type", "") in ("nmos", "pmos") for comp in components.values()) and os.path.exists(MODEL_LIB):
                lines.append(f".lib {MODEL_LIB} tt")

        lines.append(f".subckt {cellname} {' '.join(ports)}".rstrip())
        for name, comp in components.items():
            instance = self._instance_line(name, comp, nets)
            if instance:
                lines.append(instance)
        lines.append(f".ends {cellname}")
        return "\n".join(lines)

    def _pdk_model_include(self, corner="tt"):
        try:
            from pdk_manager import PDK
            if PDK.tech is not None:
                return PDK.tech.get_model_include(corner or "tt")
        except Exception:
            pass
        return ""

    def _ports(self, components, nets):
        ports = []
        for name, comp in components.items():
            ctype = comp.get("type", "")
            props = comp.get("props", {})
            if ctype in ("port", "port_in", "port_out"):
                net = nets.get((name, "P")) or props.get("net") or name
                if net and net not in ports:
                    ports.append(str(net))
        return ports

    def _instance_line(self, name, comp, nets):
        ctype = comp.get("type", "")
        props = comp.get("props", {})

        if ctype in ("nmos", "pmos"):
            model = props.get("model") or ("sg13_lv_nmos" if ctype == "nmos" else "sg13_lv_pmos")
            d = self._net(name, "D", nets)
            g = self._net(name, "G", nets)
            s = self._net(name, "S", nets)
            b = self._net(name, "B", nets)
            width = props.get("W", 2.0)
            length = props.get("L", 0.13)
            nf = props.get("nf", props.get("fingers", 1))
            mult = props.get("m", 1)
            if self._is_pdk_subckt_model(model):
                return (
                    f"{self._spice_name(name, 'X')} {d} {g} {s} {b} {model} "
                    f"W={self._mos_dimension(width)} L={self._mos_dimension(length)} nf={nf} m={mult}"
                )
            return f"{self._spice_name(name, 'M')} {d} {g} {s} {b} {model} W={self._mos_dimension(width)} L={self._mos_dimension(length)} m={mult}"

        if ctype == "resistor":
            model = props.get("model", "")
            if self._is_pdk_resistor_model(model):
                return (
                    f"{self._spice_name(name, 'X')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} "
                    f"{self._net(name, 'B', nets)} {model} w={props.get('w', '0.5u')} "
                    f"l={props.get('l', '1u')} m={props.get('m', '1')}"
                )
            value = _export_value(props.get('value', '1k'))
            return f"{self._spice_name(name, 'R')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} {value}"

        if ctype == "capacitor":
            model = props.get("model", "")
            if self._is_pdk_capacitor_model(model):
                return (
                    f"{self._spice_name(name, 'X')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} "
                    f"{model} w={props.get('w', '5u')} l={props.get('l', '5u')} m={props.get('m', '1')}"
                )
            value = _export_value(props.get('value', '1p'))
            return f"{self._spice_name(name, 'C')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} {value}"

        if ctype == "npn":
            model = props.get("model", "npn13G2")
            return (
                f"{self._spice_name(name, 'Q')} {self._net(name, 'C', nets)} {self._net(name, 'B', nets)} "
                f"{self._net(name, 'E', nets)} {self._net(name, 'S', nets)} {model} "
                f"le={props.get('le', '1u')} we={props.get('we', '0.48u')} nb={props.get('nb', '1')}"
            )

        if ctype == "inductor":
            value = _export_value(props.get('value', '1n'))
            return f"{self._spice_name(name, 'L')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} {value}"

        if ctype == "vdc":
            dc_val = props.get('dc', '0')
            return f"{self._spice_name(name, 'V')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} DC {dc_val}"

        if ctype == "vpulse":
            vals = [_export_value(props.get(key, default)) for key, default in (
                ("v1", "0"), ("v2", "1.8"), ("td", "0"), ("tr", "10p"),
                ("tf", "10p"), ("pw", "500p"), ("per", "1n"))]
            return f"{self._spice_name(name, 'V')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} PULSE({' '.join(map(str, vals))})"

        if ctype == "vsin":
            vals = [_export_value(props.get(key, default)) for key, default in (
                ("voff", "0"), ("vamp", "1"), ("freq", "1G"), ("td", "0"), ("theta", "0"))]
            return f"{self._spice_name(name, 'V')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} SIN({' '.join(map(str, vals))})"

        if ctype == "vpwl":
            pwl = " ".join(_export_value(token) for token in str(props.get('pwl', '')).split())
            return f"{self._spice_name(name, 'V')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} PWL({pwl})"

        if ctype == "idc":
            dc_val = _export_value(props.get('dc', '0'))
            return f"{self._spice_name(name, 'I')} {self._net(name, 'P', nets)} {self._net(name, 'N', nets)} DC {dc_val}"

        if ctype in ("vdd", "vss"):
            net = self._net(name, "P", nets, props.get("net", name))
            return f"* {name} is power supply {net}"

        if ctype in ("port", "port_in", "port_out"):
            net = self._net(name, "P", nets, props.get("net", name))
            return f"* .port {net}"

        if ctype == "gnd":
            return f"* {name} is ground {self._net(name, 'P', nets, '0')}"

        return ""

    def _net(self, name, pin, nets, default=None):
        return str(nets.get((name, pin)) or default or "0")

    def _spice_name(self, name, prefix):
        name = str(name or "").strip()
        if not name:
            return prefix + "1"
        return name if name[:1].upper() == prefix else prefix + name

    def _mos_dimension(self, value):
        text = str(value).strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        return text if any(ch.isalpha() for ch in text) else f"{text}u"

    def _is_pdk_subckt_model(self, model):
        text = str(model or "")
        return text.startswith("sg13") or text.startswith("npn13")

    def _is_pdk_resistor_model(self, model):
        return str(model or "") in {
            "rsil", "rhigh", "rppd", "rsil_un", "rline", "rnpoly", "rppoly", "rupolym",
        }

    def _is_pdk_capacitor_model(self, model):
        text = str(model or "")
        return text.startswith("cap_") or text in {"cmim", "cap_cmim", "cap_rfcmim"}

    def _extract(self, canvas):
        nets = {}
        components = {}
        scene = self._scene_from(canvas)
        items = self._items_from(canvas, scene)

        for item in items:
            data = getattr(item, "_schematic_data", None)
            if data is None:
                continue
            name = data.get("name", "")
            ctype = data.get("type", "")
            if not ctype or not name:
                continue
            components[name] = data
            for pin, net in data.get("pin_nets", {}).items():
                if net:
                    nets[(name, pin)] = net

        if scene is not None:
            self._infer_scene_nets(scene, components, nets)

        for name, comp in components.items():
            props = comp.get("props", {})
            if comp.get("type") in ("vdd", "vss", "port_in", "port_out") and props.get("net"):
                nets.setdefault((name, "P"), props.get("net"))
            elif comp.get("type") == "gnd":
                nets.setdefault((name, "P"), "0")

        return nets, components

    def _scene_from(self, canvas):
        if canvas is None:
            return None
        if hasattr(canvas, "scene"):
            return canvas.scene()
        if hasattr(canvas, "_scene"):
            return canvas._scene
        return None

    def _items_from(self, canvas, scene):
        if scene is not None:
            return list(scene.items())
        if canvas is None:
            return []
        if isinstance(canvas, (list, tuple, set)):
            return list(canvas)
        return []

    def _infer_scene_nets(self, scene, components, nets):
        try:
            from schematic.schematic_canvas import ComponentItem, NetLabelItem, PortItem, WireItem, SCALE
            symbols = getattr(scene.parent(), "_symbols", {})
        except Exception:
            return

        wires = [item for item in scene.items() if isinstance(item, WireItem)]
        labels = self._label_items(scene)
        generated = 1

        for item in scene.items():
            if isinstance(item, ComponentItem):
                data = getattr(item, "_schematic_data", {})
                name = data.get("name", "")
                symbol = symbols.get(item.sym_key, {})
                pin_positions = getattr(item, "pin_positions", {})
                if not pin_positions:
                    pin_positions = {
                        pin: QPointF(px * SCALE, py * SCALE)
                        for pin, (px, py) in symbol.get("pins", {}).items()
                    }
                for pin, local_pos in pin_positions.items():
                    key = (name, pin)
                    if nets.get(key):
                        continue
                    pos = item.mapToScene(local_pos)
                    net = self._net_at_point(pos, wires, labels)
                    if not net:
                        net = f"net{generated}"
                        generated += 1
                    nets[key] = net
            elif isinstance(item, PortItem):
                name = item.port_name
                nets.setdefault((name, "P"), self._net_at_point(item.pin_pos, wires, labels) or name)

    def _label_items(self, scene):
        labels = []
        for item in scene.items():
            if hasattr(item, "pin_pos") and hasattr(item, "net_name"):
                labels.append(item)
            elif isinstance(item, QGraphicsTextItem) and item.parentItem() is None:
                if getattr(item, "_schematic_label", False):
                    labels.append(item)
        return labels

    def _net_at_point(self, pos, wires, labels):
        for label in labels:
            label_pos = getattr(label, "pin_pos", label.scenePos())
            if QLineF(pos, label_pos).length() <= 15:
                return self._label_name(label)
            if label.sceneBoundingRect().adjusted(-15, -15, 15, 15).contains(pos):
                return self._label_name(label)
        for wire in wires:
            if getattr(wire, "net_name", "") and self._point_on_wire(pos, wire):
                return wire.net_name
        return ""

    def _label_name(self, label):
        if hasattr(label, "net_name"):
            return label.net_name
        return label.toPlainText()

    def _point_on_wire(self, pos, wire, threshold=3):
        line = wire.line()
        x, y = pos.x(), pos.y()
        x1, y1, x2, y2 = line.x1(), line.y1(), line.x2(), line.y2()
        if abs(y1 - y2) <= 0.001:
            return abs(y - y1) <= threshold and min(x1, x2) - threshold <= x <= max(x1, x2) + threshold
        if abs(x1 - x2) <= 0.001:
            return abs(x - x1) <= threshold and min(y1, y2) - threshold <= y <= max(y1, y2) + threshold
        return False
