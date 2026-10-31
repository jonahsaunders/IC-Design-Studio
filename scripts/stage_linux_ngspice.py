"""Stage an exact retained Linux runtime with its complete source/license record.

This prepares reviewed packaging inputs; numerical and installed gates are separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = 'packaging/ngspice/ngspice-linux47-corrected-v1.zip'
ARCHIVE_SHA256 = 'e74736fd70b2fa6972bb0e0ab77cf87fff38f5926a7cb19d03431c2663e2b714'
MANIFEST_SHA256 = '133a6dcfa101d18e36bc20445f281b985b2cba11abe0e9936065b5aa52c091ae'
ENGINE_SHA256 = '67399d2db139e9a8e7bfd118cab8acfa290bb6db003c996333e55ed682a65d25'
SPINIT_SHA256 = 'cef1e2ffa61cf0fae3afe80afa94800df8fadc67df3178aa7f1e3216ccfb0e91'
LEGACY_WINDOWS_FILES = {
    'COPYING.txt': '53e838832e7c00598bb86602a99f9644ba2060e19be209b52e60adb2c8eb6f77',
    'ngspice.exe': '86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453',
    'libomp140.x86_64.dll': '644c49149f8a5d9275a83e9331a0adbd14620f930190e985d30b842107123597',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def unlinked(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError('Linked runtime input: ' + str(parent))
    return path


def relative(name):
    if not isinstance(name, str):
        raise ValueError('Unsafe runtime member.')
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or
            any(part in ('', '.', '..') for part in name.split('/')) or
            '\\' in name or ':' in name):
        raise ValueError('Unsafe runtime member.')
    return name


def manifest(data):
    if hashlib.sha256(data).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Unreviewed runtime manifest.')
    record = json.loads(data)
    if record['id'] != 'ngspice-linux47-corrected-scalar-v1' or record['schema'] != 1:
        raise ValueError('Unreviewed runtime profile.')
    for name in record['files']:
        relative(name)
    if (record['files']['runtime/ngspice']['sha256'] != ENGINE_SHA256 or
            record['files']['runtime/spinit']['sha256'] != SPINIT_SHA256):
        raise ValueError('Changed runtime profile identities.')
    return record


def verify(folder):
    folder = unlinked(folder)
    record = manifest(unlinked(folder / 'manifest.json').read_bytes())
    actual = {}
    for path in folder.rglob('*'):
        unlinked(path)
        if path.is_file():
            actual[path.relative_to(folder).as_posix()] = path
        elif not path.is_dir():
            raise ValueError('Nonregular runtime input.')
    if set(actual) != set(record['files']) | {'manifest.json'}:
        raise ValueError('Runtime input inventory differs.')
    for name, item in record['files'].items():
        path = actual[name]
        if path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
            raise ValueError('Changed runtime input: ' + name)
        if os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) != item['mode']:
            raise ValueError('Changed runtime file permissions: ' + name)
    if (folder / 'runtime/ngspice').read_bytes()[:4] != b'\x7fELF':
        raise ValueError('Missing ELF simulator.')
    return record


def publish(ready, output):
    """Publish the verified staging directory with bounded Windows lock retries."""
    if sys.platform != 'win32':
        os.rename(ready, output)
        return
    ready, output = unlinked(ready), unlinked(output)
    identity = lambda path: (path.stat().st_dev, path.stat().st_ino)
    expected = (identity(ready), identity(ready.parent), identity(output.parent))
    delays = (.01, .02, .04, .08, .15)
    for attempt in range(len(delays) + 1):
        source, target = unlinked(ready), unlinked(output)
        if (identity(source), identity(source.parent), identity(target.parent)) != expected:
            raise ValueError('Runtime staging directory or parent changed during publication.')
        if os.path.lexists(target):
            raise FileExistsError('Runtime output appeared during staging.')
        if attempt:
            verify(source)
        try:
            os.rename(source, target)
            return
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == len(delays):
                raise
            time.sleep(delays[attempt])


def stage(archive=None, output=None):
    archive = unlinked(archive or ROOT / ARCHIVE)
    output = unlinked(output or ROOT / 'build/ngspice-linux47')
    if sha(archive) != ARCHIVE_SHA256:
        raise ValueError('Unreviewed Linux runtime archive.')
    if output.exists():
        verify(output)
        return output / 'runtime/ngspice'
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate runtime member.')
        record = manifest(z.read('manifest.json'))
        if set(names) != set(record['files']) | {'manifest.json'}:
            raise ValueError('Unreviewed runtime archive inventory.')
        for info in z.infolist():
            relative(info.filename)
            mode = info.external_attr >> 16
            wanted = record['files'].get(info.filename, {'mode': 0o644, 'bytes': len(z.read('manifest.json'))})
            if (not stat.S_ISREG(mode) or stat.S_IMODE(mode) != wanted['mode'] or
                    info.file_size != wanted['bytes']):
                raise ValueError('Invalid runtime member type, size or permissions.')
        with tempfile.TemporaryDirectory(prefix='ngspice-stage-', dir=output.parent) as temp:
            ready = Path(temp) / 'ready'
            ready.mkdir()
            for name in names:
                data = z.read(name)
                if name != 'manifest.json' and hashlib.sha256(data).hexdigest() != record['files'][name]['sha256']:
                    raise ValueError('Changed runtime archive member: ' + name)
                path = ready / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(record['files'].get(name, {'mode': 0o644})['mode'])
            verify(ready)
            if output.exists():
                raise FileExistsError('Runtime output appeared during staging.')
            publish(ready, output)
    verify(output)
    return output / 'runtime/ngspice'


def deployment_files(folder):
    """Exact file destinations underneath the final bundled engine directory."""
    record = verify(folder)
    return {(name.removeprefix('runtime/') if name.startswith('runtime/') else name):
            Path(folder) / name for name in [*record['files'], 'manifest.json']}


def deployed_inventory(folder):
    """Read all generated runtime inputs without ignoring unknown payloads."""
    folder = unlinked(folder)
    record = manifest(unlinked(folder / 'manifest.json').read_bytes())
    expected = {(n.removeprefix('runtime/') if n.startswith('runtime/') else n): item['sha256']
                for n, item in record['files'].items()}
    expected['manifest.json'] = MANIFEST_SHA256
    actual = {}
    for path in folder.rglob('*'):
        unlinked(path)
        if path.is_file() and path != folder / 'runtime-manifest.json':
            actual[path.relative_to(folder).as_posix()] = sha(path)
        elif not path.is_file() and not path.is_dir():
            raise ValueError('Nonregular deployed runtime input.')
    if os.name != 'nt' and stat.S_IMODE((folder / 'ngspice').stat().st_mode) != 0o755:
        raise ValueError('Deployed Linux simulator is not executable with its reviewed mode.')
    return folder, expected, actual


def verify_deployed(folder):
    """Check every actual deployed source/license/runtime member after freezing."""
    folder, expected, actual = deployed_inventory(folder)
    if actual != expected:
        raise ValueError('Deployed Linux runtime/source/license inventory differs.')
    return actual


def finalize_deployed(folder):
    """Remove only exact Windows inputs copied into generated Linux output.

    The complete corrected runtime and every extra input are verified before
    touching anything. Source checkout assets and unknown files are never removed.
    """
    folder, expected, actual = deployed_inventory(folder)
    extras = set(actual) - set(expected)
    if (not extras <= set(LEGACY_WINDOWS_FILES) or
            any(actual.get(name) != digest for name, digest in expected.items()) or
            any(actual[name] != LEGACY_WINDOWS_FILES[name] for name in extras)):
        raise ValueError('Unreviewed generated Linux runtime input; no legacy files removed.')
    for name in sorted(extras):
        unlinked(folder / name).unlink()
    return verify_deployed(folder)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(stage(args.archive, args.output))
