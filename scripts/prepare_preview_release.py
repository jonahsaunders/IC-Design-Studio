"""Assemble the portable preview and matching source/checksum assets.

This checks package integrity. Execute the portable app on Windows separately
before claiming native Windows qualification.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import __version__
from release_archives import source_archive

PYTHON_ARCHIVE = 'python-3.12.9-embed-amd64.zip'
PYTHON_SHA256 = '615861fb801e8b04c847598db4e1e46e4b046295017caa37cb5486dde72b5865'
WHEELS = {
    'shiboken6-6.8.3-cp39-abi3-win_amd64.whl': 'bca3a94513ce9242f7d4bbdca902072a1631888e0aa3a8711a52cc5dbe93588f',
    'PySide6_Essentials-6.8.3-cp39-abi3-win_amd64.whl': '3c0fae5550aff69f2166f46476c36e0ef56ce73d84829eac4559770b0c034b07',
    'klayout-0.30.5-cp312-cp312-win_amd64.whl': 'a07884870a4190042dafd5d414e6146f4f7c0fe54ec3082a3c113f77efc8d274',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(*args):
    subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'release')
    parser.add_argument('--cache', type=Path, default=ROOT / 'build/preview-cache')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    cache = args.cache.resolve(); cache.mkdir(parents=True, exist_ok=True)
    python_archive = cache / PYTHON_ARCHIVE
    if not python_archive.exists():
        partial = python_archive.with_suffix('.partial')
        request = urllib.request.Request('https://www.python.org/ftp/python/3.12.9/' + PYTHON_ARCHIVE)
        with urllib.request.urlopen(request, timeout=90) as response, partial.open('wb') as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
        if digest(partial) != PYTHON_SHA256:
            partial.unlink(); raise ValueError('Python archive checksum mismatch')
        partial.replace(python_archive)
    if digest(python_archive) != PYTHON_SHA256:
        raise ValueError('Cached Python archive checksum mismatch')
    wheels = cache / 'wheels'; wheels.mkdir(exist_ok=True)
    if not all((wheels / name).exists() for name in WHEELS):
        run('-m', 'pip', 'download', '--only-binary=:all:', '--no-deps',
            '--platform', 'win_amd64', '--python-version', '312', '--implementation', 'cp',
            '--abi', 'cp312', '--abi', 'abi3', '--dest', wheels,
            'PySide6-Essentials==6.8.3', 'shiboken6==6.8.3', 'klayout==0.30.5')
    if {p.name for p in wheels.glob('*.whl')} != set(WHEELS):
        raise ValueError('Unexpected wheels in release cache')
    for name, sha256 in WHEELS.items():
        if digest(wheels / name) != sha256:
            raise ValueError('Windows wheel checksum mismatch: ' + name)
    run('scripts/stage_windows_ngspice.py', '--ensure')
    run('scripts/check_simulation_assets.py')
    run('scripts/check_release.py')
    assembly = cache / 'assembled'
    run('scripts/assemble_windows.py', '--python', python_archive, '--wheels', wheels,
        '--ngspice', ROOT / 'icstudio/assets/runtime/ngspice', '--output', assembly)
    bundle = assembly / f'IC-Design-Studio-{__version__}-Windows-x64'
    manifest = json.loads((bundle / 'runtime-manifest.json').read_text())
    for relative, sha256 in manifest['files'].items():
        if digest(bundle / relative) != sha256:
            raise ValueError('Portable integrity mismatch: ' + relative)
    archive = output / (bundle.name + '.zip')
    temporary = archive.with_suffix('.zip.partial')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(bundle.parent))
    temporary.replace(archive)
    assets = [archive, source_archive(output), source_archive(output, repository=True)]
    evidence = output / f'IC-Design-Studio-{__version__}-Validation.json'
    evidence.write_bytes((ROOT / 'docs/validation' / f'{__version__}.json').read_bytes())
    assets.append(evidence)
    integrity = output / f'IC-Design-Studio-{__version__}-Package-Check.json'
    integrity.write_text(json.dumps({'application': __version__, 'status': 'passed',
        'portable_files_verified': len(manifest['files']), 'windows_execution': False,
        'python_archive': manifest['python_archive'], 'wheels': manifest['wheels'],
        'launcher': manifest['launcher']}, indent=2) + '\n')
    assets.append(integrity)
    for path in assets:
        if path.suffix == '.zip':
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:
                    raise ValueError('ZIP integrity failure: ' + path.name)
    (output / f'SHA256SUMS-{__version__}.txt').write_text(
        ''.join(digest(path) + '  ' + path.name + '\n' for path in assets))
    print(json.dumps({'version': __version__, 'assets': [p.name for p in assets]}, indent=2))


if __name__ == '__main__':
    main()
