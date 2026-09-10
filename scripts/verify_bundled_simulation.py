"""Run bundled examples with a real engine. --full adds the original 144-case deck."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import atomic_write
from icstudio.xschem_compat import review_project
from icstudio.xschem_runtime import run, find_ngspice
from icstudio.runtime_setup import check_ngspice
from check_simulation_assets import check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ngspice')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    engine = args.ngspice or os.environ.get('ICSTUDIO_TEST_NGSPICE') or find_ngspice()
    if not engine:
        raise ValueError('NGSpice is required for release qualification.')
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'assets': check(), 'runtime': check_ngspice(engine), 'cases': []}
    # Catalog-backed native projects use a different deck path from imported
    # programs. A Windows-style profile with spaces must work for both PDKs.
    from icstudio.bundled_pdks import packages
    from icstudio.pdks import PDKRegistry
    from icstudio.engines import run_ngspice
    from verify_release_pdks import circuit
    native_root = args.output / 'native PDK checks with spaces'
    registry = PDKRegistry(native_root / 'registry')
    report['native_pdk_cases'] = []
    for item in packages(verify=True):
        key = registry.install(Path(item['path']) / 'package.json')
        technology = registry.technology(key)
        model, supply = (('sky130_fd_pr/nfet_01v8.sym', 1.8) if item['family'] == 'sky130'
                         else ('symbols/nfet_03v3.sym', 3.3))
        project = circuit(technology, model, supply)
        folder = native_root / item['name']; folder.mkdir(parents=True, exist_ok=True)
        result = run_ngspice(project, project['top'], project['analysis'], str(engine), folder)
        voltage = result['traces']['out'][0]
        if not 0 < voltage < supply:
            raise ValueError('Native PDK device check failed: ' + key)
        report['native_pdk_cases'].append({'pdk': key, 'model': model, 'status': 'passed', 'output_voltage': voltage})
    tests = [('gf180-startup', 'gf180-bandgap/5vfullv2-startup.sch', 'v(vref) v(avdd)', 1),
             ('sky130-inverter', 'sky130-simulation/inverter.sch', 'v(in) v(out)', 1)]
    if args.full:
        tests.append(('gf180-full', 'gf180-bandgap/5vfullv2-original.sch', 'v(vref) v(avdd) v(v1) v(v2)', 144))
    for name, file, probes, expected in tests:
        review = review_project(ROOT / 'examples' / file)
        if review['errors'] or review['candidate']['xschem_exchange']['unresolved']:
            raise ValueError('Bundled example has unresolved dependencies: ' + file)
        p = review['candidate']
        result = run(p, p['top'], {'probes': probes, 'timeout': 3600}, str(engine), args.output / name,
                     lambda value, message: print(name + ': ' + message, flush=True))
        atomic_write(args.output / name / 'result.json', json.dumps(result))
        cases = result['xschem_cases']
        if len(cases) != expected or any(c['state'] != 'Complete' for c in cases) or result['program_status'] != 'Complete':
            raise ValueError(name + ': incomplete analyses or NGSpice diagnostics; inspect engine.log.')
        if name == 'sky130-inverter':
            traces = result['traces']
            settled = [(i, traces['out'][j]) for j, (t, i) in enumerate(zip(result['x'], traces['in']))
                       if 2e-9 < t < 4e-9 or 6e-9 < t < 8e-9]
            if not settled or not all(v < .2 if i > 1 else v > 1.6 for i, v in settled):
                raise ValueError('SKY130 inverter did not switch correctly.')
        if name == 'gf180-startup':
            if abs(result['traces']['avdd'][-1] - 5) > .01 or not .5 < result['traces']['vref'][-1] < 2:
                raise ValueError('GF180 startup did not produce a plausible bias point; inspect waveforms.')
        report['cases'].append({'name': name, 'analyses': len(cases), 'status': result['program_status'],
            'samples': len(result['x']), 'final_voltages': {k: v[-1] for k, v in result['traces'].items()}})
        atomic_write(args.output / 'report.json', json.dumps(report, indent=2))
    print(json.dumps(report['cases'], indent=2))


if __name__ == '__main__':
    main()
