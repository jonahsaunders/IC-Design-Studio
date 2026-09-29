"""Package complete qualification evidence within GitHub's release asset limit.

The reassemble command uses only Python's standard library and can be distributed
with the release as reassemble_evidence.py.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

GITHUB_ASSET_LIMIT = 2147483648  # GitHub requires each asset to be strictly smaller.
PART_BYTES = 1073741824
BUFFER_BYTES = 1024 * 1024
EVIDENCE_KINDS = ('physical', 'interoperability', 'digital', 'vga', 'statistics', 'reference')


class _SplitZipWriter:
    """An unseekable ZIP destination: only one complete set of parts uses disk."""
    def __init__(self, directory, name, part_bytes):
        self.directory, self.name, self.part_bytes = Path(directory), name, part_bytes
        self.parts = []
        self.whole_hash = hashlib.sha256()
        self.size = 0
        self.output = None

    def tell(self):
        return self.size

    def flush(self):
        if self.output is not None:
            self.output.flush()

    def _finish_part(self):
        if self.output is not None:
            self.output.close()
            self.parts.append({'name': self.part_name, 'bytes': self.part_size,
                               'sha256': self.part_hash.hexdigest()})
            self.output = None

    def write(self, data):
        pending = memoryview(data)
        while pending:
            if self.output is None:
                self.part_name = f'{self.name}.part{len(self.parts) + 1:03d}'
                self.output = (self.directory / self.part_name).open('xb')
                self.part_size, self.part_hash = 0, hashlib.sha256()
            chunk = pending[:self.part_bytes - self.part_size]
            self.output.write(chunk)
            self.part_hash.update(chunk)
            self.whole_hash.update(chunk)
            self.part_size += len(chunk)
            self.size += len(chunk)
            pending = pending[len(chunk):]
            if self.part_size == self.part_bytes:
                self._finish_part()
        return len(data)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._finish_part()


def checksum(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def preflight_assets(directory, limit=GITHUB_ASSET_LIMIT):
    """Return the upload files, refusing an empty set or any oversized asset."""
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f'Release directory does not exist: {directory}')
    files = sorted(directory.iterdir())
    if not files:
        raise ValueError('No release assets to upload')
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Release assets must be regular files: {path.name}')
        size = path.stat().st_size
        if size >= limit:
            raise ValueError(f'Release asset {path.name} is {size} bytes; must be less than {limit} bytes')
    return files


def archive_evidence(source, release, name, part_bytes=PART_BYTES):
    """Retain a complete ZIP, splitting its byte stream when it exceeds part_bytes."""
    source, release = Path(source), Path(release)
    if not isinstance(part_bytes, int) or isinstance(part_bytes, bool) or not 0 < part_bytes < GITHUB_ASSET_LIMIT:
        raise ValueError('Evidence part size must be positive and below the GitHub asset limit')
    if Path(name).name != name or not name.endswith('.zip'):
        raise ValueError('Evidence archive must have a plain ZIP filename')
    if not source.is_dir() or not any(source.rglob('*')):
        raise ValueError(f'Missing or empty evidence directory: {source}')
    release.mkdir(parents=True, exist_ok=True)
    if (release / name).exists() or list(release.glob(name + '.part*')):
        raise ValueError(f'Evidence archive already exists: {name}')
    with tempfile.TemporaryDirectory(prefix='release-evidence-', dir=release.parent) as temporary:
        # ZipFile writes data descriptors for unseekable outputs, so headers never
        # seek backwards across completed parts. ZIP64 remains available for large
        # individual evidence files and large complete archives.
        with _SplitZipWriter(temporary, name, part_bytes) as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for path in sorted(source.rglob('*')):
                    archive.write(path, arcname=path.relative_to(source).as_posix())
        if len(stream.parts) == 1:
            target = release / name
            shutil.move(Path(temporary) / stream.parts[0]['name'], target)
            return [target]
        outputs = []
        for part in stream.parts:
            target = release / part['name']
            shutil.move(Path(temporary) / part['name'], target)
            outputs.append(target)
        manifest = release / (name + '.parts.json')
        manifest.write_text(json.dumps({
            'schema': 1, 'format': 'split-zip',
            'archive': {'name': name, 'bytes': stream.size, 'sha256': stream.whole_hash.hexdigest()},
            'part_bytes': part_bytes, 'parts': stream.parts,
        }, indent=2) + '\n', encoding='utf-8')
        return outputs + [manifest]


def _validate_record(record, name):
    if not isinstance(record, dict) or record.get('name') != name:
        raise ValueError('Invalid archive name or ordered part name in evidence manifest')
    size, digest = record.get('bytes'), record.get('sha256')
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError('Invalid byte count in evidence manifest')
    if not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
        raise ValueError('Invalid SHA-256 in evidence manifest')


def reassemble(manifest_path, output_directory):
    """Verify every ordered part and whole ZIP before making the result available."""
    manifest_path, output_directory = Path(manifest_path), Path(output_directory)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or manifest.get('schema') != 1 or manifest.get('format') != 'split-zip':
        raise ValueError('Unsupported evidence manifest')
    archive, parts = manifest.get('archive'), manifest.get('parts')
    name = archive.get('name') if isinstance(archive, dict) else None
    if not isinstance(name, str) or '/' in name or '\\' in name or not name.endswith('.zip'):
        raise ValueError('Invalid archive filename in evidence manifest')
    _validate_record(archive, name)
    if not isinstance(parts, list) or len(parts) < 2:
        raise ValueError('Evidence manifest must contain at least two ordered parts')
    for index, part in enumerate(parts, 1):
        _validate_record(part, f'{name}.part{index:03d}')
    if sum(part['bytes'] for part in parts) != archive['bytes']:
        raise ValueError('Evidence part byte counts do not match the full archive')
    output_directory.mkdir(parents=True, exist_ok=True)
    target = output_directory / name
    if target.exists():
        raise ValueError(f'Refusing to overwrite existing archive: {target}')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=name + '.', suffix='.tmp', dir=output_directory, delete=False) as output:
            temporary = Path(output.name)
            whole_hash = hashlib.sha256()
            for part in parts:
                path = manifest_path.parent / part['name']
                if not path.is_file() or path.is_symlink() or path.stat().st_size != part['bytes']:
                    raise ValueError(f'Missing or wrong-sized evidence part: {part["name"]}')
                part_hash = hashlib.sha256()
                size = 0
                with path.open('rb') as source:
                    while chunk := source.read(BUFFER_BYTES):
                        output.write(chunk)
                        part_hash.update(chunk)
                        whole_hash.update(chunk)
                        size += len(chunk)
                if size != part['bytes'] or part_hash.hexdigest() != part['sha256']:
                    raise ValueError(f'Evidence part checksum mismatch: {part["name"]}')
            if output.tell() != archive['bytes'] or whole_hash.hexdigest() != archive['sha256']:
                raise ValueError('Reconstructed evidence archive checksum mismatch')
        if target.exists():
            raise ValueError(f'Refusing to overwrite existing archive: {target}')
        os.replace(temporary, target)
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def complete_evidence(build, release, commit, run_id, part_bytes=PART_BYTES):
    """Keep the existing statistical acceptance gate and checksum every final asset."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from icstudio import __version__
    from scripts.assemble_prerelease import validate_statistical_qualification

    build, release = Path(build), Path(release)
    if not release.is_dir():
        raise ValueError('Assemble the verified desktop release payloads first')
    statistics = validate_statistical_qualification(build / 'statistics-release-evidence', commit, run_id)
    (release / f'IC-Design-Studio-{__version__}-Statistical-Validation.json').write_text(
        json.dumps(statistics, indent=2) + '\n', encoding='utf-8')
    for kind in EVIDENCE_KINDS:
        archive_evidence(build / f'{kind}-release-evidence', release,
                         f'IC-Design-Studio-{__version__}-{kind}-Evidence.zip', part_bytes)
    shutil.copyfile(__file__, release / 'reassemble_evidence.py')
    (release / 'EVIDENCE-REASSEMBLY.md').write_text(
        '# Complete qualification evidence\n\n'
        'Evidence ZIPs larger than 1 GiB are split into ordered byte parts. '
        'No evidence files are omitted. Each `.zip.parts.json` manifest records '
        'the exact order, byte counts and SHA-256 hashes of every part and the full ZIP.\n\n'
        'Download the manifest, all matching `.zip.partNNN` assets and '
        '`reassemble_evidence.py` into one directory. With Python 3.11 or newer, run:\n\n'
        '```sh\npython reassemble_evidence.py reassemble "ARCHIVE.zip.parts.json" --output restored\n```\n\n'
        'Replace `ARCHIVE.zip.parts.json` with the downloaded manifest filename. '
        'The helper verifies every part and the complete ZIP before creating '
        'the archive in `restored`. Missing, reordered or corrupt parts fail; '
        'existing output archives are never overwritten. Open the restored ZIP '
        'with any ZIP64-capable archive tool. Budget disk space for both the parts '
        'and the reconstructed archive. Normal `.zip` assets need no reassembly.\n\n'
        f'`SHA256SUMS-{__version__}.txt` covers every released asset, including '
        'the parts, manifests, these instructions and the reassembly helper. '
        'Verify these downloaded assets against that checksum file before reassembly.\n', encoding='utf-8')
    sums_path = release / f'SHA256SUMS-{__version__}.txt'
    files = preflight_assets(release)
    sums_path.write_text(''.join(checksum(path) + '  ' + path.name + '\n'
                                for path in files if path != sums_path), encoding='utf-8')
    return preflight_assets(release)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    package = commands.add_parser('package', help='Complete a qualified release payload')
    package.add_argument('--build', type=Path, default=Path('build'))
    package.add_argument('--release', type=Path, default=Path('release'))
    package.add_argument('--commit', required=True)
    package.add_argument('--run-id', required=True)
    restore = commands.add_parser('reassemble', help='Verify and reassemble a split evidence ZIP')
    restore.add_argument('manifest', type=Path)
    restore.add_argument('--output', type=Path, default=Path('.'))
    args = parser.parse_args()
    if args.command == 'package':
        print(json.dumps([path.name for path in complete_evidence(args.build, args.release, args.commit, args.run_id)], indent=2))
    else:
        print(reassemble(args.manifest, args.output))


if __name__ == '__main__':
    main()
