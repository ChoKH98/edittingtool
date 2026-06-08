SYMBOLS = {
    "nmos": {
        "lines": [
            # Gate lead
            (-3, 0, -1.5, 0),
            # Gate bar (vertical)
            (-1.5, -1.2, -1.5, 1.2),
            # Channel (body, vertical)
            (-0.5, -1.2, -0.5, 1.2),
            # Drain horizontal + vertical lead up
            (-0.5, 1.2, 0, 1.2),
            (0, 1.2, 0, 2.5),
            # Source horizontal + vertical lead down
            (-0.5, -1.2, 0, -1.2),
            (0, -1.2, 0, -2.5),
            # Bulk horizontal arrow line
            (-0.5, 0, 0.5, 0),
            # Arrowhead pointing right (NMOS: bulk->channel direction)
            (-0.8, 0.25, -0.5, 0),
            (-0.8, -0.25, -0.5, 0),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"G": (-3, 0), "D": (0, 2.5), "S": (0, -2.5)},
        "name_offset": (1.5, 0),
        "value_offset": (1.5, 1.2),
        "spice_prefix": "M",
        "params": {"W": "2u", "L": "0.13u", "nf": "1", "m": "1", "model": "sg13_lv_nmos"},
    },
    "pmos": {
        "lines": [
            # Gate lead (shorter, circle added separately)
            (-3, 0, -2.0, 0),
            # Gate bar
            (-1.5, -1.2, -1.5, 1.2),
            # Channel
            (-0.5, -1.2, -0.5, 1.2),
            # Drain lead (top)
            (-0.5, 1.2, 0, 1.2),
            (0, 1.2, 0, 2.5),
            # Source lead (bottom)
            (-0.5, -1.2, 0, -1.2),
            (0, -1.2, 0, -2.5),
            # Bulk arrow line
            (-0.5, 0, 0.5, 0),
            # Arrowhead pointing left (PMOS: channel->bulk direction)
            (-0.2, 0.25, -0.5, 0),
            (-0.2, -0.25, -0.5, 0),
        ],
        # Small circle on gate: (cx, cy, radius)
        "arcs": [],
        "circles": [(-1.75, 0, 0.25)],  # gate inversion bubble
        "pins": {"G": (-3, 0), "D": (0, 2.5), "S": (0, -2.5)},
        "name_offset": (1.5, 0),
        "value_offset": (1.5, 1.2),
        "spice_prefix": "M",
        "params": {"W": "2u", "L": "0.13u", "nf": "1", "m": "1", "model": "sg13_lv_pmos"},
    },
    "resistor": {
        "lines": [
            # Left lead
            (-3, 0, -1.5, 0),
            # Right lead
            (1.5, 0, 3, 0),
            # Rectangle top
            (-1.5, -0.6, 1.5, -0.6),
            # Rectangle bottom
            (-1.5, 0.6, 1.5, 0.6),
            # Rectangle left side
            (-1.5, -0.6, -1.5, 0.6),
            # Rectangle right side
            (1.5, -0.6, 1.5, 0.6),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"P": (-3, 0), "N": (3, 0)},
        "name_offset": (0, -1.5),
        "value_offset": (0, 1.5),
        "spice_prefix": "R",
        "params": {"value": "1k"},
    },
    "capacitor": {
        "lines": [
            # Top lead
            (0, -2.5, 0, -0.3),
            # Bottom lead
            (0, 0.3, 0, 2.5),
            # Top plate (horizontal bar)
            (-1.2, -0.3, 1.2, -0.3),
            # Bottom plate (horizontal bar)
            (-1.2, 0.3, 1.2, 0.3),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"P": (0, -2.5), "N": (0, 2.5)},
        "name_offset": (1.8, 0),
        "value_offset": (-1.8, 0),
        "spice_prefix": "C",
        "params": {"value": "1p"},
    },
    "inductor": {
        "lines": [
            # Left lead
            (-3, 0, -2, 0),
            # Right lead
            (2, 0, 3, 0),
        ],
        # 4 half-circle bumps above the line, each radius=0.5, spanning 180 degrees upward
        # arc format: (cx, cy, radius, start_angle_deg, span_angle_deg)
        # Qt arc: start=0 is 3 o'clock, positive = counter-clockwise
        # We want half circles from right to left (above the line = upward bumps)
        # For bump at cx=-1.5: start=0deg, span=180deg (semicircle above)
        "arcs": [
            (-1.5, 0, 0.5, 0, 180),
            (-0.5, 0, 0.5, 0, 180),
            (0.5, 0, 0.5, 0, 180),
            (1.5, 0, 0.5, 0, 180),
        ],
        "circles": [],
        "pins": {"P": (-3, 0), "N": (3, 0)},
        "name_offset": (0, -1.5),
        "value_offset": (0, 1.5),
        "spice_prefix": "L",
        "params": {"value": "1n"},
    },
    "npn": {
        "lines": [
            # Base lead
            (-3, 0, -1.2, 0),
            # Vertical base line
            (-1.2, -1.5, -1.2, 1.5),
            # Collector lead
            (-1.2, 1.0, 0, 1.5),
            (0, 1.5, 0, 2.5),
            # Emitter lead with outward arrow
            (-1.2, -1.0, 0, -1.5),
            (0, -1.5, 0, -2.5),
            (-0.4, -1.2, 0, -1.5),
            (-0.4, -0.9, 0, -1.5),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"B": (-3, 0), "C": (0, 2.5), "E": (0, -2.5)},
        "name_offset": (1.5, 0),
        "value_offset": (1.5, 1.2),
        "spice_prefix": "Q",
        "params": {"le": "1u", "we": "0.48u", "nb": "1", "model": "npn13G2"},
    },
    "vdc": {
        "lines": [
            (0, -2.5, 0, -1.2),
            (0, 1.2, 0, 2.5),
            # "+" at top inside circle
            (0, 0.3, 0, 0.9),
            (-0.3, 0.6, 0.3, 0.6),
            # "-" at bottom inside circle
            (-0.3, -0.6, 0.3, -0.6),
        ],
        "arcs": [(0, 0, 1.2, 0, 360)],
        "circles": [],
        "pins": {"P": (0, -2.5), "N": (0, 2.5)},
        "name_offset": (1.8, 0),
        "value_offset": (-2.0, 0),
        "spice_prefix": "V",
        "params": {"dc": "1.8"},
    },
    "vpulse": {
        "lines": [
            (0, -2.5, 0, -1.2),
            (0, 1.2, 0, 2.5),
            # Pulse waveform inside circle
            (-0.7, -0.3, -0.7, 0.4),
            (-0.7, 0.4, -0.2, 0.4),
            (-0.2, 0.4, -0.2, -0.3),
            (-0.2, -0.3, 0.3, -0.3),
            (0.3, -0.3, 0.3, 0.4),
            (0.3, 0.4, 0.7, 0.4),
        ],
        "arcs": [(0, 0, 1.2, 0, 360)],
        "circles": [],
        "pins": {"P": (0, -2.5), "N": (0, 2.5)},
        "name_offset": (1.8, 0),
        "value_offset": (-2.2, 0),
        "spice_prefix": "V",
        "params": {"v1": "0", "v2": "1.8", "td": "0", "tr": "10p", "tf": "10p", "pw": "500p", "per": "1n"},
    },
    "vsin": {
        "lines": [
            (0, -2.5, 0, -1.2),
            (0, 1.2, 0, 2.5),
            # Sine approximation: 4 short line segments
            (-0.7, 0, -0.35, -0.5),
            (-0.35, -0.5, 0, 0),
            (0, 0, 0.35, 0.5),
            (0.35, 0.5, 0.7, 0),
        ],
        "arcs": [(0, 0, 1.2, 0, 360)],
        "circles": [],
        "pins": {"P": (0, -2.5), "N": (0, 2.5)},
        "name_offset": (1.8, 0),
        "value_offset": (-2.2, 0),
        "spice_prefix": "V",
        "params": {"voff": "0", "vamp": "1", "freq": "1G", "td": "0", "theta": "0"},
    },
    "vpwl": {
        "lines": [
            (0, -2.5, 0, -1.2),
            (0, 1.2, 0, 2.5),
            # PWL waveform icon inside circle
            (-0.7, 0.3, -0.3, 0.3),
            (-0.3, 0.3, (0), -0.3),
            (0, -0.3, 0.4, -0.3),
            (0.4, -0.3, 0.7, 0.1),
        ],
        "arcs": [(0, 0, 1.2, 0, 360)],
        "circles": [],
        "pins": {"P": (0, -2.5), "N": (0, 2.5)},
        "name_offset": (1.8, 0),
        "value_offset": (-2.2, 0),
        "spice_prefix": "V",
        "params": {"pwl": "0 0 1n 1.8 2n 1.8 3n 0"},
    },
    "idc": {
        "lines": [
            (0, -2.5, 0, -1.2),
            (0, 1.2, 0, 2.5),
            # Arrow pointing up inside circle
            (0, -0.6, 0, 0.3),
            # Arrowhead
            (-0.3, 0.0, 0, 0.5),
            (0.3, 0.0, 0, 0.5),
        ],
        "arcs": [(0, 0, 1.2, 0, 360)],
        "circles": [],
        "pins": {"P": (0, -2.5), "N": (0, 2.5)},
        "name_offset": (1.8, 0),
        "value_offset": (-2.0, 0),
        "spice_prefix": "I",
        "params": {"dc": "1m"},
    },
    "vdd": {
        "lines": [
            # Stem going up from pin
            (0, 0, 0, 1.5),
            # Horizontal bar at top
            (-0.8, 1.5, 0.8, 1.5),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"P": (0, 0)},
        "name_offset": (1.2, 0.8),
        "value_offset": (0, 0),
        "spice_prefix": "",
        "params": {"net": "VDD"},
    },
    "vss": {
        "lines": [
            # Stem going down from pin
            (0, 0, 0, -1.5),
            # Three horizontal bars getting shorter (ground-style)
            (-0.8, -1.5, 0.8, -1.5),
            (-0.5, -1.9, 0.5, -1.9),
            (-0.2, -2.3, 0.2, -2.3),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"P": (0, 0)},
        "name_offset": (1.2, -0.8),
        "value_offset": (0, 0),
        "spice_prefix": "",
        "params": {"net": "VSS"},
    },
    "gnd": {
        "lines": [
            (0, 0, 0, -1.5),
            (-0.8, -1.5, 0.8, -1.5),
            (-0.5, -1.9, 0.5, -1.9),
            (-0.2, -2.3, 0.2, -2.3),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"P": (0, 0)},
        "name_offset": (1.2, -0.8),
        "value_offset": (0, 0),
        "spice_prefix": "",
        "params": {"net": "0"},
    },
    "port": {
        "lines": [
            (-1, 0, 0.5, 0),
            (0.5, -0.8, 1.5, 0),
            (0.5, 0.8, 1.5, 0),
            (0.5, -0.8, 0.5, 0.8),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"P": (-1, 0)},
        "name_offset": (0, -1.5),
        "value_offset": (0, 0),
        "spice_prefix": "",
        "params": {"net": "port"},
    },
    "port_in": {
        "lines": [
            (-1.5, 0, -0.5, 0),
            (-0.5, -0.8, 0.5, 0),
            (-0.5, 0.8, 0.5, 0),
            (-0.5, -0.8, -0.5, 0.8),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"P": (-1.5, 0)},
        "name_offset": (0, -1.5),
        "value_offset": (0, 0),
        "spice_prefix": "",
        "params": {"net": "in"},
    },
    "port_out": {
        "lines": [
            (-0.5, 0, 0.5, 0),
            (0.5, -0.8, 1.5, 0),
            (0.5, 0.8, 1.5, 0),
            (0.5, -0.8, 0.5, 0.8),
        ],
        "arcs": [],
        "circles": [],
        "pins": {"P": (-0.5, 0)},
        "name_offset": (0, -1.5),
        "value_offset": (0, 0),
        "spice_prefix": "",
        "params": {"net": "out"},
    },
}
