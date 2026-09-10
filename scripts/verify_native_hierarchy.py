"""Qualify a reused, three-level native hierarchy against independent RC circuits.

Runs real ngspice. --require-xschem additionally netlists each exported project
with real Xschem. Evidence includes original inputs, edited/reopened projects,
decks, logs, waveforms, identities and numerical/analytic comparisons.
"""
from __future__ import annotations

import argparse
import cmath
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import __version__, wiring
from icstudio.capture_ops import transform
from icstudio.electrical_identity import partition
from icstudio.engines import execute
from icstudio.model import History, clone, file_digest, load_project, save_project
from icstudio.native_exchange import export_project, review_project
from icstudio.native_migration import review_path
from icstudio.native_spice import run
from icstudio.spice_program import read_plot, runtime_environment

SOURCE = ROOT / 'examples/native-hierarchy'
SIGNALS = ('data[0]', 'data[1]')
KINDS = ('op', 'tran', 'ac')


def snapshot(project):
    """Electrical and editable identity, independent of paths and revision numbers."""
    return {c['id']: {
        'name': c['name'], 'ports': c['ports'],
        'parameters': c.get('spice_parameters', {}),
        'partition': partition(c),
        'devices': {d['id']: {k: d.get(k) for k in (
            'name', 'cell', 'nets', 'terminal_ids', 'net_ids', 'native_spice',
            'x', 'y', 'rotation', 'mirror')} for d in c['devices']},
    } for c in project['cells']}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def edit(project):
    history = History(project)
    top = next(c for c in project['cells'] if c['id'] == project['top'])
    xid = next(d['id'] for d in top['devices'] if d['name'] == 'X0')
    before = clone(project['cells'])
    for dy in (20, -20, 20):
        original = clone(history.project['cells'])
        history.commit(lambda p: transform(p, p['top'], [xid], dy=dy), 'Connected instance move')
        moved = clone(history.project['cells'])
        for a, b in zip(before, moved):
            require(partition(a) == partition(b), 'Connected move changed topology')
        history.undo()
        require(history.project['cells'] == original, 'Undo did not restore exact cells')
        history.redo()
        require(history.project['cells'] == moved, 'Redo did not restore exact cells')

    def parameters(p):
        top = next(c for c in p['cells'] if c['id'] == p['top'])
        next(d for d in top['devices'] if d['id'] == xid)['native_spice']['parameters']['rtop'] = '2k'
        leaf = next(c for c in p['cells'] if c['name'] == 'leaf')
        leaf['devices'][0]['native_spice']['parameters']['value'] = '{r*1.5}'
    history.commit(parameters, 'Edit one instance and the shared leaf expression')
    edited = clone(history.project['cells'])
    history.undo()
    require(history.project['cells'] == moved, 'Parameter undo lost connected edits')
    history.redo()
    require(history.project['cells'] == edited, 'Parameter redo lost expressions')
    return history.project


def plots(directory):
    return {kind: read_plot(directory / ('hierarchy-' + kind + '.raw')) for kind in KINDS}


def check_analytic(actual, resistances):
    """Independent two-channel RC transfer functions, including AC phase."""
    rows = []
    for kind, plot in actual.items():
        require(plot['plot_kind'] == kind and bool(plot['x']), 'Missing ' + kind + ' samples')
        require(set(plot['traces']) == set(SIGNALS), 'Scalar bus members changed')
        for name, resistance in zip(SIGNALS, resistances):
            gain = 1000 / (resistance + 1000)
            tau = (resistance * 1000 / (resistance + 1000)) * 1e-8
            values = plot['traces'][name]
            require(len(values) == len(plot['x']), 'Incomplete signal samples')
            if kind == 'ac':
                phases = plot['phase'][name]
                require(len(phases) == len(values), 'Missing AC phase samples')
                values = [cmath.rect(v, math.radians(p)) for v, p in zip(values, phases)]
                expected = [gain / (1 + 2j * math.pi * f * tau) for f in plot['x']]
            else:
                expected = [gain] * len(values)
            errors = [abs(a - b) for a, b in zip(values, expected)]
            require(all(math.isfinite(e) for e in errors), 'Nonfinite numerical result')
            error = max(errors)
            require(error <= 2e-7, f'{kind}/{name}: analytic error {error:g} V')
            rows.append({'analysis': kind, 'signal': name, 'samples': len(values),
                         'maximum_error_v': error, 'tolerance_v': 2e-7})
    return rows


def reference(out, engine, resistances):
    out.mkdir()
    program = '\n'.join(
        f'{command}\nwrite hierarchy-{kind}.raw v("data[0]") v("data[1]")'
        for kind, command in [('op', 'op'), ('tran', 'tran 1u 100u'), ('ac', 'ac dec 8 10 100k')])
    circuit = '* Independent flattened two-channel RC reference\nV1 supply 0 DC 1 AC 1\n'
    for i, resistance in enumerate(resistances):
        circuit += (f'RT{i} supply data[{i}] {resistance}\n'
                    f'RB{i} data[{i}] 0 1000\nCL{i} data[{i}] 0 10n\n')
    circuit += '.control\nset filetype=ascii\nsave all\n' + program + '\n.endc\n.end\n'
    (out / 'reference.cir').write_text(circuit, encoding='utf-8')
    log = execute([engine, '-n', '-b', 'reference.cir'], out, timeout=60,
                  env=runtime_environment(engine))
    (out / 'simulation.log').write_text(log, encoding='utf-8')
    return plots(out)


def simulate(project, directory, engine):
    result = run(project, project['top'], {'timeout': 60, 'probes': 'v(data[0]) v(data[1])'}, engine, directory)
    require(result['program_status'] == 'Complete', str(result.get('warnings')))
    require(len(result['analysis_cases']) == 3, 'Expected three completed analyses')
    (directory / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return plots(directory)


def compare(reference_plots, actual):
    maximum = 0.0
    for kind in KINDS:
        a, b = reference_plots[kind], actual[kind]
        require(len(a['x']) == len(b['x']), 'Reference and actual sample counts differ')
        require(all(math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-15)
                    for x, y in zip(a['x'], b['x'])), 'Reference and actual grids differ')
        for signal in SIGNALS:
            av, bv = a['traces'][signal], b['traces'][signal]
            if kind == 'ac':
                av = [cmath.rect(v, math.radians(p)) for v, p in zip(av, a['phase'][signal])]
                bv = [cmath.rect(v, math.radians(p)) for v, p in zip(bv, b['phase'][signal])]
            errors = [abs(x - y) for x, y in zip(av, bv)]
            require(all(math.isfinite(e) and e <= 2e-7 for e in errors), 'Reference waveform mismatch')
            maximum = max(maximum, max(errors))
    return maximum


def qualify(output, ngspice, xschem=None):
    output = Path(output).resolve()
    require(not output.exists() or not any(output.iterdir()), 'Use an empty evidence directory')
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'failed', 'version': __version__, 'platform': platform.platform(),
              'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'source_sha256': {f.name: file_digest(f) for f in sorted(SOURCE.glob('*')) if f.is_file()},
              'scope': 'Three-level reused RC hierarchy; scalar bus members. Vector expansion and PDK qualification excluded.',
              'cases': []}
    try:
        from icstudio.runtime_setup import check_ngspice
        report['ngspice'] = check_ngspice(ngspice)
        source = output / 'Original source with spaces'
        shutil.copytree(SOURCE, source)
        migrated = review_path(source / 'dual-divider.sch')
        require(migrated['status'] == 'Complete', str(migrated['items']))
        baseline = migrated['candidate']
        require(len(baseline['cells']) == 3, 'Expected three hierarchy levels')
        edited = edit(clone(baseline))
        # Remove the original and its embedded source archive before native runs.
        shutil.rmtree(source)
        for project in (baseline, edited):
            project['native_migration'].pop('archive', None)
        for name, project, values in [('baseline', baseline, (1000, 3000)), ('edited', edited, (3000, 4500))]:
            directory = output / name
            directory.mkdir()
            expected = reference(directory / 'independent-reference', ngspice, values)
            check_analytic(expected, values)
            path = directory / 'Saved native project.icproj'
            save_project(project, path)
            project = load_project(path)
            original = snapshot(project)
            actual = simulate(project, directory / 'native', ngspice)
            row = {'name': name, 'native_analytic': check_analytic(actual, values),
                   'native_reference_error_v': compare(expected, actual), 'roundtrips': []}
            for cycle in range(2):
                exported = export_project(project, directory / f'export-{cycle}')
                schematic = Path(exported['directory']) / exported['top']
                if xschem:
                    from icstudio.external_tools import xschem_netlist
                    dest = directory / f'xschem-{cycle}'
                    record = xschem_netlist(schematic, dest, xschem)
                    require(record['status'] == 'complete', 'Independent Xschem netlisting failed')
                    decks = list((dest / 'netlists').glob('*.spice'))
                    require(len(decks) == 1, 'Expected one independent netlist')
                    run_dir = dest / 'sources/0'
                    log = execute([ngspice, '-n', '-b', decks[0].resolve()], run_dir, timeout=60,
                                  env=runtime_environment(ngspice))
                    (dest / 'simulation.log').write_text(log, encoding='utf-8')
                    check_analytic(plots(run_dir), values)
                    row['xschem_reference_error_v'] = compare(expected, plots(run_dir))
                review = review_project(schematic)
                require(not review['errors'] and review['candidate'] is not None, str(review['errors']))
                project = review['candidate']
                save_project(project, directory / f'reimport-{cycle}.icproj')
                project = load_project(directory / f'reimport-{cycle}.icproj')
                require(snapshot(project) == original, 'Round trip changed identities, parameters, geometry or topology')
                actual = simulate(project, directory / f'reimport-run-{cycle}', ngspice)
                row['roundtrips'].append({'cycle': cycle, 'identity_preserved': True,
                                         'analytic': check_analytic(actual, values),
                                         'reference_error_v': compare(expected, actual)})
            report['cases'].append(row)
        report.update(status='passed', connected_edits_undo_redo=True,
                      independent_xschem=bool(xschem), original_source_removed=True)
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ngspice', default=os.environ.get('ICSTUDIO_TEST_NGSPICE') or shutil.which('ngspice'))
    parser.add_argument('--xschem', default=os.environ.get('ICSTUDIO_TEST_XSCHEM') or shutil.which('xschem'))
    parser.add_argument('--require-xschem', action='store_true')
    args = parser.parse_args()
    if not args.ngspice or (args.require_xschem and not args.xschem):
        parser.error('The requested real simulation/netlisting engines must be installed')
    report = qualify(args.output, args.ngspice, args.xschem if args.require_xschem else None)
    print(json.dumps({'status': report['status'], 'cases': len(report['cases']),
                      'independent_xschem': report['independent_xschem']}))


if __name__ == '__main__':
    main()
