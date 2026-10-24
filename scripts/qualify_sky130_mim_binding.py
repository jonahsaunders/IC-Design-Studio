"""Seeded native integration of both public MiM mismatch-area parameters.

This checks the application's binding against literal model calls and the
model's stated inverse-square-root MF law. It does not validate that law
against silicon or establish complete statistical/operating envelopes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.catalog import create_device
from icstudio.engines import execute, parse_raw
from icstudio.interchange import spice
from icstudio.model import clone, example, file_digest, save_project
from icstudio.pdks import model_lines, stage_model_deck
from icstudio.spice_program import runtime_environment

SIZES = ((2, 2), (2, 10), (10, 2), (30, 30))
MULTIPLIERS = (.5, 1, 4, 16)
PROFILES = (('nominal', 27), ('ss', 0), ('ff', 85))
SEED = 20261022


def probes(trials):
    return [dict(tag=f'p{k}g{g}t{t}', model=f'sky130_fd_pr__cap_mim_m3_{k}',
                 key=f'sky130_fd_pr/cap_mim_m3_{k}.sym', w=w, l=l)
            for k in (1, 2) for g, (w, l) in enumerate(SIZES) for t in range(trials)]


def fixture(tech, rows, multiplier):
    p = example('empty'); p['pdk'] = clone(tech)
    for row in rows:
        d = create_device(tech, row['key'], row['tag'])
        d['model_params'].update(w=row['w'], l=row['l'], mf=multiplier)
        d['nets'] = dict(c0=row['tag'], c1='0')
        p['cells'][0]['devices'].append(d)
    return p


def capacitances(raw, rows):
    names, data, complex_data = parse_raw(raw)
    if not complex_data or len(data) != 3:
        raise ValueError('Expected three complex frequency samples.')
    frequencies = [float(row[0].real) for row in data]
    if frequencies != [1000., 10000., 100000.]:
        raise ValueError('Unexpected MiM frequency domain.')
    values = {}
    for row in rows:
        j = names.index('i(v'+row['tag']+')')
        cs = [-1/(2*math.pi*f*(1/-sample[j]).imag) for f, sample in zip(frequencies, data)]
        if any(not math.isfinite(c) or c <= 0 for c in cs) or max(cs)/min(cs)-1 > 1e-8:
            raise ValueError('Invalid series-RC capacitor response: ' + row['tag'])
        values[row['tag']] = cs[0]
    return values


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sky130', type=Path, required=True)
    ap.add_argument('--ngspice', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--pilot', action='store_true')
    a = ap.parse_args(); out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), ROOT/'scripts/prepare_sky130_mim_binding.py', *sorted((ROOT/'icstudio').glob('*.py'))]
    hashes = {p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    source = a.sky130.resolve(); package = json.loads((source/'package.json').read_bytes())
    tech = clone(package['technology'])
    tech.update(package_root=str(source), package_lock={k:package[k] for k in ('id','revision','files')})
    rows = probes(2 if a.pilot else 16)
    # Verify the model closure once per profile. Every run uses these staged
    # files; the final hash check binds the actual engine inputs to this run.
    staged = {}
    for corner, _ in PROFILES[:1] if a.pilot else PROFILES:
        staged[corner] = stage_model_deck(tech, '\n'.join(model_lines(tech, corner)), out)
    inputs = {p.relative_to(out).as_posix():file_digest(p) for p in (out/'pdk-models').glob('*.spice')}
    app = {}
    for m in MULTIPLIERS:
        project = fixture(tech, rows, m)
        save_project(project, out/f'm{m:g}.icproj')
        app[m] = [s for s in spice(project).splitlines() if s.startswith('X_')]
        if len(app[m]) != len(rows):
            raise ValueError('Application did not export all capacitor instances.')
    jobs = []
    for corner, temp in PROFILES[:1] if a.pilot else PROFILES:
        for m in MULTIPLIERS:
            for variant in ('application', 'independent', 'nominal') + (() if m == 1 else ('old-vm', 'missing-m')):
                key = f'{corner}-{temp}-m{m:g}-{variant}'
                folder = out/key; folder.mkdir()
                calls = app[m] if variant == 'application' else []
                if variant != 'application':
                    for row in rows:
                        mf = 'vm' if variant == 'old-vm' and row['model'].endswith('_2') else 'mf'
                        count = 1 if variant == 'missing-m' else m
                        calls.append(f"X_{row['tag']} {row['tag']} 0 {row['model']} w={row['w']:g} l={row['l']:g} {mf}={m:g} m={count:g}")
                lines = ['* Seeded MiM binding qualification', staged[corner],
                         f'.param mc_mm_switch={int(variant != "nominal")}', f'.option seed={SEED}', f'.temp {temp}',
                         *[f"V{r['tag']} {r['tag']} 0 DC 0 AC 1" for r in rows], *calls,
                         '.ac dec 1 1k 100k', '.end', '']
                # Staged paths are relative to the common output directory.
                (out/(key+'.cir')).write_bytes('\n'.join(lines).encode())
                jobs.append(dict(key=key, corner=corner, temperature=temp, multiplier=m, variant=variant))
    executable = str(a.ngspice.resolve(strict=True))
    def run(job):
        key = job['key']; folder = out/key
        log = execute([executable, '-n', '-D', 'filetype=ascii', '-b', '-r', key+'/result.raw', key+'.cir'],
                      out, timeout=300, env=runtime_environment(executable))
        (folder/'engine.log').write_bytes(log.encode())
        if 'error' in log.lower() or 'unknown parameter' in log.lower():
            raise ValueError('Native MiM engine reported an error: ' + key)
        values = capacitances(folder/'result.raw', rows)
        record = dict(**job, capacitances_F=values, raw_sha256=file_digest(folder/'result.raw'), deck_sha256=file_digest(out/(key+'.cir')))
        (folder/'record.json').write_bytes((json.dumps(record, indent=2)+'\n').encode())
        print(key, 'PASS', flush=True)
        return record
    results = {}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for future in as_completed([pool.submit(run, job) for job in jobs]):
            row = future.result(); results[row['key']] = row
    comparisons = []
    for corner, temp in PROFILES[:1] if a.pilot else PROFILES:
        def values(m, variant):
            return results[f'{corner}-{temp}-m{m:g}-{variant}']['capacitances_F']
        unit, nominal = values(1, 'application'), values(1, 'nominal')
        deltas = {tag:unit[tag]/nominal[tag]-1 for tag in unit}
        if len({round(v, 10) for v in deltas.values()}) < len(rows)//2 or max(abs(v) for v in deltas.values()) < 1e-5:
            raise ValueError('Mismatch was not enabled or independently sampled.')
        for m in MULTIPLIERS:
            actual, independent = values(m, 'application'), values(m, 'independent')
            error = max(abs(actual[k]/independent[k]-1) for k in actual)
            scaling = max(abs((actual[k]/(m*nominal[k])-1) - deltas[k]/math.sqrt(m)) for k in actual)
            deterministic = max(abs(values(m,'nominal')[k]/(m*nominal[k])-1) for k in actual)
            if error > 1e-9 or scaling > 1e-9 or deterministic > 1e-9:
                raise ValueError('MiM interface or paired mismatch scaling differs.')
            faults = {}
            if m != 1:
                for variant in ('old-vm', 'missing-m'):
                    faulty = values(m, variant)
                    affected = [r['tag'] for r in rows if variant != 'old-vm' or r['model'].endswith('_2')]
                    detected = sum(abs(actual[k]/faulty[k]-1) > 1e-9 for k in affected)
                    if detected != len(affected):
                        raise ValueError('A deliberately incorrect MiM parameter escaped detection.')
                    faults[variant] = detected
            comparisons.append(dict(corner=corner, temperature=temp, multiplier=m, instances=len(rows),
                                    max_relative_interface_error=error, max_absolute_fractional_scaling_error=scaling,
                                    max_relative_nominal_scaling_error=deterministic, detected_faults=faults))
    unchanged = inputs == {name:file_digest(out/name) for name in inputs}
    if not unchanged:
        raise ValueError('Staged models changed during execution.')
    if hashes != {p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}:
        raise ValueError('Application or qualification sources changed during execution.')
    result = dict(schema=1, status='PASS', chunk=7, chunk_complete=False, qualified=False, scope=__doc__,
                  package=dict(revision=package['revision'], manifest_sha256=file_digest(source/'package.json')),
                  engine_sha256=file_digest(executable), source_sha256=hashes, source_unchanged=True,
                  trials_per_shape=2 if a.pilot else 16, seed=SEED, comparisons=comparisons,
                  native_runs=len(results), results=results, staged_inputs=inputs, inputs_unchanged=unchanged)
    (out/'record.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
    print('PASS', len(comparisons), 'comparisons', len(results), 'native runs', flush=True)


if __name__ == '__main__':
    main()
