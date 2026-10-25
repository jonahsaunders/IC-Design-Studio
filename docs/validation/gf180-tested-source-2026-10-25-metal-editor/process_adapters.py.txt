"""Explicit process capabilities. A catalog entry is never layout qualification.

Adapters own native recipe dispatch and physical engine inputs. Model emission
stays in the immutable catalog binding; it is not translated by this interface.
"""
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from .model import digest, file_digest


@dataclass(frozen=True)
class ProcessAdapter:
    id: str
    module: str
    recipes: tuple
    technology_file: str
    setup_file: str
    drawing_datatype: int = 20
    label_datatype: int = 5
    port_datatypes: tuple = (5, 16)

    def implementation(self):
        return import_module('.' + self.module, __package__)

    def layers(self, technology):
        return self.implementation().layers(technology)

    def engine_assets(self, technology):
        self.layers(technology)
        from .interoperability import tool_asset
        return {'technology':tool_asset(technology,'magic','technology',self.technology_file),
                'setup':tool_asset(technology,'netgen','setup',self.setup_file)}


SKY130 = ProcessAdapter('sky130A', 'sky130_layout', ('mos', 'inverter', 'ring', 'current_mirror', 'analog_bank',
                       'mim_capacitor', 'poly_resistor', 'contacted_guard', 'tied_mos_dummy'),
                       'libs.tech/magic/sky130A.tech', 'libs.tech/netgen/sky130A_setup.tcl')
GF180 = ProcessAdapter('gf180mcuC', 'gf180_layout', ('mos', 'inverter'),
                       'libs.tech/magic/gf180mcuC.tech', 'libs.tech/netgen/gf180mcuC_setup.tcl',
                       drawing_datatype=0, label_datatype=10, port_datatypes=(10,))
GF180D = ProcessAdapter('gf180mcuD', 'gf180_layout', ('mos', 'inverter'),
                       'libs.tech/magic/gf180mcuD.tech', 'libs.tech/netgen/gf180mcuD_setup.tcl',
                       drawing_datatype=0, label_datatype=10, port_datatypes=(10,))
IHP = ProcessAdapter('ihp-sg13g2', 'ihp_layout', ('mos', 'inverter'),
                     'libs.tech/magic/ihp-sg13g2.tech', 'libs.tech/netgen/ihp-sg13g2_setup.tcl',
                     drawing_datatype=0, label_datatype=2, port_datatypes=(2,25))
ADAPTERS = {p.id: p for p in (SKY130, GF180, GF180D, IHP)}


class DeclaredProcessAdapter:
    """Physical verification for any registered PDK with explicit locked decks."""
    recipes = ()
    def __init__(self,technology):
        self.id=technology['package_lock']['id']
        self.technology_file=technology['interoperability']['tools']['magic']['technology']
        self.setup_file=technology['interoperability']['tools']['netgen']['setup']
    def engine_assets(self,technology):
        from .interoperability import tool_asset
        return {'technology':tool_asset(technology,'magic','technology'),
                'setup':tool_asset(technology,'netgen','setup')}
    def implementation(self):
        raise ValueError('This PDK supports external physical verification. Import its generated device geometry and assign terminals, or install a native geometry adapter.')


def physical_adapter(technology):
    key=technology.get('package_lock',{}).get('id')
    if key in ADAPTERS:return ADAPTERS[key]
    tools=technology.get('interoperability',{}).get('tools',{})
    if tools.get('magic',{}).get('technology') and tools.get('netgen',{}).get('setup'):
        return DeclaredProcessAdapter(technology)
    raise ValueError('Configure matching locked Magic technology and Netgen setup files for this PDK revision.')


def layer_datatypes(technology):
    process = ADAPTERS.get(technology.get('package_lock', {}).get('id'))
    return (process.drawing_datatype, process.label_datatype, process.port_datatypes) if process else (20, 5, (5,16))


def inverter_devices(p, cid):
    return adapter(p['pdk']).implementation().inverter_devices(p, cid)


def regenerate_mos(p, cid, did):
    return adapter(p['pdk']).implementation().regenerate_mos(p, cid, did)


def adapter(technology):
    key = technology.get('package_lock', {}).get('id')
    if key not in ADAPTERS:
        raise ValueError((key or 'This technology') + ': native physical generation and saved-bench layout verification are not implemented. Model simulation and physical qualification are separate capabilities.')
    return ADAPTERS[key]


def capabilities(technology, installed=False):
    lock = technology.get('package_lock', {})
    catalog = technology.get('simulation', {}).get('catalog', {})
    native = ADAPTERS.get(lock.get('id'))
    reason = ''
    if native:
        try:
            native.layers(technology)
            # These recipes use the locked extraction/rule decks as their
            # process contract; an ID or catalog alone is not sufficient.
            if native is not SKY130: native.engine_assets(technology)
        except (ValueError, OSError, KeyError) as exc: reason = str(exc); native = None
    if not native and not reason: reason = 'No native physical adapter implemented for this process.'
    evidence = 'No release physical qualification for this revision.'
    verified = {
        'sky130A': ('b19a81c06779a79d', '290edf827f10135ca494897c528d892e23babc2dd5983f03c5755db8f126b434',
                    'Bounded SKY130 1.8 V MOS, inverter, ring and equal-device current-mirror fixtures; verify each edited design.'),
        'gf180mcuC': ('a1610a6b160f44d6', 'ec942a4a9ceb40bb0665de1ac84824f0f86a067fa7273626041f4fcb7fc2e6ae',
                      'Bounded GF180 C 3.3 V single-finger NMOS/PMOS and inverter fixtures; W 1–10 µm, L 0.28–2 µm. Verify each edited design.'),
    }
    expected = verified.get(lock.get('id'))
    student_verified = {
        ('gf180mcuC', '627ca682d68e1e92'): ('4c79aea1becb579297045c3ac832ab9c3d8779f43c4c51391d05a81e8e1b0c6a', 'GF180 C 3.3 V', '0.28'),
        ('gf180mcuD', '7dd87219f1333dbb'): ('15fa22041b0add5f2be3df6eafd914edc4134bb57370ed4a7118de519712ad5a', 'GF180 D 3.3 V', '0.28'),
        ('ihp-sg13g2', '3abac20fcb57e184'): ('7fcea14348e40f54c70fd4d781b009a144615d020044ece423080e21ef39aabb', 'IHP SG13G2 1.2 V', '0.13'),
    }
    student = student_verified.get((lock.get('id'), lock.get('revision')))
    if student:
        expected = (lock['revision'], student[0],
                    f'Bounded {student[1]} single-finger NMOS/PMOS inverter; W 1–10 µm, L {student[2]}–2 µm. DC/transient, full DRC/LVS, fault/repair and four size boundaries passed. Verify each edited design.')
    if native and expected and lock.get('revision') == expected[0] and digest(lock.get('files', {})) == expected[1]: evidence = expected[2]
    try:physical=physical_adapter(technology);physical.engine_assets(technology);external_verification=True
    except (ValueError,OSError,KeyError):external_verification=False
    native_layout=list(native.recipes) if native else []
    if native is SKY130 and external_verification:
        from .sky130_bipolar_rules import TECH_SHA256
        if file_digest(native.engine_assets(technology)['technology'])==TECH_SHA256:native_layout.append('fixed_pnp')
    from .em_technology import capabilities as em_capabilities
    return {
        'installed': installed or bool(lock),
        'indexed': len(catalog),
        'placeable': sum(not b.get('unavailable') for b in catalog.values()),
        'simulation': bool(technology.get('simulation', {}).get('includes')),
        'native_layout': native_layout,
        'external_verification':external_verification,
        'inductor_em':em_capabilities(technology),
        'native_reason': reason,
        'physical_evidence': evidence,
        'runtime': 'The Student Hub uses matching compiled IHP OSDI models in the included Linux/WSL runtime. Custom native simulation needs compatible OSDI libraries.' if lock.get('id') == 'ihp-sg13g2' else 'Model simulation requires configured ngspice and intact locked assets.',
    }


def capability_text(technology, installed=False):
    c = capabilities(technology, installed)
    return '\n'.join([
        'Installed / registered: ' + ('yes' if c['installed'] else 'no'),
        f"Catalog: {c['placeable']} placeable / {c['indexed']} indexed symbols",
        'Model bindings: ' + ('available. ' + c['runtime'] if c['simulation'] else 'no model include binding'),
        'Native layout: ' + (', '.join(c['native_layout']) if c['native_layout'] else c['native_reason']),
        'External physical verification: ' + ('locked decks available' if c['external_verification'] else 'configure matching locked decks'),
        'Inductor geometry: ' + ('declared layer/via rules available' if c['inductor_em']['geometry'] else c['inductor_em']['geometry_reason']),
        'Physical EM profile: ' + ('routing layers mapped; selected layout still requires checks' if c['inductor_em']['profile_ready']
                                   else '; '.join(c['inductor_em']['profile_issues'][:3])),
        'Release physical evidence: ' + c['physical_evidence'],
    ])


def generate_inverter(p, cid, replace=False):
    return adapter(p['pdk']).implementation().generate_inverter(p, cid, replace)


def install_mos(p, cid, did, x=0, y=0):
    return adapter(p['pdk']).implementation().install_mos(p, cid, did, x, y)


def audit(p, cid):
    c = next(c for c in p['cells'] if c['id'] == cid)
    if not c.get('pdk_layouts'): return []
    try: return adapter(p['pdk']).implementation().audit(p, cid)
    except ValueError as exc:
        return [{'severity': 'error', 'code': 'PDK.ADAPTER', 'object': '',
                 'message': str(exc), 'fingerprint': digest(str(exc))}]
