"""Qualify native SKY130 resistor preservation, terminal RC and electrical use.

One tied-substrate poly-resistor coupon, strict DRC/LVS, a parameter-preserving
contracted reference, and independent ngspice terminal-admittance comparisons.
This is a bounded source regression, not broad process or foundry signoff.
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from icstudio.model import atomic_write, file_digest, uid, scalar
from icstudio.sky130_devices import install_dummy, layers
from icstudio.external_tools import extraction_commands, executable_info
from icstudio.silicon_flow import magic_script
from icstudio.magic_rc import contract
from icstudio.testbenches import native_subcircuit
from scripts.qualify_sky130_devices import fixture, verify, measure


def qualify(args):
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a new primitive RC evidence directory.')
    out.mkdir(parents=True)
    report = {'status': 'failed', 'signoff': False,
              'scope': 'One 1x20um SKY130 poly resistor with an explicit substrate tie; nominal 27C only.'}
    sources = ['icstudio/magic_rc.py', 'icstudio/silicon_flow.py', 'icstudio/rc_islands.py',
               'icstudio/sky130_devices.py', 'icstudio/sky130_layout.py', 'scripts/qualify_rc_primitives.py']
    report['source'] = {name: file_digest(ROOT / name) for name in sources}
    try:
        root = args.pdk.resolve(); manifest = json.loads((root / 'package.json').read_text())
        lock = json.loads((ROOT / 'examples/sky130-qualification-lock.json').read_text())
        if file_digest(root / 'package.json') != lock['manifest_sha256']:
            raise ValueError('Use the committed SKY130 physical qualification adapter.')
        tech = manifest['technology']
        tech.update(package_root=str(root), package_lock={k: manifest[k] for k in ('id', 'revision', 'files')})
        tools = {name: str(Path(getattr(args, name)).resolve()) for name in ('magic', 'netgen', 'ngspice')}
        report['tools'] = {name: executable_info(path) for name, path in tools.items()}
        library = Path(tools['magic']).parent.parent / 'lib/magic/tcl/tclmagic.so'
        if library.is_file():
            report['tools']['magic']['implementation_sha256'] = file_digest(library)
        p, c = fixture(tech, 'res', 1, 20)
        dummy = install_dummy(p, c['id'], 'MDUMMY', 'NMOS', 'N', x=30000, y=0)
        c = p['cells'][0]
        body = next(pin for pin in c['layout_pins'] if pin['device_id'] == dummy['id'] and pin['pin'] == 'b')['point']
        negative = next(pin for pin in c['layout_ports'] if pin['name'] == 'N')['point']
        c['shapes'].append(dict(id=uid(), kind='path', layer=layers(tech)['m1'],
                                points=[negative, [body[0], negative[1]], body], width=340,
                                net='N', device_id=''))
        report['physical'] = verify(p, c, out / 'physical', tools)
        commands, _ = extraction_commands('rc')
        work = out / 'rc'
        magic_script(tools['magic'], root / 'libs.tech/magic/sky130A.tech', out / 'physical/layout.gds',
                     c['name'], c['ports'], work, commands + 'ext2spice -o extracted.spice')
        normalization = json.loads((work / 'rc-normalization.json').read_text())
        text = (work / 'extracted.spice').read_text()
        contracted = contract(text, normalization); atomic_write(out / 'contracted.spice', contracted)
        passives = [d for d in normalization['devices'] if d.get('name')]
        if len(passives) != 1 or passives[0]['model'] != 'sky130_fd_pr__res_generic_po':
            raise ValueError('Expected one preserved physical poly resistor.')
        physical_name = passives[0]['name'].casefold(); leads = []
        for port, terminal in zip(c['ports'], passives[0]['terminals']):
            rows = [line.split() for line in text.splitlines()
                    if line and line[0].upper() == 'R' and line.split()[0].casefold() != physical_name]
            values = [scalar(row[3]) for row in rows if set(row[1:3]) == {port, terminal}]
            if len(values) != 1:
                raise ValueError('The independent lead-resistance fixture changed topology.')
            leads.extend(values)
        values = measure(p, {'schematic': native_subcircuit(p, c['id']), 'contracted': contracted,
                              'extracted': (work / 'electrical.spice').read_text()},
                         'res', 'nominal', 27, tools, out / 'simulation')
        if not math.isclose(values['schematic'], values['contracted'], rel_tol=1e-10):
            raise ValueError('Contracted primitive model differs from the schematic.')
        delta = values['extracted'] - values['contracted']
        if not math.isclose(delta, math.fsum(leads), rel_tol=1e-8, abs_tol=1e-8):
            raise ValueError('Post-RC terminal resistance does not equal the independently extracted leads.')
        if report['source'] != {name: file_digest(ROOT / name) for name in sources}:
            raise ValueError('Source changed during primitive RC qualification.')
        report.update(status='passed', resistor_values_ohm=values, extracted_leads_ohm=leads,
                      post_rc_increase_ohm=delta, wire_resistors=normalization['resistor_count'],
                      device_parameters=normalization['export']['device_parameters'],
                      normalization_sha256=file_digest(work / 'rc-normalization.json'),
                      islands=json.loads((work / 'electrical.spice.islands.json').read_text()))
        return report
    except Exception as exc:
        report['error'] = str(exc); raise
    finally:
        atomic_write(out / 'qualification.json', json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pdk', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('magic', 'netgen', 'ngspice'):
        parser.add_argument('--' + name, required=True)
    print(json.dumps(qualify(parser.parse_args()), indent=2))
