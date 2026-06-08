"""PEX (Parasitic Extraction) engine for IHP SG13G2."""

# Sheet resistance (ohm/sq) per layer
RSHEET = {
    "GatPoly": 7.0,
    "M1": 0.08,
    "M2": 0.06,
    "M3": 0.05,
    "M4": 0.04,
}

# Area capacitance (fF/um^2) per layer to substrate
CCAP = {
    "M1": 0.03,
    "M2": 0.02,
    "M3": 0.015,
    "M4": 0.010,
    "GatPoly": 0.05,
}


class PexEngine:
    """RC parasitic extraction for IHP SG13G2 layout shapes."""

    def run(self, shapes):
        """Extract RC parasitics from a list of shape dicts.

        Each shape dict has keys: type, layer, x, y, w, h, label.
        Returns list of dicts with keys: layer, label, R_ohm, C_fF, area_um2.
        """
        results = []
        for shape in shapes:
            layer = shape.get("layer", "")
            w = shape.get("w", 0)
            h = shape.get("h", 0)
            if w <= 0 or h <= 0:
                continue
            in_r = layer in RSHEET
            in_c = layer in CCAP
            if not in_r and not in_c:
                continue
            r_ohm = RSHEET[layer] * (h / w) if in_r else 0.0
            c_ff = CCAP[layer] * w * h if in_c else 0.0
            results.append({
                "layer": layer,
                "label": shape.get("label", ""),
                "R_ohm": r_ohm,
                "C_fF": c_ff,
                "area_um2": w * h,
            })
        return results
