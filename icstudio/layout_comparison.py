"""Saved-study schematic/extracted comparison with independent physical gates."""
import json
from pathlib import Path
from .model import validate, clone, design_digest, digest, file_digest, now, atomic_write
from .testbenches import get
from .characterization import prepared_cases
from .build_info import WORKFLOW_SOURCE_HASH


def run(p, testbench, spec, tools, directory, progress=lambda *_: None):
    from .hierarchical_flow import run as verify
    validate(p); t = clone(get(p, testbench)); samples = prepared_cases(p, t, spec)
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()): raise ValueError('Choose a new or empty comparison directory.')
    directory.mkdir(parents=True, exist_ok=True)
    result = {'schema': 1, 'created': now(), 'project_id': p['id'], 'revision': p['revision'],
              'design_hash': design_digest(p), 'pdk_hash': digest(p['pdk']), 'rule_hash': digest(p['pdk']['layers']),
              'cell_id': t['bench_cell'], 'testbench_id': t['id'], 'testbench': t,
              'engine': 'Magic / Netgen / ngspice saved-bench comparison', 'engine_hash': '',
              'study_engine_hash': WORKFLOW_SOURCE_HASH,
              'settings': {'type': 'characterization', 'testbench': t['id'], 'study': clone(spec)},
              'status': 'running', 'characterization_rows': [], 'summary': {'runs': len(samples), 'passed': 0, 'failed': 0},
              'layout_comparison': True, 'evidence_directory': str(directory),
              'x': [], 'x_label': 'Study run', 'y_label': '', 'traces': {}, 'phase': {}, 'operating_point': {},
              'warnings': ['Every case requires schematic limits, full DRC, unique LVS without property errors, capacitance extraction and post-layout limits. Distributed resistance is outside this flow.']}
    atomic_write(directory/'input.json', json.dumps({'project': p, 'testbench': t, 'study': spec}, indent=2))
    def publish(): atomic_write(directory/'report.json', json.dumps(result, indent=2, allow_nan=False))
    publish()
    for i, (labels, changes, sample, bench) in enumerate(samples, 1):
        work = directory/f'case-{i:04d}'
        row = {'index': i, **labels, 'changes': changes, 'status': 'failed',
               'design_hash': design_digest(sample), 'measurements': [], 'before_measurements': [], 'comparison': []}
        result['characterization_rows'].append(row)
        try:
            report = verify(sample, bench['id'], work, tools,
                            lambda f,m: progress((i-1+f)/len(samples), f'Case {i}/{len(samples)}: {m}'))
            row.update(status=report['status'], physical_report=f'case-{i:04d}/report.json',
                       physical_report_sha256=file_digest(work/'report.json'), stages=report['stages'],
                       comparison=report.get('comparison', []), error=report.get('error', ''))
            for stage, prefix, field in (('schematic', '', 'before_measurements'), ('post-layout', 'post_', 'measurements')):
                path = work/stage/'result.json'
                if path.is_file():
                    wave = json.loads(path.read_text())
                    row[field] = wave['measurements']['measurements']
                    row[prefix+'result_file'] = path.relative_to(directory).as_posix()
                    row[prefix+'result_sha256'] = file_digest(path)
            result['engine_hash'] = digest(report['stages'][0].get('evidence', {}))
        except InterruptedError: raise
        except Exception as exc:
            row['error'] = str(exc); work.mkdir(parents=True, exist_ok=True)
            atomic_write(work/'error.json', json.dumps({'error': str(exc)}))
        publish()
    passed = sum(row['status'] == 'passed' for row in result['characterization_rows'])
    result['summary'] = {'runs': len(samples), 'passed': passed, 'failed': len(samples)-passed}
    result['status'] = 'passed' if passed == len(samples) else 'failed'; publish(); return result
