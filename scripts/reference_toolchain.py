"""Transfer one source-locked RC toolchain between jobs in the same CI run.

This is a verified build artifact, not a hermetic environment or an acceptance
cache. Consumers still install runtime dependencies and run fresh qualification.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = {
    'build/gf180-engines': ('examples/gf180-rc-engine-lock.json', None),
    'build/modern-engines': ('examples/modern-schematic-engine-lock.json', 'ngspice'),
}
MANIFEST = 'reference-toolchain-manifest.json'
RESOLUTION = 'reference-toolchain-resolution.json'
READY = 'reference-toolchain-restored.json'


class ImageVersionMismatch(ValueError):
    """A valid payload has matching identity except the hosted image version."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def apt_sources(apt_root, output):
    """Copy source definitions, bypassing only the hosted Ubuntu Azure mirror.

    Keep suites, components and trust settings byte-for-byte. APT receives these
    copies through command-line options; the runner's /etc/apt is never changed.
    Both the current mirror+file form and older direct Azure URIs are supported.
    """
    apt_root, output = Path(apt_root), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new APT source directory.')
    paths = [apt_root / 'sources.list']
    parts = apt_root / 'sources.list.d'
    if parts.is_symlink():
        raise ValueError('Linked APT source directory is not supported.')
    paths += sorted([*parts.glob('*.list'), *parts.glob('*.sources')])
    definitions = {}
    for path in paths:
        if path.is_symlink():
            raise ValueError('Linked APT source definition is not supported: ' + str(path))
        if not path.exists():
            continue
        raw = path.read_bytes()
        # Match complete URI tokens only, never lookalike hosts or paths. Do not
        # interpret or rewrite unknown mirror lists, options, comments or keys.
        pattern = rb'(?<!\S)(?:https?://azure\.archive\.ubuntu\.com/ubuntu/?|mirror\+file:/etc/apt/apt-mirrors\.txt)(?=\s|$)'
        lines = []
        for line in raw.splitlines(keepends=True):
            active, marker, comment = line.partition(b'#')
            lines.append(re.sub(pattern, b'https://archive.ubuntu.com/ubuntu/', active)
                         + marker + comment)
        changed = b''.join(lines)
        definitions[path.relative_to(apt_root).as_posix()] = (raw, changed)
    if not definitions or not any(raw.strip() for raw, _ in definitions.values()):
        raise ValueError('No APT source definitions were found.')
    receipt = {'schema': 1, 'source_root': str(apt_root), 'files': {}}
    (output / 'sources.list.d').mkdir(parents=True)
    # An explicit empty main list prevents APT from reading its system default.
    (output / 'sources.list').write_bytes(b'')
    for name, (raw, changed) in definitions.items():
        (output / name).write_bytes(changed)
        receipt['files'][name] = {'original_sha256': digest(raw),
                                  'selected_sha256': digest(changed),
                                  'changed': raw != changed}
    (output / 'receipt.json').write_bytes(
        (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode())
    return receipt


def expected_locks(root):
    result = {}
    for folder, (name, only) in BUNDLES.items():
        lock = json.loads((root / name).read_bytes())
        result[folder] = {only: lock[only]} if only else lock
    return result


def inputs(root):
    names = {'scripts/reference_toolchain.py', 'scripts/build_physical_engines.py',
             '.github/workflows/reference-compatibility.yml', 'requirements.txt'}
    names.update(name for name, _ in BUNDLES.values())
    for lock in expected_locks(root).values():
        for entry in lock.values():
            if entry.get('patch'):
                name = entry['patch']
                path = root / safe_name(name)
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError('Unsafe toolchain input: ' + name)
                if digest(path.read_bytes()) != entry['patch_sha256']:
                    raise ValueError('Pinned engine patch changed: ' + name)
                names.add(name)
    return {name: digest((root / name).read_bytes()) for name in sorted(names)}


def environment():
    if platform.system() != 'Linux':
        raise ValueError('The reference toolchain is a Linux CI artifact.')
    if not all(os.environ.get(key, '').strip() for key in ('ImageOS', 'ImageVersion')):
        raise ValueError('The hosted runner ImageOS and ImageVersion are required.')
    return {'system': platform.system(), 'machine': platform.machine(),
            'image_os': os.environ.get('ImageOS', ''),
            'image_version': os.environ.get('ImageVersion', '')}


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or '..' in path.parts or '\\' in name
            or ':' in name or str(path) != name):
        raise ValueError('Unsafe archive path: ' + name)
    return name


def identity(root, candidate):
    if not re.fullmatch('[0-9a-f]{40}', candidate):
        raise ValueError('A full immutable candidate SHA is required.')
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                     text=True, env=clean_env).strip()
    if actual != candidate:
        raise ValueError('Checkout differs from the requested candidate.')
    return {'schema': 1, 'candidate': candidate, 'workspace': str(root),
            'environment': environment(), 'inputs': inputs(root)}


def identity_mismatch(root, expected, supplied):
    """Retain only the known identity fields; never dump the process environment."""
    fields = ('candidate', 'workspace', 'environment', 'inputs')
    environment_keys = ('system', 'machine', 'image_os', 'image_version')

    def scalar(value):
        return value[:4096] if isinstance(value, str) else {'invalid_type': type(value).__name__}

    def mapping(value, keys, hashes=False):
        if not isinstance(value, dict):
            return {'invalid_type': type(value).__name__}
        result = {key: (scalar(value.get(key)) if not hashes else
                        value[key] if isinstance(value.get(key), str) and
                        re.fullmatch('[0-9a-f]{64}', value[key]) else {'invalid_hash': True})
                  for key in keys}
        result['unlisted_keys_count'] = len(set(value) - set(keys))
        return result

    def whitelisted(value):
        return {'candidate': scalar(value.get('candidate')),
                'workspace': scalar(value.get('workspace')),
                'environment': mapping(value.get('environment'), environment_keys),
                'inputs': mapping(value.get('inputs'), sorted(expected['inputs']), hashes=True)}

    report = {'status': 'rejected_identity_mismatch',
              'fields': [key for key in fields if supplied.get(key) != expected[key]],
              'unlisted_identity_mismatch': any(supplied.get(key) != value
                                                for key, value in expected.items() if key not in fields),
              'producer': whitelisted(supplied), 'consumer': whitelisted(expected)}
    raw = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    path = root / 'build/reference-toolchain-mismatch.json'
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise OSError('Unsafe diagnostic location.')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        print('Toolchain identity mismatch fields: ' + ', '.join(report['fields']) +
              '; details: build/reference-toolchain-mismatch.json', file=sys.stderr)
    except OSError:
        # Diagnostics must not replace the original rejection if disk writes
        # fail. This fallback contains exactly the same whitelisted fields.
        print(raw.decode(), file=sys.stderr)


def selected(root):
    """Only runtime prefixes, licenses and build provenance; never source trees."""
    result = []
    for folder, lock in expected_locks(root).items():
        directory = root / folder
        if json.loads((directory / 'source-lock.json').read_bytes()) != lock:
            raise ValueError('Built toolchain source lock differs: ' + folder)
        paths = [directory / 'installed', directory / 'licenses',
                 directory / 'source-lock.json']
        for engine in lock:
            paths.extend(directory / (engine + suffix)
                         for suffix in ('-build.log', '-version.log'))
            if not (directory / 'installed/bin' / engine).is_file():
                raise ValueError('Missing installed engine: ' + engine)
            if not any((directory / 'licenses' / engine).iterdir()):
                raise ValueError('Missing upstream license: ' + engine)
        for path in paths:
            if not path.exists() or path.is_symlink():
                raise ValueError('Missing or linked artifact root: ' + str(path))
            result.append(path)
            if path.is_dir():
                for parent, directories, files in os.walk(path, followlinks=False):
                    result.extend(Path(parent) / name for name in directories + files)
    return sorted(set(result), key=lambda path: path.relative_to(root).as_posix())


def file_record(root, path):
    name = path.relative_to(root).as_posix()
    mode = path.lstat().st_mode
    if stat.S_IMODE(mode) & 0o7000:
        raise ValueError('Special runtime permission bits are not allowed: ' + name)
    result = {'mode': stat.S_IMODE(mode)}
    if stat.S_ISLNK(mode):
        target = os.readlink(path)
        if (Path(target).is_absolute() or not path.resolve().is_relative_to(root)
                or not any(path.resolve().is_relative_to(root / folder / 'installed')
                           for folder in BUNDLES)):
            raise ValueError('Symlink escapes installed runtime: ' + name)
        result.update(kind='symlink', target=target)
    elif stat.S_ISDIR(mode):
        result.update(kind='directory')
    elif stat.S_ISREG(mode):
        result.update(kind='file', size=path.stat().st_size,
                      sha256=digest(path.read_bytes()))
    else:
        raise ValueError('Unexpected runtime file type: ' + name)
    return result


def pack(root, output, candidate):
    root = Path(root).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new toolchain archive.')
    record = identity(root, candidate)
    paths = selected(root)
    record['files'] = {p.relative_to(root).as_posix(): file_record(root, p) for p in paths}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz', dereference=False) as archive:
        raw = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode('utf-8')
        header = tarfile.TarInfo(MANIFEST)
        header.size = len(raw)
        header.mode = 0o644
        archive.addfile(header, io.BytesIO(raw))
        for path in paths:
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    (output.parent / MANIFEST).write_bytes(raw)
    return digest(output.read_bytes())


def empty_prefixes(root):
    for folder in BUNDLES:
        if (root / folder).exists() or (root / folder).is_symlink():
            raise ValueError('Refusing to overwrite an existing toolchain: ' + folder)


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate toolchain metadata key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def validate_archive(root, archive_path, expected_sha256, candidate, require_empty=True):
    """Validate every payload byte and path before allowing a reuse miss."""
    root = Path(root).resolve()
    if not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('The producer archive checksum is required.')
    raw = Path(archive_path).read_bytes()
    if digest(raw) != expected_sha256:
        raise ValueError('Toolchain archive checksum differs from its producer.')
    expected = identity(root, candidate)
    if require_empty:
        empty_prefixes(root)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        names = [safe_name(member.name) for member in members]
        if len(names) != len(set(names)) or names.count(MANIFEST) != 1:
            raise ValueError('Duplicate or absent archive manifest.')
        manifest_member = archive.getmember(MANIFEST)
        if not manifest_member.isfile() or manifest_member.size > 20_000_000:
            raise ValueError('Invalid archive manifest.')
        record = unique_json(archive.extractfile(manifest_member).read())
        if (not isinstance(record, dict) or set(record) != {*expected, 'files'}
                or type(record.get('schema')) is not int or record['schema'] != 1
                or not isinstance(record.get('files'), dict)):
            raise ValueError('Invalid toolchain manifest schema.')
        if set(names) != {MANIFEST, *record['files']}:
            raise ValueError('Toolchain file inventory differs.')
        locks = expected_locks(root)
        ordinary = {folder + '/source-lock.json' for folder in locks}
        ordinary.update(folder + '/' + engine + suffix for folder, lock in locks.items()
                        for engine in lock for suffix in ('-build.log', '-version.log'))
        trees = [folder + '/' + child for folder in locks for child in ('installed', 'licenses')]
        links = {member.name: member.linkname for member in members if member.issym()}
        for member in members:
            if member.name == MANIFEST:
                continue
            if member.name not in ordinary and not any(member.name == tree or member.name.startswith(tree + '/') for tree in trees):
                raise ValueError('Unexpected toolchain location: ' + member.name)
            if member.islnk() or not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError('Unexpected archive file type: ' + member.name)
            kind = 'file' if member.isfile() else 'directory' if member.isdir() else 'symlink'
            details = record['files'][member.name]
            fields = {'kind', 'mode'} | ({'sha256', 'size'} if member.isfile() else {'target'} if member.issym() else set())
            if (not isinstance(details, dict) or set(details) != fields
                    or type(details.get('mode')) is not int or member.mode < 0 or member.mode & ~0o777
                    or details.get('mode') != member.mode or details.get('kind') != kind):
                raise ValueError('Invalid or inconsistent runtime permissions/type: ' + member.name)
            if any(parent.as_posix() in links for parent in PurePosixPath(member.name).parents):
                raise ValueError('Archive member would follow a symlink: ' + member.name)
            if member.issym():
                if member.linkname != details['target']:
                    raise ValueError('Toolchain archive bytes, modes or links changed.')
                resolved = (root / member.name).parent / member.linkname
                if (Path(member.linkname).is_absolute()
                        or not any(resolved.resolve().is_relative_to(root / folder / 'installed')
                                   for folder in BUNDLES)):
                    raise ValueError('Unsafe runtime symlink: ' + member.name)
            if member.isfile() and (type(details['size']) is not int or member.size != details['size']
                    or digest(archive.extractfile(member).read()) != details['sha256']):
                raise ValueError('Toolchain archive bytes, modes or links changed.')
            destination = root / member.name
            if not destination.resolve().is_relative_to(root):
                raise ValueError('Archive path escapes checkout.')
        # Resolve links against the archive's virtual tree, including cycles and
        # intermediate aliases, before trusting a mismatched-image payload.
        def target(name, visited=()):
            parts = PurePosixPath(name).parts
            for end in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:end])
                if prefix in links:
                    if prefix in visited:
                        raise ValueError('Cyclic runtime symlink: ' + prefix)
                    path = (root / prefix).parent / links[prefix]
                    resolved = path.resolve().relative_to(root).as_posix()
                    return target('/'.join([resolved, *parts[end:]]), (*visited, prefix))
            return name
        for name in links:
            resolved = target(name)
            if not any(resolved.startswith(folder + '/installed/') for folder in BUNDLES):
                raise ValueError('Unsafe runtime symlink: ' + name)
        for name in record['files']:
            for tree in trees:
                if name == tree or name.startswith(tree + '/'):
                    parents = [PurePosixPath(name), *PurePosixPath(name).parents]
                    for parent in parents:
                        key = parent.as_posix()
                        if key == tree or key.startswith(tree + '/'):
                            if key != name and record['files'].get(key, {}).get('kind') != 'directory':
                                raise ValueError('Missing runtime parent directory: ' + key)
                    if record['files'].get(tree, {}).get('kind') != 'directory':
                        raise ValueError('Missing runtime root directory: ' + tree)
        for name in ordinary:
            if name not in record['files'] or record['files'][name]['kind'] != 'file':
                raise ValueError('Missing built provenance: ' + name)
        for folder, lock in locks.items():
            if unique_json(archive.extractfile(folder + '/source-lock.json').read()) != lock:
                raise ValueError('Built toolchain source lock differs: ' + folder)
            for engine in lock:
                binary = target(folder + '/installed/bin/' + engine)
                if record['files'].get(binary, {}).get('kind') != 'file':
                    raise ValueError('Missing installed engine: ' + engine)
                if not any(name.startswith(folder + '/licenses/' + engine + '/') and item['kind'] == 'file'
                           for name, item in record['files'].items()):
                    raise ValueError('Missing upstream license: ' + engine)
    return raw, record, expected


def check_identity(root, record, expected):
    supplied = {key: record.get(key) for key in expected}
    if supplied == expected:
        return
    identity_mismatch(root, expected, record)
    old, new = supplied.get('environment'), expected['environment']
    version_only = (isinstance(old, dict) and set(old) == set(new)
                    and isinstance(old.get('image_version'), str) and bool(old['image_version'].strip())
                    and old['image_version'] != new['image_version']
                    and all(old[key] == value for key, value in new.items() if key != 'image_version')
                    and all(supplied[key] == value for key, value in expected.items() if key != 'environment'))
    error = ImageVersionMismatch if version_only else ValueError
    raise error('Toolchain candidate, prefix, environment or inputs changed.')


def restore(root, archive_path, expected_sha256, candidate):
    root = Path(root).resolve()
    raw, record, expected = validate_archive(root, archive_path, expected_sha256, candidate)
    check_identity(root, record, expected)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        # Keep data_filter's traversal/type/ownership guards, but preserve the
        # ordinary permission bits verified above. Its default strips group
        # write and discards directory modes; that breaks legitimate 0664/0750
        # installations. Symlinks retain mode=None, so extraction never chmods
        # their targets; members below symlinks were rejected before any writes.
        def verified_filter(member, destination):
            checked = tarfile.data_filter(member, destination)
            return checked if member.issym() else checked.replace(mode=member.mode)
        # extractall applies directory permissions after their children, so a
        # valid read-only directory cannot prevent restoring its own contents.
        archive.extractall(root, members=[member for member in archive.getmembers() if member.name != MANIFEST],
                           filter=verified_filter)
    actual = {p.relative_to(root).as_posix(): file_record(root, p) for p in selected(root)}
    if actual != record['files']:
        raise ValueError('Restored toolchain bytes, modes or links changed.')
    (root / 'build' / MANIFEST).write_bytes(
        (json.dumps(record, indent=2, sort_keys=True) + '\n').encode('utf-8'))
    return record


def receipt_path(root, name):
    path = root / 'build' / name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Unsafe toolchain receipt path.')
    return path


def write_receipt(root, name, record):
    path = receipt_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(record, indent=2, sort_keys=True) + '\n').encode())


def prepare(root, archive_path, expected_sha256, candidate):
    root = Path(root).resolve()
    if receipt_path(root, RESOLUTION).exists() or receipt_path(root, READY).exists():
        raise ValueError('Toolchain resolution already exists.')
    _, record, expected = validate_archive(root, archive_path, expected_sha256, candidate)
    try:
        check_identity(root, record, expected)
    except ImageVersionMismatch:
        resolution, status = 'rebuilt_for_image_version', 'rebuild_required'
    else:
        restore(root, archive_path, expected_sha256, candidate)
        resolution, status = 'reused', 'prepared'
    result = {'schema': 1, 'resolution': resolution, 'status': status,
              'producer_archive_sha256': expected_sha256,
              'producer_identity': {key: record[key] for key in expected}, 'consumer_identity': expected}
    write_receipt(root, RESOLUTION, result)
    return result


def resolution_record(root, archive_path, expected_sha256, candidate, require_empty=False):
    result = unique_json(receipt_path(root, RESOLUTION).read_bytes())
    _, producer, expected = validate_archive(root, archive_path, expected_sha256, candidate, require_empty)
    if (not isinstance(result, dict) or type(result.get('schema')) is not int or result['schema'] != 1
            or result.get('producer_archive_sha256') != expected_sha256
            or result.get('consumer_identity') != expected
            or result.get('producer_identity') != {key: producer[key] for key in expected}):
        raise ValueError('Toolchain resolution identity changed.')
    return result, producer, expected


def rebuild(root, archive_path, expected_sha256, candidate):
    root = Path(root).resolve()
    result, producer, expected = resolution_record(root, archive_path, expected_sha256, candidate, True)
    if result.get('resolution') != 'rebuilt_for_image_version' or result.get('status') != 'rebuild_required':
        raise ValueError('A verified image-version rebuild is not pending.')
    try:
        check_identity(root, producer, expected)
    except ImageVersionMismatch:
        pass
    else:
        raise ValueError('A matching toolchain must not be rebuilt.')
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    for folder, (lock, only) in BUNDLES.items():
        command = [sys.executable, str(root / 'scripts/build_physical_engines.py'),
                   '--lock', str(root / lock), '--output', str(root / folder)]
        if only:
            command += ['--only', only]
        subprocess.check_call(command, cwd=root, env=clean_env)
    output = receipt_path(root, 'reference-toolchain-local.tar.gz')
    result.update(status='rebuilt', local_archive_sha256=pack(root, output, candidate))
    write_receipt(root, RESOLUTION, result)
    return result


def ready(root, archive_path, expected_sha256, candidate):
    """Unconditional final gate: skipped or failed rebuilds cannot qualify."""
    root = Path(root).resolve()
    if receipt_path(root, READY).exists():
        raise ValueError('Toolchain readiness already exists.')
    result, producer, expected = resolution_record(root, archive_path, expected_sha256, candidate)
    if result.get('resolution') == 'reused' and result.get('status') == 'prepared':
        check_identity(root, producer, expected)
        manifest, sha = producer, expected_sha256
    elif result.get('resolution') == 'rebuilt_for_image_version' and result.get('status') == 'rebuilt':
        try:
            check_identity(root, producer, expected)
        except ImageVersionMismatch:
            pass
        else:
            raise ValueError('Rebuilt toolchain has no verified image-version mismatch.')
        sha = result.get('local_archive_sha256', '')
        _, manifest, local_expected = validate_archive(root, receipt_path(root, 'reference-toolchain-local.tar.gz'), sha, candidate, False)
        check_identity(root, manifest, local_expected)
    else:
        raise ValueError('Toolchain is not ready; required build or restore did not complete.')
    if json.loads(receipt_path(root, MANIFEST).read_bytes()) != manifest:
        raise ValueError('Installed toolchain manifest differs.')
    actual = {p.relative_to(root).as_posix(): file_record(root, p) for p in selected(root)}
    if actual != manifest['files']:
        raise ValueError('Installed toolchain bytes, modes or links changed.')
    receipt = {'candidate': candidate, 'resolution': result['resolution'], 'identity': expected,
               'archive_sha256': sha, 'producer_archive_sha256': expected_sha256,
               'manifest_sha256': digest(receipt_path(root, MANIFEST).read_bytes()), 'engines': probe(root)}
    write_receipt(root, READY, receipt)
    return receipt


def probe(root):
    results = {}
    for folder, lock in expected_locks(root).items():
        for engine, entry in lock.items():
            executable = root / folder / 'installed/bin' / engine
            command = [str(executable), *entry.get('version_args', ['--version'])]
            output = subprocess.check_output(command, text=True, stderr=subprocess.STDOUT,
                                             timeout=30)
            if entry['version'] not in output or (entry.get('require_klu') and 'KLU' not in output):
                raise ValueError('Restored engine version or KLU support differs: ' + engine)
            results[engine] = output
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    apt = commands.add_parser('apt-sources', help='Prepare scoped official Ubuntu archive sources')
    apt.add_argument('--apt-root', type=Path, default=Path('/etc/apt'))
    apt.add_argument('--output', type=Path, required=True)
    for action in ('pack', 'restore', 'prepare', 'rebuild', 'ready'):
        command = commands.add_parser(action)
        command.add_argument('--archive', type=Path, required=True)
        command.add_argument('--candidate', required=True)
        if action != 'pack':
            command.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    if args.action == 'apt-sources':
        print(json.dumps(apt_sources(args.apt_root, args.output), indent=2))
        return
    if args.action == 'pack':
        sha = pack(ROOT, args.archive, args.candidate)
        print(sha)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                output.write('sha256=' + sha + '\n')
    elif args.action == 'restore':
        restore(ROOT, args.archive, args.expected_sha256, args.candidate)
        result = {'candidate': args.candidate, 'archive_sha256': args.expected_sha256,
                  'engines': probe(ROOT)}
        (ROOT / 'build/reference-toolchain-restored.json').write_bytes(
            (json.dumps(result, indent=2) + '\n').encode('utf-8'))
        print('Verified source-locked RC toolchain for ' + args.candidate)
    else:
        result = {'prepare': prepare, 'rebuild': rebuild, 'ready': ready}[args.action](
            ROOT, args.archive, args.expected_sha256, args.candidate)
        if args.action == 'prepare' and os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                output.write('needs_rebuild=' + str(result['status'] == 'rebuild_required').lower() + '\n')
        print(json.dumps({'action': args.action, 'resolution': result['resolution'],
                          'candidate': args.candidate}, sort_keys=True))


if __name__ == '__main__':
    main()
