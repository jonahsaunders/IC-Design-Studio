"""Exercise published MOS boundaries and explicitly selected undocumented axes.

Independent decks and per-device fault controls qualify application integration,
not silicon accuracy, reliability, continuous ranges or physical geometry.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.catalog import create_device
from icstudio.engines import parse_raw, run_deck, run_ngspice
from icstudio.model import clone, device, example, file_digest, save_project
from icstudio.osdi import configure, preload
from icstudio.pdks import model_lines, stage_model_deck
from scripts.qualify_standard_mos import PROFILES, independent_device, load_technology, write

SOURCES = ROOT / 'docs/qualification/mos-boundary-sources-v1'
AXES = ('gate', 'drain', 'body')
PINS = ('d', 'g', 's', 'b')
FAULTS = ('wrong-multiplicity', 'gate-drain-swap')
REL, ABS = 1e-6, 1e-12
STEPS = 40


def contract(target):
    if target == 'sky130A':
        return dict(voltage=1.95, reverse_body=1.95, forward_body={'n': .3, 'p': .1},
                    sizes=[(.42, .15), (.42, 1), (.42, 8), (7, .15), (7, 8)],
                    temperatures=[0, 27, 85], published=['gate voltage', 'drain voltage', 'body voltage'],
                    selected=['temperature', 'geometry points from public characterization tables'])
    if target in ('gf180mcuC', 'gf180mcuD'):
        return dict(voltage=3.3, reverse_body=.3, forward_body={'n': 0., 'p': 0.},
                    sizes=[(w, l) for w in (.22, .5, 1.2, 10) for l in (.28, .5, 1, 10)],
                    temperatures=[-40, 25, 125], published=['measured geometry matrix', 'characterization temperatures'],
                    selected=['0 to nominal 3.3 V gate/drain', '0 to 0.3 V reverse body bias'])
    if target == 'ihp-sg13g2':
        return dict(voltage=1.5, reverse_body=.3, forward_body={'n': 0., 'p': 0.},
                    sizes=[(w, l) for w in (.15, 10) for l in (.13, 10)],
                    temperatures=[0, 27, 85], published=['geometry bounds', 'maximum drain-source voltage', '27 C measurement'],
                    selected=['0 to nominal 1.2 V gate', '0 to 0.3 V reverse body bias', '0 and 85 C'])
    raise ValueError('Unknown boundary target: ' + target)


def source_identity():
    sources = json.loads((SOURCES / 'sources.json').read_bytes())
    for name, row in sources.items():
        if Path(name).name != name or file_digest(SOURCES / name) != row['sha256']:
            raise ValueError('Changed boundary source: ' + name)
    ihp = ROOT / 'icstudio/assets/pdks/ihp-sg13g2/libs.tech/ngspice/models/cornerMOSlv.lib'
    expected = '03d505847c880d233b341be115a1e5460edf4d8e9b3e8a7df791a52fa4455d67'
    if file_digest(ihp) != expected:
        raise ValueError('Changed IHP model boundary source.')
    return dict(documentation=sources, ihp=dict(path=ihp.relative_to(ROOT).as_posix(), sha256=expected))


def sweep(target, polarity, axis):
    limits = contract(target)
    voltage = 1.2 if target == 'ihp-sg13g2' and axis == 'gate' else limits['voltage']
    if axis == 'body':
        low, high = -limits['reverse_body'], limits['forward_body'][polarity]
    elif axis in ('gate', 'drain'):
        low, high = 0., voltage
    else:
        raise ValueError('Unknown sweep axis.')
    return (-high, -low) if polarity == 'p' else (low, high)


def probes(target, polarity, axis):
    limits = contract(target)
    sign = -1 if polarity == 'p' else 1
    gate = 1.2 if target == 'ihp-sg13g2' else limits['voltage']
    for index, (width, length) in enumerate(limits['sizes']):
        for first in range(2):
            for second in range(2):
                tag = f'q{index}a{first}b{second}'
                values = dict(d=sign*limits['voltage'], g=sign*gate, s=0., b=0.)
                if axis == 'gate':
                    values.update(d=sign*limits['voltage']*(.05, 1.)[first],
                                  b=-sign*limits['reverse_body']*second)
                elif axis == 'drain':
                    values.update(g=sign*gate*(.5, 1.)[first], b=-sign*limits['reverse_body']*second)
                elif axis == 'body':
                    values.update(g=sign*gate*(.75, 1.)[first], d=sign*limits['voltage']*(.05, .5)[second])
                else:
                    raise ValueError('Unknown sweep axis.')
                yield dict(tag=tag, size=dict(w=width, l=length, fingers=1, copies=1),
                           dc=values, nodes={pin: tag+'_'+pin for pin in PINS})


def fixture(tech, target, polarity, axis, osdi=()):
    project = example('empty')
    project['pdk'] = clone(tech)
    cell = project['cells'][0]
    cell.update(name='mos_boundary_coupon', devices=[])
    source = device('V', 'VSWEEP', 0, 0, value='0', nets={'p': 'drive', 'n': '0'})
    source['source']['ac'] = '0'
    cell['devices'].append(source)
    key = PROFILES[target]['prefix'] + PROFILES[target]['symbols'][polarity == 'p'] + '.sym'
    driven = {'gate': 'g', 'drain': 'd', 'body': 'b'}[axis]
    for row in probes(target, polarity, axis):
        for pin in PINS:
            probe = device('V', 'V'+row['tag']+pin, 0, 0,
                           value='0' if pin == driven else str(row['dc'][pin]),
                           nets={'p': row['nodes'][pin], 'n': 'drive' if pin == driven else '0'})
            probe['source']['ac'] = '0'
            cell['devices'].append(probe)
        transistor = create_device(tech, key, 'M'+row['tag'])
        transistor['params'].update(w=str(row['size']['w'])+'u', l=str(row['size']['l'])+'u')
        transistor['nets'] = row['nodes']
        cell['devices'].append(transistor)
    if target == 'ihp-sg13g2':
        project['simulation_runtime'] = {'osdi': clone(list(osdi))}
    return project


def independent(tech, target, polarity, axis, corner, temperature):
    lines = ['* Independent published-boundary terminal probes', *model_lines(tech, corner),
             'VSWEEP drive 0 DC 0 AC 0']
    driven = {'gate': 'g', 'drain': 'd', 'body': 'b'}[axis]
    for row in probes(target, polarity, axis):
        for pin in PINS:
            ground = 'drive' if pin == driven else '0'
            value = 0 if pin == driven else row['dc'][pin]
            lines.append(f'V{row["tag"]}{pin} {row["nodes"][pin]} {ground} DC {value:.12g} AC 0')
        fields = independent_device(target, polarity, row['size']).split()
        fields[0] = 'XREF'+row['tag']
        fields[1:5] = [row['nodes'][pin] for pin in PINS]
        lines.append(' '.join(fields))
    low, high = sweep(target, polarity, axis)
    lines += [f'.temp {temperature}', f'.dc VSWEEP {low:.12g} {high:.12g} {(high-low)/STEPS:.12g}', '.end', '']
    return '\n'.join(lines)


def vectors(result, target, polarity, axis, require_response=True):
    low, high = sweep(target, polarity, axis)
    grid = [low+(high-low)*i/STEPS for i in range(STEPS+1)]
    actual = result['x']
    if len(actual) != len(grid) or any(not math.isfinite(a) or not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12) for a, b in zip(actual, grid)):
        raise ValueError('Boundary sweep does not cover the declared coordinates.')
    currents = {key.casefold(): values for key, values in result['currents'].items()}
    selected = {}
    for row in probes(target, polarity, axis):
        group = []
        for pin in PINS:
            name = 'v'+row['tag']+pin
            values = currents.get(name, [])
            if len(values) != len(grid) or not all(math.isfinite(v) for v in values):
                raise ValueError('Missing or nonfinite boundary terminal current: '+name)
            selected[name] = values
            group.append(values)
        if require_response:
            drain = group[0]
            if max(drain)-min(drain) <= ABS:
                raise ValueError('Boundary transistor has no resolvable response: '+row['tag'])
            signed = max(drain) if polarity == 'p' else -min(drain)
            if signed <= ABS:
                raise ValueError('Boundary transistor has the wrong current sign: '+row['tag'])
            for sample in zip(*group):
                if abs(sum(sample)) > ABS+REL*max(abs(v) for v in sample):
                    raise ValueError('Boundary terminal currents do not conserve charge: '+row['tag'])
    return selected


def compare(actual, reference, target, polarity, axis):
    expected = vectors(reference, target, polarity, axis)
    measured = vectors(actual, target, polarity, axis, require_response=False)
    errors = {}
    for row in probes(target, polarity, axis):
        errors[row['tag']] = max(abs(a-b)/(ABS+REL*abs(b))
            for pin in PINS for a, b in zip(measured['v'+row['tag']+pin], expected['v'+row['tag']+pin]))
    status = 'PASS' if max(errors.values()) <= 1 else 'DIFFERENT'
    if status == 'PASS':
        vectors(actual, target, polarity, axis)
    return dict(status=status, device_errors=errors, terminal_vectors=len(expected), samples=STEPS+1,
                relative_tolerance=REL, absolute_tolerance_a=ABS)


def altered(project, target, fault):
    changed = clone(project)
    for transistor in changed['cells'][0]['devices']:
        if not transistor['name'].startswith('Mq'):
            continue
        if fault == 'wrong-multiplicity':
            transistor['model_params']['mult' if target == 'sky130A' else 'm'] = 3
        elif fault == 'gate-drain-swap':
            transistor['nets']['g'], transistor['nets']['d'] = transistor['nets']['d'], transistor['nets']['g']
        else:
            raise ValueError('Unknown boundary fault.')
    return changed


def raw_response(path):
    names, rows, complex_data = parse_raw(path)
    if complex_data:
        raise ValueError('Expected DC boundary data.')
    return dict(x=[r[0] for r in rows], currents={name[2:-1]: [r[i] for r in rows]
                for i, name in enumerate(names) if name.lower().startswith('i(') and name.endswith(')')})


def case(tech, target, polarity, axis, corner, temperature, output, engine, osdi):
    name = f'{target}-{polarity}-{axis}-{corner}-{temperature}'
    folder = output/name
    folder.mkdir()
    row = dict(name=name, target=target, polarity=polarity, axis=axis, corner=corner,
               temperature_c=temperature, status='RUNNING', faults=[])
    try:
        project = fixture(tech, target, polarity, axis, osdi)
        save_project(project, folder/'input.icproj')
        low, high = sweep(target, polarity, axis)
        settings = dict(type='dc', source='VSWEEP', corner=corner, temperature=temperature,
                        dc_start=str(low), dc_stop=str(high), dc_step=str((high-low)/STEPS))
        app, ref = folder/'application', folder/'independent'
        app.mkdir(); ref.mkdir()
        actual = run_ngspice(project, project['top'], settings, engine, app)
        text = preload(project, stage_model_deck(tech, independent(tech, target, polarity, axis, corner, temperature), ref), ref)
        path = ref/'reference.cir'; path.write_bytes(text.encode())
        expected = run_deck(project, project['top'], dict(deck=str(path), analysis=settings), engine, ref)
        row['comparison'] = compare(actual, expected, target, polarity, axis)
        if row['comparison']['status'] != 'PASS':
            raise ValueError('Independent boundary currents differ.')
        row['raw_sha256'] = dict(application=file_digest(app/'result.raw'), independent=file_digest(ref/'deck.raw'))
        raw_actual, raw_expected = raw_response(app/'result.raw'), raw_response(ref/'deck.raw')
        if compare(raw_actual, raw_expected, target, polarity, axis) != row['comparison']:
            raise ValueError('Independent raw readback differs from engine result.')
        for fault in FAULTS:
            dest = folder/fault; dest.mkdir()
            changed = altered(project, target, fault)
            measured = run_ngspice(changed, changed['top'], settings, engine, dest)
            comparison = compare(measured, expected, target, polarity, axis)
            if not all(error > 1 for error in comparison['device_errors'].values()):
                raise ValueError('Not every deliberately faulted device was detected: '+fault)
            if compare(raw_response(dest/'result.raw'), raw_expected, target, polarity, axis) != comparison:
                raise ValueError('Fault raw readback differs.')
            row['faults'].append(dict(fault=fault, status='detected', devices=len(comparison['device_errors']),
                                     comparison=comparison, raw_sha256=file_digest(dest/'result.raw')))
        row['status'] = 'PASS'
    except Exception as error:
        row.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    write(folder/'record.json', row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--osdi', type=Path)
    parser.add_argument('--targets', nargs='+', choices=PROFILES, default=list(PROFILES))
    parser.add_argument('--pilot', action='store_true', help='Nominal corner and 27 C only; does not complete the batch.')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    # Workers execute from case directories; resolve the user's engine path once.
    args.ngspice = str(Path(args.ngspice).resolve(strict=True))
    identities = source_identity()
    if 'ihp-sg13g2' in args.targets and args.osdi is None:
        parser.error('IHP requires --osdi.')
    osdi = configure(sorted(args.osdi.glob('*.osdi'))) if args.osdi else []
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    source_files = [Path(__file__), ROOT/'scripts/qualify_standard_mos.py', *sorted((ROOT/'icstudio').rglob('*.py'))]
    before = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in source_files}
    write(output/'source-files.json', before)
    report = dict(schema=1, chunk=7, status='RUNNING', chunk_complete=False, qualified=False, pilot=args.pilot,
                  scope='Sampled published MOS boundaries and explicitly selected unbounded axes. No continuous-range, silicon-accuracy, reliability, statistical, physical or full device qualification.',
                  engine_sha256=file_digest(args.ngspice), sources=identities, osdi=osdi,
                  contracts={t: contract(t) for t in args.targets}, source_files_sha256=file_digest(output/'source-files.json'), processes={}, cases=[])
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = []
        for target in args.targets:
            tech, identity = load_technology(target); report['processes'][target] = identity
            for polarity in ('n', 'p'):
                for axis in AXES:
                    for corner in ('nominal',) if args.pilot else PROFILES[target]['corners']:
                        for temperature in (27,) if args.pilot else contract(target)['temperatures']:
                            jobs.append(pool.submit(case, tech, target, polarity, axis, corner, temperature, output, args.ngspice, osdi))
        report['expected_cases'] = len(jobs)
        for job in as_completed(jobs):
            row = job.result(); report['cases'].append(row)
            write(output/'qualification.json', report)
            print(row['name'], row['status'], row.get('error', ''), flush=True)
    report['implementation_unchanged'] = before == {p.relative_to(ROOT).as_posix(): file_digest(p) for p in source_files}
    report['status'] = 'PASS' if report['implementation_unchanged'] and len(report['cases']) == len(jobs) and all(r['status'] == 'PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r: r['name'])
    write(output/'qualification.json', report)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
