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
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = {
    'build/gf180-engines': ('examples/gf180-rc-engine-lock.json', None),
    'build/modern-engines': ('examples/modern-schematic-engine-lock.json', 'ngspice'),
}
MANIFEST = 'reference-toolchain-manifest.json'


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
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                     text=True, env=clean_env).strip()
    if actual != candidate:
        raise ValueError('Checkout differs from the requested candidate.')
    return {'schema': 1, 'candidate': candidate, 'workspace': str(root),
            'environment': environment(), 'inputs': inputs(root)}


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


def restore(root, archive_path, expected_sha256, candidate):
    root = Path(root).resolve()
    archive_path = Path(archive_path)
    if not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('The producer archive checksum is required.')
    if digest(archive_path.read_bytes()) != expected_sha256:
        raise ValueError('Toolchain archive checksum differs from its producer.')
    expected = identity(root, candidate)
    for folder in BUNDLES:
        if (root / folder).exists() or (root / folder).is_symlink():
            raise ValueError('Refusing to overwrite an existing toolchain: ' + folder)
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = archive.getmembers()
        names = [safe_name(member.name) for member in members]
        if len(names) != len(set(names)) or names.count(MANIFEST) != 1:
            raise ValueError('Duplicate or absent archive manifest.')
        manifest_member = archive.getmember(MANIFEST)
        if not manifest_member.isfile() or manifest_member.size > 20_000_000:
            raise ValueError('Invalid archive manifest.')
        record = json.load(archive.extractfile(manifest_member))
        if {key: record.get(key) for key in expected} != expected:
            raise ValueError('Toolchain candidate, prefix, environment or inputs changed.')
        if set(names) != {MANIFEST, *record.get('files', {})}:
            raise ValueError('Toolchain file inventory differs.')
        links = {member.name for member in members if member.issym()}
        for member in members:
            if member.name == MANIFEST:
                continue
            if not any(member.name.startswith(folder + '/') for folder in BUNDLES):
                raise ValueError('Unexpected toolchain location: ' + member.name)
            if member.islnk() or not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError('Unexpected archive file type: ' + member.name)
            kind = 'file' if member.isfile() else 'directory' if member.isdir() else 'symlink'
            details = record['files'][member.name]
            if (member.mode < 0 or member.mode & ~0o777
                    or details.get('mode') != member.mode or details.get('kind') != kind):
                raise ValueError('Invalid or inconsistent runtime permissions/type: ' + member.name)
            if any(parent.as_posix() in links for parent in PurePosixPath(member.name).parents):
                raise ValueError('Archive member would follow a symlink: ' + member.name)
            if member.issym():
                resolved = (root / member.name).parent / member.linkname
                if (Path(member.linkname).is_absolute()
                        or not any(resolved.resolve().is_relative_to(root / folder / 'installed')
                                   for folder in BUNDLES)):
                    raise ValueError('Unsafe runtime symlink: ' + member.name)
            destination = root / member.name
            if not destination.resolve().is_relative_to(root):
                raise ValueError('Archive path escapes checkout.')
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
        archive.extractall(root, members=[member for member in members if member.name != MANIFEST],
                           filter=verified_filter)
    actual = {p.relative_to(root).as_posix(): file_record(root, p) for p in selected(root)}
    if actual != record['files']:
        raise ValueError('Restored toolchain bytes, modes or links changed.')
    (root / 'build' / MANIFEST).write_bytes(
        (json.dumps(record, indent=2, sort_keys=True) + '\n').encode('utf-8'))
    return record


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
    for action in ('pack', 'restore'):
        command = commands.add_parser(action)
        command.add_argument('--archive', type=Path, required=True)
        command.add_argument('--candidate', required=True)
        if action == 'restore':
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
    else:
        restore(ROOT, args.archive, args.expected_sha256, args.candidate)
        result = {'candidate': args.candidate, 'archive_sha256': args.expected_sha256,
                  'engines': probe(ROOT)}
        (ROOT / 'build/reference-toolchain-restored.json').write_bytes(
            (json.dumps(result, indent=2) + '\n').encode('utf-8'))
        print('Verified source-locked RC toolchain for ' + args.candidate)


if __name__ == '__main__':
    main()
