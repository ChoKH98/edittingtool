"""
SPICE unit string parsing and formatting utilities.

Supports SI prefixes: f, p, n, u, m, k, M (meg), G
and electrical unit suffixes: V, A, Hz, Ohm, F, H, s, W

Examples:
  parse_value("1mV")    -> 0.001
  parse_value("500uV")  -> 0.0005
  parse_value("3.3V")   -> 3.3
  parse_value("1nA")    -> 1e-9
  parse_value("100Meg") -> 100e6
  parse_value("1.5k")   -> 1500.0
  parse_value("1e-3")   -> 0.001
  format_value(0.001)   -> "1m"
  format_spice(0.001)   -> "1e-03"
"""

import re

# SI prefix map (case-sensitive where needed)
_PREFIX = {
    'f': 1e-15,
    'p': 1e-12,
    'n': 1e-9,
    'u': 1e-6,
    'U': 1e-6,
    'm': 1e-3,
    'k': 1e3,
    'K': 1e3,
    'M': 1e6,
    'meg': 1e6,
    'MEG': 1e6,
    'Meg': 1e6,
    'G': 1e9,
    'T': 1e12,
}

# Unit suffixes to strip (case-insensitive)
_UNIT_SUFFIXES = re.compile(
    r'(V|A|Hz|Ohm|ohm|OHM|Ω|F|H|s|S|W|Wb|°C)$',
    re.IGNORECASE
)


def parse_value(s: str) -> float:
    """
    Parse a SPICE value string with optional SI prefix and unit suffix.
    Returns float. Raises ValueError on failure.

    Accepted formats:
      "1.5"        -> 1.5
      "1.5V"       -> 1.5
      "1mV"        -> 0.001
      "500uV"      -> 0.0005
      "3.3V"       -> 3.3
      "1nA"        -> 1e-9
      "100Meg"     -> 1e8
      "100MEG"     -> 1e8
      "1.5k"       -> 1500
      "1e-3"       -> 0.001
      "1e-3V"      -> 0.001
      "-5mV"       -> -0.005
    """
    if not s or not str(s).strip():
        return 0.0
    s = str(s).strip()

    try:
        return float(s)
    except ValueError:
        pass

    s_clean = _UNIT_SUFFIXES.sub('', s).strip()

    try:
        return float(s_clean)
    except ValueError:
        pass

    pat = re.match(
        r'^([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)'
        r'(meg|MEG|Meg|f|p|n|u|U|m|k|K|M|G|T)?'
        r'$',
        s_clean,
        re.IGNORECASE
    )
    if pat:
        num = float(pat.group(1))
        prefix = pat.group(2) or ''
        multiplier = _PREFIX.get(prefix, _PREFIX.get(prefix.lower(), 1.0))
        return num * multiplier

    if s_clean and not s_clean[-1].isdigit() and s_clean[-1] not in 'eE.':
        try:
            prefix_char = s_clean[-1]
            num = float(s_clean[:-1])
            multiplier = _PREFIX.get(prefix_char, 1.0)
            return num * multiplier
        except ValueError:
            pass

    raise ValueError(f"Cannot parse SPICE value: {s!r}")


def try_parse_value(s: str, default: float = 0.0) -> float:
    """Like parse_value but returns default on failure instead of raising."""
    try:
        return parse_value(s)
    except (ValueError, TypeError):
        return default


def format_value(v: float, unit: str = '') -> str:
    """
    Format a float value with the most readable SI prefix.
    format_value(0.001, 'V') -> "1mV"
    format_value(1500, 'Hz') -> "1.5kHz"
    format_value(3.3, 'V')   -> "3.3V"
    """
    if v == 0:
        return f"0{unit}"
    abs_v = abs(v)
    for prefix, mult in [
        ('T', 1e12), ('G', 1e9), ('M', 1e6), ('k', 1e3),
        ('', 1), ('m', 1e-3), ('u', 1e-6), ('n', 1e-9),
        ('p', 1e-12), ('f', 1e-15)
    ]:
        if abs_v >= mult * 0.999:
            scaled = v / mult
            if scaled == int(scaled):
                return f"{int(scaled)}{prefix}{unit}"
            return f"{scaled:.4g}{prefix}{unit}"
    return f"{v:.4g}{unit}"


def format_spice(v: float) -> str:
    """Format value for SPICE netlist (scientific notation, no prefix letters)."""
    if v == int(v) and abs(v) < 1e9:
        return str(int(v))
    return f"{v:.6g}"


def normalize_spice_value(s: str) -> str:
    """
    Parse a user-entered value string and return a clean SPICE-compatible string.
    "1mV" -> "1e-03"
    "3.3V" -> "3.3"
    "1.5k" -> "1500"
    "500uV" -> "5e-04"
    If parsing fails, return the original string unchanged.
    """
    try:
        v = parse_value(s)
        return format_spice(v)
    except ValueError:
        return s
