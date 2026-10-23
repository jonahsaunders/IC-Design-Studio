"""Fail-closed development reuse of one complete native LI physical case.

Linux's reviewed headless IC Studio launchers are the only supported profile.
No release entry point imports this module. A receipt is published last, after
raw-output audit and unchanged-input checks; lookup never trusts status alone.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import sysconfig
import time
import uuid

from scripts.audit_sky130_li_case import CASE, FAULTS, audit

SUITE = 'sky130-li-physical-development-v1'
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = {'case': CASE, 'model': 'sky130_fd_pr__res_generic_l1', 'width_um': 2,
            'length_um': 5, 'multiplicity': 1, 'rotations': [0, 90], 'faults': list(FAULTS),
            'drc_counts': [0, 0, 2, 0, 0, 0, 0], 'dimension_tolerance_um': 0,
            'stream_database_unit_um': .001, 'scope': 'physical-only; no simulation PDK used'}
# A changed launcher needs review of its execution dependencies, not merely a
# new cache key. Native binaries/libraries may change and are identity misses.
LAUNCHERS = {
    '/opt/icstudio/bin/magic': '359bd5dbfccf21114b2f18e2ffa008debf159bd0d1ab78e01738d2af9500b223',
    '/opt/icstudio/bin/netgen': '209cc0bab75420d13094a99de13e94af05d735e744e06d817fac022ac74401d3',
    '/opt/icstudio/physical/installed/bin/magic': '4b74020f201fd8b09b4984614249f3602dd1f4b2a3731e087dfe88eeacc887c5',
}
NATIVE_TREES = {
    '/opt/icstudio/physical/installed': '12a0cae4b96c59dddbd3e8d4470973871fab052ef047fb0e98c3040c8f52eb8f',
    '/usr/share/tcltk': '18d3ef2d1f0c3c3d253a05c4bf0c7c189de54f8384ef926dd18178cc1b34bc9e',
    '/usr/lib/tcltk': '1ca2ada63b252a96da6f6a98c63301aed76e48dcba7c2b343314d00d1f77b1d5',
}
EMPTY_HOME = '/__icstudio_li_development_no_home__'
EMPTY_BYTECODE = '/__icstudio_li_development_no_bytecode__'
ENV = {'PATH': '/opt/icstudio/bin:/usr/bin:/bin', 'HOME': EMPTY_HOME,
       'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC', 'PYTHONDONTWRITEBYTECODE': '1',
       'PYTHONNOUSERSITE': '1', 'PYTHONHASHSEED': '0'}


def digest(path):
    with Path(path).open('rb') as stream:
        before = os.fstat(stream.fileno())
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('Input changed while hashing: ' + str(path))
    return value


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def key(value):
    return hashlib.sha256(encode(value)).hexdigest()


def write(path, value):
    # Every invocation has a new directory. Atomic terminal publication avoids
    # making a truncated receipt appear complete after cancellation.
    path = Path(path)
    temporary = path.with_name(path.name + '.writing')
    with temporary.open('xb') as stream:
        stream.write(encode(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def now():
    return datetime.now(timezone.utc).isoformat()


def selection(values):
    if values != [CASE]:
        raise ValueError('Development pilot requires exactly one --select l1-w2-l5; empty, duplicate and unknown cases are rejected.')
    return list(values)


def file_identity(path):
    path = Path(path)
    if not path.exists():
        return {'absent': True}
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError('Expected a regular identity input: ' + str(path))
    return {'sha256': digest(path), 'bytes': path.stat().st_size,
            'mode': stat.S_IMODE(path.stat().st_mode), 'resolved': str(resolved)}


def tree(root, *, evidence=False):
    root = Path(root)
    if evidence and root.is_symlink():
        raise ValueError('Symlinked evidence directory.')
    if not root.exists():
        if evidence:
            raise ValueError('Missing evidence directory.')
        return {'$root': {'absent': True}}
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                if evidence or path.resolve().is_dir():
                    raise ValueError('Unsupported evidence/runtime directory symlink: ' + str(path))
                result[relative] = {'link': os.readlink(path), **file_identity(path)}
            elif path.is_dir():
                result[relative] = {'directory': True}
            elif path.is_file():
                result[relative] = file_identity(path)
                # Evidence is relocatable for independent audit/control copies;
                # absolute execution identity is retained separately in receipt.
                if evidence:
                    result[relative].pop('resolved')
            else:
                raise ValueError('Unsupported special file: ' + str(path))
    return result


def sources(root=ROOT):
    root = Path(root)
    paths = [p for name in ('icstudio', 'scripts', 'tests') for p in (root / name).rglob('*.py')]
    # Fixtures, limits, locks and application assets can affect this path even
    # when no Python changes. Include these bounded locations conservatively.
    paths += [p for p in (root / 'icstudio/assets').rglob('*') if p.is_file()]
    paths += [p for p in (root / 'examples').glob('*') if p.is_file() and p.suffix in ('.json', '.icproj')]
    paths += [p for p in root.glob('requirements*.txt') if p.is_file()]
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(set(paths))}


@contextmanager
def controlled_environment():
    if Path(EMPTY_HOME).exists():
        raise ValueError('The development no-home sentinel exists; refusing possible startup configuration.')
    old = dict(os.environ)
    os.environ.clear()
    os.environ.update(ENV)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


def elf(path):
    with Path(path).open('rb') as stream:
        return stream.read(4) == b'\x7fELF'


def libraries(executables):
    """Resolve actual ELF dependencies under the effective native library path."""
    result = {}
    for executable in sorted(set(map(str, executables))):
        if not elf(executable):
            continue
        proc = subprocess.run(['/usr/bin/ldd', executable], capture_output=True, text=True,
                              env={**ENV, 'LD_LIBRARY_PATH': '/opt/icstudio/lib'}, timeout=30)
        if proc.returncode or 'not found' in proc.stdout + proc.stderr:
            raise ValueError('Unresolved ELF dependency: ' + executable + '\n' + proc.stdout + proc.stderr)
        paths = re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', proc.stdout, re.M)
        if not paths and proc.stdout.strip() != 'statically linked':
            raise ValueError('No resolved dynamic dependencies for ' + executable)
        result[executable] = {path: file_identity(path) for path in sorted(set(paths))}
    return result


def runtime(tools):
    if sys.platform != 'linux' or platform.machine() != 'x86_64':
        raise ValueError('Development reuse supports only the reviewed Linux x86_64 headless runtime; use the fresh runner otherwise.')
    if any(tools[name] != '/opt/icstudio/bin/' + name for name in ('magic', 'netgen')):
        raise ValueError('Unsupported native launcher paths for development reuse.')
    if not sys.dont_write_bytecode or sys.version_info[:2] != (3, 12):
        raise ValueError('Development reuse requires Python 3.12 with bytecode writes disabled (-B).')
    if sys.flags.hash_randomization or not sys.flags.no_user_site:
        raise ValueError('Start Python with PYTHONHASHSEED=0 and PYTHONNOUSERSITE=1; setting these after startup is insufficient.')
    if sys.pycache_prefix != EMPTY_BYTECODE or Path(EMPTY_BYTECODE).exists():
        raise ValueError('Use -X pycache_prefix=' + EMPTY_BYTECODE + ' with -B and keep that path absent; stale project bytecode cannot establish source identity.')
    for path, expected in LAUNCHERS.items():
        if digest(path) != expected:
            raise ValueError('Unreviewed launcher dependency closure: ' + path)
    # Import before reading mapped native dependencies. KLayout is the only
    # native Python dependency exercised by the selected headless case/audit.
    import klayout.db  # noqa: F401
    import klayout
    native = Path('/opt/icstudio/physical/installed')
    roots = [native, Path('/opt/icstudio/lib'), Path('/usr/share/tcltk'), Path('/usr/lib/tcltk'),
             Path('/usr/lib/x86_64-linux-gnu/tcl8.6'), Path('/usr/lib/x86_64-linux-gnu/tk8.6'),
             Path(sysconfig.get_path('stdlib')), Path(sysconfig.get_path('purelib'))]
    # All non-project import roots must be inventoried. This captures .pth,
    # package metadata, Python modules, bytecode and extension payloads.
    for value in sys.path:
        path = Path(value or os.getcwd()).absolute()
        if path.is_relative_to(ROOT):
            continue
        if not (str(path).startswith('/usr/') or str(path).startswith(str(Path(sys.prefix)))):
            raise ValueError('Unsupported Python import root: ' + str(path))
        roots.append(path)
    roots = sorted(set(roots))
    roots = [p for p in roots if not any(p != q and p.is_relative_to(q) for q in roots)]
    inventories = {str(path): tree(path) if path.is_dir() else {'$file': file_identity(path)} for path in roots}
    # Changes to native Tcl or its executables can introduce new dynamically
    # opened paths that ldd cannot enumerate. Reject them until that call graph
    # has been reviewed; version strings alone cannot establish this profile.
    for path, expected in NATIVE_TREES.items():
        if key(inventories[path]) != expected:
            raise ValueError('Unreviewed native/Tcl runtime closure: ' + path)
    executables = [Path(sys.executable).resolve(), Path('/usr/bin/tclsh8.6'),
                   native / 'lib/magic/tcl/magicdnull', *native.rglob('*.so'),
                   *[Path('/usr/bin') / name for name in ('bash', 'dash', 'env', 'dirname', 'uname', 'cut')]]
    # Map actual imported Python ELF payloads as well as explicitly loaded Tcl
    # extensions. Full package trees above detect unimported helper changes.
    mapped = []
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) == 6 and fields[5].startswith('/'):
            path = Path(fields[5])
            if not path.exists():
                raise ValueError('Mapped runtime payload was removed: ' + str(path))
            if path.is_file() and elf(path):
                if path.stat().st_ino != int(fields[4]):
                    raise ValueError('Mapped runtime payload differs from the file on disk: ' + str(path))
                mapped.append(path)
    executables += mapped
    dependencies = libraries(executables)
    fixed = [*map(Path, LAUNCHERS), Path('/usr/bin/ldd'), Path('/etc/ld.so.cache'),
             Path('/etc/ld.so.preload'), Path('/etc/os-release'), Path(sys.prefix) / 'pyvenv.cfg',
             *executables]
    if Path('/etc/ld.so.preload').exists() and Path('/etc/ld.so.preload').read_text().strip():
        raise ValueError('System preloaded libraries are outside the reviewed runtime profile.')
    return {'profile': 'linux-x86_64-headless-icstudio-v1', 'python': sys.version,
            'executable': str(Path(sys.executable)), 'prefix': sys.prefix,
            'python_flags': repr(sys.flags), 'filesystem_encoding': sys.getfilesystemencoding(),
            'bytecode_cache_prefix': sys.pycache_prefix,
            'klayout': klayout.__version__, 'sys_path': sys.path,
            'platform': platform.platform(), 'libc': platform.libc_ver(),
            'environment': dict(os.environ), 'native_launcher_environment': {
                'LD_LIBRARY_PATH': '/opt/icstudio/lib', 'TCL_LIBRARY': '/usr/share/tcltk/tcl8.6',
                'CAD_ROOT': '/opt/icstudio/physical/installed/lib'},
            'files': {str(path): file_identity(path) for path in sorted(set(fixed))},
            'trees': inventories, 'elf_dependencies': dependencies}


def identity(pdk, tools):
    return {'schema': 1, 'suite': SUITE, 'contract': CONTRACT, 'sources': sources(),
            'physical_pdk': {'root': str(pdk), 'files': tree(pdk)}, 'simulation_pdk': None,
            'tools': tools, 'runtime': runtime(tools)}


def source_commit(root=ROOT):
    """Accept a narrow frozen source copy only with an exact source manifest."""
    root = Path(root)
    frozen = root / '.qualification-source.json'
    if frozen.exists():
        value = json.loads(frozen.read_bytes())
        if value.get('schema') != 1 or value.get('sources') != sources(root) or not re.fullmatch(r'[0-9a-f]{40}', value.get('commit', '')):
            raise ValueError('Frozen source identity is missing, corrupt or changed.')
        return value['commit']
    env = {name: value for name, value in os.environ.items() if not name.startswith('GIT_')}
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(root), 'rev-parse', 'HEAD'], cwd=root, text=True, env=env).strip()


def receipt(case_folder, identity_value, execution):
    case_folder = Path(case_folder)
    outcome = audit(case_folder, identity=identity_value)
    manifest = tree(case_folder, evidence=True)
    write(case_folder.parent / 'case-manifest.json', manifest)
    value = {'schema': 1, 'suite': SUITE, 'case': CASE, 'status': 'COMPLETE',
             'input_key': key(identity_value), 'identity_sha256': digest(case_folder.parent / 'inputs.json'),
             'manifest_sha256': digest(case_folder.parent / 'case-manifest.json'),
             'execution': execution, 'audit': outcome, 'published': now()}
    write(case_folder.parent / 'receipt.json', value)
    return value


def lookup(previous, identity_value):
    """Return only an independently audited original execution; all errors miss."""
    previous = Path(previous)
    try:
        if previous.is_symlink():
            raise ValueError('Symlinked evidence root.')
        previous = previous.resolve()
        report = json.loads((previous / 'qualification.json').read_bytes())
        if report.get('mode') != 'development' or report.get('status') != 'PASS' or report.get('selected') != [CASE]:
            raise ValueError('Original run is incomplete, failed or not this selected development suite.')
        value = json.loads((previous / 'receipt.json').read_bytes())
        if value.get('schema') != 1 or value.get('suite') != SUITE or value.get('case') != CASE or value.get('status') != 'COMPLETE':
            raise ValueError('Missing complete terminal receipt.')
        old_identity = json.loads((previous / 'inputs.json').read_bytes())
        if value['input_key'] != key(identity_value) or key(old_identity) != value['input_key']:
            raise ValueError('Input identity changed.')
        if value['identity_sha256'] != digest(previous / 'inputs.json'):
            raise ValueError('Original execution input identity is corrupt.')
        execution = value['execution']
        if execution['output'] != str(previous) or execution['case_path'] != str(previous / CASE):
            raise ValueError('Receipt origin does not match original execution; resume from the original directory.')
        if report.get('execution') != execution or report.get('input_key') != value['input_key']:
            raise ValueError('Original aggregate and receipt disagree.')
        if execution.get('source_hashes') != old_identity.get('sources', execution.get('source_hashes')):
            raise ValueError('Original execution source hashes disagree with inputs.')
        if value['manifest_sha256'] != digest(previous / 'case-manifest.json'):
            raise ValueError('Corrupt case manifest.')
        manifest = json.loads((previous / 'case-manifest.json').read_bytes())
        if manifest != tree(previous / CASE, evidence=True):
            raise ValueError('Incomplete or corrupt native evidence inventory.')
        checked = audit(previous / CASE, identity=identity_value)
        return {'hit': True, 'execution': execution, 'receipt_sha256': digest(previous / 'receipt.json'),
                'manifest_sha256': value['manifest_sha256'], 'validated': now(), 'audit': checked}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        return {'hit': False, 'reason': str(error), 'validated': now()}


def execute(args, producer, technology):
    selection(args.select)
    if args.pilot or args.models != list(producer.MODELS) or args.workers != 2:
        raise ValueError('Development --select owns case selection; do not combine it with --pilot, --models or --workers overrides.')
    sys.dont_write_bytecode = True
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 1, 'suite': SUITE, 'mode': 'development', 'status': 'RUNNING',
              'selected': [CASE], 'pilot_supported_cases': [CASE],
              'exhaustive_required_cases': [f'{m}-w{w:g}-l{l:g}' for m in producer.MODELS
                                            for w, l in (*producer.SIZES, (producer.MODELS[m][1],) * 2)],
              'qualified': False, 'chunk_complete': False, 'release_acceptance': False,
              'created': now(), 'timings_seconds': {}}
    write(out / 'qualification.json', report)
    start = time.monotonic()
    try:
        pdk = args.sky130.resolve(strict=True)
        tech, process = technology('sky130A', pdk)
        tools = {name: str(Path(getattr(args, name)).resolve(strict=True)) for name in ('magic', 'netgen')}
        commit = source_commit()
        with controlled_environment():
            before_start = time.monotonic()
            before = identity(pdk, tools)
            report['timings_seconds']['input_identity_before'] = round(time.monotonic() - before_start, 6)
            write(out / 'inputs.json', before)
            report['input_key'] = key(before)
            lookup_start = time.monotonic()
            reuse = lookup(args.resume_from, before) if args.resume_from else {'hit': False, 'reason': 'No prior run selected.'}
            report['reuse'] = reuse
            report['timings_seconds']['reuse_lookup_and_audit'] = round(time.monotonic() - lookup_start, 6)
            if reuse['hit']:
                report['original_execution'] = reuse['execution']
                report['native_execution'] = False
            else:
                execution = {'run_id': str(uuid.uuid4()), 'case_id': CASE, 'output': str(out),
                             'case_path': str(out / CASE), 'source_commit': commit,
                             'source_hashes': before['sources'], 'started': now()}
                native_start = time.monotonic()
                result = producer.case(tech, 'l1', 2, 5, out, tools)
                execution.update(finished=now(), native_elapsed_seconds=round(time.monotonic() - native_start, 6))
                report['execution'] = execution
                report['native_execution'] = True
                report['timings_seconds']['native_execution'] = execution['native_elapsed_seconds']
                if result['status'] != 'PASS':
                    raise ValueError('Native selected case failed: ' + str(result.get('error')))
                audit_start = time.monotonic()
                report['independent_audit'] = audit(out / CASE, identity=before)
                report['timings_seconds']['independent_audit'] = round(time.monotonic() - audit_start, 6)
            after_start = time.monotonic()
            after = identity(pdk, tools)
            report['timings_seconds']['input_identity_after'] = round(time.monotonic() - after_start, 6)
            if before != after:
                write(out / 'inputs-after.json', after)
                raise ValueError('Inputs changed during execution/reuse validation; no terminal receipt published.')
            report.update(status='PASS', process=process, inputs_unchanged=True)
            if not reuse['hit']:
                receipt(out / CASE, before, execution)
    except Exception as error:
        report.update(status='FAIL', error=repr(error))
    report['timings_seconds']['total'] = round(time.monotonic() - start, 6)
    write(out / 'qualification.json', report)
    reuse_summary = {name: report.get('reuse', {}).get(name) for name in ('hit', 'reason', 'validated')}
    print(json.dumps({'status': report['status'], 'reuse': reuse_summary, 'error': report.get('error'),
                      'timings_seconds': report['timings_seconds']}, indent=2), flush=True)
    return 0 if report['status'] == 'PASS' else 1
