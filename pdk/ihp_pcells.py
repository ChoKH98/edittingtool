"""
IHP SG13G2 Parametric Layout Cells (PCells).
generate(cell_name, params) -> list of shape dicts (coords in um).
"""

# Supported cell names and their default parameters
PCELL_DEFAULTS = {
    'sg13_lv_nmos': {'w': 2.0, 'l': 0.13, 'nf': 1, 'ng': 1},
    'sg13_hv_nmos': {'w': 2.0, 'l': 0.45, 'nf': 1, 'ng': 1},
    'sg13_lv_pmos': {'w': 4.0, 'l': 0.13, 'nf': 1, 'ng': 1},
    'sg13_hv_pmos': {'w': 4.0, 'l': 0.45, 'nf': 1, 'ng': 1},
    'rsil': {'w': 0.5, 'l': 2.0, 'ps': 1},
    'rhigh': {'w': 0.5, 'l': 2.0, 'ps': 1},
    'rppd': {'w': 0.5, 'l': 2.0, 'ps': 1},
    'cap_cmim': {'w': 2.0, 'l': 2.0, 'wfeed': 0.4},
    'npn13G2': {'le': 1.0, 'we': 0.48, 'nbc': 1},
}

PCELL_GENERATORS = {}


def register(name):
    def decorator(fn):
        PCELL_GENERATORS[name] = fn
        return fn
    return decorator


def generate(cell_name, params=None):
    """Return list of shape dicts for the given cell with given params."""
    if params is None:
        params = {}
    defaults = PCELL_DEFAULTS.get(cell_name, {})
    p = {
        **defaults,
        **{
            k: float(v) if k not in ('nf', 'ng', 'ps', 'nbc') else int(float(v))
            for k, v in params.items()
            if k in defaults
        },
    }
    fn = PCELL_GENERATORS.get(cell_name)
    if fn is None:
        return []
    return fn(p)


# MOSFET helpers

def _mos_shapes(p, is_pmos=False, is_hv=False):
    """Generate MOSFET layout shapes."""
    shapes = []
    w = float(p['w'])          # channel width per finger (um)
    l = float(p['l'])          # gate length (um)
    nf = int(p.get('nf', 1))   # number of fingers
    int(p.get('ng', 1))        # number of gate stripes (reserved)

    poly_ext = 0.25 if is_hv else 0.18
    cont_sz = 0.16
    cont_enc = 0.06
    m1_enc = 0.04
    sd_w = 0.32

    finger_w = sd_w + l + sd_w
    total_w = finger_w * nf + sd_w

    activ_x = 0.0
    activ_y = 0.0
    activ_w = total_w
    activ_h = w + 2 * cont_enc
    shapes.append({
        'type': 'rect', 'layer': 'Activ',
        'x': activ_x, 'y': activ_y, 'w': activ_w, 'h': activ_h,
    })

    for i in range(nf):
        gx = sd_w + i * (sd_w + l)
        shapes.append({
            'type': 'rect', 'layer': 'GatPoly',
            'x': gx,
            'y': activ_y - poly_ext,
            'w': l,
            'h': activ_h + 2 * poly_ext,
        })

    for i in range(nf + 1):
        region_x = i * (sd_w + l)
        cx = region_x + cont_enc
        cy = activ_y + cont_enc
        n_cont_x = max(1, int((sd_w - 2 * cont_enc) / 0.32))
        n_cont_y = max(1, int(w / 0.32))
        for ix in range(n_cont_x):
            for iy in range(n_cont_y):
                shapes.append({
                    'type': 'rect', 'layer': 'Cont',
                    'x': cx + ix * 0.32,
                    'y': cy + iy * 0.32,
                    'w': cont_sz,
                    'h': cont_sz,
                })

    for i in range(nf + 1):
        region_x = i * (sd_w + l)
        shapes.append({
            'type': 'rect', 'layer': 'M1',
            'x': region_x,
            'y': activ_y - m1_enc,
            'w': sd_w,
            'h': activ_h + 2 * m1_enc,
        })

    for i in range(nf):
        gx = sd_w + i * (sd_w + l)
        shapes.append({
            'type': 'rect', 'layer': 'M1',
            'x': gx - m1_enc,
            'y': activ_y + activ_h + poly_ext - 0.2,
            'w': l + 2 * m1_enc,
            'h': 0.2,
        })

    if is_pmos:
        nwell_enc = 0.31
        shapes.append({
            'type': 'rect', 'layer': 'NWell',
            'x': activ_x - nwell_enc,
            'y': activ_y - nwell_enc,
            'w': activ_w + 2 * nwell_enc,
            'h': activ_h + 2 * nwell_enc,
        })
        shapes.append({
            'type': 'rect', 'layer': 'pSD',
            'x': activ_x,
            'y': activ_y,
            'w': activ_w,
            'h': activ_h,
        })

    return shapes


@register('sg13_lv_nmos')
def draw_lv_nmos(p):
    return _mos_shapes(p, is_pmos=False, is_hv=False)


@register('sg13_hv_nmos')
def draw_hv_nmos(p):
    return _mos_shapes(p, is_pmos=False, is_hv=True)


@register('sg13_lv_pmos')
def draw_lv_pmos(p):
    return _mos_shapes(p, is_pmos=True, is_hv=False)


@register('sg13_hv_pmos')
def draw_hv_pmos(p):
    return _mos_shapes(p, is_pmos=True, is_hv=True)


# Resistors

def _resistor_shapes(p, layer):
    shapes = []
    w = float(p['w'])
    l = float(p['l'])
    cont_sz = 0.16
    m1_enc = 0.1
    term_l = 0.4

    shapes.append({
        'type': 'rect', 'layer': layer,
        'x': 0, 'y': 0, 'w': l + 2 * term_l, 'h': w,
    })

    shapes.append({
        'type': 'rect', 'layer': 'Cont',
        'x': 0.12, 'y': (w - cont_sz) / 2,
        'w': cont_sz, 'h': cont_sz,
    })
    shapes.append({
        'type': 'rect', 'layer': 'M1',
        'x': 0, 'y': -m1_enc,
        'w': term_l, 'h': w + 2 * m1_enc,
    })

    rx = l + 2 * term_l - 0.12 - cont_sz
    shapes.append({
        'type': 'rect', 'layer': 'Cont',
        'x': rx, 'y': (w - cont_sz) / 2,
        'w': cont_sz, 'h': cont_sz,
    })
    shapes.append({
        'type': 'rect', 'layer': 'M1',
        'x': l + term_l, 'y': -m1_enc,
        'w': term_l, 'h': w + 2 * m1_enc,
    })

    return shapes


@register('rsil')
def draw_rsil(p):
    return _resistor_shapes(p, 'Activ')


@register('rhigh')
def draw_rhigh(p):
    return _resistor_shapes(p, 'GatPoly')


@register('rppd')
def draw_rppd(p):
    return _resistor_shapes(p, 'pSD')


# MIM Capacitor

@register('cap_cmim')
def draw_cap_cmim(p):
    shapes = []
    w = float(p['w'])
    l = float(p['l'])
    feed = float(p.get('wfeed', 0.4))
    m2_enc = 0.2

    shapes.append({
        'type': 'rect', 'layer': 'M2',
        'x': 0, 'y': 0, 'w': l + 2 * m2_enc, 'h': w + 2 * m2_enc,
    })
    shapes.append({
        'type': 'rect', 'layer': 'TM2',
        'x': m2_enc, 'y': m2_enc, 'w': l, 'h': w,
    })

    via_sz = 0.18
    via_sp = 0.36
    nx = max(1, int((l + 2 * m2_enc - 0.1) / via_sp))
    ny = max(1, int((w + 2 * m2_enc - 0.1) / via_sp))
    for ix in range(nx):
        for iy in range(ny):
            shapes.append({
                'type': 'rect', 'layer': 'Via1',
                'x': 0.05 + ix * via_sp,
                'y': 0.05 + iy * via_sp,
                'w': via_sz,
                'h': via_sz,
            })

    shapes.append({
        'type': 'rect', 'layer': 'M1',
        'x': -feed, 'y': m2_enc,
        'w': l + 2 * m2_enc + feed, 'h': 0.4,
    })
    return shapes


# NPN BJT

@register('npn13G2')
def draw_npn(p):
    shapes = []
    le = float(p.get('le', 1.0))
    we = float(p.get('we', 0.48))
    enc = 0.2

    shapes.append({
        'type': 'rect', 'layer': 'Activ',
        'x': 0, 'y': 0, 'w': we, 'h': le,
    })
    shapes.append({
        'type': 'rect', 'layer': 'pSD',
        'x': -enc, 'y': -enc,
        'w': we + 2 * enc, 'h': le + 2 * enc,
    })

    nw_enc = 0.5
    shapes.append({
        'type': 'rect', 'layer': 'NWell',
        'x': -nw_enc, 'y': -nw_enc,
        'w': we + 2 * nw_enc, 'h': le + 2 * nw_enc,
    })

    cont_sz = 0.16
    nc = max(1, int((le - 0.1) / 0.32))
    for i in range(nc):
        shapes.append({
            'type': 'rect', 'layer': 'Cont',
            'x': (we - cont_sz) / 2,
            'y': 0.05 + i * 0.32,
            'w': cont_sz,
            'h': cont_sz,
        })

    shapes.append({
        'type': 'rect', 'layer': 'M1',
        'x': -0.04, 'y': -0.04,
        'w': we + 0.08, 'h': le + 0.08,
    })
    return shapes
