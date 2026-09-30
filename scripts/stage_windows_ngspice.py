"""Provision the pinned console runtime; retry downloads and verify every launch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.client import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.runtime_setup import check_ngspice, verify_runtime_files

URL = 'https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/42/ngspice-42_64.7z/download'
SHA256 = 'aa98b3c74743260a38835bd2698f58221b7237939798d1fdf2297f44ecf1d6ec'
DOWNLOAD_URLS = (URL, 'https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/old-releases/42/ngspice-42_64.7z')


def download(archive):
    """Retry interrupted mirrors from byte zero; only publish verified bytes."""
    partial = archive.with_suffix('.part')
    for attempt in range(4):
        try:
            request = urllib.request.Request(DOWNLOAD_URLS[attempt % len(DOWNLOAD_URLS)],
                                             headers={'User-Agent': 'ICDesignStudio-runtime-setup/1'})
            with urllib.request.urlopen(request, timeout=120) as response, partial.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(partial.read_bytes()).hexdigest() != SHA256:
                raise ValueError('Downloaded NGSpice archive checksum differs from the pinned release.')
            partial.replace(archive)
            return
        except (OSError, urllib.error.URLError, HTTPException, ValueError) as exc:
            if attempt == 3:
                raise RuntimeError('Could not download the verified NGSpice runtime after four attempts. '
                                   'Retry provisioning or supply the pinned archive with --archive.') from exc
            print(f'NGSpice download attempt {attempt + 1} failed: {exc}. Retrying…', flush=True)
            time.sleep(2 ** (attempt + 1))
        finally:
            partial.unlink(missing_ok=True)


def stage(archive=None, target=None):
    target = Path(target or ROOT / 'icstudio/assets/runtime/ngspice')
    cache = ROOT / 'build/ngspice-windows'
    cache.mkdir(parents=True, exist_ok=True)
    supplied = archive is not None
    archive = Path(archive or cache / 'ngspice-42_64.7z')
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        if supplied:
            raise ValueError('The supplied Windows NGSpice archive does not match the pinned checksum.')
        print('Downloading NGSpice 42 console runtime…', flush=True)
        download(archive)
    import py7zr
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        with py7zr.SevenZipFile(archive) as package:
            package.extractall(temporary)
        source = Path(temporary) / 'Spice64'
        staged = Path(temporary) / 'ready'
        staged.mkdir()
        for relative, name in [('bin/ngspice_con.exe', 'ngspice.exe'),
                               ('bin/libomp140.x86_64.dll', 'libomp140.x86_64.dll'),
                               ('docs/COPYING', 'COPYING.txt')]:
            shutil.copy2(source / relative, staged / name)
        shutil.copy2(ROOT / 'icstudio/assets/ngspice/spinit', staged / 'spinit')
        record = {'version': '42', 'archive_url': URL, 'archive_sha256': SHA256,
                  'scope': 'Console SPICE runtime; optional XSPICE/OSDI plugins are separate.',
                  'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(staged.iterdir())}}
        # Keep this tracked manifest byte-identical on Windows and Linux.
        (staged / 'runtime-manifest.json').write_bytes(json.dumps(record, indent=2).encode('utf-8'))
        verify_runtime_files(staged)
        if os.name == 'nt':
            check_ngspice(staged / 'ngspice.exe')
        target.mkdir(parents=True, exist_ok=True)
        # Publish the manifest last, so interrupted copies fail verification.
        for name in [*record['files'], 'runtime-manifest.json']:
            partial = target / (name + '.part')
            shutil.copy2(staged / name, partial)
            partial.replace(target / name)
    return target / 'ngspice.exe'


def ensure(archive=None, target=None):
    target = Path(target or ROOT / 'icstudio/assets/runtime/ngspice')
    try:
        record = verify_runtime_files(target)
        if record.get('archive_sha256') != SHA256:
            raise ValueError('A different runtime revision is staged.')
    except (OSError, ValueError, KeyError):
        stage(archive, target)
    executable = target / 'ngspice.exe'
    if os.name == 'nt':
        check_ngspice(executable)
    return executable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, help='Verified offline archive, if a download is unavailable')
    parser.add_argument('--target', type=Path)
    parser.add_argument('--ensure', action='store_true', help='Reuse a healthy bundle; repair missing or changed files')
    args = parser.parse_args()
    print((ensure if args.ensure else stage)(args.archive, args.target))


if __name__ == '__main__':
    main()
