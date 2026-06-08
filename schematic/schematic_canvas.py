from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsLineItem, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsItemGroup, QGraphicsRectItem, QGraphicsPolygonItem,
    QGraphicsPathItem, QGraphicsItem,
    QMenu, QInputDialog, QDialog, QFormLayout, QDoubleSpinBox, QSpinBox,
    QLineEdit, QDialogButtonBox, QComboBox, QUndoCommand, QUndoStack,
    QVBoxLayout, QLabel, QTabWidget, QTextEdit, QWidget, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QCheckBox, QMessageBox
)
from PyQt5.QtGui import QPen, QBrush, QColor, QPainter, QFont, QPolygonF, QPainterPath
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QLineF, QRectF

from schematic.net_manager import NetManager
from schematic.spice_units import normalize_spice_value, try_parse_value, format_value

SCALE = 10
GRID = 10


def _snap_value(value):
    return round(value / GRID) * GRID


def snap_point(point):
    return QPointF(_snap_value(point.x()), _snap_value(point.y()))


class AddComponentCommand(QUndoCommand):
    def __init__(self, scene, component):
        super().__init__("Add Component")
        self.scene = scene
        self.component = component

    def redo(self):
        if self.component.scene() is None:
            self.scene.addItem(self.component)

    def undo(self):
        if self.component.scene() is self.scene:
            self.scene.removeItem(self.component)


class AddItemCommand(QUndoCommand):
    def __init__(self, scene, item, text="Add Item"):
        super().__init__(text)
        self.scene = scene
        self.item = item

    def redo(self):
        if self.item.scene() is None:
            self.scene.addItem(self.item)

    def undo(self):
        if self.item.scene() is self.scene:
            self.scene.removeItem(self.item)


class AddWireCommand(QUndoCommand):
    def __init__(self, scene, *wires):
        super().__init__("Add Wire")
        self.scene = scene
        self.wires = [wire for wire in wires if wire is not None]

    def redo(self):
        for wire in self.wires:
            if wire.scene() is None:
                self.scene.addItem(wire)

    def undo(self):
        for wire in self.wires:
            if wire.scene() is self.scene:
                self.scene.removeItem(wire)


class MoveWireEndpointCommand(QUndoCommand):
    def __init__(self, wire, old_line, new_line):
        super().__init__("Move Wire Endpoint")
        self.wire = wire
        self.old_line = QLineF(old_line)
        self.new_line = QLineF(new_line)

    def redo(self):
        self.wire.setLine(self.new_line)

    def undo(self):
        self.wire.setLine(self.old_line)


class DeleteCommand(QUndoCommand):
    def __init__(self, scene, items):
        super().__init__("Delete")
        self.scene = scene
        self.items = list(items)

    def redo(self):
        for item in self.items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)

    def undo(self):
        for item in self.items:
            if item.scene() is None:
                self.scene.addItem(item)


class ComponentItem(QGraphicsItemGroup):
    def __init__(self, sym_key, symbols=None, name="", props=None, parent=None):
        if isinstance(sym_key, (int, float)) and isinstance(symbols, (int, float)):
            x, y, sym_key, props = sym_key, symbols, name, props
            symbols = None
            name = ""
            parent = None
        else:
            x = y = None
        super().__init__(parent)
        self.sym_key = sym_key
        self.comp_name = name or self._default_name(sym_key)
        self.pin_positions = {}
        self._symbols = symbols or self._load_symbols()
        self.props = dict(self._symbols.get(self.sym_key, {}).get("params", {}))
        self.props.update(props or {})
        self._build()
        if x is not None:
            self.setPos(snap_point(QPointF(x, y)))
        self.setFlag(self.ItemIsMovable, True)
        self.setFlag(self.ItemIsSelectable, True)
        self.setFlag(self.ItemSendsGeometryChanges, True)
        self._schematic_data = {
            "name": self.comp_name, "type": sym_key, "props": self.props, "pin_nets": {}
        }

    @staticmethod
    def _load_symbols():
        try:
            from schematic.symbols import SYMBOLS
            return SYMBOLS
        except ImportError:
            return {}

    @staticmethod
    def _default_name(sym_key):
        prefixes = {
            "resistor": "R1", "capacitor": "C1", "inductor": "L1",
            "vdc": "V1", "vpulse": "V1", "vsin": "V1", "vpwl": "V1",
            "idc": "I1", "nmos": "M1", "pmos": "M1", "npn": "Q1",
        }
        return prefixes.get(sym_key, str(sym_key).upper() or "X1")

    def _build(self):
        for child in list(self.childItems()):
            self.removeFromGroup(child)
            child.setParentItem(None)
            if child.scene() is not None:
                child.scene().removeItem(child)
        self.pin_positions = {}
        sym = self._symbols.get(self.sym_key, {})
        if sym:
            self._draw_symbol_definition(sym)
        else:
            draw = getattr(self, f"_draw_{self.sym_key}", None)
            if callable(draw):
                draw()
            else:
                self._draw_legacy()
        self._add_labels()
        if hasattr(self, "_schematic_data"):
            self._schematic_data.update({"name": self.comp_name, "type": self.sym_key, "props": self.props})

    def _symbol_pen(self, width=1.5):
        pen = QPen(QColor("#cdd6f4"), width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def _body_brush(self):
        return QBrush(QColor("#1e1e2e"))

    def _no_brush(self):
        return QBrush(Qt.NoBrush)

    def _add_item(self, item, pen=None, brush=None):
        if pen is not None:
            item.setPen(pen)
        if brush is not None and hasattr(item, "setBrush"):
            item.setBrush(brush)
        self.addToGroup(item)
        return item

    def _line(self, x1, y1, x2, y2, width=1.5):
        return self._add_item(
            QGraphicsLineItem(x1 * SCALE, y1 * SCALE, x2 * SCALE, y2 * SCALE),
            self._symbol_pen(width)
        )

    def _rect(self, x, y, w, h, fill=False, width=1.5):
        return self._add_item(
            QGraphicsRectItem(x * SCALE, y * SCALE, w * SCALE, h * SCALE),
            self._symbol_pen(width),
            self._body_brush() if fill else self._no_brush()
        )

    def _ellipse(self, x, y, w, h, fill=False, width=1.5, color=None):
        pen = self._symbol_pen(width)
        if color:
            pen.setColor(QColor(color))
        return self._add_item(
            QGraphicsEllipseItem(x * SCALE, y * SCALE, w * SCALE, h * SCALE),
            pen,
            QBrush(QColor(color)) if fill and color else (self._body_brush() if fill else self._no_brush())
        )

    def _path(self, path, width=1.5):
        return self._add_item(QGraphicsPathItem(path), self._symbol_pen(width), self._no_brush())

    def _sp(self, x, y):
        return QPointF(x * SCALE, y * SCALE)

    def _pins(self, **pins):
        self.pin_positions = {name: self._sp(x, y) for name, (x, y) in pins.items()}

    def _draw_symbol_definition(self, sym):
        pen = self._symbol_pen()
        for x1, y1, x2, y2 in sym.get("lines", []):
            self._line(x1, y1, x2, y2)
        for cx, cy, r, start_angle, span_angle in sym.get("arcs", []):
            x = cx * SCALE - r * SCALE
            y = cy * SCALE - r * SCALE
            size = 2 * r * SCALE
            if span_angle == 360:
                item = QGraphicsEllipseItem(x, y, size, size)
                item.setPen(pen)
                item.setBrush(QBrush(Qt.NoBrush))
                self.addToGroup(item)
            else:
                path = QPainterPath()
                path.arcMoveTo(x, y, size, size, start_angle)
                path.arcTo(x, y, size, size, start_angle, span_angle)
                arc_item = QGraphicsPathItem(path)
                arc_item.setPen(pen)
                self.addToGroup(arc_item)
        for cx, cy, r in sym.get("circles", []):
            x = cx * SCALE - r * SCALE
            y = cy * SCALE - r * SCALE
            size = 2 * r * SCALE
            item = QGraphicsEllipseItem(x, y, size, size)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.NoBrush))
            self.addToGroup(item)
        self._pins(**sym.get("pins", {}))

    def _draw_resistor(self):
        self._line(-3, 0, -1.5, 0)
        self._line(1.5, 0, 3, 0)
        self._rect(-1.5, -0.6, 3, 1.2, fill=True)
        self._pins(P=(-3, 0), N=(3, 0))

    def _draw_capacitor(self):
        self._line(0, -2.5, 0, -0.3)
        self._line(0, 0.3, 0, 2.5)
        self._line(-1, -0.3, 1, -0.3, 2.5)
        self._line(-1, 0.3, 1, 0.3, 2.5)
        self._pins(P=(0, -2.5), N=(0, 2.5))

    def _draw_inductor(self):
        self._line(-3, 0, -2, 0)
        self._line(2, 0, 3, 0)
        path = QPainterPath(self._sp(-2, 0))
        for i in range(4):
            path.arcTo(QRectF((-2 + i) * SCALE, -0.5 * SCALE, 1 * SCALE, 1 * SCALE), 180, -180)
        self._path(path)
        self._pins(P=(-3, 0), N=(3, 0))

    def _draw_mos(self, pmos=False):
        self._line(-3, 0, -1.5, 0)
        self._line(-1.5, -1.2, -1.5, 1.2, 2.5)
        self._line(-0.5, -1.2, -0.5, 1.2)
        self._line(-0.5, 1.2, 0, 1.2)
        self._line(0, 1.2, 0, 2.5)
        self._line(-0.5, -1.2, 0, -1.2)
        self._line(0, -1.2, 0, -2.5)
        self._line(-0.5, 0, 0.5, 0)
        if pmos:
            self._line(-0.3, 0.2, -0.5, 0)
            self._line(-0.3, -0.2, -0.5, 0)
            self._ellipse(-1.8, -0.15, 0.3, 0.3, fill=True, color="#ffffff")
        else:
            self._line(-0.7, 0.2, -0.5, 0)
            self._line(-0.7, -0.2, -0.5, 0)
        self._pins(G=(-3, 0), D=(0, 2.5), S=(0, -2.5), B=(0.5, 0))

    def _draw_nmos(self):
        self._draw_mos(False)

    def _draw_pmos(self):
        self._draw_mos(True)

    def _draw_source_circle(self):
        self._ellipse(-1.2, -1.2, 2.4, 2.4)
        self._line(0, -2.5, 0, -1.2)
        self._line(0, 1.2, 0, 2.5)
        self._pins(P=(0, -2.5), N=(0, 2.5))

    def _draw_vdc(self):
        self._draw_source_circle()
        self._line(-0.35, 0.5, 0.35, 0.5)
        self._line(0, 0.15, 0, 0.85)
        self._line(-0.35, -0.5, 0.35, -0.5)

    def _draw_vpulse(self):
        self._draw_source_circle()
        path = QPainterPath(self._sp(-0.7, -0.4))
        for x, y in [(-0.7, 0.4), (-0.2, 0.4), (-0.2, -0.4), (0.3, -0.4), (0.3, 0.4), (0.7, 0.4)]:
            path.lineTo(self._sp(x, y))
        self._path(path)

    def _draw_vsin(self):
        self._draw_source_circle()
        path = QPainterPath(self._sp(-0.7, 0))
        path.cubicTo(self._sp(-0.4, -0.6), self._sp(0.4, 0.6), self._sp(0.7, 0))
        self._path(path)

    def _draw_vpwl(self):
        self._draw_source_circle()
        path = QPainterPath(self._sp(-0.6, -0.4))
        for x, y in [(-0.2, 0.4), (0.1, -0.2), (0.6, 0.3)]:
            path.lineTo(self._sp(x, y))
        self._path(path)

    def _draw_idc(self):
        self._draw_source_circle()
        self._line(0, -0.7, 0, 0.4)
        path = QPainterPath(self._sp(-0.3, 0.1))
        path.lineTo(self._sp(0, 0.6))
        path.lineTo(self._sp(0.3, 0.1))
        self._path(path)

    def _draw_vdd(self):
        self._line(0, 0, 0, 1.5)
        self._line(-0.8, 1.5, 0.8, 1.5)
        self._text("VDD", -1.0, 1.55, "#f38ba8", 7, bold=True)
        self._pins(P=(0, 0))

    def _draw_vss(self):
        self._line(0, 0, 0, -1.5)
        self._line(-0.8, -1.5, 0.8, -1.5)
        self._line(-0.5, -1.8, 0.5, -1.8)
        self._line(-0.2, -2.1, 0.2, -2.1)
        self._text("VSS", -1.0, -3.3, "#89b4fa", 7, bold=True)
        self._pins(P=(0, 0))

    def _draw_gnd(self):
        self._line(0, 0, 0, -1.5)
        self._line(-0.8, -1.5, 0.8, -1.5)
        self._line(-0.5, -1.8, 0.5, -1.8)
        self._line(-0.2, -2.1, 0.2, -2.1)
        self._pins(P=(0, 0))

    def _draw_legacy(self):
        sym = self._symbols.get(self.sym_key, {})
        self._draw_symbol_definition(sym)

    def _value_text(self):
        if self.sym_key in ("nmos", "pmos"):
            return f"W={self.props.get('W', '2u')}\nL={self.props.get('L', '0.13u')}"
        if self.sym_key in ("resistor", "capacitor", "inductor"):
            return str(self.props.get("value", ""))
        if self.sym_key == "vdc":
            return str(self.props.get("dc", "1.8"))
        if self.sym_key == "vpulse":
            return f"{self.props.get('v1', '0')}->{self.props.get('v2', '1.8')}"
        if self.sym_key == "vsin":
            return f"{self.props.get('vamp', '1')} {self.props.get('freq', '1G')}"
        if self.sym_key == "vpwl":
            return "PWL"
        if self.sym_key == "idc":
            return str(self.props.get("dc", "1m"))
        return str(self.props.get("net", ""))

    def _text(self, text, x, y, color, size=8, bold=False):
        item = QGraphicsTextItem(str(text))
        item.setDefaultTextColor(QColor(color))
        font = QFont("Monospace", size)
        font.setBold(bold)
        item.setFont(font)
        item.setPos(x * SCALE, y * SCALE)
        self.addToGroup(item)
        return item

    def _add_labels(self):
        sym = self._symbols.get(self.sym_key, {})
        nx, ny = sym.get("name_offset", (0, -3))
        vx, vy = sym.get("value_offset", (0, 2.2))
        self._text(self.comp_name, nx, ny, "#a6e3a1", 8)
        value = self._value_text()
        if value:
            self._text(value, vx, vy, "#fab387", 8)

    def rotate90(self):
        self.setRotation(self.rotation() + 90)

    def mirror_horizontal(self):
        self.setScale(-self.scale() if self.scale() else -1)

    def itemChange(self, change, value):
        if change == self.ItemPositionChange:
            return snap_point(value)
        if change == self.ItemPositionHasChanged and self.scene():
            parent = self.scene().parent()
            if hasattr(parent, "_rebuild_junctions"):
                parent._rebuild_junctions()
        return super().itemChange(change, value)


class ComponentPropertiesDialog(QDialog):
    NUMERIC_VALUE_KEYS = {
        "dc", "tran", "v1", "v2", "td", "tr", "tf", "pw", "per",
        "voff", "vamp", "freq", "value", "ac", "idc",
        "resistance", "capacitance", "inductance",
    }

    TYPE_NAMES = {
        "nmos": "NMOS Transistor", "pmos": "PMOS Transistor",
        "resistor": "Resistor", "capacitor": "Capacitor", "inductor": "Inductor",
        "vdc": "DC Voltage Source", "vpulse": "Pulse Voltage Source",
        "vsin": "Sine Voltage Source", "vpwl": "PWL Voltage Source",
        "idc": "DC Current Source", "vdd": "VDD Supply", "vss": "VSS Supply",
        "gnd": "Ground",
    }

    DESCRIPTIONS = {
        "nmos": "N-channel MOSFET with drain, gate, source, and bulk terminals.",
        "pmos": "P-channel MOSFET with drain, gate, source, and bulk terminals.",
        "resistor": "Two-terminal resistor. Value is emitted directly into SPICE.",
        "capacitor": "Two-terminal capacitor. Model selects ideal or IHP MIM metadata.",
        "inductor": "Two-terminal inductor with optional quality factor metadata.",
        "vdc": "Independent DC voltage source.",
        "vpulse": "Independent transient PULSE voltage source.",
        "vsin": "Independent sinusoidal voltage source.",
        "vpwl": "Independent piecewise-linear voltage source.",
        "idc": "Independent DC current source.",
        "vdd": "Named supply net marker.",
        "vss": "Named supply return marker.",
        "gnd": "Ground net marker.",
    }

    def __init__(self, component, parent=None):
        super().__init__(parent)
        self.component = component
        self.comp_type = component.sym_key
        self.fields = {}
        self.unit_fields = {}
        self.extra_widgets = {}
        try:
            import os
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from pdk_manager import PDK
            self._tech = PDK.tech
        except Exception:
            self._tech = None
        self.setWindowTitle(f"Properties — {self.comp_type} {component.comp_name}")
        self.resize(400, 500)
        self.setStyleSheet("""
            QDialog, QWidget { background: #1e1e2e; color: #cdd6f4; }
            QLineEdit, QComboBox, QSpinBox, QTextEdit, QTableWidget {
                background: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 3px;
            }
            QLabel { color: #cdd6f4; }
            QTabWidget::pane { border: 1px solid #45475a; }
            QTabBar::tab { background: #313244; color: #cdd6f4; padding: 6px 10px; }
            QTabBar::tab:selected { background: #45475a; }
            QPushButton { background: #313244; color: #cdd6f4; border: 1px solid #585b70; padding: 5px 10px; }
        """)

        layout = QVBoxLayout(self)
        header = QLabel(self.TYPE_NAMES.get(self.comp_type, self.comp_type.upper()))
        header_font = QFont("Sans Serif", 14)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        form = QFormLayout()
        self.name_edit = QLineEdit(component.comp_name)
        self.name_edit.textChanged.connect(self._update_preview)
        form.addRow("Instance Name", self.name_edit)
        layout.addLayout(form)

        tabs = QTabWidget()
        self.params_tab = QWidget()
        self.params_layout = QFormLayout(self.params_tab)
        self._build_parameters()
        tabs.addTab(self.params_tab, "Parameters")

        self.spice_preview = QTextEdit()
        self.spice_preview.setReadOnly(True)
        mono = QFont("Monospace", 9)
        self.spice_preview.setFont(mono)
        self.spice_preview.setStyleSheet("background: #11111b; color: #a6e3a1; border: 1px solid #45475a;")
        tabs.addTab(self.spice_preview, "SPICE")

        tabs.addTab(self._build_info_tab(), "Info")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        layout.addWidget(buttons)
        self._update_preview()

    def _build_parameters(self):
        ctype = self.comp_type
        if ctype in ("nmos", "pmos"):
            variant = self._initial_mos_variant()
            constraints = self._mos_constraints(variant)
            if constraints:
                self._mos_desc_label = QLabel(constraints.get("description", ""))
                self._mos_desc_label.setWordWrap(True)
                self.params_layout.addRow("PDK Device", self._mos_desc_label)
                variant_combo = self._add_combo("variant", "HV / LV", variant.upper(), ["LV", "HV"])
            else:
                variant_combo = None
            w_edit = self._add_unit_line("W", "W (Width)", self._constraint_default(constraints, "W_default", "2.0"), ["u", "n", "p"])
            l_edit = self._add_unit_line("L", "L (Length)", self._constraint_default(constraints, "L_default", "0.13"), ["u", "n", "p"])
            self._apply_mos_tooltips(constraints, w_edit, l_edit)
            self._add_spin("fingers", "Fingers", constraints.get("nf_default", 1) if constraints else 1,
                           constraints.get("nf_min", 1) if constraints else 1,
                           constraints.get("nf_max", 64) if constraints else 64)
            models = self._mos_models(constraints, ctype)
            if not models:
                models = ["sg13_lv_nmos", "sg13_hv_nmos"] if ctype == "nmos" else ["sg13_lv_pmos", "sg13_hv_pmos"]
            self._add_combo("model", "Model", models[0], models)
            if variant_combo is not None:
                variant_combo.currentTextChanged.connect(self._on_mos_variant_changed)
            self._add_spin("m", "Multiplier (m)", 1, 1, 64)
            self.total_width = QLabel("")
            self.params_layout.addRow("Total Width", self.total_width)
            self._connect_total_width()
        elif ctype == "resistor":
            self._add_unit_line("value", "Value", "1", ["Ω", "kΩ", "MΩ"])
            models = self._tech.get_resistor_models() if self._tech is not None else ["ideal", "rhigh", "rppd", "rsil"]
            default = self._tech.devices.get("resistor", {}).get("model_default", models[0]) if self._tech is not None and models else "ideal"
            combo = self._add_combo("model", "Model", default, models)
            if self._tech is not None:
                descs = self._tech.devices.get("resistor", {}).get("descriptions", {})
                combo.setToolTip(descs.get(combo.currentText(), "IHP SG13G2 resistor model"))
                combo.currentTextChanged.connect(lambda text: combo.setToolTip(descs.get(text, "IHP SG13G2 resistor model")))
            self._add_line("tc1", "TC1", "0")
            self._add_line("tc2", "TC2", "0")
        elif ctype == "capacitor":
            self._add_unit_line("value", "Value", "1", ["f", "p", "n", "u"])
            models = self._tech.get_capacitor_models() if self._tech is not None else ["ideal", "cmim"]
            default = self._tech.devices.get("capacitor", {}).get("model_default", models[0]) if self._tech is not None and models else "cmim"
            self._add_combo("model", "Model", default, models)
            self._add_line("voltage", "Voltage", "1.8")
        elif ctype == "inductor":
            self._add_unit_line("value", "Value", "1", ["H", "mH", "uH", "nH", "pH"])
            self._add_line("q", "Q", "10")
        elif ctype == "vdc":
            self._add_unit_line("dc", "DC Voltage", "1.8", ["V", "mV"])
            self._add_line("ac", "AC Magnitude (optional)", "")
        elif ctype == "vpulse":
            self._add_line("v1", "V1 (low)", "0")
            self._add_line("v2", "V2 (high)", "1.8")
            for key, label, default in [
                ("td", "TD (delay)", "0"), ("tr", "TR (rise)", "10"),
                ("tf", "TF (fall)", "10"), ("pw", "PW (pulse width)", "500"),
                ("per", "PER (period)", "1"),
            ]:
                self._add_unit_line(key, label, default, ["s", "ms", "us", "ns", "ps"])
        elif ctype == "vsin":
            self._add_unit_line("voff", "VOFF (offset)", "0", ["V", "mV"])
            self._add_unit_line("vamp", "VAMP (amplitude)", "1", ["V", "mV"])
            self._add_unit_line("freq", "FREQ (frequency)", "1", ["Hz", "kHz", "MHz", "GHz"])
            self._add_unit_line("td", "TD", "0", ["s", "ms", "us", "ns", "ps"])
            self._add_line("theta", "THETA (damping)", "0")
        elif ctype == "vpwl":
            self._add_pwl_table()
        elif ctype == "idc":
            self._add_unit_line("dc", "DC", "1", ["A", "mA", "uA", "nA"])
            self._add_line("ac", "AC", "0")
        elif ctype in ("vdd", "vss", "gnd"):
            defaults = {"vdd": ("VDD", "1.8"), "vss": ("VSS", "0"), "gnd": ("0", "0")}
            net, voltage = defaults[ctype]
            self._add_line("net", "Net Name", net)
            self._add_line("voltage", "Voltage (for reference)", voltage)

    def _add_line(self, key, label, default):
        edit = QLineEdit(str(self.component.props.get(key, default)))
        edit.textChanged.connect(self._update_preview)
        if self._is_numeric_value_key(key):
            row, preview = self._value_preview_row(edit)
            edit.textChanged.connect(lambda text, p=preview: self._update_value_preview(p, text))
            self._update_value_preview(preview, edit.text())
            self.params_layout.addRow(label, row)
        else:
            self.params_layout.addRow(label, edit)
        self.fields[key] = edit
        return edit

    def _add_spin(self, key, label, default, minimum, maximum):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(int(self.component.props.get(key, default)))
        spin.valueChanged.connect(self._update_preview)
        self.params_layout.addRow(label, spin)
        self.fields[key] = spin
        return spin

    def _add_combo(self, key, label, default, values):
        combo = QComboBox()
        combo.addItems(values)
        current = str(self.component.props.get(key, default))
        if current in values:
            combo.setCurrentText(current)
        combo.currentTextChanged.connect(self._update_preview)
        self.params_layout.addRow(label, combo)
        self.fields[key] = combo
        return combo

    def _add_unit_line(self, key, label, default, units):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        combo = QComboBox()
        if self._is_numeric_value_key(key):
            combo.addItem("")
        combo.addItems(units)
        current_value = str(self.component.props.get(key, default))
        value, unit = self._split_unit(current_value, units, default)
        if self._is_numeric_value_key(key) and key in self.component.props and self._is_plain_number(current_value):
            unit = ""
        edit.setText(value)
        combo.setCurrentText(unit)
        edit.textChanged.connect(self._update_preview)
        combo.currentTextChanged.connect(self._update_preview)
        layout.addWidget(edit, 1)
        layout.addWidget(combo)
        if self._is_numeric_value_key(key):
            preview = QLabel()
            preview.setStyleSheet("color: #6c7086; font-size: 10px;")
            preview.setMinimumWidth(80)
            layout.addWidget(preview)
            edit.textChanged.connect(lambda _text, e=edit, c=combo, p=preview: self._update_value_preview(p, e.text(), c.currentText()))
            combo.currentTextChanged.connect(lambda _text, e=edit, c=combo, p=preview: self._update_value_preview(p, e.text(), c.currentText()))
            self._update_value_preview(preview, edit.text(), combo.currentText())
        self.params_layout.addRow(label, row)
        self.fields[key] = edit
        self.unit_fields[key] = combo
        return edit

    def _is_numeric_value_key(self, key):
        return key in self.NUMERIC_VALUE_KEYS

    def _value_preview_row(self, edit):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        edit.setMinimumWidth(120)
        preview = QLabel()
        preview.setStyleSheet("color: #6c7086; font-size: 10px;")
        preview.setMinimumWidth(80)
        layout.addWidget(edit, 1)
        layout.addWidget(preview)
        return row, preview

    def _update_value_preview(self, preview, text, unit=''):
        value_text = self._combine_unit_value(str(text).strip(), unit)
        parsed = try_parse_value(value_text, default=None)
        if parsed is None:
            preview.setText("?")
            preview.setStyleSheet("color: #f38ba8; font-size: 10px;")
            return
        unit_text = self._preview_unit_suffix(unit)
        preview.setText(f"= {parsed:.4g}{unit_text}")
        preview.setStyleSheet("color: #a6e3a1; font-size: 10px;")

    def _preview_unit_suffix(self, unit):
        text = str(unit or "")
        if not text:
            return ""
        if "V" in text:
            return " V"
        if "A" in text:
            return " A"
        if "Hz" in text:
            return " Hz"
        if "s" in text:
            return " s"
        if "H" in text:
            return " H"
        if "F" in text:
            return " F"
        if "Ω" in text or "Ohm" in text:
            return " Ohm"
        return ""

    def _combine_unit_value(self, value, unit):
        value = str(value or "").strip()
        unit = str(unit or "")
        if value and unit and not self._has_value_suffix(value):
            return f"{value}{unit}"
        return value

    def _has_value_suffix(self, value):
        text = str(value or "").strip()
        if self._is_plain_number(text):
            return False
        return any(ch.isalpha() or ch in "Ω°" for ch in text)

    def _is_plain_number(self, value):
        try:
            float(str(value).strip())
            return True
        except ValueError:
            return False

    def _build_info_tab(self):
        page = QWidget()
        layout = QFormLayout(page)
        desc = QLabel(self.DESCRIPTIONS.get(self.comp_type, "Schematic component instance."))
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addRow("Component", desc)
        if self._tech is not None:
            params = self._tech.tech_params
            version = ".".join(str(params.get(key, "")) for key in ("majorVersion", "minorVersion", "bugfixVersion"))
            version = version.strip(".") or params.get("relName", "")
            pdk_text = params.get("techName") or "None loaded"
            detail = f"{pdk_text}"
            if version:
                detail += f" {version}"
            info = QLabel(detail)
            info.setToolTip(self._tech.model_lib_path or "")
            layout.addRow("PDK", info)
            model_lib = QLabel(self._tech.model_lib_path or "-")
            model_lib.setWordWrap(True)
            layout.addRow("Model Lib", model_lib)
        else:
            layout.addRow("PDK", QLabel("None loaded"))
        return page

    def _initial_mos_variant(self):
        model = str(self.component.props.get("model", "")).lower()
        return "hv" if "hv" in model else "lv"

    def _mos_constraints(self, variant):
        if self._tech is None:
            return {}
        return self._tech.devices.get(f"{self.comp_type}_{variant}", {}) or self._tech.get_mos_constraints(variant)

    def _mos_models(self, constraints, ctype):
        key = "models_n" if ctype == "nmos" else "models_p"
        return list(constraints.get(key, [])) if constraints else []

    def _constraint_default(self, constraints, key, fallback):
        value = str(constraints.get(key, fallback)) if constraints else str(fallback)
        return value[:-1] if value.endswith("u") else value

    def _apply_mos_tooltips(self, constraints, w_edit=None, l_edit=None):
        if not constraints:
            return
        w_widget = w_edit or self.fields.get("W")
        l_widget = l_edit or self.fields.get("L")
        if w_widget is not None:
            w_widget.setToolTip(f"Min: {constraints.get('W_min', '-')}, Max: {constraints.get('W_max', '-')}")
        if l_widget is not None:
            l_widget.setToolTip(f"Min: {constraints.get('L_min', '-')}, Max: {constraints.get('L_max', '-')}")

    def _on_mos_variant_changed(self, text):
        variant = text.lower()
        constraints = self._mos_constraints(variant)
        models = self._mos_models(constraints, self.comp_type)
        model_combo = self.fields.get("model")
        if isinstance(model_combo, QComboBox) and models:
            current = model_combo.currentText()
            model_combo.blockSignals(True)
            model_combo.clear()
            model_combo.addItems(models)
            model_combo.setCurrentText(current if current in models else models[0])
            model_combo.blockSignals(False)
        if hasattr(self, "_mos_desc_label"):
            self._mos_desc_label.setText(constraints.get("description", ""))
        self._apply_mos_tooltips(constraints)
        self._update_preview()

    def _add_pwl_table(self):
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Time", "Voltage"])
        values = str(self.component.props.get("pwl", "0 0 1n 1.8")).split()
        pairs = list(zip(values[0::2], values[1::2])) or [("0", "0"), ("1n", "1.8")]
        for time, voltage in pairs:
            self._append_pwl_row(time, voltage)
        self.table.itemChanged.connect(self._update_preview)
        self.params_layout.addRow("PWL Table", self.table)
        row = QWidget()
        buttons = QHBoxLayout(row)
        buttons.setContentsMargins(0, 0, 0, 0)
        add_btn = QPushButton("Add Row")
        remove_btn = QPushButton("Remove Row")
        add_btn.clicked.connect(lambda: self._append_pwl_row("0", "0"))
        add_btn.clicked.connect(self._update_preview)
        remove_btn.clicked.connect(self._remove_pwl_row)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        self.params_layout.addRow("", row)
        repeat = QCheckBox("Repeat")
        repeat.setChecked(str(self.component.props.get("repeat", "")).lower() in ("1", "true", "yes"))
        repeat.stateChanged.connect(self._update_preview)
        self.fields["repeat"] = repeat
        self.params_layout.addRow("", repeat)

    def _append_pwl_row(self, time, voltage):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(time)))
        self.table.setItem(row, 1, QTableWidgetItem(str(voltage)))

    def _remove_pwl_row(self):
        row = self.table.currentRow()
        if row < 0:
            row = self.table.rowCount() - 1
        if row >= 0:
            self.table.removeRow(row)
        self._update_preview()

    def _connect_total_width(self):
        for key in ("W", "fingers", "m"):
            widget = self.fields.get(key)
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._update_total_width)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._update_total_width)
        self._update_total_width()

    def _update_total_width(self):
        try:
            width = float(self.fields["W"].text())
            fingers = int(self.fields["fingers"].value())
            mult = int(self.fields["m"].value())
            unit = self.unit_fields["W"].currentText()
            self.total_width.setText(f"{width * fingers * mult:g}{unit}")
        except (KeyError, ValueError):
            self.total_width.setText("-")

    def _split_unit(self, value, units, default):
        text = str(value).strip()
        ordered = sorted(units, key=len, reverse=True)
        for unit in ordered:
            if text.endswith(unit):
                return text[:-len(unit)].strip() or str(default), unit
        defaults = {"Ω": "kΩ", "f": "p", "H": "nH", "V": "V", "A": "mA", "s": "ns", "Hz": "GHz"}
        return text or str(default), defaults.get(units[0], units[0])

    def _base_value(self, key, default):
        value, _unit = self._split_unit(str(self.component.props.get(key, default)), ["V", "mV"], default)
        return value

    def _collect_props(self):
        props = dict(self.component.props)
        for key, widget in self.fields.items():
            if key == "repeat":
                props[key] = "true" if widget.isChecked() else "false"
            elif isinstance(widget, QSpinBox):
                props[key] = widget.value()
            elif isinstance(widget, QComboBox):
                props[key] = widget.currentText()
            else:
                value = widget.text().strip()
                if key in self.unit_fields:
                    value = self._combine_unit_value(value, self.unit_fields[key].currentText())
                if self._is_numeric_value_key(key) and value:
                    value = normalize_spice_value(value)
                props[key] = value
        if self.comp_type == "vpwl":
            vals = []
            for row in range(self.table.rowCount()):
                time_item = self.table.item(row, 0)
                volt_item = self.table.item(row, 1)
                vals.extend([
                    time_item.text().strip() if time_item else "0",
                    volt_item.text().strip() if volt_item else "0",
                ])
            props["pwl"] = " ".join(vals)
        return props

    def _spice_line(self, props):
        name = self.name_edit.text().strip() or self.component.comp_name
        ctype = self.comp_type
        if ctype in ("nmos", "pmos"):
            model = props.get("model", "sg13_lv_nmos" if ctype == "nmos" else "sg13_lv_pmos")
            return f"{name} drain gate source bulk {model} W={props.get('W', '2u')} L={props.get('L', '0.13u')} nf={props.get('fingers', 1)} m={props.get('m', 1)}"
        if ctype == "resistor":
            return f"{name} n1 n2 {props.get('value', '1kΩ').replace('Ω', '')}"
        if ctype == "capacitor":
            return f"{name} n1 n2 {props.get('value', '1p')}"
        if ctype == "inductor":
            return f"{name} n1 n2 {props.get('value', '1nH')}"
        if ctype == "vdc":
            spice_name = name if name[:1].upper() == "V" else f"V{name}"
            return f"{spice_name} n+ n- DC {props.get('dc', '1.8')}"
        if ctype == "vpulse":
            vals = [props.get(k, d) for k, d in (
                ("v1", "0"), ("v2", "1.8"), ("td", "0ns"), ("tr", "10ps"),
                ("tf", "10ps"), ("pw", "500ps"), ("per", "1ns"))]
            return f"{name} p n PULSE({' '.join(map(str, vals))})"
        if ctype == "vsin":
            vals = [props.get(k, d) for k, d in (
                ("voff", "0V"), ("vamp", "1V"), ("freq", "1GHz"), ("td", "0ns"), ("theta", "0"))]
            return f"{name} p n SIN({' '.join(map(str, vals))})"
        if ctype == "vpwl":
            return f"{name} p n PWL({props.get('pwl', '0 0 1n 1.8')})"
        if ctype == "idc":
            return f"{name} p n DC {props.get('dc', '1mA')}"
        if ctype in ("vdd", "vss", "gnd"):
            return f"* {name} net={props.get('net', '0')} voltage={props.get('voltage', '0')}"
        return f"* {name}"

    def _update_preview(self):
        if hasattr(self, "total_width"):
            self._update_total_width()
        if hasattr(self, "spice_preview"):
            self.spice_preview.setPlainText(self._spice_line(self._collect_props()))

    def apply(self):
        self.component.comp_name = self.name_edit.text().strip() or self.component.comp_name
        self.component.props.clear()
        self.component.props.update(self._collect_props())
        self.component._build()

    def accept(self):
        self.apply()
        super().accept()


class WireItem(QGraphicsLineItem):
    def __init__(self, x1, y1, x2, y2, net_name=""):
        super().__init__(x1, y1, x2, y2)
        self.net_name = net_name or ""
        self._net_label = QGraphicsTextItem(self)
        self._net_label.setDefaultTextColor(QColor("#a6e3a1"))
        self._net_label.setFont(QFont("Monospace", 8))
        self._net_label.setZValue(11)
        self.setPen(QPen(QColor("#00FF88"), 1.5))
        self.setFlag(self.ItemIsSelectable, True)
        self.setFlag(self.ItemSendsGeometryChanges, True)
        self._sync_net_label()

    def setLine(self, *args):
        super().setLine(*args)
        if hasattr(self, "_net_label"):
            self._sync_net_label()

    def set_net_name(self, name):
        self.net_name = name or ""
        self._sync_net_label()

    def _sync_net_label(self):
        self._net_label.setPlainText(self.net_name)
        self._net_label.setVisible(bool(self.net_name))
        line = self.line()
        mid = QPointF((line.x1() + line.x2()) / 2, (line.y1() + line.y2()) / 2)
        self._net_label.setPos(mid + QPointF(3, -14))

    def itemChange(self, change, value):
        if change == self.ItemPositionHasChanged and self.scene():
            self._sync_net_label()
            parent = self.scene().parent()
            if hasattr(parent, "_rebuild_junctions"):
                parent._rebuild_junctions()
        return super().itemChange(change, value)


class NetLabelItem(QGraphicsItemGroup):
    def __init__(self, net_name, pos=QPointF(0, 0), parent=None):
        super().__init__(parent)
        self.net_name = net_name
        self._schematic_label = True
        self._build()
        self.setPos(snap_point(pos))
        self.setFlag(self.ItemIsMovable, True)
        self.setFlag(self.ItemIsSelectable, True)
        self.setFlag(self.ItemSendsGeometryChanges, True)

    def _build(self):
        text_name = self.net_name[2:] if self.net_name.startswith("N_") else self.net_name
        self._text = QGraphicsTextItem(text_name)
        font = QFont("Monospace", 9)
        font.setBold(True)
        self._text.setFont(font)
        self._text.setDefaultTextColor(QColor("#a6e3a1"))
        self._text.setPos(2, -18)
        self.addToGroup(self._text)

        pen = QPen(QColor("#a6e3a1"), 1.2)
        self._line = QGraphicsLineItem(-10, 0, 0, 0)
        self._line.setPen(pen)
        self.addToGroup(self._line)

        diamond = QPolygonF([
            QPointF(-14, 0), QPointF(-10, -4), QPointF(-6, 0), QPointF(-10, 4)
        ])
        self._diamond = QGraphicsPolygonItem(diamond)
        self._diamond.setPen(pen)
        self._diamond.setBrush(QBrush(QColor("#a6e3a1")))
        self.addToGroup(self._diamond)

        if self.net_name.startswith("N_"):
            self._overline = QGraphicsLineItem(2, -18, max(24, self._text.boundingRect().width()), -18)
            self._overline.setPen(pen)
            self.addToGroup(self._overline)

    @property
    def pin_pos(self):
        return self.mapToScene(QPointF(-10, 0))

    def to_dict(self):
        return {"text": self.net_name, "x": self.pos().x(), "y": self.pos().y(), "kind": "netlabel"}

    @classmethod
    def from_dict(cls, data):
        return cls(data.get("text", data.get("net_name", "")), QPointF(data.get("x", 0), data.get("y", 0)))

    def itemChange(self, change, value):
        if change == self.ItemPositionChange:
            return snap_point(value)
        if change == self.ItemPositionHasChanged and self.scene():
            parent = self.scene().parent()
            if hasattr(parent, "_rebuild_junctions"):
                parent._rebuild_junctions()
        return super().itemChange(change, value)


class PortItem(QGraphicsItemGroup):
    COLORS = {"IN": "#89b4fa", "OUT": "#f38ba8", "INOUT": "#fab387"}

    def __init__(self, name, direction="INOUT", pos=QPointF(0, 0), parent=None):
        super().__init__(parent)
        self.port_name = name
        self.direction = direction if direction in self.COLORS else "INOUT"
        self.props = {"name": name, "direction": self.direction, "net": name}
        self._schematic_data = {
            "name": name, "type": "port", "props": self.props, "pin_nets": {"P": name}
        }
        self._build()
        self.setPos(snap_point(pos))
        self.setFlag(self.ItemIsMovable, True)
        self.setFlag(self.ItemIsSelectable, True)
        self.setFlag(self.ItemSendsGeometryChanges, True)

    def _build(self):
        color = QColor(self.COLORS[self.direction])
        self._rect = QGraphicsRectItem(0, -10, 40, 20)
        self._rect.setPen(QPen(color, 1.5))
        self._rect.setBrush(QBrush(QColor("#1e1e2e")))
        self.addToGroup(self._rect)

        arrow_pen = QPen(color, 1.5)
        if self.direction in ("IN", "INOUT"):
            for line in (QGraphicsLineItem(-10, 0, 0, 0),
                         QGraphicsLineItem(-5, -4, 0, 0),
                         QGraphicsLineItem(-5, 4, 0, 0)):
                line.setPen(arrow_pen)
                self.addToGroup(line)
        if self.direction in ("OUT", "INOUT"):
            for line in (QGraphicsLineItem(50, 0, 40, 0),
                         QGraphicsLineItem(45, -4, 40, 0),
                         QGraphicsLineItem(45, 4, 40, 0)):
                line.setPen(arrow_pen)
                self.addToGroup(line)

        self._text = QGraphicsTextItem(self.port_name)
        self._text.setDefaultTextColor(QColor("#ffffff"))
        self._text.setFont(QFont("Monospace", 7))
        self._text.setTextWidth(38)
        self._text.setPos(2, -10)
        self.addToGroup(self._text)

    @property
    def pin_pos(self):
        if self.direction == "OUT":
            return self.mapToScene(QPointF(50, 0))
        return self.mapToScene(QPointF(-10, 0))

    def to_dict(self):
        return {
            "name": self.port_name, "direction": self.direction,
            "x": self.pos().x(), "y": self.pos().y()
        }

    @classmethod
    def from_dict(cls, data):
        return cls(data.get("name", "P"), data.get("direction", "INOUT"),
                   QPointF(data.get("x", 0), data.get("y", 0)))

    def itemChange(self, change, value):
        if change == self.ItemPositionChange:
            return snap_point(value)
        if change == self.ItemPositionHasChanged and self.scene():
            parent = self.scene().parent()
            if hasattr(parent, "_rebuild_junctions"):
                parent._rebuild_junctions()
        return super().itemChange(change, value)


class BlockItem(QGraphicsItemGroup):
    def __init__(self, name, pins, rect=QRectF(0, 0, 120, 80), pos=QPointF(0, 0), parent=None):
        super().__init__(parent)
        self.props = {"name": name, "cell": name, "pins": ",".join(pins)}
        self.block_name = name
        self.pin_names = [pin.strip() for pin in pins if pin.strip()]
        self.local_rect = QRectF(rect)
        self.pins = {}
        self._pin_stubs = []
        self._build()
        self.setPos(snap_point(pos))
        self.setFlag(self.ItemIsMovable, True)
        self.setFlag(self.ItemIsSelectable, True)
        self.setFlag(self.ItemSendsGeometryChanges, True)

    def _build(self):
        self._rect = QGraphicsRectItem(self.local_rect)
        self._rect.setPen(QPen(QColor("#cdd6f4"), 1.5))
        self._rect.setBrush(QBrush(QColor("#1e1e2e")))
        self.addToGroup(self._rect)

        self._label = QGraphicsTextItem(self.block_name)
        self._label.setDefaultTextColor(QColor("#cdd6f4"))
        font = QFont("Monospace", 8)
        font.setBold(True)
        self._label.setFont(font)
        label_rect = self._label.boundingRect()
        self._label.setPos(
            self.local_rect.center().x() - label_rect.width() / 2,
            self.local_rect.center().y() - label_rect.height() / 2
        )
        self.addToGroup(self._label)

        left_y = self.local_rect.top() + 16
        right_y = self.local_rect.top() + 16
        top_x = self.local_rect.left() + 24
        bottom_x = self.local_rect.left() + 24
        for pin in self.pin_names:
            lname = pin.lower()
            if lname in ("vdd", "vcc", "vss", "gnd", "vss!"):
                if lname in ("vdd", "vcc"):
                    start = QPointF(top_x, self.local_rect.top())
                    end = QPointF(top_x, self.local_rect.top() - 10)
                    text_pos = QPointF(top_x + 3, self.local_rect.top() + 2)
                    top_x += 28
                else:
                    start = QPointF(bottom_x, self.local_rect.bottom())
                    end = QPointF(bottom_x, self.local_rect.bottom() + 10)
                    text_pos = QPointF(bottom_x + 3, self.local_rect.bottom() - 16)
                    bottom_x += 28
            elif lname.startswith("out") or lname in ("y", "q"):
                start = QPointF(self.local_rect.right(), right_y)
                end = QPointF(self.local_rect.right() + 10, right_y)
                text_pos = QPointF(self.local_rect.right() - 30, right_y - 12)
                right_y += 18
            else:
                start = QPointF(self.local_rect.left(), left_y)
                end = QPointF(self.local_rect.left() - 10, left_y)
                text_pos = QPointF(self.local_rect.left() + 3, left_y - 12)
                left_y += 18
            line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
            line.setPen(QPen(QColor("#cdd6f4"), 1.2))
            txt = QGraphicsTextItem(pin)
            txt.setDefaultTextColor(QColor("#cdd6f4"))
            txt.setFont(QFont("Monospace", 6))
            txt.setPos(text_pos)
            self.addToGroup(line)
            self.addToGroup(txt)
            self._pin_stubs.append((line, txt))
            self.pins[pin] = end

    def scene_pin_positions(self):
        return {name: self.mapToScene(pos) for name, pos in self.pins.items()}

    def to_dict(self):
        return {
            "name": self.block_name,
            "pins": ",".join(self.pin_names),
            "x": self.pos().x(), "y": self.pos().y(),
            "w": self.local_rect.width(), "h": self.local_rect.height()
        }

    @classmethod
    def from_dict(cls, data):
        pins = [pin.strip() for pin in data.get("pins", "").split(",") if pin.strip()]
        rect = QRectF(0, 0, max(40, data.get("w", 120)), max(30, data.get("h", 80)))
        return cls(data.get("name", "X1"), pins, rect, QPointF(data.get("x", 0), data.get("y", 0)))

    def itemChange(self, change, value):
        if change == self.ItemPositionChange:
            return snap_point(value)
        if change == self.ItemPositionHasChanged and self.scene():
            parent = self.scene().parent()
            if hasattr(parent, "_rebuild_junctions"):
                parent._rebuild_junctions()
        return super().itemChange(change, value)


class SchematicCanvas(QGraphicsView):
    net_highlight_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QBrush(QColor("#2b2b2b")))
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self._mode = "select"
        self._wire_start = None
        self._wire_h_first = True
        self._wire_preview_items = []
        self._pin_indicator = None
        self._block_start = None
        self._block_preview = None
        self._pending_instance = None
        self._preview_item = None
        self._wire_drag_item = None
        self._wire_drag_end = None
        self._wire_drag_fixed = None
        self._wire_drag_old_line = None
        self._highlighted_nets = set()
        self._highlight_items = []
        self._junction_items = []
        self._net_manager = NetManager()
        self._snap_to_grid = True
        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._on_undo_index_changed)
        self._symbols = {}
        try:
            from schematic.symbols import SYMBOLS
            self._symbols = SYMBOLS
        except ImportError:
            pass

    def start_mode(self, mode):
        self._mode = "netlabel" if mode == "label" else mode
        self._wire_start = None
        self._block_start = None
        if mode != "instance":
            self._pending_instance = None
            self._clear_instance_preview()
        self._clear_wire_drag()
        self._clear_wire_preview()
        self._clear_pin_indicator()
        self._clear_block_preview()
        if self._mode == "select":
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        self._status(f"Mode: {self._mode}")

    def set_mode(self, mode):
        self.start_mode(mode)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_Escape:
            self._scene.clearSelection()
            self._cancel_mode()
        elif mods == Qt.ControlModifier and key == Qt.Key_A:
            for item in self._scene.items():
                if item.flags() & item.ItemIsSelectable:
                    item.setSelected(True)
        elif mods == Qt.ControlModifier and key == Qt.Key_Z:
            self._undo()
        elif mods == Qt.ControlModifier and key == Qt.Key_Y:
            self._redo()
        elif key == Qt.Key_U and mods & Qt.ShiftModifier:
            self._redo()
        elif key == Qt.Key_U:
            self._undo()
        elif key == Qt.Key_I:
            self._add_instance_dialog()
        elif key == Qt.Key_W:
            self.start_mode("wire")
        elif key == Qt.Key_L:
            self.start_mode("netlabel")
        elif key == Qt.Key_P:
            self.start_mode("port")
        elif key == Qt.Key_B:
            self.start_mode("block")
        elif key == Qt.Key_Q or key == Qt.Key_F4:
            self._edit_selected_properties()
        elif key == Qt.Key_E:
            self._status("Descend: Not implemented")
        elif key == Qt.Key_Delete:
            self._delete_selected()
        elif key == Qt.Key_F:
            self.fit_all()
        elif key == Qt.Key_Z and mods & Qt.ShiftModifier:
            self.zoom_at_viewport_pos(self.viewport().rect().center(), 1 / 1.2)
        elif key == Qt.Key_Z:
            self.zoom_at_viewport_pos(self.viewport().rect().center(), 1.2)
        elif key == Qt.Key_C:
            self.copy_selected()
        elif key == Qt.Key_M and mods & Qt.ShiftModifier:
            self.mirror_selected()
        elif key == Qt.Key_M:
            self._status("Move: drag selected objects")
        elif key == Qt.Key_R:
            self.rotate_selected()
        elif key == Qt.Key_G:
            self._snap_to_grid = not self._snap_to_grid
            self._status(f"Snap grid: {'on' if self._snap_to_grid else 'off'}")
        elif key == Qt.Key_F5:
            self._call_parent("_open_ade")
        elif key == Qt.Key_X and mods & Qt.ShiftModifier:
            self._call_parent("_check_and_save")
        elif mods == Qt.ControlModifier and key == Qt.Key_S:
            self._call_parent("_save")
        elif mods == Qt.ControlModifier and key == Qt.Key_O:
            self._call_parent("_load")
        elif mods == Qt.ControlModifier and key == Qt.Key_N:
            self._call_parent("_new")
        elif mods == (Qt.ControlModifier | Qt.ShiftModifier) and key == Qt.Key_A:
            self._call_parent("_open_ade")
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        pos = self._snap(self.mapToScene(event.pos()))
        if self._mode == "wire":
            pos = self._get_nearest_connection(pos)
            if self._wire_start is None:
                self._wire_start = pos
                self._update_wire_preview(pos)
            else:
                self._finish_wire(pos)
                self._wire_start = pos
                self._update_wire_preview(pos)
        elif self._mode == "netlabel":
            text, ok = QInputDialog.getText(self, "Net Label", "Net name:")
            if ok and text:
                self._add_net_label(pos, text)
        elif self._mode == "port":
            self._add_port_dialog(pos)
        elif self._mode == "block":
            self._block_start = pos
            self._update_block_preview(pos)
        elif self._mode == "instance":
            self._place_pending_instance(pos)
        else:
            clicked_items = self._scene.items(self.mapToScene(event.pos())) if self._mode == "select" else []
            if event.button() == Qt.LeftButton and self._mode == "select":
                endpoint = self._find_wire_endpoint(pos, tol=8.0)
                if endpoint is not None:
                    wire, drag_end, fixed_point = endpoint
                    self._wire_drag_item = wire
                    self._wire_drag_end = drag_end
                    self._wire_drag_fixed = QPointF(fixed_point)
                    self._wire_drag_old_line = QLineF(wire.line())
                    self._mode = "_wire_drag"
                    self.setDragMode(QGraphicsView.NoDrag)
                    self.setCursor(Qt.CrossCursor)
                    event.accept()
                    return
            super().mousePressEvent(event)
            if event.button() == Qt.LeftButton and self._mode == "select":
                for item in clicked_items:
                    net = self.get_net_for_item(item)
                    if net:
                        first_net = net.split(", ", 1)[0]
                        self._status(f"Net: {net}  ({len(self._net_manager.get_pins_on_net(first_net))} connections)")
                        self._highlight_net(first_net)
                        break

    def mouseMoveEvent(self, event):
        pos = self._snap(self.mapToScene(event.pos()))
        if self._mode == "wire":
            snapped_pos = self._get_nearest_connection(pos)
            self._update_pin_indicator(pos)
            self._update_wire_preview(snapped_pos)
        elif self._mode == "instance" and self._preview_item is not None:
            self._preview_item.setPos(pos)
        elif self._mode == "block" and self._block_start is not None:
            self._update_block_preview(pos)
        elif self._mode == "_wire_drag" and self._wire_drag_item is not None:
            self._set_dragged_wire_endpoint(pos)
            event.accept()
            return
        elif self._mode == "select":
            self.setCursor(Qt.SizeAllCursor if self._find_wire_endpoint(pos, tol=8.0) is not None else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mode == "_wire_drag" and self._wire_drag_item is not None:
            final_pos = self._snap(self.mapToScene(event.pos()))
            pin_pos = self._find_nearest_pin(final_pos, tol=12.0)
            wire_pos = self._find_nearest_wire_point(final_pos, tol=12.0)
            if pin_pos is not None:
                final_pos = pin_pos
            elif wire_pos is not None:
                final_pos = wire_pos

            old_line = QLineF(self._wire_drag_old_line)
            self._set_dragged_wire_endpoint(final_pos)
            new_line = QLineF(self._wire_drag_item.line())
            if not self._same_line(old_line, new_line):
                self.undo_stack.push(MoveWireEndpointCommand(self._wire_drag_item, old_line, new_line))

            self._clear_wire_drag()
            self._mode = "select"
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.setCursor(Qt.ArrowCursor)
            self._rebuild_junctions()
            self._scene.update()
            self.viewport().update()
            event.accept()
            return
        if self._mode == "block" and self._block_start is not None:
            end = self._snap(self.mapToScene(event.pos()))
            rect = QRectF(self._block_start, end).normalized()
            if rect.width() < 40 or rect.height() < 30:
                rect = QRectF(self._block_start, self._block_start + QPointF(120, 80)).normalized()
            self._clear_block_preview()
            self._add_block_dialog(rect.topLeft(), QRectF(0, 0, rect.width(), rect.height()))
            self._block_start = None
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
            self.zoom_at_viewport_pos(event.pos(), factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(pos, self.transform())
        owner = self._owning_item(item)
        if isinstance(owner, ComponentItem):
            self._edit_properties(owner)
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(pos, self.transform())
        owner = self._owning_item(item)
        if isinstance(owner, WireItem):
            menu = QMenu(self)
            highlight_act = menu.addAction("Highlight Net")
            highlight_act.setEnabled(bool(owner.net_name))
            highlight_act.triggered.connect(lambda: self.highlight_net(owner.net_name))
            layout_act = menu.addAction("Highlight net in Layout")
            layout_act.setEnabled(bool(owner.net_name))
            layout_act.triggered.connect(lambda: self.net_highlight_requested.emit(owner.net_name))
            menu.addAction("Clear Highlights", self.clear_highlights)
            menu.exec_(event.globalPos())
        else:
            super().contextMenuEvent(event)

    def _finish_wire(self, end_pos):
        self._wire_h_first = not QApplicationKeyboard.shift_pressed()
        sx, sy = self._wire_start.x(), self._wire_start.y()
        ex, ey = end_pos.x(), end_pos.y()
        net_name = self._net_name_for_wire(self._wire_start, end_pos)
        points = [(sx, sy)]
        if self._wire_h_first:
            points.append((ex, sy))
        else:
            points.append((sx, ey))
        points.append((ex, ey))
        wires = []
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            if abs(x1 - x2) > 0.001 or abs(y1 - y2) > 0.001:
                wires.append(WireItem(x1, y1, x2, y2, net_name))
        if wires:
            self.undo_stack.push(AddWireCommand(self._scene, *wires))
            self._rebuild_junctions()

    def _route_preview_segments(self, end_pos):
        if self._wire_start is None:
            return []
        sx, sy = self._wire_start.x(), self._wire_start.y()
        ex, ey = end_pos.x(), end_pos.y()
        mid = (ex, sy) if self._wire_h_first else (sx, ey)
        return [(sx, sy, mid[0], mid[1]), (mid[0], mid[1], ex, ey)]

    def highlight_net(self, net_name):
        self._rebuild_nets()
        self.clear_highlights()
        if not net_name:
            return
        self._highlighted_nets = {net_name}
        brush = QBrush(QColor(255, 235, 59, 80))
        pen = QPen(QColor(255, 235, 59, 160), 1)
        for wire in self._wire_items():
            if wire.net_name != net_name:
                continue
            rect = wire.sceneBoundingRect().adjusted(-5, -5, 5, 5)
            overlay = QGraphicsRectItem(rect)
            overlay.setPen(pen)
            overlay.setBrush(brush)
            overlay.setZValue(900)
            self._scene.addItem(overlay)
            self._highlight_items.append(overlay)
        for label in self._label_items():
            if label.net_name != net_name:
                continue
            rect = label.sceneBoundingRect().adjusted(-3, -3, 3, 3)
            overlay = QGraphicsRectItem(rect)
            overlay.setPen(pen)
            overlay.setBrush(brush)
            overlay.setZValue(900)
            self._scene.addItem(overlay)
            self._highlight_items.append(overlay)

    def _highlight_net(self, net_name: str):
        """Highlight all wires and components on this net."""
        if not net_name:
            return
        connected_pins = self._net_manager.get_pins_on_net(net_name)
        for item in self._scene.items():
            if isinstance(item, WireItem) and getattr(item, "net_name", "") == net_name:
                item.setSelected(True)
            elif isinstance(item, ComponentItem):
                cname = getattr(item, "comp_name", "")
                for pin in getattr(item, "pin_positions", {}).keys():
                    if f"{cname}.{pin}" in connected_pins:
                        item.setSelected(True)
                        break

    def get_net_for_item(self, item) -> str:
        """Return net name for a component pin or wire."""
        item = self._owning_item(item)
        if hasattr(item, "net_name"):
            return item.net_name or ""
        if hasattr(item, "comp_name"):
            nets = set()
            for pin in getattr(item, "pin_positions", {}).keys():
                n = self._net_manager.get_net_for_pin(item.comp_name, pin)
                if n:
                    nets.add(n)
            return ", ".join(sorted(nets))
        return ""

    def clear_highlights(self):
        for item in self._highlight_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._highlight_items = []
        self._highlighted_nets = set()

    def _add_net_label(self, pos, text):
        self.undo_stack.push(AddItemCommand(self._scene, NetLabelItem(text, pos), "Add Net Label"))
        self._rebuild_junctions()

    def _add_label(self, pos, text):
        self._add_net_label(pos, text)

    def _add_port_dialog(self, pos):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Port")
        layout = QFormLayout(dlg)
        name_edit = QLineEdit("OUT")
        direction = QComboBox()
        direction.addItems(["IN", "OUT", "INOUT"])
        layout.addRow("Name:", name_edit)
        layout.addRow("Direction:", direction)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addRow(btns)
        if dlg.exec_() == QDialog.Accepted and name_edit.text().strip():
            item = PortItem(name_edit.text().strip(), direction.currentText(), pos)
            self.undo_stack.push(AddItemCommand(self._scene, item, "Add Port"))
            self._rebuild_junctions()

    def _add_block_dialog(self, pos, rect):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Block")
        layout = QFormLayout(dlg)
        name_edit = QLineEdit("X1")
        pins_edit = QLineEdit("in,out,vdd,vss")
        layout.addRow("Block Name:", name_edit)
        layout.addRow("Pins:", pins_edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addRow(btns)
        if dlg.exec_() == QDialog.Accepted and name_edit.text().strip():
            pins = [pin.strip() for pin in pins_edit.text().split(",") if pin.strip()]
            item = BlockItem(name_edit.text().strip(), pins, rect, pos)
            self.undo_stack.push(AddItemCommand(self._scene, item, "Add Block"))
            self._rebuild_junctions()

    def _add_instance_dialog(self, sym_key=None):
        from schematic.add_instance_dialog import AddInstanceDialog
        dlg = AddInstanceDialog(self)
        if sym_key:
            matches = dlg.tree.findItems(sym_key, Qt.MatchExactly | Qt.MatchRecursive)
            if matches:
                dlg.tree.setCurrentItem(matches[0])
        if dlg.exec_() == QDialog.Accepted:
            self.enter_instance_mode(
                dlg.selected_comp_type or dlg.selected_cell,
                library=dlg.selected_library,
                view=dlg.selected_view,
                props=getattr(dlg, "selected_props", {}),
                cell_name_display=dlg.selected_cell,
            )

    def enter_instance_mode(self, cell_name, library="", view="schematic", props=None, cell_name_display=None):
        if not cell_name:
            return
        display_name = cell_name_display or cell_name
        self._pending_instance = {
            "cell": cell_name,
            "library": library,
            "view": view,
            "props": dict(props or {}),
            "display_cell": display_name,
        }
        self.start_mode("instance")
        self._clear_instance_preview()
        if cell_name in self._symbols:
            self._preview_item = ComponentItem(cell_name, self._symbols, name="", props=props or {})
            self._preview_item.setOpacity(0.45)
            self._preview_item.setFlag(QGraphicsItem.ItemIsMovable, False)
            self._preview_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self._preview_item.setZValue(1000)
            self._scene.addItem(self._preview_item)
        self._status(f"Place instance: {library + '/' if library else ''}{display_name}")

    def _place_pending_instance(self, pos):
        self._clear_instance_preview()
        if not self._pending_instance:
            self.start_mode("select")
            return
        cell = self._pending_instance.get("cell", "")
        library = self._pending_instance.get("library", "")
        props = self._pending_instance.get("props", {})
        if cell in self._symbols:
            self.add_instance(cell, self._default_instance_name(cell), pos, props=props)
        else:
            item = BlockItem(cell, [], QRectF(0, 0, 120, 80), pos)
            self.undo_stack.push(AddItemCommand(self._scene, item, "Add Instance"))
            self._rebuild_junctions()
        self._scene.update()
        self.viewport().update()
        self.start_mode("select")

    def add_instance(self, sym_key, name="", pos=QPointF(0, 0), props=None):
        comp = ComponentItem(sym_key, self._symbols, name=name or self._default_instance_name(sym_key), props=props)
        comp.setPos(snap_point(pos))
        self.undo_stack.push(AddComponentCommand(self._scene, comp))
        self._rebuild_junctions()
        self._scene.update()
        self.viewport().update()

    def _default_instance_name(self, sym_key):
        prefixes = {"resistor": "R1", "capacitor": "C1", "inductor": "L1", "vdc": "V1", "idc": "I1", "npn": "Q1"}
        return prefixes.get(sym_key, "M1" if sym_key in ("nmos", "pmos") else sym_key.upper() or "X1")

    def _edit_properties(self, comp):
        dlg = ComponentPropertiesDialog(comp, self)
        if dlg.exec_() == QDialog.Accepted:
            self._rebuild_junctions()

    def _edit_selected_properties(self):
        for item in self._scene.selectedItems():
            owner = self._owning_item(item)
            if isinstance(owner, ComponentItem):
                self._edit_properties(owner)
                return
        self._status("No editable component selected")

    def _undo(self):
        self.undo_stack.undo()

    def _redo(self):
        self.undo_stack.redo()

    def _on_undo_index_changed(self, _index):
        try:
            self._rebuild_junctions()
        except RuntimeError:
            pass

    def _delete_selected(self):
        items = []
        seen = set()
        for item in self._scene.selectedItems():
            item = self._owning_item(item)
            if item in self._wire_preview_items or item is self._pin_indicator or item in self._junction_items:
                continue
            key = id(item)
            if key not in seen:
                seen.add(key)
                items.append(item)
        if items:
            self.undo_stack.push(DeleteCommand(self._scene, items))
            self._rebuild_junctions()

    def rotate_selected(self):
        for item in self._scene.selectedItems():
            owner = self._owning_item(item)
            if hasattr(owner, "rotate90"):
                owner.rotate90()
        self._rebuild_junctions()

    def mirror_selected(self):
        for item in self._scene.selectedItems():
            owner = self._owning_item(item)
            if hasattr(owner, "mirror_horizontal"):
                owner.mirror_horizontal()
        self._rebuild_junctions()

    def copy_selected(self):
        for item in list(self._scene.selectedItems()):
            owner = self._owning_item(item)
            if isinstance(owner, WireItem):
                line = owner.line()
                copy = WireItem(line.x1() + GRID, line.y1() + GRID, line.x2() + GRID, line.y2() + GRID, owner.net_name)
                self._scene.addItem(copy)
            elif isinstance(owner, NetLabelItem):
                self._scene.addItem(NetLabelItem(owner.net_name, owner.pos() + QPointF(GRID, GRID)))
            elif isinstance(owner, PortItem):
                self._scene.addItem(PortItem(owner.port_name, owner.direction, owner.pos() + QPointF(GRID, GRID)))
            elif isinstance(owner, BlockItem):
                self._scene.addItem(BlockItem(owner.block_name, owner.pin_names, owner.local_rect, owner.pos() + QPointF(GRID, GRID)))
        self._rebuild_junctions()

    def fit_all(self):
        rect = self._scene.itemsBoundingRect()
        if rect.isValid() and not rect.isEmpty():
            self.fitInView(rect.adjusted(-30, -30, 30, 30), Qt.KeepAspectRatio)

    def zoom_at_viewport_pos(self, viewport_pos, factor):
        before = self.mapToScene(viewport_pos)
        self.scale(factor, factor)
        after = self.mapToScene(viewport_pos)
        delta = after - before
        self.translate(delta.x(), delta.y())

    def _get_nearest_connection(self, scene_pos, threshold=15):
        pin_pos = self._nearest_connection_pos(scene_pos, threshold)
        return pin_pos if pin_pos is not None else self._snap(scene_pos)

    def _nearest_connection_pos(self, scene_pos, threshold=15):
        nearest = None
        nearest_dist = threshold
        for candidate in self._connection_points(include_wire_endpoints=True):
            dist = QLineF(scene_pos, candidate).length()
            if dist <= nearest_dist:
                nearest = candidate
                nearest_dist = dist
        return nearest

    def _nearest_pin_pos(self, scene_pos, threshold=15):
        nearest = None
        nearest_dist = threshold
        for candidate in self._pin_points():
            dist = QLineF(scene_pos, candidate).length()
            if dist <= nearest_dist:
                nearest = candidate
                nearest_dist = dist
        return nearest

    def _update_pin_indicator(self, scene_pos):
        pin_pos = self._nearest_connection_pos(scene_pos)
        if pin_pos is None:
            self._clear_pin_indicator()
            return
        if self._pin_indicator is None:
            self._pin_indicator = QGraphicsItemGroup()
            pen = QPen(QColor("#f9e2af"), 1)
            for line in (QGraphicsLineItem(-5, 0, 5, 0), QGraphicsLineItem(0, -5, 0, 5)):
                line.setPen(pen)
                self._pin_indicator.addToGroup(line)
            self._pin_indicator.setZValue(1000)
            self._scene.addItem(self._pin_indicator)
        self._pin_indicator.setPos(pin_pos)

    def _clear_pin_indicator(self):
        if self._pin_indicator is not None:
            if self._pin_indicator.scene() is self._scene:
                self._scene.removeItem(self._pin_indicator)
            self._pin_indicator = None

    def _update_wire_preview(self, end_pos):
        self._clear_wire_preview()
        if self._wire_start is None:
            return
        pen = QPen(QColor("#FFD700"), 1, Qt.DashLine)
        self._wire_h_first = not QApplicationKeyboard.shift_pressed()
        for x1, y1, x2, y2 in self._route_preview_segments(end_pos):
            if abs(x1 - x2) <= 0.001 and abs(y1 - y2) <= 0.001:
                continue
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setZValue(999)
            self._scene.addItem(line)
            self._wire_preview_items.append(line)

    def _clear_wire_preview(self):
        for item in self._wire_preview_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._wire_preview_items = []

    def _update_block_preview(self, end_pos):
        self._clear_block_preview()
        if self._block_start is None:
            return
        rect = QRectF(self._block_start, end_pos).normalized()
        self._block_preview = QGraphicsRectItem(rect)
        self._block_preview.setPen(QPen(QColor("#fab387"), 1, Qt.DashLine))
        self._block_preview.setZValue(999)
        self._scene.addItem(self._block_preview)

    def _clear_block_preview(self):
        if self._block_preview is not None and self._block_preview.scene() is self._scene:
            self._scene.removeItem(self._block_preview)
        self._block_preview = None

    def _clear_instance_preview(self):
        if self._preview_item is not None and self._preview_item.scene() is self._scene:
            self._scene.removeItem(self._preview_item)
        self._preview_item = None

    def _clear_wire_drag(self):
        self._wire_drag_item = None
        self._wire_drag_end = None
        self._wire_drag_fixed = None
        self._wire_drag_old_line = None

    def _cancel_mode(self):
        self._scene.clearSelection()
        self._clear_instance_preview()
        self._clear_wire_drag()
        self.start_mode("select")

    def _wire_scene_endpoints(self, wire):
        line = wire.line()
        return wire.mapToScene(line.p1()), wire.mapToScene(line.p2())

    def _set_wire_scene_line(self, wire, p1, p2):
        local_p1 = wire.mapFromScene(p1)
        local_p2 = wire.mapFromScene(p2)
        wire.setLine(QLineF(local_p1, local_p2))

    def _set_dragged_wire_endpoint(self, scene_pos):
        if self._wire_drag_item is None or self._wire_drag_fixed is None:
            return
        if self._wire_drag_end == "start":
            self._set_wire_scene_line(self._wire_drag_item, scene_pos, self._wire_drag_fixed)
        else:
            self._set_wire_scene_line(self._wire_drag_item, self._wire_drag_fixed, scene_pos)

    def _same_line(self, a, b, tol=0.001):
        return (
            abs(a.x1() - b.x1()) <= tol and abs(a.y1() - b.y1()) <= tol
            and abs(a.x2() - b.x2()) <= tol and abs(a.y2() - b.y2()) <= tol
        )

    def _find_wire_endpoint(self, scene_pos: QPointF, tol: float = 8.0):
        for item in self._wire_items():
            p1, p2 = self._wire_scene_endpoints(item)
            if QLineF(p1, scene_pos).length() < tol:
                return item, "start", p2
            if QLineF(p2, scene_pos).length() < tol:
                return item, "end", p1
        return None

    def _find_nearest_pin(self, scene_pos: QPointF, tol: float = 12.0):
        best_dist = tol
        best_pos = None
        for candidate in self._pin_points():
            dist = QLineF(scene_pos, candidate).length()
            if dist < best_dist:
                best_dist = dist
                best_pos = candidate
        return best_pos

    def _find_nearest_wire_point(self, scene_pos: QPointF, tol: float = 12.0):
        best_dist = tol
        best_pos = None
        for item in self._wire_items():
            if item is self._wire_drag_item:
                continue
            for point in self._wire_scene_endpoints(item):
                dist = QLineF(scene_pos, point).length()
                if dist < best_dist:
                    best_dist = dist
                    best_pos = point
        return best_pos

    def _label_items(self):
        return [item for item in self._scene.items() if isinstance(item, NetLabelItem)]

    def _port_items(self):
        return [item for item in self._scene.items() if isinstance(item, PortItem)]

    def _block_items(self):
        return [item for item in self._scene.items() if isinstance(item, BlockItem)]

    def _wire_items(self):
        return [item for item in self._scene.items() if isinstance(item, WireItem)]

    def _label_at_point(self, pos, threshold=15):
        for label in self._label_items():
            if QLineF(pos, label.pin_pos).length() <= threshold:
                return label.net_name
            if label.sceneBoundingRect().adjusted(-threshold, -threshold, threshold, threshold).contains(pos):
                return label.net_name
        return ""

    def _net_name_for_wire(self, start_pos, end_pos):
        return (
            self._label_at_point(start_pos)
            or self._label_at_point(end_pos)
            or self._wire_net_at_point(start_pos)
            or self._wire_net_at_point(end_pos)
        )

    def _wire_net_at_point(self, pos, threshold=3):
        for wire in self._wire_items():
            if wire.net_name and self._point_on_segment(pos, self._segment_for_wire(wire), threshold, include_endpoints=True):
                return wire.net_name
        return ""

    def _segment_for_wire(self, wire):
        line = wire.line()
        offset = wire.scenePos()
        return (
            line.x1() + offset.x(), line.y1() + offset.y(),
            line.x2() + offset.x(), line.y2() + offset.y(), wire
        )

    def _rebuild_junctions(self):
        for item in self._junction_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._junction_items = []

        wires = self._wire_items()
        segments = [self._segment_for_wire(wire) for wire in wires]
        t_points = {}
        endpoint_points = {}
        endpoints = []
        for idx, seg in enumerate(segments):
            x1, y1, x2, y2, wire = seg
            endpoints.append((QPointF(x1, y1), idx, wire))
            endpoints.append((QPointF(x2, y2), idx, wire))

        label_nets = {}
        for label in self._label_items():
            label_nets[(round(label.pin_pos.x(), 3), round(label.pin_pos.y(), 3))] = label.net_name

        for point, idx, wire in endpoints:
            key = (round(point.x(), 3), round(point.y(), 3))
            for label in self._label_items():
                if QLineF(point, label.pin_pos).length() <= 2:
                    wire.set_net_name(label.net_name)
                    label_nets[key] = label.net_name
            for j, seg in enumerate(segments):
                if idx == j:
                    continue
                if self._point_on_segment(point, seg, threshold=1, include_endpoints=False):
                    t_points[key] = QPointF(point)

        for i, (point_a, _idx_a, wire_a) in enumerate(endpoints):
            for point_b, _idx_b, wire_b in endpoints[i + 1:]:
                if wire_a is wire_b:
                    continue
                if QLineF(point_a, point_b).length() <= 0.001:
                    key = (round(point_a.x(), 3), round(point_a.y(), 3))
                    endpoint_points[key] = QPointF(point_a)
                    if wire_a.net_name and not wire_b.net_name:
                        wire_b.set_net_name(wire_a.net_name)
                    elif wire_b.net_name and not wire_a.net_name:
                        wire_a.set_net_name(wire_b.net_name)

        for key, net_name in label_nets.items():
            if not net_name:
                continue
            for point, _idx, wire in endpoints:
                if (round(point.x(), 3), round(point.y(), 3)) == key:
                    wire.set_net_name(net_name)

        for point in t_points.values():
            self._add_junction_marker(point, 5, "#f38ba8", "circle")
        for point in endpoint_points.values():
            self._add_junction_marker(point, 6, "#a6e3a1", "circle")
        for point in self._pin_connected_endpoints(endpoints):
            self._add_junction_marker(point, 4, "#89b4fa", "square")
        self._rebuild_nets()

    def _rebuild_nets(self):
        self._net_manager.rebuild_from_scene(self._scene)

    def _add_junction_marker(self, point, radius, color, shape):
        if shape == "square":
            item = QGraphicsRectItem(point.x() - radius / 2, point.y() - radius / 2, radius, radius)
        else:
            item = QGraphicsEllipseItem(point.x() - radius, point.y() - radius, radius * 2, radius * 2)
        item.setPen(QPen(QColor(color), 1))
        item.setBrush(QBrush(QColor(color)))
        item.setZValue(10)
        self._scene.addItem(item)
        self._junction_items.append(item)

    def _pin_connected_endpoints(self, endpoints):
        points = []
        pins = self._pin_points(include_net_labels=False)
        for point, _idx, _wire in endpoints:
            if any(QLineF(point, pin).length() <= 2 for pin in pins):
                points.append(QPointF(point))
        return points

    def _point_on_segment(self, pos, seg, threshold=3, include_endpoints=True):
        x, y = pos.x(), pos.y()
        x1, y1, x2, y2, _wire = seg
        if not include_endpoints:
            if QLineF(pos, QPointF(x1, y1)).length() <= threshold or QLineF(pos, QPointF(x2, y2)).length() <= threshold:
                return False
        if abs(y1 - y2) <= 0.001:
            return abs(y - y1) <= threshold and min(x1, x2) - threshold <= x <= max(x1, x2) + threshold
        if abs(x1 - x2) <= 0.001:
            return abs(x - x1) <= threshold and min(y1, y2) - threshold <= y <= max(y1, y2) + threshold
        length = QLineF(QPointF(x1, y1), QPointF(x2, y2)).length()
        if length <= 0.001:
            return QLineF(pos, QPointF(x1, y1)).length() <= threshold
        dx, dy = x2 - x1, y2 - y1
        t = ((x - x1) * dx + (y - y1) * dy) / (length * length)
        if not include_endpoints and (t <= 0.001 or t >= 0.999):
            return False
        t = max(0, min(1, t))
        nearest = QPointF(x1 + t * dx, y1 + t * dy)
        return QLineF(pos, nearest).length() <= threshold

    def _connection_points(self, include_wire_endpoints=True):
        points = self._pin_points()
        if include_wire_endpoints:
            for wire in self._wire_items():
                line = wire.line()
                offset = wire.scenePos()
                points.append(QPointF(line.x1() + offset.x(), line.y1() + offset.y()))
                points.append(QPointF(line.x2() + offset.x(), line.y2() + offset.y()))
        return points

    def _pin_points(self, include_net_labels=True):
        points = []
        for item in self._scene.items():
            if isinstance(item, ComponentItem):
                for pin in item.pin_positions.values():
                    points.append(item.mapToScene(pin))
            elif include_net_labels and isinstance(item, NetLabelItem):
                points.append(item.pin_pos)
            elif isinstance(item, PortItem):
                points.append(item.pin_pos)
            elif isinstance(item, BlockItem):
                points.extend(item.scene_pin_positions().values())
        return points

    def _snap(self, pos):
        return snap_point(pos) if self._snap_to_grid else pos

    def _owning_item(self, item):
        while item is not None and item.parentItem() is not None:
            item = item.parentItem()
        return item

    def _call_parent(self, method):
        parent = self.window()
        fn = getattr(parent, method, None)
        if callable(fn):
            fn()

    def _status(self, message, timeout=2000):
        window = self.window()
        if hasattr(window, "statusBar") and window.statusBar():
            window.statusBar().showMessage(message, timeout)

    def import_from_spice(self, path: str):
        """Parse a SPICE netlist and place components on the canvas."""
        from schematic.spice_import import SpiceParser, auto_layout

        parser = SpiceParser()
        if not parser.parse_file(path):
            QMessageBox.warning(self, "Import Error", f"Could not parse SPICE file:\n{path}")
            return False

        placements = auto_layout(parser.components, parser.nets)
        if not placements:
            QMessageBox.information(self, "Import", "No components found in SPICE file.")
            return False

        if self._has_schematic_items():
            answer = QMessageBox.question(
                self,
                "Import SPICE",
                "Clear the current schematic before importing this SPICE file?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return False
            self.clear_schematic()

        imported_items = []
        for comp, x_sym, y_sym in placements:
            sym_type = comp["type"]
            pos = snap_point(QPointF(x_sym * SCALE, y_sym * SCALE))
            props = dict(comp.get("props", {}))
            nets = dict(comp.get("nets", {}))

            if sym_type == "block" or sym_type not in self._symbols:
                pins = [pin for pin in nets.keys()]
                item = BlockItem(comp["name"], pins, pos=pos)
                item.props.update(props)
                item.props["name"] = comp["name"]
            else:
                item = ComponentItem(sym_type, self._symbols, name=comp["name"], props=props)
                item.setPos(pos)

            item._imported_nets = nets
            self._scene.addItem(item)
            imported_items.append(item)

        self._route_imported_nets(imported_items)
        self._rebuild_junctions()
        self.undo_stack.clear()
        self.fit_all()
        self._status(f"Imported {len(placements)} components from SPICE")
        return True

    def _has_schematic_items(self):
        ignored = set(self._junction_items + self._wire_preview_items + self._highlight_items)
        ignored.update(item for item in (self._pin_indicator, self._block_preview) if item is not None)
        return any(item not in ignored for item in self._scene.items())

    def _route_imported_nets(self, imported_items):
        """Draw wires between components sharing the same net name."""
        net_pins = {}
        for item in imported_items:
            imported_nets = getattr(item, "_imported_nets", {})
            for pin_name, net_name in imported_nets.items():
                normalized = self._normalize_imported_net(net_name)
                pin_pos = self._imported_pin_scene_pos(item, pin_name)
                net_pins.setdefault(normalized, []).append(pin_pos)

        for net_name, pins in net_pins.items():
            if net_name in ("0", "") or len(pins) < 2:
                continue
            for p1, p2 in zip(pins, pins[1:]):
                self._add_imported_wire(p1, p2, net_name)

    def _normalize_imported_net(self, net_name):
        text = str(net_name or "").strip()
        return "0" if text.lower() in ("0", "gnd", "vss") else text

    def _imported_pin_scene_pos(self, item, pin_name):
        if isinstance(item, ComponentItem):
            return item.mapToScene(item.pin_positions.get(pin_name, QPointF(0, 0)))
        if isinstance(item, BlockItem):
            return item.scene_pin_positions().get(pin_name, item.pos())
        return item.pos()

    def _add_imported_wire(self, p1, p2, net_name):
        p1 = snap_point(p1)
        p2 = snap_point(p2)
        if QLineF(p1, p2).length() <= 0.001:
            return
        mid = snap_point(QPointF(p2.x(), p1.y()))
        if QLineF(p1, mid).length() > 0.001:
            self._scene.addItem(WireItem(p1.x(), p1.y(), mid.x(), mid.y(), net_name=net_name))
        if QLineF(mid, p2).length() > 0.001:
            self._scene.addItem(WireItem(mid.x(), mid.y(), p2.x(), p2.y(), net_name=net_name))

    def to_dict(self):
        self._rebuild_nets()
        data = {"components": [], "wires": [], "labels": [], "ports": [], "blocks": []}
        for item in self._scene.items():
            if isinstance(item, ComponentItem):
                data["components"].append({
                    "name": item.comp_name, "type": item.sym_key, "props": item.props,
                    "x": item.pos().x(), "y": item.pos().y(), "rotation": item.rotation(),
                })
            elif isinstance(item, WireItem):
                line = item.line()
                offset = item.scenePos()
                data["wires"].append({
                    "x1": line.x1() + offset.x(), "y1": line.y1() + offset.y(),
                    "x2": line.x2() + offset.x(), "y2": line.y2() + offset.y(),
                    "net": item.net_name,
                })
            elif isinstance(item, NetLabelItem):
                data["labels"].append(item.to_dict())
            elif isinstance(item, PortItem):
                data["ports"].append(item.to_dict())
            elif isinstance(item, BlockItem):
                data["blocks"].append(item.to_dict())
        data["nets"] = self._net_manager.to_dict()
        return data

    def load_dict(self, data):
        self.clear_schematic()
        for comp_data in data.get("components", []):
            comp = ComponentItem(
                comp_data.get("type", ""), self._symbols,
                name=comp_data.get("name", ""), props=comp_data.get("props", {}),
            )
            comp.setPos(comp_data.get("x", 0), comp_data.get("y", 0))
            comp.setRotation(comp_data.get("rotation", 0))
            self._scene.addItem(comp)
        for wire_data in data.get("wires", []):
            wire = WireItem(
                wire_data.get("x1", 0), wire_data.get("y1", 0),
                wire_data.get("x2", 0), wire_data.get("y2", 0),
                wire_data.get("net", ""),
            )
            self._scene.addItem(wire)
        for label_data in data.get("labels", []):
            self._scene.addItem(NetLabelItem.from_dict(label_data))
        for port_data in data.get("ports", []):
            self._scene.addItem(PortItem.from_dict(port_data))
        for block_data in data.get("blocks", []):
            self._scene.addItem(BlockItem.from_dict(block_data))
        if "nets" in data:
            self._net_manager.from_dict(data["nets"])
        self.undo_stack.clear()
        self._rebuild_junctions()

    def clear_schematic(self):
        self._clear_wire_preview()
        self._clear_pin_indicator()
        self._clear_block_preview()
        self.clear_highlights()
        self._scene.clear()
        self._junction_items = []
        self._net_manager = NetManager()
        self._wire_start = None
        self._block_start = None
        self.undo_stack.clear()


class QApplicationKeyboard:
    @staticmethod
    def shift_pressed():
        from PyQt5.QtWidgets import QApplication
        return bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
