import os
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal

from pdk_loader import load_pdk, default_pdk_path


class PDKTechLoader:
    """Parses IHP SG13G2 PDK tech files and extracts device constraints."""

    def __init__(self, pdk_root: str):
        self.pdk_root = pdk_root
        self.tech_params = {}
        self.devices = {}
        self.model_lib_path = ""
        self.corners = {}
        self._corner_sections = {}
        self._load()

    def _load(self):
        """Load all PDK tech data."""
        for loader in (
            self._load_tech_json,
            self._load_mos_params,
            self._load_resistor_models,
            self._load_capacitor_models,
            self._load_corners,
            self._find_model_lib,
        ):
            try:
                loader()
            except Exception:
                continue

    def _load_tech_json(self):
        """Read sg13g2_tech.json for grid and tech params."""
        path = os.path.join(
            self.pdk_root,
            "libs.tech/klayout/python/sg13g2_pycell_lib/sg13g2_tech.json",
        )
        if not os.path.exists(path):
            return
        import json
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        self.tech_params = data.get("techParams", {})

    def _load_mos_params(self):
        """Parse sg13g2_moslv_parm.lib and sg13g2_moshv_parm.lib for MOS constraints."""
        lv_path = os.path.join(self.pdk_root, "libs.tech/ngspice/models/sg13g2_moslv_parm.lib")
        hv_path = os.path.join(self.pdk_root, "libs.tech/ngspice/models/sg13g2_moshv_parm.lib")

        lv_constraints = {
            "L_min": "0.13u", "L_max": "10u", "L_default": "0.13u",
            "W_min": "0.15u", "W_max": "10u", "W_default": "2u",
            "nf_min": 1, "nf_max": 64, "nf_default": 1,
            "models_n": ["sg13_lv_nmos"],
            "models_p": ["sg13_lv_pmos"],
            "vdd_max": "1.5V",
            "description": "Low-Voltage MOS (PSP 103.6), Vds_max=1.5V",
        }
        if os.path.exists(lv_path):
            lv_models_n, lv_models_p = self._parse_mos_model_names(lv_path)
            if lv_models_n:
                lv_constraints["models_n"] = lv_models_n
            if lv_models_p:
                lv_constraints["models_p"] = lv_models_p

        self.devices["nmos_lv"] = dict(lv_constraints)
        self.devices["pmos_lv"] = {
            **lv_constraints,
            "models_n": lv_constraints.get("models_p", ["sg13_lv_pmos"]),
            "models_p": lv_constraints.get("models_p", ["sg13_lv_pmos"]),
            "description": "Low-Voltage PMOS (PSP 103.6), Vds_max=1.5V",
        }

        hv_constraints = {
            "L_min": "0.45u", "L_max": "10u", "L_default": "0.45u",
            "W_min": "0.15u", "W_max": "10u", "W_default": "2u",
            "nf_min": 1, "nf_max": 64, "nf_default": 1,
            "models_n": ["sg13_hv_nmos"],
            "models_p": ["sg13_hv_pmos"],
            "vdd_max": "3.3V",
            "description": "High-Voltage MOS, Vds_max=3.3V",
        }
        if os.path.exists(hv_path):
            hv_models_n, hv_models_p = self._parse_mos_model_names(hv_path)
            if hv_models_n:
                hv_constraints["models_n"] = hv_models_n
            if hv_models_p:
                hv_constraints["models_p"] = hv_models_p
        self.devices["nmos_hv"] = dict(hv_constraints)
        self.devices["pmos_hv"] = {
            **hv_constraints,
            "models_n": hv_constraints.get("models_p", ["sg13_hv_pmos"]),
            "description": "High-Voltage PMOS, Vds_max=3.3V",
        }

    def _parse_mos_model_names(self, lib_path: str):
        """Extract .model and .subckt names from a SPICE lib file."""
        models_n, models_p = [], []
        try:
            with open(lib_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped = line.strip()
                    lower = stripped.lower()
                    if lower.startswith(".subckt ") or lower.startswith(".model "):
                        parts = stripped.split()
                        if len(parts) >= 2:
                            name = parts[1]
                            name_l = name.lower()
                            if ("nmos" in name_l or "_n_" in name_l) and name not in models_n:
                                models_n.append(name)
                            elif ("pmos" in name_l or "_p_" in name_l) and name not in models_p:
                                models_p.append(name)
        except Exception:
            pass
        return models_n, models_p

    def _load_resistor_models(self):
        """Parse resistors_mod.lib for resistor subcircuit names and default params."""
        path = os.path.join(self.pdk_root, "libs.tech/ngspice/models/resistors_mod.lib")
        models = []
        descriptions = {}
        default_params = {}
        last_desc = ""
        if os.path.exists(path):
            current_subckt = None
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("**") and current_subckt is None:
                        desc = stripped.lstrip("*").strip()
                        if desc:
                            last_desc = desc
                    if stripped.lower().startswith(".subckt "):
                        parts = stripped.split()
                        if len(parts) >= 2:
                            current_subckt = parts[1]
                            models.append(current_subckt)
                            descriptions[current_subckt] = last_desc or current_subckt
                    if current_subckt and stripped.lower().startswith(".param "):
                        param_str = stripped[7:]
                        for kv in param_str.split():
                            if "=" in kv:
                                k, v = kv.split("=", 1)
                                default_params.setdefault(current_subckt, {})[k.strip()] = v.strip()
                    if stripped.lower().startswith(".ends"):
                        current_subckt = None

        if not models:
            models = ["rsil", "rppd", "rhigh", "rsil_un", "rline"]

        self.devices["resistor"] = {
            "models": models,
            "model_default": "rsil" if "rsil" in models else (models[0] if models else "rsil"),
            "descriptions": descriptions,
            "default_params": default_params,
            "description": "IHP SG13G2 Resistors",
        }

    def _load_capacitor_models(self):
        """Parse capacitors_mod.lib for capacitor subcircuit names."""
        path = os.path.join(self.pdk_root, "libs.tech/ngspice/models/capacitors_mod.lib")
        models = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.lower().startswith(".subckt "):
                        parts = stripped.split()
                        if len(parts) >= 2:
                            models.append(parts[1])

        if not models:
            models = ["cmim", "cap_rfcmim"]

        self.devices["capacitor"] = {
            "models": models,
            "model_default": "cap_cmim" if "cap_cmim" in models else (models[0] if models else "cmim"),
            "description": "IHP SG13G2 Capacitors",
        }

    def _load_corners(self):
        """Find corner lib files."""
        models_dir = os.path.join(self.pdk_root, "libs.tech/ngspice/models")
        corner_files = {
            "tt": ("cornerMOSlv.lib", "mos_tt"),
            "ff": ("cornerMOSlv.lib", "mos_ff"),
            "ss": ("cornerMOSlv.lib", "mos_ss"),
            "hv_tt": ("cornerMOShv.lib", "mos_tt"),
        }
        for corner, (filename, section) in corner_files.items():
            full_path = os.path.join(models_dir, filename)
            if os.path.exists(full_path):
                self.corners[corner] = full_path
                self._corner_sections[corner] = section

    def _find_model_lib(self):
        """Find the main model include path for ngspice simulations."""
        candidates = [
            os.path.join(self.pdk_root, "libs.tech/ngspice/models/cornerMOSlv.lib"),
            os.path.join(self.pdk_root, "libs.tech/ngspice/models/sg13g2_moslv_mod.lib"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                self.model_lib_path = candidate
                break

    def get_mos_constraints(self, variant="lv") -> dict:
        """Return NMOS constraints dict for the given variant (lv or hv)."""
        return self.devices.get(f"nmos_{variant}", {})

    def get_resistor_models(self) -> list:
        return self.devices.get("resistor", {}).get("models", ["rsil"])

    def get_capacitor_models(self) -> list:
        return self.devices.get("capacitor", {}).get("models", ["cmim"])

    def get_pdk_library(self) -> dict:
        """Returns a library dict for IHP_SG13G2 in the Library Manager format."""
        cells = {}

        mos_lv = self.devices.get("nmos_lv", {})
        mos_hv = self.devices.get("nmos_hv", {})
        pmos_lv = self.devices.get("pmos_lv", {})
        pmos_hv = self.devices.get("pmos_hv", {})

        cells["sg13_lv_nmos"] = {
            "views": ["schematic", "symbol"],
            "symbol_type": "nmos",
            "description": "Low-Voltage NMOS (Vds_max=1.5V)",
            "category": "MOS",
            "default_params": {
                "model": mos_lv.get("models_n", ["sg13_lv_nmos"])[0],
                "W": mos_lv.get("W_default", "2u"),
                "L": mos_lv.get("L_default", "0.13u"),
                "nf": "1",
                "m": "1",
            },
            "constraints": {
                "W_min": mos_lv.get("W_min", "0.15u"),
                "W_max": mos_lv.get("W_max", "10u"),
                "L_min": mos_lv.get("L_min", "0.13u"),
                "L_max": mos_lv.get("L_max", "10u"),
            },
            "spice_prefix": "X",
            "spice_format": "X{name} {D} {G} {S} {bulk} {model} W={W} L={L} nf={nf} m={m}",
        }
        cells["sg13_hv_nmos"] = {
            "views": ["schematic", "symbol"],
            "symbol_type": "nmos",
            "description": "High-Voltage NMOS (Vds_max=3.3V)",
            "category": "MOS",
            "default_params": {
                "model": mos_hv.get("models_n", ["sg13_hv_nmos"])[0],
                "W": mos_hv.get("W_default", "2u"),
                "L": mos_hv.get("L_default", "0.45u"),
                "nf": "1",
                "m": "1",
            },
            "constraints": {
                "W_min": mos_hv.get("W_min", "0.15u"),
                "W_max": mos_hv.get("W_max", "10u"),
                "L_min": mos_hv.get("L_min", "0.45u"),
                "L_max": mos_hv.get("L_max", "10u"),
            },
            "spice_prefix": "X",
            "spice_format": "X{name} {D} {G} {S} {bulk} {model} W={W} L={L} nf={nf} m={m}",
        }
        cells["sg13_lv_pmos"] = {
            "views": ["schematic", "symbol"],
            "symbol_type": "pmos",
            "description": "Low-Voltage PMOS (Vds_max=1.5V)",
            "category": "MOS",
            "default_params": {
                "model": pmos_lv.get("models_n", ["sg13_lv_pmos"])[0],
                "W": pmos_lv.get("W_default", "2u"),
                "L": pmos_lv.get("L_default", "0.13u"),
                "nf": "1",
                "m": "1",
            },
            "constraints": {
                "W_min": pmos_lv.get("W_min", "0.15u"),
                "W_max": pmos_lv.get("W_max", "10u"),
                "L_min": pmos_lv.get("L_min", "0.13u"),
                "L_max": pmos_lv.get("L_max", "10u"),
            },
            "spice_prefix": "X",
            "spice_format": "X{name} {D} {G} {S} {bulk} {model} W={W} L={L} nf={nf} m={m}",
        }
        cells["sg13_hv_pmos"] = {
            "views": ["schematic", "symbol"],
            "symbol_type": "pmos",
            "description": "High-Voltage PMOS (Vds_max=3.3V)",
            "category": "MOS",
            "default_params": {
                "model": pmos_hv.get("models_n", ["sg13_hv_pmos"])[0],
                "W": pmos_hv.get("W_default", "2u"),
                "L": pmos_hv.get("L_default", "0.45u"),
                "nf": "1",
                "m": "1",
            },
            "constraints": {
                "W_min": pmos_hv.get("W_min", "0.15u"),
                "W_max": pmos_hv.get("W_max", "10u"),
                "L_min": pmos_hv.get("L_min", "0.45u"),
                "L_max": pmos_hv.get("L_max", "10u"),
            },
            "spice_prefix": "X",
            "spice_format": "X{name} {D} {G} {S} {bulk} {model} W={W} L={L} nf={nf} m={m}",
        }

        res_descriptions = {
            "rsil": "n+ silicided resistor (~7 ohm/sq)",
            "rhigh": "n+ non-silicided resistor (~1260 ohm/sq)",
            "rppd": "p+ poly resistor (~260 ohm/sq)",
            "rsil_un": "unsilicided rsil",
        }
        for model in [m for m in self.get_resistor_models() if m not in ("ptap1", "ntap1", "Rparasitic")]:
            cells[model] = {
                "views": ["schematic", "symbol"],
                "symbol_type": "resistor",
                "description": res_descriptions.get(model, f"Resistor: {model}"),
                "category": "Passive",
                "default_params": {"model": model, "w": "0.5u", "l": "1u", "m": "1"},
                "constraints": {"w_min": "0.5u", "l_min": "0.5u"},
                "spice_prefix": "X",
                "spice_format": "X{name} {1} {2} {bn} {model} w={w} l={l} m={m}",
            }

        cap_descriptions = {
            "cap_cmim": "MIM capacitor (~2 fF/um^2)",
            "cap_rfcmim": "RF MIM capacitor",
        }
        for model in [m for m in self.get_capacitor_models() if "parasitic" not in m.lower()]:
            cells[model] = {
                "views": ["schematic", "symbol"],
                "symbol_type": "capacitor",
                "description": cap_descriptions.get(model, f"Capacitor: {model}"),
                "category": "Passive",
                "default_params": {"model": model, "w": "5u", "l": "5u", "m": "1"},
                "constraints": {"w_min": "1.8u", "l_min": "1.8u"},
                "spice_prefix": "X",
                "spice_format": "X{name} {1} {2} {model} w={w} l={l} m={m}",
            }

        hbt_path = os.path.join(self.pdk_root, "libs.tech/ngspice/models/sg13g2_hbt_mod.lib")
        if os.path.exists(hbt_path):
            cells["npn13G2"] = {
                "views": ["schematic", "symbol"],
                "symbol_type": "npn",
                "description": "SiGe HBT npn transistor",
                "category": "BJT",
                "default_params": {"model": "npn13G2", "le": "1u", "we": "0.48u", "nb": "1"},
                "constraints": {"le_min": "0.84u", "we_min": "0.48u"},
                "spice_prefix": "Q",
                "spice_format": "Q{name} {C} {B} {E} {S} {model} le={le} we={we} nb={nb}",
            }

        return {
            "name": "IHP_SG13G2",
            "version": self.tech_params.get("relName", "SG13G2"),
            "read_only": True,
            "auto_generated": True,
            "color": "#a6e3a1",
            "cells": cells,
        }

    def get_model_include(self, corner="tt") -> str:
        """Return the ngspice .lib include line for the given corner."""
        path = self.corners.get(corner, self.model_lib_path)
        if path:
            section = self._corner_sections.get(corner, corner)
            return f'.lib "{path}" {section}'
        return ""

    def to_dict(self) -> dict:
        """Serialize loaded tech data to dict (for caching)."""
        return {
            "pdk_root": self.pdk_root,
            "tech_params": self.tech_params,
            "devices": self.devices,
            "model_lib_path": self.model_lib_path,
            "corners": self.corners,
        }


class PDKManager(QObject):
    pdk_changed = pyqtSignal(str, dict, dict)

    def __init__(self):
        super().__init__()
        name, layers = load_pdk(default_pdk_path())
        self._name = name
        self._layers = dict(layers)
        self._tech_loader: Optional[PDKTechLoader] = None

    def load(self, path):
        try:
            name, layers = load_pdk(path)
            self._name = name
            self._layers = dict(layers)
        except Exception:
            if not self._layers:
                name, layers = load_pdk(default_pdk_path())
                self._name = name
                self._layers = dict(layers)

        pdk_root = self._find_pdk_root(path)
        if pdk_root:
            self._tech_loader = PDKTechLoader(pdk_root)
            self._name = self._tech_loader.tech_params.get("techName") or self._name
        else:
            self._tech_loader = None
        self.pdk_changed.emit(self._name, self._layers, self._tech_loader.to_dict() if self._tech_loader else {})
        return self._name, self._layers

    def _find_pdk_root(self, start_path: str) -> str:
        """Walk up from start_path to find directory containing libs.tech."""
        abs_path = os.path.abspath(start_path)
        d = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
        for _ in range(6):
            if os.path.isdir(os.path.join(d, "libs.tech")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return ""

    @property
    def layers(self):
        return self._layers

    @property
    def name(self):
        return self._name

    @property
    def tech(self):
        return self._tech_loader


PDK = PDKManager()


def load_ihp_pdk(pdk_root=None):
    """Load IHP SG13G2 PDK. If pdk_root is None, tries common locations."""
    if pdk_root is None:
        candidates = [
            "/home/whqkrel/tools/IHP-Open-PDK/ihp-sg13g2",
            os.path.expanduser("~/tools/IHP-Open-PDK/ihp-sg13g2"),
            "/usr/share/pdk/ihp-sg13g2",
        ]
        for candidate in candidates:
            if os.path.isdir(candidate):
                pdk_root = candidate
                break
    if pdk_root:
        PDK.load(os.path.join(
            pdk_root,
            "libs.tech/klayout/python/sg13g2_pycell_lib/sg13g2_tech.json",
        ))
    return PDK.tech
