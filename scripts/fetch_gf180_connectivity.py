"""Fetch the exact independent GF180 cell views and native rule sources."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.digital import relative_path
from icstudio.model import file_digest

LIBRARY_LOCK = ROOT / 'examples/gf180-connectivity-library-lock.json'
PV_LOCK = ROOT / 'examples/gf180-lvs-source-lock.json'


def sources():
    """Validate both locks before any network or destination writes."""
    selected = {}
    for directory, path in (('library', LIBRARY_LOCK), ('pv', PV_LOCK)):
        lock = json.loads(path.read_text(encoding='utf-8'))
        match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)', lock['repository'])
        if not match or not re.fullmatch('[0-9a-f]{40}', lock['revision']) or not lock['files']:
            raise ValueError('GF180 source lock needs a pinned GitHub revision and files.')
        base = f'https://raw.githubusercontent.com/{match[1]}/{lock["revision"]}/'
        for name, item in lock['files'].items():
            name = relative_path(name)
            item = dict(item) if isinstance(item, dict) else dict(sha256=item)
            if (not re.fullmatch('[0-9a-f]{64}', item.get('sha256', '')) or
                    item.get('url', base + name) != base + name or
                    ('bytes' in item and (type(item['bytes']) is not int or item['bytes'] < 0))):
                raise ValueError('GF180 source entry differs from its pinned URL or checksum.')
            selected[directory + '/' + name] = dict(item, url=base + name)
    return selected


def download(url, path, expected):
    """Only publish a checksum-verified object; retain an old cache on failure."""
    with tempfile.NamedTemporaryFile(prefix='.gf180-', dir=path.parent, delete=False) as stream:
        partial = Path(stream.name)
    try:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as stream:
                    shutil.copyfileobj(response, stream)
                if file_digest(partial) != expected:
                    raise ValueError('GF180 source checksum mismatch: ' + url)
                partial.replace(path)
                return
            except urllib.error.HTTPError as exc:
                if exc.code not in (408, 425, 429, 500, 502, 503, 504) or attempt == 2:
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead):
                if attempt == 2:
                    raise
            time.sleep(attempt + 1)
    finally:
        partial.unlink(missing_ok=True)


def fetch(output, *, cache=None):
    """Publish a complete source tree, reusing only authenticated cache objects."""
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new GF180 source destination; preserve existing files.')
    output = output.resolve()
    selected = sources()
    cache = Path(cache).resolve() if cache else output.parent / 'gf180-downloads'
    if output.is_relative_to(cache) or cache.is_relative_to(output):
        raise ValueError('Keep the GF180 download cache separate from its output.')
    objects = cache / 'sha256'; objects.mkdir(parents=True, exist_ok=True)
    unique = {}
    for item in selected.values(): unique.setdefault(item['sha256'], item)
    def obtain(item):
        path = objects / item['sha256']
        if path.is_symlink(): raise ValueError('GF180 cache objects must not be links.')
        if not path.is_file() or file_digest(path) != item['sha256']:
            download(item['url'], path, item['sha256'])
        if file_digest(path) != item['sha256']:
            raise ValueError('GF180 download changed before staging.')
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(obtain, unique.values()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gf180-sources-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'sources'; staging.mkdir()
        for name, item in selected.items():
            data = (objects / item['sha256']).read_bytes()
            if (hashlib.sha256(data).hexdigest() != item['sha256'] or
                    ('bytes' in item and len(data) != item['bytes']) or
                    ('git_blob' in item and hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != item['git_blob'])):
                raise ValueError('GF180 source bytes differ from the complete lock: ' + name)
            target = staging / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        for name, path in (('library-source-lock.json', LIBRARY_LOCK), ('pv-source-lock.json', PV_LOCK)):
            (staging / name).write_bytes(path.read_bytes())
        if output.exists() or output.is_symlink():
            raise ValueError('GF180 source destination appeared during the download.')
        staging.rename(output)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cache', type=Path)
    args = parser.parse_args(argv)
    print(fetch(args.output, cache=args.cache))


if __name__ == '__main__': main()
