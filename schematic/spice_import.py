"""Parse SPICE netlist files (.cir/.sp/.spice) into schematic component data."""

import re
from typing import Dict, List, Optional, Tuple


class SpiceParser:
    """
    Parses a SPICE netlist and extracts component instances.

    Supported elements:
      Rname n1 n2 value [model params]
      Cname n1 n2 value [model params]
      Lname n1 n2 value
      Vname n+ n- type(params)
      Iname n+ n- type(params)
      Mname drain gate source bulk model [params]
      Qname C B E [S] model [params]
      Xname n1 n2 ... modelname [params]  <- subcircuit call
      .subckt name ports
      .ends
      .model name type params
      .param name=value
    """

    def __init__(self):
        self.components: List[Dict] = []
        self.nets = set()
        self.params: Dict[str, str] = {}
        self.subckts: Dict[str, Dict] = {}
        self.top_ports: List[str] = []

    def parse_file(self, path: str) -> bool:
        try:
            with open(path, "r", errors="ignore") as f:
                text = f.read()
            return self.parse_text(text)
        except Exception as e:
            print(f"SpiceParser error: {e}")
            return False

    def parse_text(self, text: str) -> bool:
        self.components = []
        self.nets = set()
        self.params = {}
        self.subckts = {}
        self.top_ports = []

        lines = self._join_continuations(text.splitlines())
        in_subckt = False
        subckt_name: Optional[str] = None
        subckt_ports: List[str] = []
        subckt_body: List[str] = []
        top_level_lines: List[str] = []
        first_subckt_name: Optional[str] = None

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("*"):
                continue
            lower = stripped.lower()

            if lower.startswith(".subckt"):
                parts = stripped.split()
                if len(parts) >= 2:
                    subckt_name = parts[1]
                    subckt_ports = parts[2:]
                    in_subckt = True
                    subckt_body = []
                continue

            if lower.startswith(".ends"):
                if subckt_name:
                    self.subckts[subckt_name] = {"ports": subckt_ports, "body": subckt_body}
                    if first_subckt_name is None:
                        first_subckt_name = subckt_name
                in_subckt = False
                subckt_name = None
                subckt_ports = []
                subckt_body = []
                continue

            if lower.startswith(".param"):
                self._parse_param(stripped)
                continue

            if lower.startswith((".lib", ".inc", ".model", ".global", ".opt", ".temp", ".tran", ".dc", ".ac", ".op")):
                continue

            if in_subckt:
                subckt_body.append(stripped)
            else:
                top_level_lines.append(stripped)

        if top_level_lines:
            self._parse_elements(top_level_lines, is_top=True)
        elif first_subckt_name is not None:
            subckt = self.subckts[first_subckt_name]
            self._parse_elements(subckt["body"], is_top=True)
            self.top_ports = subckt["ports"]

        return len(self.components) > 0

    def _join_continuations(self, lines):
        """Join lines that start with '+' (SPICE continuation)."""
        result = []
        for line in lines:
            if line.lstrip().startswith("+") and result:
                result[-1] = result[-1] + " " + line.lstrip()[1:].strip()
            else:
                result.append(line)
        return result

    def _parse_elements(self, lines, is_top=False):
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("*"):
                self._parse_element(stripped)

    def _parse_element(self, line):
        if not line:
            return
        parts = line.split()
        if not parts:
            return
        name = parts[0]
        prefix = name[0].upper()

        comp = None

        if prefix == "R":
            if len(parts) >= 4:
                n1, n2 = parts[1], parts[2]
                value = parts[3]
                extra = self._parse_params(parts[4:])
                model = extra.pop("model", None) or (parts[4] if len(parts) > 4 and "=" not in parts[4] else "ideal")
                comp = {
                    "type": "resistor",
                    "name": name,
                    "nets": {"P": n1, "N": n2},
                    "props": {"value": value, "model": model, **extra},
                }
                self.nets.update([n1, n2])

        elif prefix == "C":
            if len(parts) >= 4:
                n1, n2 = parts[1], parts[2]
                value = parts[3]
                extra = self._parse_params(parts[4:])
                comp = {
                    "type": "capacitor",
                    "name": name,
                    "nets": {"P": n1, "N": n2},
                    "props": {"value": value, **extra},
                }
                self.nets.update([n1, n2])

        elif prefix == "L":
            if len(parts) >= 4:
                n1, n2 = parts[1], parts[2]
                value = parts[3]
                comp = {
                    "type": "inductor",
                    "name": name,
                    "nets": {"P": n1, "N": n2},
                    "props": {"value": value},
                }
                self.nets.update([n1, n2])

        elif prefix == "V":
            if len(parts) >= 3:
                np, nn = parts[1], parts[2]
                rest = " ".join(parts[3:])
                vtype, vparams = self._parse_vsource(rest)
                comp = {"type": vtype, "name": name, "nets": {"P": np, "N": nn}, "props": vparams}
                self.nets.update([np, nn])

        elif prefix == "I":
            if len(parts) >= 3:
                np, nn = parts[1], parts[2]
                rest = " ".join(parts[3:])
                _, iparams = self._parse_vsource(rest)
                comp = {"type": "idc", "name": name, "nets": {"P": np, "N": nn}, "props": iparams}
                self.nets.update([np, nn])

        elif prefix == "M":
            if len(parts) >= 6:
                drain, gate, source, bulk = parts[1], parts[2], parts[3], parts[4]
                model = parts[5]
                extra = self._parse_params(parts[6:])
                mos_type = "pmos" if "pmos" in model.lower() or "_p_" in model.lower() else "nmos"
                comp = {
                    "type": mos_type,
                    "name": name,
                    "nets": {"D": drain, "G": gate, "S": source, "B": bulk},
                    "props": {"model": model, **extra},
                }
                self.nets.update([drain, gate, source, bulk])

        elif prefix == "Q":
            if len(parts) >= 5:
                c, b, e = parts[1], parts[2], parts[3]
                if len(parts) >= 6 and "=" not in parts[5]:
                    substrate = parts[4]
                    model = parts[5]
                    param_tokens = parts[6:]
                else:
                    substrate = None
                    model = parts[4]
                    param_tokens = parts[5:]
                extra = self._parse_params(param_tokens)
                nets = {"C": c, "B": b, "E": e}
                if substrate:
                    nets["S"] = substrate
                comp = {
                    "type": "npn",
                    "name": name,
                    "nets": nets,
                    "props": {"model": model, **extra},
                }
                self.nets.update(nets.values())

        elif prefix == "X":
            param_start = len(parts)
            for i, p in enumerate(parts[1:], 1):
                if "=" in p:
                    param_start = i
                    break
            net_and_model = parts[1:param_start]
            if net_and_model:
                model = net_and_model[-1]
                nets_list = net_and_model[:-1]
                extra = self._parse_params(parts[param_start:])
                cell_type = self._map_subckt_to_type(model, extra)
                pin_names = self._get_pin_names(cell_type, len(nets_list))
                net_map = {pin: net for pin, net in zip(pin_names, nets_list)}
                props = {"model": model, **extra}
                if cell_type == "block":
                    props["pins"] = ",".join(pin_names)
                comp = {"type": cell_type, "name": name, "nets": net_map, "props": props}
                self.nets.update(nets_list)

        if comp:
            self.components.append(comp)

    def _map_subckt_to_type(self, model_name, params):
        """Map subcircuit model name to symbol type."""
        ml = model_name.lower()
        if "nmos" in ml or ml in ("sg13_lv_nmos", "sg13_hv_nmos"):
            return "nmos"
        if "pmos" in ml or ml in ("sg13_lv_pmos", "sg13_hv_pmos"):
            return "pmos"
        if "rsil" in ml or "rhigh" in ml or "rppd" in ml:
            return "resistor"
        if "cap" in ml or "cmim" in ml:
            return "capacitor"
        if "npn" in ml or "hbt" in ml:
            return "npn"
        if "ind" in ml:
            return "inductor"
        return "block"

    def _get_pin_names(self, cell_type, n_nets):
        pin_maps = {
            "nmos": ["D", "G", "S", "B"],
            "pmos": ["D", "G", "S", "B"],
            "resistor": ["P", "N", "BN"],
            "capacitor": ["P", "N", "BN"],
            "npn": ["C", "B", "E", "S"],
            "inductor": ["P", "N"],
        }
        pins = pin_maps.get(cell_type, [f"p{i}" for i in range(n_nets)])
        return pins[:n_nets] + [f"p{i}" for i in range(len(pins), n_nets)]

    def _parse_vsource(self, rest):
        text = rest.strip()
        upper = text.upper()
        if upper.startswith("PULSE"):
            vals = re.findall(r"[\w.e+\-]+", text[5:])
            keys = ["v1", "v2", "td", "tr", "tf", "pw", "per"]
            return "vpulse", {k: v for k, v in zip(keys, vals)}
        if upper.startswith("SIN"):
            vals = re.findall(r"[\w.e+\-]+", text[3:])
            keys = ["voff", "vamp", "freq", "td", "theta"]
            return "vsin", {k: v for k, v in zip(keys, vals)}
        if upper.startswith("PWL"):
            return "vpwl", {"pwl": text[3:].strip("() ")}
        if upper.startswith("AC"):
            vals = text.split()
            return "vdc", {"ac": vals[1] if len(vals) > 1 else "1"}
        vals = text.split()
        dc = vals[1] if len(vals) > 1 and vals[0].upper() == "DC" else (vals[0] if vals else "0")
        return "vdc", {"dc": dc}

    def _parse_params(self, tokens):
        result = {}
        canonical = {"w": "W", "l": "L"}
        for tok in tokens:
            if "=" in tok:
                k, v = tok.split("=", 1)
                key = k.strip()
                result[canonical.get(key.lower(), key.lower())] = v.strip()
        return result

    def _parse_param(self, line):
        for tok in line.split()[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                self.params[k.strip()] = v.strip()


def auto_layout(components, nets):
    """
    Auto-place components in a grid layout for schematic display.

    Returns list of (comp_dict, x, y) tuples with placed positions.
    SCALE = 10 (scene units per symbol unit). Use symbol units here.
    """
    placed: List[Tuple[Dict, int, int]] = []
    spacing_x = 8
    spacing_y = 10

    sources = [c for c in components if c["type"] in ("vdc", "vpulse", "vsin", "vpwl", "idc")]
    mos = [c for c in components if c["type"] in ("nmos", "pmos")]
    passives = [c for c in components if c["type"] in ("resistor", "capacitor", "inductor")]
    others = [c for c in components if c not in sources + mos + passives]

    col = 0
    for i, comp in enumerate(sources):
        placed.append((comp, col * spacing_x, i * spacing_y))
    if sources:
        col += 1

    for i, comp in enumerate(mos):
        placed.append((comp, col * spacing_x, i * spacing_y))
    if mos:
        col += 1

    for i, comp in enumerate(passives):
        placed.append((comp, col * spacing_x, i * spacing_y))
    if passives:
        col += 1

    for i, comp in enumerate(others):
        placed.append((comp, col * spacing_x, i * spacing_y))

    return placed
