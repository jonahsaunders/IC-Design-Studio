"""Run Studio's bounded Banba searches and independent second-pass model checks.

python scripts/verify_gf180_banba_pass2.py --ngspice /path/to/ngspice --out /new/results
Add --apply to save the selected dimensions into the example. Raw decks, logs,
waveforms and optimizer manifests stay in the chosen results directory.
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import load_project, clone, erc, file_digest, design_digest, save_project
from icstudio.engines import run_ngspice
from icstudio import analog_optimizer as opt, specifications

EXAMPLE = ROOT / 'examples/gf180-banba/pass2'


def cell(p, name):
    return next(c for c in p['cells'] if c['name'] == name)


def transient_metrics(result, target=.6, tolerance=.006):
    times, values = result['x'], result['traces']['vref']
    outside = [i for i, value in enumerate(values) if abs(value-target) > tolerance]
    settle = None if outside and outside[-1] == len(values)-1 else times[outside[-1]+1] if outside else times[0]
    tail = [value for time, value in zip(times, values) if time >= .8*times[-1]]
    return dict(final_vref=values[-1], peak_vref=max(values), settling_seconds=settle,
                tail_peak_to_peak=max(tail)-min(tail))


def verify(executable, output, apply=False, skip_search=False, search_only=False, start_search=1):
    executable = str(Path(executable).resolve())
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Choose an empty results directory.')
    path = EXAMPLE/'banba.icproj'
    p = load_project(path)
    baseline = load_project(EXAMPLE.parent/'banba.icproj')
    if erc(p):
        raise ValueError(erc(p))

    def run(project, cid, settings, name):
        folder = output/name
        folder.mkdir(parents=True)
        result = run_ngspice(project, cid, settings, executable, folder)
        specifications.attach(dict(project=project, cell=cid, settings=settings), result)
        (folder/'result.json').write_text(json.dumps(result))
        return result

    def prepare(settings, engine, project, cell):
        return dict(settings=clone(settings), engine=engine, project=clone(project), cell=cell, executable=executable)

    searches = []
    if not skip_search:
        # Recreate the pre-trim circuit for the first search, even when opening
        # the already-selected example. The second search consumes its winner.
        core = cell(p, 'banba_core')
        output_cap = next(d for d in core['devices'] if d['name'] == 'COUT')
        if start_search < 3:
            # The first two searches preceded the output-filter addition.
            # Retain its named stubs so restoring the device preserves wiring.
            core['devices'].remove(output_cap)
        if start_search == 1:
            opt.set_target(p, core['id'], 'RPTAT.model_params.l', '11u')
            opt.set_target(p, core['id'], 'ROUT.model_params.l', '50u')
        for index, config in enumerate(json.loads((EXAMPLE/'optimizer.json').read_text())):
            if index+1 < start_search:
                continue
            if index == 2 and start_search < 3:
                cell(p, 'banba_core')['devices'].append(output_cap)
            cid = cell(p, config['cell'])['id']
            plan = next(plan for plan in p['test_plans'] if plan['id'] == config['plan'])
            manifest = opt.prepare(p, cid, plan, config['spec'], prepare)
            folder = output/f'search-{index+1}'
            folder.mkdir()
            (folder/'manifest.json').write_text(json.dumps(manifest))
            rows = []
            for job in manifest['jobs']:
                case = job['case']['index']
                try:
                    result = run(job['project'], job['cell'], job['settings'], f'search-{index+1}/case-{case:03d}')
                    specifications.attach(job, result)
                    rows.append(dict(id=str(case), job=job, state='Complete', result=result))
                except Exception as exc:
                    rows.append(dict(id=str(case), job=job, state='Failed', log=str(exc)))
                    print('Failed case', case, str(exc), flush=True)
                if case % 10 == 0:
                    print(f'Search {index+1}: {case}/{len(manifest["jobs"])} simulations', flush=True)
            report = opt.evaluate(manifest, rows)
            # Waveforms already live beside each deck; do not duplicate them
            # and every circuit snapshot through evaluate()'s current-row map.
            (folder/'report.json').write_text(json.dumps({k:v for k,v in report.items() if k != 'current'}, indent=2))
            if not report['complete'] or not report['best']:
                raise ValueError(f'Search {index+1} has no fully passing candidate; inspect {folder}/report.json')
            opt.apply_candidate(p, manifest, rows, report['best']['candidate'])
            searches.append(dict(name=config['spec']['name'], plan=plan, spec=config['spec'],
                simulations=report['total'], complete=report['complete'], best=report['best'], candidates=report['candidates']))
            print('Selected', report['best']['candidate'], report['best']['changes'], flush=True)
        (output/'searches.json').write_text(json.dumps(searches, indent=2)+'\n')
        if apply:
            saved = clone(p)
            saved['pdk']['package_root'] = '../../../icstudio/assets/pdks/gf180mcuD'
            save_project(saved, path)
            p = load_project(path)
    if search_only:
        return searches

    summary = dict(schema=1, engine='ngspice', engine_sha256=file_digest(executable),
        pdk_revision=p['pdk']['revision'], source_project_sha256=file_digest(path),
        project_sha256=file_digest(path) if design_digest(load_project(path)) == design_digest(p) else None,
        design_hash=design_digest(p),
        baseline_sha256=file_digest(EXAMPLE.parent/'banba.icproj'), erc_issues=erc(p), searches=searches)
    # Compare both circuits under identical fixtures, including the original edge.
    comparisons = {}
    for label, project in [('first_pass', baseline), ('second_pass', p)]:
        op = run(project, project['top'], project['analysis'], label+'/op')
        s = project['simulation_setups'][1]
        tr = run(project, s['cell'], s['settings'], label+'/startup')
        pair = op['device_operating_point']['XDUT/XAMP/MPA']
        data = dict(vref=op['traces']['vref'][-1], supply_current=-op['operating_currents']['VDD'],
                    input_pair_gmid=abs(pair['gm']/pair['id']), startup=transient_metrics(tr))
        temperatures = []
        for temp in [-40,-20,0,27,50,75,100,125]:
            r = run(project, project['top'], {**project['analysis'], 'temperature':temp}, label+f'/temp-{temp}')
            temperatures.append(dict(temperature=temp, vref=r['traces']['vref'][-1], supply_current=-r['operating_currents']['VDD']))
        voltages = [x['vref'] for x in temperatures]
        data.update(temperature=temperatures, temperature_span=max(voltages)-min(voltages),
                    box_tc_ppm=(max(voltages)-min(voltages))/(sum(voltages)/len(voltages)*165)*1e6)
        settings = {**project['analysis'], 'type':'dc', 'source':'VDD', 'dc_start':'2.7', 'dc_stop':'3.6', 'dc_step':'.05'}
        dc = run(project, project['top'], settings, label+'/line')
        data['line'] = dict(supplies=dc['x'], vref=dc['traces']['vref'], span=max(dc['traces']['vref'])-min(dc['traces']['vref']))
        ac_project = clone(project)
        ac_cell = cell(ac_project, 'tb_psrr' if any(c['name'] == 'tb_psrr' for c in project['cells']) else 'tb_dc')
        # DC output/current limits do not describe an AC transfer function.
        ac_cell['specifications'] = []
        next(d for d in ac_cell['devices'] if d['name'] == 'VDD')['source']['ac'] = '1'
        ac = run(ac_project, ac_cell['id'], {**project['analysis'], 'type':'ac', 'start':'1', 'end':'100Meg', 'points':40}, label+'/psrr')
        data['psrr'] = dict(frequency=ac['x'], rejection_db=[-20*math.log10(v) for v in ac['traces']['vref']])
        comparisons[label] = data
        print(label, 'Vref', data['vref'], 'IDD', data['supply_current'], 'peak', data['startup']['peak_vref'], flush=True)
    summary['comparison'] = comparisons
    # Independent supply extremes, process corners and three supply ramp rates.
    # Diagnostic PWL replaces the pulse source and starts with UIC/VREF=0.
    checks = []
    for corner in ['nominal','ff','ss','fs','sf']:
        for temp in [-40,125]:
            for vdd in [2.7,3.6]:
                q = clone(p)
                q['parameters']['vdd'] = str(vdd)
                base_settings = {**q['analysis'], 'corner':corner, 'temperature':temp}
                prefix = f'pvt/{corner}-{temp}-{vdd}'
                op = run(q, q['top'], base_settings, prefix+'/op')
                row = dict(corner=corner, temperature=temp, supply=vdd, vref=op['traces']['vref'][-1],
                           supply_current=-op['operating_currents']['VDD'], ramps=[])
                for ramp, stop, step in [('100n','500u','100n'), ('10u','500u','100n'), ('1m','2m','500n')]:
                    settings = {**base_settings, 'type':'tran', 'stop':stop, 'step':step,
                        'diagnostic':dict(kind='startup', source='VDD', output='VREF', initial_node='VREF',
                            initial_voltage='0', ramp=ramp, supply=str(vdd), stop=stop,
                            minimum='.57', maximum='.63', tail_fraction='.2')}
                    bench = 'tb_slow_startup' if ramp == '1m' else 'tb_medium_startup' if ramp == '10u' else 'tb_startup'
                    tr = run(q, cell(q,bench)['id'], settings, prefix+'/ramp-'+ramp)
                    # Settling here uses the ±5% PVT window; nominal comparisons use ±1%.
                    values = transient_metrics(tr, tolerance=.03)
                    limit = .00125 if ramp == '1m' else .00025
                    values['passed'] = (all(s['status'] == 'PASS' for s in tr.get('specifications', []))
                        and values['peak_vref'] <= .75 and .57 <= values['final_vref'] <= .63
                        and values['settling_seconds'] is not None and values['settling_seconds'] <= limit
                        and values['tail_peak_to_peak'] < .0006)
                    row['ramps'].append(dict(ramp=ramp, stop=stop, settling_limit_seconds=limit, **values))
                row['passed'] = .57 <= row['vref'] <= .63 and row['supply_current'] <= 70e-6 and all(x['passed'] for x in row['ramps'])
                checks.append(row)
                print('PVT', corner, temp, vdd, 'PASS' if row['passed'] else 'FAIL',
                      'peak', max(x['peak_vref'] for x in row['ramps']), flush=True)
    summary['pvt'] = checks
    summary['passed'] = all(row['passed'] for row in checks)
    summary['limitations'] = ['Schematic models with a fixed 5 pF load; no mismatch or extracted-layout results.',
        'Process aliases use the bundled corner mapping; this is not an independent resistor/BJT/capacitor corner matrix.',
        'No formal return-ratio, noise or output-load qualification.',
        'Larger capacitors and long resistors need layout segmentation and geometry review.']
    (output/'validation.json').write_text(json.dumps(summary, indent=2)+'\n')
    if not summary['passed']:
        raise ValueError('Independent checks found failures; inspect validation.json before accepting this design.')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--skip-search', action='store_true')
    parser.add_argument('--search-only', action='store_true')
    parser.add_argument('--start-search', type=int, choices=[1,2,3], default=1,
                        help='Resume at a later search using the saved preceding dimensions.')
    args = parser.parse_args()
    verify(args.ngspice, args.out, args.apply, args.skip_search, args.search_only, args.start_search)
