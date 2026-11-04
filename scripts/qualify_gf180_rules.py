"""Run the complete pinned GF180 deck on a captured production finish job.

The geometry gate still executes and records density. It never labels a
density-failing layout clean or qualified for tapeout.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import digital_flow
from icstudio.digital_macro import verify_inputs
from icstudio.model import atomic_write, file_digest

LOCK = ROOT / 'examples/gf180-digital-drc-lock.json'
GROUPS = {'main', 'antenna', 'density'}
COMPLETION = {'main': ': main DRC Total Run time ',
              'antenna': ': Antenna DRC total Run time: ',
              'density': ': DRC Total Run time '}


def read_reports(output, top, exit_code):
    """Require all three completed native runs, not just an empty report."""
    output = Path(output)
    log = (output / 'engine.log').read_text(errors='replace')
    if any(word in log for word in ('Traceback (most recent call last)', 'ERROR:', 'CalledProcessError')):
        raise ValueError('The native rule engine failed; inspect engine.log.')
    starts = re.findall(r'checks on design (main|antenna|density) on cell ' + re.escape(top) + ':', log)
    if len(starts) != 3 or set(starts) != GROUPS:
        raise ValueError('The native log must identify all three rule runs on this top cell.')
    reports = []
    for path in sorted((output / 'drc').rglob('*.lyrdb')):
        tree = ET.parse(path)
        if (tree.getroot().tag != 'report-database' or tree.findtext('top-cell') != top
                or tree.find('items') is None or tree.find('categories') is None):
            raise ValueError('A native report is incomplete or names a different top cell.')
        group = path.stem.rsplit('_', 1)[-1]
        if group not in COMPLETION or not re.search(re.escape(COMPLETION[group]) + r'[0-9.]+ seconds', log):
            raise ValueError('The native engine did not complete rule group: ' + group)
        items = tree.findall('./items/item')
        reports.append({'path': path.relative_to(output).as_posix(), 'sha256': file_digest(path),
            'group': group, 'markers': len(items),
            'categories': dict(Counter(item.findtext('category') for item in items))})
    counts = {r['group']: r['markers'] for r in reports}
    if len(reports) != 3 or set(counts) != GROUPS:
        raise ValueError('Require exactly one main, antenna and density report.')
    if type(exit_code) is not int or exit_code != (1 if any(counts.values()) else 0):
        raise ValueError('The native exit code does not agree with its complete reports.')
    return reports, counts


def verify_deck(root, lock):
    root = Path(root).resolve()
    actual = {p.relative_to(root).as_posix(): file_digest(p)
        for p in (root / 'klayout/drc').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    if actual != lock['files']:
        raise ValueError('Use the complete unchanged GF180 DRC source at ' + lock['revision'] + '.')
    return actual


def qualify(job, deck, output, variant, gate, python, klayout):
    job = Path(job).resolve(); deck = Path(deck).resolve(); output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Choose an empty rule-verification output directory.')
    output.mkdir(parents=True, exist_ok=True)
    record = {'schema': 1, 'status': 'running', 'gate': gate, 'variant': variant,
        'scope': 'Pinned GF180 full-deck reference execution; no full-chip or foundry acceptance claim.',
        'qualifier_sha256': file_digest(Path(__file__))}
    def retain(): atomic_write(output / 'report.json', json.dumps(record, indent=2) + '\n')
    retain()
    try:
        lock = json.loads(LOCK.read_text()); files = verify_deck(deck, lock)
        raw = json.loads((job / 'result.json').read_text())
        digital_flow.validate_result(raw, job)
        data = raw['digital_result']
        if data['stage'] != 'finish': raise ValueError('Select a captured final implementation job.')
        prepared = json.loads((job / 'input.json').read_text())
        if not data.get('input_key'):
            raise ValueError('Run physical finish with a saved stage identity before qualification.')
        config = verify_inputs(raw, prepared)
        expected = {'TRACK_OPTION': '9t', 'METAL_OPTION': '5LM_1TM',
                    'KVALUE': {'C': '9', 'D': '11'}[variant], 'POWER_OPTION': '5v0'}
        if config['platform'].get('orfs', {}).get('variables') != expected:
            raise ValueError('The requested variant does not match the captured physical stack.')
        gds = job / data['artifacts']['gds']['path']; before = file_digest(gds)
        executable = Path(shutil.which(klayout) or klayout).absolute()
        if executable.name != 'klayout' or not executable.is_file():
            raise ValueError('Select the native klayout executable or an isolated launcher named klayout.')
        env = {**os.environ, 'PATH': str(executable.parent) + os.pathsep + os.environ.get('PATH', '')}
        version = subprocess.run([str(executable), '-v'], env=env, check=True,
            capture_output=True, text=True).stdout.strip()
        if version != 'KLayout 0.30.5': raise ValueError('This qualification pins KLayout 0.30.5.')
        command = [str(python), str(deck / 'klayout/drc/run_drc.py'), '--path=' + str(gds),
            '--variant=' + variant, '--topcell=' + config['top'], '--run_dir=' + str(output / 'drc'),
            '--thr=2', '--mp=1', '--density', '--antenna']
        record.update(command=command, top=config['top'], input_sha256=file_digest(job / 'input.json'),
            result_sha256=file_digest(job / 'result.json'), gds_sha256=before,
            platform_fingerprint=config['platform']['fingerprint'],
            geometry_recipe=config['platform'].get('orfs', {}).get('geometry_recipe'),
            deck_lock_sha256=file_digest(LOCK), deck_revision=lock['revision'],
            deck_files=files, klayout={'path': str(executable), 'sha256': file_digest(executable), 'version': version})
        retain()
        with (output / 'engine.log').open('w') as stream:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1200)
        record.update(exit=result.returncode, engine_log_sha256=file_digest(output / 'engine.log')); retain()
        if before != file_digest(gds) or files != verify_deck(deck, lock):
            raise ValueError('Input geometry or verification sources changed during execution.')
        reports, counts = read_reports(output, config['top'], result.returncode)
        geometry = counts['main'] == counts['antenna'] == 0
        density = counts['density'] == 0
        record.update(reports=reports, counts=counts, geometry_passed=geometry, density_passed=density,
            status='all_rules_passed' if geometry and density else
                   'geometry_passed_density_failed' if geometry else 'geometry_failed')
        retain()
        return geometry and (density or gate == 'geometry')
    except Exception as exc:
        record.update(status='failed', error=str(exc)); retain(); raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--deck', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variant', choices=('C', 'D'), required=True)
    parser.add_argument('--gate', choices=('geometry', 'all'), default='all')
    parser.add_argument('--python', default=sys.executable, help='Python with klayout 0.30.5 and docopt 0.6.2.')
    parser.add_argument('--klayout', default='klayout')
    args = parser.parse_args()
    return 0 if qualify(args.job, args.deck, args.output, args.variant, args.gate, args.python, args.klayout) else 1


if __name__ == '__main__': raise SystemExit(main())
