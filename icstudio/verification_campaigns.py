"""Bounded, resumable saved-plan execution on a trusted worker filesystem.

Each case has an immutable input and separate attempt directories. SQLite's
rollback journal arbitrates leases; stale workers cannot publish over a retry.
Workers use Studio's existing subprocess protocol, never a supplied shell command.
Cross-host operation requires the same paths/tools and a filesystem whose SQLite
locking and fsync behavior the operator has qualified. NFS/cloud-sync folders are
not implicitly supported; the local locking probe is not cross-host qualification.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import csv
import hashlib
import json
import os
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time

from .model import atomic_write, clone, design_digest, digest, file_digest, now, uid

SCHEMA = 1
PAGE_SIZE = 100
MAX_WORKERS = 16
MAX_LOG_BYTES = 1024 * 1024
TERMINAL = ('Complete', 'Failed', 'Cancelled')


def _json(value):
    return json.dumps(value, allow_nan=False, sort_keys=True)


def _command(*args):
    prefix = [sys.executable]
    if not getattr(sys, 'frozen', False):
        prefix.append(str(Path(__file__).resolve().parents[1] / 'main.py'))
    return prefix + list(args)


def source_identity():
    from .build_info import WORKFLOW_SOURCE_HASH
    if getattr(sys, 'frozen', False):
        return {'workflow_hash': WORKFLOW_SOURCE_HASH}
    return {'workflow_hash': WORKFLOW_SOURCE_HASH,
            'sources': digest({p.name: file_digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))})}


def _snapshot_pdk(project, stage, destination):
    """Copy locked assets once; preserve their exact bytes and relative names."""
    p = clone(project)
    tech = p['pdk']; lock = tech.get('package_lock', {})
    if not lock.get('files'):
        return p
    source = Path(tech.get('package_root', '')).resolve()
    for relative, expected in lock['files'].items():
        origin = (source / relative).resolve()
        target = (stage / 'assets' / 'pdk' / relative).resolve()
        if not origin.is_relative_to(source) or not target.is_relative_to(stage / 'assets' / 'pdk'):
            raise ValueError('Unsafe locked PDK asset: ' + relative)
        if not origin.is_file() or file_digest(origin) != expected:
            raise ValueError('Locked PDK asset is missing or changed: ' + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
        if file_digest(target) != expected:
            raise ValueError('PDK asset changed while capturing campaign: ' + relative)
    tech['package_root'] = str(destination / 'assets' / 'pdk')
    return p


def _environment(job):
    from .run_environment import stamp
    out = stamp(job)
    out['python_abi'] = [sys.implementation.cache_tag, platform.python_version(), sys.platform, platform.machine()]
    if job['settings'].get('type') == 'silicon':
        try:out['klayout_version'] = version('klayout')
        except PackageNotFoundError:out['klayout_version'] = None
    # Physical jobs invoke more than ngspice; preserve those executable identities.
    if job['engine'] != 'digital':
        out['tools'] = {name: file_digest(path) for name, path in job['settings'].get('tools', {}).items() if path}
    return out


def _seeds(value, path=''):
    found = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = path + '/' + key
            if key in ('seed', 'random_seed', 'mc_seed'):found[name] = item
            else:found.update(_seeds(item, name))
    elif isinstance(value, list):
        for index, item in enumerate(value):found.update(_seeds(item, path + '/' + str(index)))
    return found


def create(directory, project, plan, prepare_job):
    """Stream at most 10,000 captured cases to a new, atomically published folder."""
    from .test_plans import iter_prepare, validate_plans, case_count
    validate_plans({**project, 'test_plans': [plan]})
    destination = Path(directory).resolve()
    if destination.exists():raise ValueError('Choose a new campaign folder; existing evidence is never replaced.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.with_name('.' + destination.name + '.preparing-' + uid())
    stage.mkdir()
    connection = None
    try:
        captured = _snapshot_pdk(project, stage, destination)
        campaign_id = uid()
        manifest = dict(schema=SCHEMA, id=campaign_id, name=plan['name'], created=now(),
                        project_id=project['id'], original_design_hash=design_digest(project),
                        plan=clone(plan), case_count=case_count(plan), source=source_identity(),
                        filesystem='SQLite rollback journal; trusted workers with identical mount paths')
        atomic_write(stage / 'manifest.json', _json(manifest))
        connection = sqlite3.connect(stage / 'campaign.sqlite3')
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.execute('PRAGMA synchronous=FULL')
        connection.executescript('''
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE cases (
                case_index INTEGER PRIMARY KEY, name TEXT NOT NULL, labels TEXT NOT NULL,
                input_hash TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'Queued',
                attempts INTEGER NOT NULL DEFAULT 0, token TEXT, worker TEXT,
                lease_until REAL, elapsed REAL NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
                summary TEXT, result_path TEXT, result_hash TEXT, updated TEXT NOT NULL);
            CREATE INDEX claimable ON cases(state, case_index);
        ''')
        connection.execute('INSERT INTO metadata VALUES (?,?)', ('manifest_hash', digest(manifest)))
        connection.execute('INSERT INTO metadata VALUES (?,?)', ('paused', 'false'))
        # Preparation needs access to the snapshot before its final rename. Use
        # the original, verified assets when validating, then relocate each job.
        for job in iter_prepare(project, plan, prepare_job, group=campaign_id):
            if captured['pdk'].get('package_root') != project['pdk'].get('package_root'):
                job['project']['pdk'] = clone(captured['pdk'])
            from .run_environment import stamp
            job['environment'] = stamp(job)
            case = job['case']; index = case['index']
            case['fingerprint'] = digest({key: value for key, value in job.items() if key != 'case'})
            provenance = dict(source=manifest['source'], environment=_environment(job),
                              original_design_hash=manifest['original_design_hash'],
                              design_hash=design_digest(job['project']),
                              pdk_hash=digest(job['project']['pdk']),
                              models=clone(job['project']['pdk'].get('package_lock', {})),
                              embedded_models=clone(job['project'].get('spice', {}).get('library_lock', {})),
                              conditions=clone(case['labels']), seeds=_seeds(job['project']) | _seeds(job['settings'], '/settings'))
            job['campaign_provenance'] = provenance
            path = stage / 'cases' / f'{index:05d}' / 'input.json'
            atomic_write(path, _json(job))
            connection.execute('INSERT INTO cases(case_index,name,labels,input_hash,updated) VALUES (?,?,?,?,?)',
                               (index, case['test_name'], _json(case['labels']), file_digest(path), now()))
            if index % 100 == 0:connection.commit()
        connection.commit(); connection.close(); connection = None
        os.rename(stage, destination)
        return Campaign(destination)
    except BaseException:
        if connection is not None:connection.close()
        shutil.rmtree(stage, ignore_errors=True)
        raise


class Campaign:
    def __init__(self, directory):
        self.path = Path(directory).resolve()
        self.manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
        if self.manifest.get('schema') != SCHEMA:raise ValueError('Unsupported verification campaign format.')
        with self.connect() as db:
            expected = db.execute("SELECT value FROM metadata WHERE key='manifest_hash'").fetchone()
            if expected is None or expected[0] != digest(self.manifest):raise ValueError('Campaign manifest changed since capture.')

    @contextmanager
    def connect(self):
        # mode=rw never creates a new database while opening a damaged campaign.
        db = sqlite3.connect((self.path / 'campaign.sqlite3').as_uri() + '?mode=rw', uri=True, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:yield db
        finally:db.close()

    def counts(self):
        with self.connect() as db:
            result = {row['state']: row['n'] for row in db.execute('SELECT state,COUNT(*) n FROM cases GROUP BY state')}
            result['total'] = sum(result.values())
            result['specification_failures'] = db.execute("SELECT COUNT(*) FROM cases WHERE state='Complete' AND json_extract(summary,'$.failed')>0").fetchone()[0]
            result['paused'] = db.execute("SELECT value FROM metadata WHERE key='paused'").fetchone()[0] == 'true'
            return result

    def page(self, offset=0, limit=PAGE_SIZE, failures_only=False):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= PAGE_SIZE:
            raise ValueError('Campaign pages contain 1–100 cases and a nonnegative offset.')
        with self.connect() as db:
            where = "WHERE state IN ('Failed','Interrupted','Cancelled') OR (state='Complete' AND json_extract(summary,'$.failed')>0)" if failures_only else ''
            return [dict(row) for row in db.execute('SELECT * FROM cases ' + where + ' ORDER BY case_index LIMIT ? OFFSET ?', (limit, offset))]

    def job(self, index):
        with self.connect() as db:row = db.execute('SELECT input_hash FROM cases WHERE case_index=?', (index,)).fetchone()
        if row is None:raise ValueError('Unknown campaign case.')
        path = self.path / 'cases' / f'{index:05d}' / 'input.json'
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row[0]:raise ValueError('Campaign input changed since capture; create a new campaign.')
        return json.loads(data)

    def claim(self, worker, lease_seconds=60):
        if not 5 <= lease_seconds <= 3600:raise ValueError('Worker leases must last 5–3,600 seconds.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT value FROM metadata WHERE key='paused'").fetchone()[0] == 'true':return None
            db.execute("UPDATE cases SET state='Interrupted',token=NULL,error='Worker lease expired; prior attempt retained.',updated=? WHERE state='Running' AND lease_until<?", (now(), time.time()))
            row = db.execute("SELECT * FROM cases WHERE state IN ('Queued','Interrupted') ORDER BY case_index LIMIT 1").fetchone()
            if row is None:return None
            token = uid()
            db.execute("UPDATE cases SET state='Running',attempts=attempts+1,token=?,worker=?,lease_until=?,updated=? WHERE case_index=?",
                       (token, worker, time.time() + lease_seconds, now(), row['case_index']))
            return dict(row, token=token, attempts=row['attempts'] + 1)

    def heartbeat(self, index, token, lease_seconds=60):
        with self.connect() as db:
            if db.execute("SELECT value FROM metadata WHERE key='paused'").fetchone()[0] == 'true':return False
            return db.execute("UPDATE cases SET lease_until=?,updated=? WHERE case_index=? AND token=? AND state='Running'",
                              (time.time() + lease_seconds, now(), index, token)).rowcount == 1

    def finish(self, index, token, state, elapsed=0, error='', summary=None, result_path=None, result_hash=None):
        if state not in TERMINAL + ('Interrupted',):raise ValueError('Invalid terminal case state.')
        with self.connect() as db:
            return db.execute('''UPDATE cases SET state=?,elapsed=?,error=?,summary=?,result_path=?,result_hash=?,token=NULL,
                lease_until=NULL,updated=? WHERE case_index=? AND token=? AND state='Running' ''',
                (state, elapsed, error[-16000:], _json(summary) if summary is not None else None,
                 result_path, result_hash, now(), index, token)).rowcount == 1

    def pause(self):
        with self.connect() as db:db.execute("UPDATE metadata SET value='true' WHERE key='paused'")

    def resume(self, retry_failed=False):
        with self.connect() as db:
            db.execute("UPDATE metadata SET value='false' WHERE key='paused'")
            if retry_failed:
                db.execute("UPDATE cases SET state='Queued',error='',updated=? WHERE state IN ('Failed','Cancelled') OR (state='Complete' AND json_extract(summary,'$.failed')>0)", (now(),))

    def row(self, index):
        """Load one case's waveform on demand, using the normal result validator."""
        with self.connect() as db:row = db.execute('SELECT * FROM cases WHERE case_index=?', (index,)).fetchone()
        if row is None:raise ValueError('Unknown campaign case.')
        job = self.job(index)
        path = self.path / row['result_path'] if row['result_path'] else self.path / 'cases' / f'{index:05d}'
        if not path.resolve().is_relative_to(self.path):raise ValueError('Invalid campaign result path.')
        result = dict(id=str(index), name=row['name'], job=job, path=path, state=row['state'],
                      elapsed=row['elapsed'], log=row['error'], progress=100 if row['state']=='Complete' else 0)
        if row['state'] == 'Complete':
            from .job_store import read_result
            if file_digest(path / 'input.json') != row['input_hash']:
                raise ValueError('Saved attempt input differs from the immutable campaign case.')
            if not row['result_hash'] or file_digest(path / 'result.json') != row['result_hash']:
                raise ValueError('Saved result changed after campaign completion.')
            from .pdks import model_lines
            model_lines(job['project']['pdk'], job['settings'].get('corner','nominal'))
            result['result'] = read_result(path / 'result.json', self.manifest['project_id'])
        return result

    def export(self, path):
        """Stream summaries; waveform arrays stay in their separate attempt files."""
        with open(path, 'w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['case', 'test', 'conditions', 'state', 'attempts', 'elapsed_s', 'error', 'summary', 'result_directory'])
            with self.connect() as db:
                for row in db.execute('SELECT * FROM cases ORDER BY case_index'):
                    writer.writerow([row[key] for key in ('case_index','name','labels','state','attempts','elapsed','error','summary','result_path')])


def _summary(job, result):
    from .test_plans import matrix
    data = matrix([dict(id='case', job=job, result=result, state='Complete')], job['case']['group'])
    requirements = []
    for row in data['rows']:
        for value in row['values'].values():
            requirements.append(dict(name=row['name'], unit=row['unit'], **{key: value[key] for key in ('status','value','margin','detail')}))
    return dict(requirements=requirements,
                passed=sum(r['status']=='PASS' for r in requirements),
                failed=sum(r['status'] in ('FAIL','ERROR') for r in requirements))


def locking_probe(directory):
    campaign = Campaign(directory)
    with campaign.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        completed = subprocess.run(_command('--campaign', 'lock-probe', str(campaign.path / 'campaign.sqlite3')),
                                   capture_output=True, text=True, timeout=15)
        if completed.returncode != 0:raise ValueError('Filesystem locking probe failed; use a qualified local filesystem.')


def _terminate(process):
    if process.poll() is not None:return
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'], capture_output=True)
    else:
        try:os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:return
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':process.kill()
        else:
            try:os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:pass
        process.wait(timeout=5)


def _execute(campaign, claim, stop, timeout, lease_seconds):
    index, token = claim['case_index'], claim['token']
    start = time.monotonic(); process = None
    attempt = campaign.path / 'cases' / f'{index:05d}' / ('attempt-' + token)
    attempt.mkdir()
    try:
        job = campaign.job(index)
        def verify_provenance():
            if source_identity() != campaign.manifest['source']:
                raise ValueError('Studio source changed since capture; use the original application or create a new campaign.')
            if _environment(job) != job['campaign_provenance']['environment']:
                raise ValueError('Captured engine/tool identity differs on this worker; restore the exact executable.')
            from .pdks import model_lines
            model_lines(job['project']['pdk'], job['settings'].get('corner', 'nominal'))
        verify_provenance()
        atomic_write(attempt / 'input.json', _json(job))
        from .job_store import state, read_result
        state(attempt, 'running')
        with open(attempt / 'output.log', 'wb') as log:
            process = subprocess.Popen(_command('--worker', str(attempt/'input.json'), str(attempt/'result.json')),
                                       stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=os.name != 'nt')
            heartbeat = 0.
            while process.poll() is None:
                current = time.monotonic()
                if stop.is_set():raise InterruptedError('Worker stopped; resume this campaign to retry its saved input.')
                if current - start > timeout:raise TimeoutError(f'Case exceeded the {timeout:g} second time limit.')
                if log.tell() > MAX_LOG_BYTES:raise ValueError('Worker output exceeded the 1 MiB log limit; inspect the retained attempt log.')
                if current >= heartbeat:
                    if not campaign.heartbeat(index, token, lease_seconds):raise InterruptedError('Campaign paused or worker lease reassigned.')
                    heartbeat = current + min(5, lease_seconds / 3)
                stop.wait(.1)
        if process.returncode != 0:
            message = (attempt / 'output.log').read_bytes()[-16000:].decode('utf-8', 'replace')
            raise ValueError(f'Worker exited with code {process.returncode}.\n' + message)
        verify_provenance()
        result = read_result(attempt / 'result.json', campaign.manifest['project_id'], False)
        summary = _summary(job, result)
        state(attempt, 'complete', elapsed=time.monotonic()-start)
        campaign.finish(index, token, 'Complete', time.monotonic()-start, summary=summary,
                        result_path=str(attempt.relative_to(campaign.path)),result_hash=file_digest(attempt / 'result.json'))
    except Exception as exc:
        if process is not None:_terminate(process)
        status = 'Interrupted' if isinstance(exc, InterruptedError) else 'Failed'
        from .job_store import state
        state(attempt, status.lower(), elapsed=time.monotonic()-start, error=str(exc))
        campaign.finish(index, token, status, time.monotonic()-start, str(exc),
                        result_path=str(attempt.relative_to(campaign.path)))


def run(directory, workers=2, timeout=3600, stop=None, trusted=False, lease_seconds=60):
    """Use only trusted project snapshots: simulator inputs can contain code."""
    if not trusted:raise ValueError('Use --trust-project only for campaign inputs and shared worker folders you trust.')
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:raise ValueError('Choose 1–16 workers.')
    if not 1 <= timeout <= 86400:raise ValueError('Choose a per-case time limit of 1–86,400 seconds.')
    campaign = Campaign(directory)
    if campaign.manifest['source'] != source_identity():raise ValueError('Studio source changed since capture; use the original application or create a new campaign.')
    locking_probe(directory)
    stop = stop or threading.Event()
    def one(number):
        worker = f'{socket.gethostname()}:{os.getpid()}:{number}'
        while not stop.is_set():
            claim = campaign.claim(worker, lease_seconds)
            if claim is None:
                counts=campaign.counts()
                if counts.get('Running') and not counts['paused']:
                    stop.wait(min(1,lease_seconds/3));continue
                break
            _execute(campaign, claim, stop, timeout, lease_seconds)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, index) for index in range(workers)]
        for future in futures:future.result()
    return campaign.counts()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Durable saved-plan campaigns; trusted local or qualified shared-filesystem workers')
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('create'); build.add_argument('project'); build.add_argument('--plan', required=True); build.add_argument('--output', required=True)
    build.add_argument('--ngspice', default='ngspice'); build.add_argument('--magic', default='magic'); build.add_argument('--netgen', default='netgen')
    execute = sub.add_parser('run'); execute.add_argument('directory'); execute.add_argument('--workers', type=int, default=2)
    execute.add_argument('--timeout', type=float, default=3600); execute.add_argument('--trust-project', action='store_true')
    for name in ('status', 'pause', 'resume', 'retry-failed'):
        sub.add_parser(name).add_argument('directory')
    export = sub.add_parser('export'); export.add_argument('directory'); export.add_argument('--output', required=True)
    probe = sub.add_parser('lock-probe', help=argparse.SUPPRESS); probe.add_argument('database')
    args = parser.parse_args(argv)
    try:
        if args.command == 'lock-probe':
            with sqlite3.connect(args.database, timeout=0) as db:
                try:db.execute('BEGIN IMMEDIATE')
                except sqlite3.OperationalError as exc:return 0 if 'locked' in str(exc).lower() else 1
            return 1
        if args.command == 'create':
            from .model import load_project
            project = load_project(args.project)
            plans = [p for p in project.get('test_plans', []) if args.plan in (p['id'], p['name'])]
            if len(plans) != 1:raise ValueError('Choose one saved plan by its exact name or identity.')
            def prepare(settings, engine, project, cell):
                if engine == 'digital':
                    from .digital_design import config, set_config
                    from .digital_flow import prepare as prepare_digital
                    project = clone(project); case = settings['digital_case']; value = clone(config(project, cell))
                    value.pop('tests', None)
                    value.update(testbench=case['testbench'], defines={**value.get('defines', {}), **case.get('defines', {})}, coverage=case.get('coverage', False))
                    set_config(project, cell, value)
                    job = prepare_digital(project, 'simulate', case.get('simulator', 'icarus'), cell_id=cell)
                    job['settings']['digital_case'] = clone(case)
                    return job
                job = dict(settings=clone(settings), engine=engine, project=clone(project), cell=cell)
                if settings['type'] == 'silicon':
                    bench = next(t for t in project['testbenches'] if t['id']==settings['testbench'])
                    job['cell'] = bench['dut_cell']
                    job['settings']['tools'] = {name: shutil.which(getattr(args,name)) or getattr(args,name) for name in ('magic','netgen','ngspice')}
                if engine == 'ngspice':job['executable'] = shutil.which(args.ngspice) or args.ngspice
                return job
            campaign = create(args.output, project, plans[0], prepare)
        else:campaign = Campaign(args.directory)
        if args.command == 'run':
            stop = threading.Event()
            for kind in (signal.SIGINT, signal.SIGTERM):signal.signal(kind, lambda *_:stop.set())
            counts = run(args.directory, args.workers, args.timeout, stop, args.trust_project)
            print(_json(counts));return 2 if counts.get('Failed') or counts['specification_failures'] or counts.get('Complete',0)!=counts['total'] else 0
        if args.command == 'pause':campaign.pause()
        if args.command in ('resume', 'retry-failed'):campaign.resume(args.command == 'retry-failed')
        if args.command == 'export':campaign.export(args.output)
        print(_json(campaign.counts()));return 0
    except Exception as exc:
        print(_json({'error': str(exc)}), file=sys.stderr);return 1


if __name__ == '__main__':raise SystemExit(main())
