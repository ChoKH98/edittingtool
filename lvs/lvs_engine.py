class LvsError:
    def __init__(self, category, component, detail):
        self.category = category
        self.component = component
        self.detail = detail
    def __repr__(self):
        return f'LvsError({self.category}, {self.component}: {self.detail})'

class LvsResult:
    def __init__(self):
        self.matches = []
        self.errors = []
        self.warnings = []

class LvsEngine:
    def run(self, layout_netlist, schematic_netlist):
        result = LvsResult()
        if not layout_netlist and not schematic_netlist:
            return result
        layout_comps = set(layout_netlist.keys()) if layout_netlist else set()
        schem_comps = set(schematic_netlist.keys()) if schematic_netlist else set()
        for comp in schem_comps - layout_comps:
            result.errors.append(LvsError('Missing in layout', comp,
                f'{comp} present in schematic but not in layout'))
        for comp in layout_comps - schem_comps:
            result.errors.append(LvsError('Extra in layout', comp,
                f'{comp} present in layout but not in schematic'))
        for comp in schem_comps & layout_comps:
            l_pins = layout_netlist[comp]
            s_pins = schematic_netlist[comp]
            l_type = l_pins.get('type','')
            s_type = s_pins.get('type','')
            if l_type != s_type:
                result.errors.append(LvsError('Pin mismatch', comp,
                    f'type mismatch: layout={l_type} schematic={s_type}'))
                continue
            mismatch = False
            for pin in set(list(l_pins.keys()) + list(s_pins.keys())):
                if pin == 'type':
                    continue
                l_net = l_pins.get(pin)
                s_net = s_pins.get(pin)
                if l_net != s_net:
                    if l_net and s_net:
                        result.warnings.append(LvsError('Net name mismatch', comp,
                            f'pin {pin}: layout={l_net} schematic={s_net}'))
                    else:
                        result.errors.append(LvsError('Pin mismatch', comp,
                            f'pin {pin}: layout={l_net} schematic={s_net}'))
                    mismatch = True
            if not mismatch:
                result.matches.append(comp)
        return result
