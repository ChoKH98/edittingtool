"""
Persistent net connectivity manager for schematic editor.

Net model:
  - A "net" is a named set of (component_name, pin_name) pairs that are
    electrically connected.
  - Nets are formed by drawing wires between component pins.
  - Net names are auto-assigned ("net1", "net2", ...) or taken from NetLabelItem.
  - A net persists until all wires connecting it are removed.
  - Special net names: "VDD", "VSS", "GND", "0" are reserved for power/ground.

Wire-based connectivity:
  - Wires are line segments. Two wires that share an endpoint are connected.
  - A wire endpoint within snap_tol of a component pin connects them.
  - Union-Find is used for efficient net merging.
"""

from __future__ import annotations
from typing import Dict, Set, Tuple, Optional, List

# Pin ID: "CompName.PinName" e.g. "M1.D"
PinId = str


class _UnionFind:
    def __init__(self):
        self._parent: Dict[str, str] = {}
        self._rank: Dict[str, int] = {}

    def add(self, x: str):
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0

    def find(self, x: str) -> str:
        self.add(x)
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def groups(self) -> Dict[str, Set[str]]:
        result: Dict[str, Set[str]] = {}
        for x in list(self._parent):
            root = self.find(x)
            result.setdefault(root, set()).add(x)
        return result


class NetInfo:
    """Data for one net."""

    __slots__ = ("name", "pins", "wire_ids", "color")

    def __init__(self, name: str):
        self.name = name
        self.pins: Set[PinId] = set()
        self.wire_ids: Set[int] = set()
        self.color: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "pins": sorted(self.pins)}

    @classmethod
    def from_dict(cls, d: dict) -> "NetInfo":
        n = cls(d["name"])
        n.pins = set(d.get("pins", []))
        return n


class NetManager:
    """
    Manages net connectivity for the schematic.
    Call rebuild_from_scene() after any structural change.
    """

    SNAP_TOL = 6.0
    _AUTO_PREFIX = "net"

    def __init__(self):
        self._nets: Dict[str, NetInfo] = {}
        self._pin_to_net: Dict[PinId, str] = {}
        self._counter = 0

    def rebuild_from_scene(self, scene):
        """
        Scan all schematic items and re-derive net connectivity from scratch.
        Existing net names from labels or restored pin mappings are preserved where possible.
        """
        from schematic.schematic_canvas import WireItem, ComponentItem, NetLabelItem

        uf = _UnionFind()
        wires: List[WireItem] = []
        pins: List[Tuple[str, object]] = []
        labels: List[Tuple[str, object]] = []

        for item in scene.items():
            if isinstance(item, WireItem):
                wires.append(item)
            elif isinstance(item, ComponentItem):
                cname = getattr(item, "comp_name", "") or getattr(item, "_name", "U?")
                for pin_name, pin_local in (getattr(item, "pin_positions", None) or {}).items():
                    pin_scene = item.mapToScene(pin_local)
                    pid = f"{cname}.{pin_name}"
                    pins.append((pid, pin_scene))
                    uf.add(pid)
            elif isinstance(item, NetLabelItem):
                lbl = getattr(item, "net_name", "") or getattr(item, "text", "")
                if lbl:
                    lpos = item.pin_pos if hasattr(item, "pin_pos") else item.mapToScene(item.boundingRect().center())
                    labels.append((lbl, lpos))

        def wp1(w):
            return f"wire_{id(w)}_p1"

        def wp2(w):
            return f"wire_{id(w)}_p2"

        def _pt(w, end):
            if hasattr(w, "line"):
                line = w.line()
                pt = line.p1() if end == "p1" else line.p2()
                return w.mapToScene(pt)
            return None

        for w in wires:
            uf.add(wp1(w))
            uf.add(wp2(w))
            uf.union(wp1(w), wp2(w))

        tol = self.SNAP_TOL
        pts = [(wp1(w), _pt(w, "p1")) for w in wires] + [(wp2(w), _pt(w, "p2")) for w in wires]

        for i, (na, pa) in enumerate(pts):
            if pa is None:
                continue
            for nb, pb in pts[i + 1:]:
                if pb is not None and (pa - pb).manhattanLength() < tol:
                    uf.union(na, nb)

        for node, pt in pts:
            if pt is None:
                continue
            for pid, ppos in pins:
                if (pt - ppos).manhattanLength() < tol:
                    uf.union(node, pid)

        for lbl, lpos in labels:
            candidates = pts + [(pid, ppos) for pid, ppos in pins]
            closest = min(
                candidates,
                key=lambda np: (np[1] - lpos).manhattanLength() if np[1] is not None else 999,
                default=None,
            )
            if closest and (closest[1] - lpos).manhattanLength() < tol * 4:
                uf.add(lbl)
                uf.union(lbl, closest[0])

        groups = uf.groups()
        new_nets: Dict[str, NetInfo] = {}
        old_pin_net = dict(self._pin_to_net)

        for _root, members in groups.items():
            pin_members = {m for m in members if "." in m and not m.startswith("wire_")}
            label_members = {m for m in members if m not in pin_members and not m.startswith("wire_")}
            if not pin_members and not label_members:
                continue

            name = None
            for lbl_name in sorted(label_members):
                name = lbl_name
                break
            if not name:
                for pid in sorted(pin_members):
                    if pid in old_pin_net:
                        name = old_pin_net[pid]
                        break
            if not name:
                name = self._new_name()

            net = NetInfo(name)
            net.pins = pin_members
            for w in wires:
                if wp1(w) in members or wp2(w) in members:
                    net.wire_ids.add(id(w))
            new_nets[name] = net

        self._nets = new_nets
        self._pin_to_net = {}
        for net in new_nets.values():
            for pid in net.pins:
                self._pin_to_net[pid] = net.name

        for w in wires:
            net_name = ""
            wid = id(w)
            for net in new_nets.values():
                if wid in net.wire_ids:
                    net_name = net.name
                    break
            if hasattr(w, "set_net_name"):
                w.set_net_name(net_name)
            else:
                w.net_name = net_name

    def get_net_for_pin(self, comp_name: str, pin_name: str) -> Optional[str]:
        return self._pin_to_net.get(f"{comp_name}.{pin_name}")

    def get_pins_on_net(self, net_name: str) -> Set[PinId]:
        net = self._nets.get(net_name)
        return net.pins.copy() if net else set()

    def get_all_nets(self) -> Dict[str, NetInfo]:
        return dict(self._nets)

    def net_names(self) -> List[str]:
        return list(self._nets.keys())

    def rename_net(self, old_name: str, new_name: str):
        if old_name not in self._nets or new_name == old_name:
            return
        net = self._nets.pop(old_name)
        net.name = new_name
        self._nets[new_name] = net
        for pid in net.pins:
            self._pin_to_net[pid] = new_name

    def to_dict(self) -> dict:
        return {"nets": {n: info.to_dict() for n, info in self._nets.items()}}

    def from_dict(self, d: dict):
        self._nets = {}
        self._pin_to_net = {}
        for name, info_d in d.get("nets", {}).items():
            net = NetInfo.from_dict(info_d)
            self._nets[name] = net
            for pid in net.pins:
                self._pin_to_net[pid] = name

    def _new_name(self) -> str:
        while True:
            self._counter += 1
            name = f"{self._AUTO_PREFIX}{self._counter}"
            if name not in self._nets:
                return name
