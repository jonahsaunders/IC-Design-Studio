"""Exercise ordinary m=2 and explicit parallel units through saved-bench PEX.

Finite source integration at nominal/27 C only; no operating envelope,
calibrated PEX, arbitrary hierarchy, installed or family qualification.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.hierarchical_flow import run
from icstudio.model import clone, device, file_digest, load_project, save_project, uid, validate
from icstudio.testbenches import create, native_subcircuit
from scripts.qualify_ihp_cmim_multiplicity import attach, two_units
from scripts.qualify_ihp_mim_layout import generate, rotate
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_ihp_cmim_reference import sources
from scripts.check_ihp_cmim_enclosures import safe_path


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def bench(project):
    p = clone(project)
    fixture = {'id': uid(), 'name': 'fixture', 'ports': [], 'shapes': [], 'devices': [
        device('V', 'VIN', value='0', nets={'p': 'vin', 'n': '0'}),
        device('X', 'DUT', cell=p['top'], nets={'C1': 'vin', 'C2': '0'})]}
    p['cells'].append(fixture)
    p['analysis'].update(type='ac', start='100k', end='1meg', points=2, temperature=27, corner='nominal')
    t = create(p, fixture['id'], 'parallel_cmim')
    t['measurements'] = [{'name': 'finite_current', 'kind': 'current', 'source': 'VIN', 'at': '1meg'}]
    p['testbenches'] = [t]
    models = ('psp103', 'psp103_nqs', 'r3_cmc', 'mosvar', 'cap_cmomi', 'cap_cmomf')
    p['simulation_runtime'] = {'osdi': [{'path': str(Path('/opt/icstudio/osdi/ihp-sg13g2')/(n+'.osdi')),
        'sha256': file_digest(Path('/opt/icstudio/osdi/ihp-sg13g2')/(n+'.osdi')),
        'system': 'Linux', 'machine': 'x86_64'} for n in models]}
    validate(p)
    return p, t


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    a = parser.parse_args()
    if sys.platform != 'linux': raise ValueError('Use a verified source snapshot on native Linux storage.')
    out = safe_path(a.output.absolute()).resolve()
    if out.exists() or out.is_relative_to(ROOT): raise ValueError('Use a fresh output outside the source tree.')
    out.mkdir(parents=True)
    tools = {n: str(Path(shutil.which(n)).resolve(strict=True)) for n in ('magic', 'netgen', 'ngspice')}
    guarded = sources()
    for name in ('qualify_ihp_cmim_parallel.py', 'check_ihp_cmim_parallel.py', 'qualify_ihp_cmim_multiplicity.py', 'qualify_ihp_cmim_reference.py'):
        guarded['scripts/'+name] = file_digest(ROOT/'scripts'/name)
    report = {'schema': 1, 'scope': __doc__, 'qualified': False, 'installed_acceptance': False,
              'source_files': guarded, 'tools': {n: {'path': p, 'sha256': file_digest(p)} for n, p in tools.items()}, 'cases': []}
    technology, report['package'] = load_technology('ihp-sg13g2')
    masks = two_units(generate(technology, 7, 7, out/'generator', tools['magic']))
    for name in ('m2-0', 'pair-0', 'm2-90', 'pair-90', 'm1-0', 'm3-0', 'wrong-width-0'):
        mode, angle = name.rsplit('-', 1)
        layout = out/(name+'-layout.icproj')
        save_project(masks if angle == '0' else rotate(masks), layout)
        p, t = bench(attach(layout, technology, mode))
        case = out/name
        case.mkdir()
        save_project(p, case/'project.icproj')
        p = load_project(case/'project.icproj')
        original = native_subcircuit(p, p['top'])
        (case/'captured.spice').write_text(original)
        result = run(p, t['id'], case/'job', tools, physical_extraction={'mode': 'capacitance'})
        if native_subcircuit(p, p['top']) != original: raise ValueError('Original simulation source changed.')
        report['cases'].append({'name': name, 'status': result['status'],
            'stages': {r['name']: r['status'] for r in result['stages']}})
        write(out/'report.json', report)
        print(json.dumps(report['cases'][-1]), flush=True)
    if any(file_digest(ROOT/n) != h for n,h in guarded.items()): raise ValueError('Source changed during native run.')
    if any(file_digest(t['path']) != t['sha256'] for t in report['tools'].values()): raise ValueError('Tool changed during native run.')
    from scripts.check_ihp_cmim_parallel import inventory
    report['files'] = inventory(out)
    report['status'] = 'OBSERVED'
    write(out/'report.json', report)
    from scripts.check_ihp_cmim_parallel import verify
    receipt = verify(out)
    write(out/'verification.json', receipt)
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__': main()
