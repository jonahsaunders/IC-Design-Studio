"""Fetch checksum-pinned SKY130 archives; optionally prepare only physical inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(output, *, physical_only=False, cache=None):
    out = Path(output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Choose an empty PDK destination.')
    lock = json.loads((ROOT / 'examples/sky130-reference-assets.json').read_text())
    selected = {name: value for name, value in lock['files'].items()
                if not physical_only or name in ('common.tar.zst', 'sky130_fd_pr.tar.zst')}
    cache = Path(cache).resolve() if cache else out.parent / 'sky130-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    archives = []
    for name, expected in selected.items():
        path = cache / name
        if not path.is_file() or sha256(path) != expected:
            url = f'https://github.com/{lock["repository"]}/releases/download/{lock["release"]}/{name}'
            partial = path.with_suffix(path.suffix + '.part')
            try:
                with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as target:
                    shutil.copyfileobj(response, target)
                if sha256(partial) != expected:
                    raise ValueError('Checksum mismatch: ' + name)
                partial.replace(path)
            finally:
                partial.unlink(missing_ok=True)
        archives.append(path)
        print('Verified ' + name, flush=True)
    # Publish only a completely extracted tree. The data filter rejects unsafe
    # absolute paths, directory escapes and links in the upstream archives.
    from backports import zstd
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sky130-staging-', dir=out.parent) as temporary:
        staging = Path(temporary) / 'pdk'
        staging.mkdir()
        for path in archives:
            with zstd.open(path, 'rb') as stream, tarfile.open(fileobj=stream, mode='r|') as archive:
                archive.extractall(staging, filter='data')
        provenance = {**lock, 'files': selected}
        (staging / 'upstream-lock.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
        if out.exists():
            out.rmdir()
        staging.replace(out)
    return out / 'sky130A'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--physical-only', action='store_true', help='Omit the standard-cell reference archive')
    args = parser.parse_args()
    print('SKY130A directory: ' + str(fetch(args.output, physical_only=args.physical_only, cache=args.cache)))


if __name__ == '__main__':
    main()
