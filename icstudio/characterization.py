"""Saved-bench studies with immutable case evidence and explicit failed rows."""
import csv
import io
import json
from pathlib import Path
from .model import clone, validate, design_digest, digest, file_digest, now, atomic_write
from .testbenches import get, simulate
from .studies import cases, set_target
from .build_info import WORKFLOW_SOURCE_HASH


def prepared_cases(p, t, spec):
    if not t.get('measurements'):
        raise ValueError('Save at least one measurement before characterization.')
    jobs = cases(p, t['bench_cell'], spec)
    samples = []
    for labels, changes, overrides in jobs:
        sample = clone(p)
        bench = get(sample, t['id'])
        # The study changes the saved bench analysis, not the unrelated active view.
        bench['analysis'].update(overrides)
        for target, value in changes.items(): set_target(sample, t['bench_cell'], target, value)
        validate(sample)
        samples.append((labels, changes, sample, bench))
    return samples


def run(p, testbench, spec, executable, directory, progress=lambda *_: None, tools=None):
    if spec.get('compare_layout'):
        from .layout_comparison import run as compare
        return compare(p, testbench, spec, {**(tools or {}), 'ngspice': executable}, directory, progress)
    validate(p)
    t = clone(get(p, testbench))
    samples = prepared_cases(p, t, spec)
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Choose a new or empty characterization directory.')
    directory.mkdir(parents=True, exist_ok=True)
    result = {'schema': 1, 'created': now(), 'project_id': p['id'], 'revision': p['revision'],
              'design_hash': design_digest(p), 'pdk_hash': digest(p['pdk']),
              'rule_hash': digest(p['pdk']['layers']), 'cell_id': t['bench_cell'],
              'testbench_id': t['id'], 'testbench': t,
              'engine': 'ngspice saved-bench characterization', 'engine_hash': '',
              'study_engine_hash': WORKFLOW_SOURCE_HASH,
              'settings': {'type': 'characterization', 'testbench': t['id'], 'study': clone(spec)},
              'status': 'running', 'characterization_rows': [], 'summary': {},
              'evidence_directory': str(directory), 'x': [], 'x_label': 'Study run',
              'y_label': '', 'traces': {}, 'phase': {}, 'operating_point': {},
              'warnings': ['Schematic characterization; physical DRC/LVS are separate runs.']}
    if spec['kind'] == 'monte_carlo':
        result['warnings'].append('User-declared component tolerances; not foundry mismatch models.')
    atomic_write(directory / 'input.json', json.dumps({'project': p, 'testbench': t, 'study': spec}, indent=2))
    def publish(): atomic_write(directory / 'report.json', json.dumps(result, indent=2, allow_nan=False))
    publish()
    for index, (labels, changes, sample, bench) in enumerate(samples, 1):
        work = directory / f'case-{index:04d}'
        work.mkdir()
        row = {'index': index, **labels, 'changes': changes, 'status': 'failed',
               'design_hash': design_digest(sample), 'measurements': []}
        result['characterization_rows'].append(row)
        atomic_write(work / 'input.json', json.dumps({'project': sample, 'testbench': bench}, indent=2))
        progress((index-1)/len(samples), f'Characterizing {index} of {len(samples)}')
        try:
            r = simulate(sample, bench, executable, work,
                         progress=lambda f, m: progress((index-1+f)/len(samples), m))
            row.update(status=r['measurements']['status'], measurements=r['measurements']['measurements'],
                       result_file=f'case-{index:04d}/result.json',
                       result_sha256=file_digest(work / 'result.json'))
            result['engine_hash'] = r['engine_hash']
        except InterruptedError: raise
        except Exception as exc:
            row['error'] = str(exc)
            atomic_write(work / 'error.json', json.dumps({'error': str(exc)}))
        publish()
    rows = result['characterization_rows']
    passed = sum(row['status'] == 'passed' for row in rows)
    result['summary'] = {'runs': len(rows), 'passed': passed, 'failed': len(rows)-passed}
    result['status'] = 'passed' if passed == len(rows) else 'failed'
    publish()
    return result


def read_case(result, index, stage='schematic'):
    row = result['characterization_rows'][index]
    if stage not in ('schematic', 'post-layout'): raise ValueError('Choose schematic or post-layout waveforms.')
    prefix = 'post_' if stage == 'post-layout' else ''
    if prefix+'result_file' not in row: raise ValueError(row.get('error') or 'This case produced no '+stage+' waveform.')
    base = Path(result['evidence_directory']).resolve()
    path = (base / row[prefix+'result_file']).resolve()
    if not path.is_relative_to(base) or not path.is_file() or file_digest(path) != row[prefix+'result_sha256']:
        raise ValueError('Characterization waveform evidence is missing or changed.')
    case = json.loads(path.read_text())
    if case['project_id'] != result['project_id'] or case['design_hash'] != row['design_hash'] or case['cell_id'] != result['cell_id']:
        raise ValueError('Waveform does not match this characterization case.')
    return case


def csv_text(result):
    stream = io.StringIO()
    columns = ['index', 'value', 'corner', 'voltage', 'temperature', 'trial', 'case_status',
               'measurement', 'measured_value', 'unit', 'measurement_status', 'detail']
    if result.get('layout_comparison'): columns += ['before_value', 'before_status', 'after_value', 'delta']
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in result['characterization_rows']:
        after = {m['name']: m for m in row['measurements']}
        before = {m['name']: m for m in row.get('before_measurements', [])}
        measures = [after.get(name, {'name': name}) for name in dict.fromkeys([*after, *before])]
        for m in measures or [{}]:
            values = {key: row.get(key, '') for key in columns[:6]}
            values.update(case_status=row['status'], measurement=m.get('name', ''),
                          measured_value=m.get('value', ''), unit=m.get('unit', ''),
                          measurement_status=m.get('status', ''), detail=m.get('error', row.get('error', '')))
            if result.get('layout_comparison'):
                pre = before.get(m.get('name'), {}); comparison = next((c for c in row['comparison'] if c['name']==m.get('name')), {})
                values.update(before_value=pre.get('value',''), before_status=pre.get('status',''),
                              after_value=m.get('value',''), delta=comparison.get('delta',''))
            writer.writerow(values)
    return stream.getvalue()
