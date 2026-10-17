"""Selected capacitor interfaces and complex terminal admittance matrices.

Reference calls are explicit contracts from the pinned public model/symbol
sources, independent of the application emitter. These selected test points
do not establish complete operating ranges, RF accuracy or silicon accuracy.
"""
import argparse, cmath, json, math, sys, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import clone, device, example, file_digest, save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice, run_deck
from icstudio.osdi import configure, preload
from icstudio.pdks import model_lines, stage_model_deck
from scripts.qualify_standard_mos import load_technology, PROFILES, write

SKY = ('cap_mim_m3_1', 'cap_mim_m3_2', 'cap_var_hvt', 'cap_var_lvt')
GF = ('cap_mim_1f0fF', 'cap_mim_1f5fF', 'cap_mim_2f0fF', 'cap_mim_2p0fF',
      'cap_mim_analog', 'cap_nmos_03v3', 'cap_nmos_03v3_b', 'cap_nmos_06v0',
      'cap_nmos_06v0_b', 'cap_pmos_03v3', 'cap_pmos_03v3_b', 'cap_pmos_06v0', 'cap_pmos_06v0_b')
IHP = ('cap_cmim', 'cap_cmomf', 'cap_cmomi', 'cap_cpara', 'cap_rfcmim', 'moscap_n', 'moscap_p')
REL, ABS = 1e-6, 1e-15
# Parallel comparison additionally includes simulator numerical shunts and
# cancellation of internal conductances. The original stricter failures are
# retained: ngspice inserts an unscaled 1e15-ohm shunt for nonlinear C, and the
# IHP RF model shows a 1.635e-15-S cancellation residual at 100 Hz. This floor
# does not qualify conductance below 1e-14 S. Application/reference matching
# still uses ABS above; no geometry or connection fault uses this allowance.
PARALLEL_ABS = 1e-14
FREQUENCIES = [100 * 10**(i/5) for i in range(26)]


def probes(target):
    names = SKY if target == 'sky130A' else GF if target.startswith('gf180') else IHP
    for index, name in enumerate(names):
        for shape in (0, 1):
            for copies in (1, 3):
                if target == 'sky130A':
                    var = name.startswith('cap_var')
                    w, l = ((5, .5) if shape == 0 else (10, 1)) if var else ((2, 2) if shape == 0 else (7, 7))
                    pins = ('c0', 'c1', 'b') if var else ('c0', 'c1')
                    params = dict(w=w, l=l, **{('vm' if var else 'mf'): copies})
                    model = 'sky130_fd_pr__' + name
                    # The hvt wrapper handles vm internally; lvt's public
                    # symbol additionally emits the ngspice subckt multiplier.
                    manual = f'w={w:g} l={l:g} ' + (f'vm={copies}' if var else f"{'vm' if name == 'cap_mim_m3_2' else 'mf'}={copies} m={copies}")
                    if name == 'cap_var_lvt': manual += f' m={copies}'
                    key = 'sky130_fd_pr/' + name + '.sym'
                elif target.startswith('gf180'):
                    w, l = (2, 2) if shape == 0 else (7, 7)
                    pins = ('g', 'b'); params = dict(w=w*1e-6, l=l*1e-6, m=copies)
                    model = {'cap_mim_2p0fF': 'cap_mim_2f0fF', 'cap_mim_analog': 'cap_mim_2f0_m3m4_noshield'}.get(name, name)
                    manual = f'c_width={w:g}u c_length={l:g}u m={copies}'
                    key = 'symbols/' + name + '.sym'
                else:
                    w, l = ((1, 1) if shape == 0 else (2, 2)) if name.startswith('moscap') else ((7, 7) if shape == 0 else (10, 8))
                    pins = ('g', 'sub' if name == 'moscap_n' else 'nw') if name.startswith('moscap') else ('c0', 'c1', 'bn') if name == 'cap_rfcmim' else ('c0', 'c1')
                    params = dict(w=w*1e-6, l=l*1e-6, m=copies)
                    model = 'sg13_' + name if name.startswith('moscap') else name
                    manual = f'w={w:g}u l={l:g}u m={copies} mm_ok=1'
                    if name in ('cap_cmomf', 'cap_cmomi'):
                        manual += ' mmin=1 mmax=5 subblock=0'
                        if name == 'cap_cmomi': manual += ' feed=2'
                    elif name == 'cap_rfcmim': manual += ' wfeed=5u'
                    elif name == 'cap_cpara':
                        model = 'cparasitic'; params = dict(c=(10 if shape == 0 else 40)*copies*1e-15)
                        manual = f'c={(10 if shape == 0 else 40)*copies}f'
                    key = 'sg13g2_pr/' + name + '.sym'
                yield dict(tag=f'c{index}s{shape}m{copies}', name=name, key=key, pins=pins,
                           params=params, model=model, manual=manual, shape=shape, copies=copies)


def fixture(tech, target, drive, bias, osdi):
    p = example('empty'); p['pdk'] = clone(tech); c = p['cells'][0]; c['devices'] = []
    for row in probes(target):
        d = create_device(tech, row['key'], 'D'+row['tag']); d['model_params'].update(row['params'])
        d['nets'] = {pin: row['tag']+'p'+str(i) for i, pin in enumerate(row['pins'])}
        for i, pin in enumerate(row['pins']):
            v = device('V', 'V'+row['tag']+'p'+str(i), 0, 0,
                       value=str(bias if i == 0 else -.2 if i == 2 else 0), nets={'p': d['nets'][pin], 'n': '0'})
            v['source']['ac'] = '1' if i == drive else '0'; c['devices'].append(v)
        c['devices'].append(d)
    if target == 'ihp-sg13g2': p['simulation_runtime'] = {'osdi': clone(osdi)}
    return p


def independent(tech, target, drive, bias, corner, temp, parallel_varactors=False):
    lines = ['* Independent capacitor terminal probes', *model_lines(tech, corner)]
    for row in probes(target):
        nodes = [row['tag']+'p'+str(i) for i in range(len(row['pins']))]
        for i, node in enumerate(nodes):
            lines.append(f'V{node} {node} 0 DC {bias if i == 0 else -.2 if i == 2 else 0:g} AC {int(i == drive)}')
        if parallel_varactors and target == 'sky130A' and row['name'].startswith('cap_var'):
            # Literal independent single devices, without the new wrapper or
            # the upstream VM>1 equations, establish the parallel contract.
            for copy in range(row['copies']):
                params = row['params']
                lines.append(f"X{row['tag']}copy{copy} "+' '.join(nodes)+f" {row['model']} w={params['w']:g} l={params['l']:g} vm=1")
        else:
            lines.append(f'X{row["tag"]} '+ ' '.join(nodes) + f' {row["model"]} {row["manual"]}')
    return '\n'.join([*lines, f'.temp {temp}', '.ac dec 5 100 10meg', '.end', ''])


def currents(result, rows):
    x = result.get('x', [])
    if len(x) != len(FREQUENCIES) or any(not math.isfinite(a) or not math.isclose(a, b, rel_tol=1e-9) for a, b in zip(x, FREQUENCIES)):
        raise ValueError('Invalid capacitor frequency domain.')
    mag = {k.casefold(): v for k, v in result.get('currents', {}).items()}
    phase = {k.casefold(): v for k, v in result.get('current_phase', {}).items()}; values = {}
    for row in rows:
        for i in range(len(row['pins'])):
            key = 'v'+row['tag']+'p'+str(i); m = mag.get(key, []); p = phase.get(key, [])
            if len(m) != len(x) or len(p) != len(x) or any(not math.isfinite(v) for v in m+p) or any(v < 0 for v in m):
                raise ValueError('Missing or invalid capacitor terminal: '+key)
            values[key] = [cmath.rect(a, math.radians(b)) for a, b in zip(m, p)]
    return values


def compare(actual, reference, rows, drive):
    a, b = currents(actual, rows), currents(reference, rows)
    for row in rows:
        if drive < len(row['pins']):
            y = [-v for v in b['v'+row['tag']+'p'+str(drive)]]
            if max(abs(v) for v in y) < 1e-13:
                raise ValueError('Reference has no driven capacitor response: '+row['tag'])
    errors = {key: max(abs(u-v)/(ABS+REL*abs(v)) for u, v in zip(a[key], b[key])) for key in b}
    device_errors = {r['tag']: max(errors['v'+r['tag']+'p'+str(i)] for i in range(len(r['pins']))) for r in rows}
    return dict(status='PASS' if max(errors.values()) <= 1 else 'MISMATCH', channel_errors=errors,
                device_errors=device_errors, complex_vectors=len(errors), samples=len(FREQUENCIES),
                maximum_normalized_error=max(errors.values()), relative_tolerance=REL, absolute_tolerance_a=ABS)


def scaling(reference, rows):
    values = currents(reference, rows); errors = {}
    for r in rows:
        if r['copies'] != 3: continue
        baseline = r['tag'].removesuffix('m3')+'m1'
        errors[r['tag']] = max(abs(a-3*b)/(PARALLEL_ABS+REL*abs(3*b))
            for i in range(len(r['pins']))
            for a, b in zip(values['v'+r['tag']+'p'+str(i)], values['v'+baseline+'p'+str(i)]))
    return dict(status='PASS' if max(errors.values()) <= 1 else 'MISMATCH', device_errors=errors,
                relative_tolerance=REL, absolute_tolerance_a=PARALLEL_ABS,
                limitation='Numerical conductance below 1e-14 S is not resolved by this comparison.')


def case(tech, target, drive, bias, corner, temp, out, engine, osdi, parallel_varactors=False):
    name = f'{target}-port{drive}-{bias:g}-{corner}-{temp}'; folder = out/name; folder.mkdir()
    result = dict(name=name, target=target, drive=drive, bias_v=bias, corner=corner, temperature_c=temp, status='RUNNING')
    rows = list(probes(target))
    try:
        p = fixture(tech, target, drive, bias, osdi); save_project(p, folder/'input.icproj')
        settings = dict(type='ac', corner=corner, temperature=temp, start='100', end='10meg', points=5)
        app, ref = folder/'application', folder/'independent'; app.mkdir(); ref.mkdir()
        a = run_ngspice(p, p['top'], settings, engine, app)
        text = preload(p, stage_model_deck(tech, independent(tech, target, drive, bias, corner, temp, parallel_varactors), ref), ref)
        path = ref/'reference.cir'; path.write_bytes(text.encode())
        b = run_deck(p, p['top'], dict(deck=str(path), analysis=settings), engine, ref)
        write(app/'comparison-result.json', a); write(ref/'comparison-result.json', b)
        result['comparison'] = compare(a, b, rows, drive)
        if result['comparison']['status'] != 'PASS': raise ValueError('Independent capacitor terminal responses differ.')
        result['raw_sha256'] = dict(application=file_digest(app/'result.raw'), independent=file_digest(ref/'deck.raw'))
        if drive == 0:
            result['parallel_scaling'] = scaling(b, rows)
            # Record upstream multiplier behavior independently of matching the
            # application call; a failure is never hidden by matching emitters.
            result['faults'] = []
            for fault in ('wrong-size', 'disconnected-terminal'):
                q = clone(p)
                for row in rows:
                    d = next(d for d in q['cells'][0]['devices'] if d['name'] == 'D'+row['tag'])
                    if fault == 'wrong-size': d['model_params']['c' if row['name'] == 'cap_cpara' else 'w'] *= 1.2
                    else: d['nets'][row['pins'][0]] = '0'
                dest = folder/fault; dest.mkdir(); save_project(q, dest/'input.icproj')
                changed = run_ngspice(q, q['top'], settings, engine, dest); write(dest/'comparison-result.json', changed)
                check = compare(changed, b, rows, drive)
                if not all(e > 1 for e in check['device_errors'].values()): raise ValueError('Capacitor fault missed on a device: '+fault)
                result['faults'].append(dict(fault=fault, status='detected', comparison=check, raw_sha256=file_digest(dest/'result.raw')))
            if result['parallel_scaling']['status'] != 'PASS': raise ValueError('Public capacitor multiplier is not three parallel single devices.')
        result['status'] = 'PASS'
    except Exception as error:
        result.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    write(folder/'record.json', result); return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True); ap.add_argument('--ngspice', required=True)
    ap.add_argument('--osdi', type=Path, required=True); ap.add_argument('--pilot', action='store_true')
    ap.add_argument('--parallel-varactors', action='store_true')
    ap.add_argument('--targets', nargs='+', choices=PROFILES, default=list(PROFILES))
    ap.add_argument('--workers', type=int, choices=range(1, 9), default=4); a = ap.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False); osdi = configure(sorted(a.osdi.glob('*.osdi')))
    sources = [Path(__file__), ROOT/'scripts/qualify_standard_mos.py', ROOT/'scripts/prepare_sky130_parallel_varactors.py', *sorted((ROOT/'icstudio').rglob('*.py'))]
    before = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in sources}; write(out/'source-files.json', before)
    report = dict(schema=1, chunk=7, status='RUNNING', chunk_complete=False, qualified=False, cases=[], processes={},
        scope='Selected public capacitor interfaces, complex terminal responses, parallel factors and deliberate device faults. No full operating range, physical, RF-band or silicon-model qualification.',
        engine_sha256=file_digest(a.ngspice), osdi=osdi, source_files_sha256=file_digest(out/'source-files.json'),
        probes={t: list(probes(t)) for t in a.targets}, frequencies_hz=FREQUENCIES)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs = []
        for target in a.targets:
            tech, identity = load_technology(target)
            if a.parallel_varactors and target == 'sky130A':
                from scripts.prepare_sky130_parallel_varactors import prepare
                folder = out/'parallel-varactor-package'
                identity.update(prepare(ROOT/'icstudio/assets/pdks/sky130A', folder))
                package = json.loads((folder/'package.json').read_bytes()); tech = clone(package['technology'])
                tech.update(package_root=str(folder), package_lock={k: package[k] for k in ('id', 'revision', 'files')})
            report['processes'][target] = identity
            for drive in range(max(len(r['pins']) for r in probes(target))):
                for bias in ((.5,) if a.pilot else (-.5, .5)):
                    for corner in (('nominal',) if a.pilot else PROFILES[target]['corners']):
                        for temp in ((27,) if a.pilot else (0, 27, 85)):
                            jobs.append(pool.submit(case, tech, target, drive, bias, corner, temp, out, a.ngspice, osdi, a.parallel_varactors))
        for job in as_completed(jobs):
            row = job.result(); report['cases'].append(row); write(out/'qualification.json', report)
            print(row['name'], row['status'], row.get('error', ''), flush=True)
    report['implementation_unchanged'] = before == {p.relative_to(ROOT).as_posix(): file_digest(p) for p in sources}
    report['status'] = 'PASS' if report['cases'] and report['implementation_unchanged'] and all(r['status'] == 'PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r: r['name']); write(out/'qualification.json', report)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
