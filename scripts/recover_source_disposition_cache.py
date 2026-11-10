"""Recover pinned audit inputs as authenticated bytes; never execute/extract sources."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HISTORY = 'docs/qualification/source-dispositions-2026-11-08-v1.json.gz'
HISTORY_SHA = 'ff2a08f3698dcf09d01c38f77bb9f76866e981401ae380e02efac9bc8084a442'
CHUNK = 1024*1024
# Exact pinned archive root observed after the public repository was renamed.
# Source paths, revision and every retained Git/SHA256 identity remain unchanged.
ARCHIVE_NAMES = {
    'VolkerMuehlhaus/openems_ihp_sg13g2@e29417aa1e5fb97b4ebd27dd1e4fcf043f97ef63': 'gds2openEMS',
}


def require(ok, message):
    if not ok:
        raise ValueError('Source cache recovery: '+message)


class LimitedReader:
    def __init__(self, stream, limit, seconds=600):
        self.stream, self.remaining = stream, limit
        self.deadline = time.monotonic()+seconds

    def read(self, size=-1):
        require(time.monotonic() <= self.deadline, 'stream deadline exceeded')
        size = min(self.remaining+1, CHUNK if size < 0 else size)
        raw = self.stream.read(size)
        self.remaining -= len(raw)
        require(self.remaining >= 0, 'stream exceeds byte limit')
        return raw


def verify_stream(stream, expected, destination=None, blob=None):
    size, digest = expected
    sha = hashlib.sha256()
    git = hashlib.sha1(b'blob '+str(size).encode()+b'\0')
    count = 0
    while True:
        raw = stream.read(min(CHUNK, size-count+1))
        if not raw:
            break
        count += len(raw)
        require(count <= size, 'oversized input')
        sha.update(raw); git.update(raw)
        if destination is not None:
            destination.write(raw)
    require(count == size and sha.hexdigest() == digest, 'size/SHA256 mismatch')
    require(blob is None or git.hexdigest() == blob, 'Git blob mismatch')


def verify_file(path, row, blob=True):
    require(not path.is_symlink() and path.is_file(), 'cache path is not a regular file')
    with path.open('rb') as stream:
        verify_stream(stream, (row['bytes'], row['sha256']), blob=row['git_blob_sha1'] if blob else None)


def recover_archive(stream, repository, wanted, cache, expanded_limit):
    """Consume a gzip tar stream; stage only exact wanted bytes, atomically publish."""
    from scripts.inventory_upstream_views import safe_path
    repository_name, revision = repository.rsplit('@', 1)
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository_name) and
            re.fullmatch(r'[0-9a-f]{40}', revision), 'invalid pinned repository')
    prefix = ARCHIVE_NAMES.get(repository, repository_name.rsplit('/', 1)[1])+'-'+revision
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    require(not cache.is_symlink(), 'cache directory is a symlink')
    require(all(re.fullmatch('[0-9a-f]{40}', r['git_blob_sha1']) for r in wanted.values()), 'invalid blob key')
    seen = set(); found = set(); staged = {}
    with tempfile.TemporaryDirectory(prefix='recover-', dir=cache) as temporary:
        with gzip.GzipFile(fileobj=LimitedReader(stream, expanded_limit), mode='rb') as zipped:
            expanded = LimitedReader(zipped, expanded_limit)
            with tarfile.open(fileobj=expanded, mode='r|') as archive:
                for member in archive:
                    name = member.name.rstrip('/') if member.isdir() else member.name
                    safe_path(name)
                    require(name == prefix or name.startswith(prefix+'/'), 'unexpected archive root')
                    require(name not in seen, 'duplicate archive member')
                    seen.add(name)
                    require(member.isdir() or member.isfile() or member.issym(), 'unsupported archive member type')
                    relative = name[len(prefix)+1:]
                    if relative not in wanted:
                        continue
                    row = wanted[relative]
                    require(relative not in found, 'duplicate wanted member')
                    found.add(relative)
                    require(type(row['bytes']) is int and row['bytes'] >= 0, 'unbounded source size')
                    if row['mode'] == '120000':
                        require(member.issym(), 'symlink source type changed')
                        content = io.BytesIO(member.linkname.encode('utf-8'))
                    else:
                        require(row['mode'] in ('100644', '100755') and member.isfile(), 'regular source type changed')
                        require(member.size == row['bytes'], 'source member size changed')
                        content = archive.extractfile(member)
                    destination = Path(temporary)/row['git_blob_sha1']
                    with destination.open('wb') as output:
                        verify_stream(content, (row['bytes'], row['sha256']), output, row['git_blob_sha1'])
                    staged[row['git_blob_sha1']] = destination
            # Authenticate gzip trailer and enforce the complete stream budget.
            while expanded.read(CHUNK):
                pass
        require(found == set(wanted), 'missing required archive members')
        for blob, source in staged.items():
            target = cache/blob
            require(not target.is_symlink(), 'cache destination is a symlink')
            source.replace(target)
    return len(staged)


def reviewed_plan():
    from scripts.inventory_upstream_semantics import load_sources
    from scripts.inventory_upstream_views import verified_closure
    from scripts.audit_source_dispositions import COMPANION_ROOTS, COMPANION_PINS
    from scripts.inventory_sky130_release import verified_metadata
    raw = (ROOT/HISTORY).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == HISTORY_SHA, 'historical report changed')
    history = json.loads(gzip.decompress(raw))
    files, _ = load_sources(ROOT/'docs/qualification/upstream-view-inputs-2026-10-20.json.gz',
                            ROOT/'docs/qualification/upstream-semantics-gf-inputs-2026-11-07.json.gz')
    more, _ = verified_closure(json.loads(gzip.decompress((ROOT/'docs/qualification/source-dispositions-companion-inputs-2026-11-07.json.gz').read_bytes())),
                              roots=COMPANION_ROOTS, repositories=COMPANION_PINS)
    ledger = {(r['family'], r['path']):r for r in files+more}
    require(len(ledger) == len(history['files']), 'historical file ledger differs from closure')
    unique = {}; totals = defaultdict(int); counts = defaultdict(int)
    for row in files+more:
        totals[row['repository']] += row['bytes'] or 0
        counts[row['repository']] += 1
    for row in history['files']:
        expected = ledger[(row['family'], row['path'])]
        require(all(row[k] == expected[k] for k in ('repository','repository_path','git_blob_sha1','mode','bytes')),
                'historical source disagrees with authenticated closure')
        if 'sha256' not in row:
            continue
        blob = row['git_blob_sha1']
        if blob in unique:
            require((unique[blob]['sha256'], unique[blob]['bytes']) == (row['sha256'],row['bytes']), 'inconsistent duplicate blob')
        else:
            unique[blob] = row
    groups = defaultdict(dict)
    for row in unique.values():
        groups[row['repository']][row['repository_path']] = row
    budgets = {repo:totals[repo]+counts[repo]*4096+16*CHUNK for repo in groups}
    metadata = json.loads((ROOT/'docs/qualification/sky130-release-inputs-2026-11-07.json').read_bytes())
    verified_metadata(metadata)
    return groups, budgets, metadata['archives']


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'IC-Design-Studio-source-audit'}), timeout=120)


def bounded_retry(action, emit, identity):
    for attempt in (1, 2):
        try:
            return action()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            emit(event='network-error', identity=identity, attempt=attempt, error=str(exc))
            if attempt == 2:
                raise
            time.sleep(2)


def recover(cache, sky_cache, receipt):
    groups, budgets, assets = reviewed_plan()
    cache, sky_cache, receipt = Path(cache), Path(sky_cache), Path(receipt)
    for folder in (cache, sky_cache, receipt.parent):
        folder.mkdir(parents=True, exist_ok=True)
        require(not folder.is_symlink(), 'output directory is a symlink')
    require(not receipt.exists() and not receipt.is_symlink(), 'choose a fresh receipt')
    def emit(**row):
        row['time_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        with receipt.open('a', encoding='utf-8') as out:
            out.write(json.dumps(row, sort_keys=True)+'\n')
        print(json.dumps(row, sort_keys=True), flush=True)
    needed = sum(r['bytes'] for rows in groups.values() for r in rows.values())+sum(r['bytes'] for r in assets)
    require(shutil.disk_usage(cache).free >= needed+2*1024**3, 'insufficient disk for required cache plus reserve')
    emit(event='start', repositories=len(groups), git_blobs=sum(map(len,groups.values())), required_bytes=needed, upstream_code_executed=False)
    try:
        for repository, wanted in sorted(groups.items()):
            missing = {}
            for name, row in wanted.items():
                path = cache/row['git_blob_sha1']
                if path.exists() or path.is_symlink():
                    verify_file(path, row)
                else:
                    missing[name] = row
            if missing:
                repo, rev = repository.rsplit('@',1)
                url = 'https://codeload.github.com/'+repo+'/tar.gz/'+rev
                emit(event='fetch-git', repository=repository, missing=len(missing))
                def download():
                    with request(url) as stream:
                        return recover_archive(stream, repository, missing, cache, budgets[repository])
                bounded_retry(download, emit, repository)
            emit(event='verified-git', repository=repository, blobs=len(wanted))
        for asset in assets:
            target = sky_cache/asset['name']
            if target.exists() or target.is_symlink():
                verify_file(target, asset, blob=False)
            else:
                emit(event='fetch-sky', name=asset['name'], bytes=asset['bytes'])
                def download_asset():
                    part = None
                    try:
                        with tempfile.NamedTemporaryFile(dir=sky_cache, prefix='download-', delete=False) as out:
                            part = Path(out.name)
                            with request(asset['url']) as stream:
                                verify_stream(LimitedReader(stream, asset['bytes']), (asset['bytes'],asset['sha256']), out)
                        part.replace(target)
                    finally:
                        # Close the file before cleanup, also on ordinary Windows.
                        if part is not None:
                            part.unlink(missing_ok=True)
                bounded_retry(download_asset, emit, asset['name'])
            emit(event='verified-sky', name=asset['name'], sha256=asset['sha256'])
        # Independent final cache readback, not an inference from downloader exit.
        for wanted in groups.values():
            for row in wanted.values():
                verify_file(cache/row['git_blob_sha1'], row)
        for asset in assets:
            verify_file(sky_cache/asset['name'], asset, blob=False)
        emit(event='PASS_CACHE_READBACK', qualified=False, inventory_complete=False)
    except BaseException as exc:
        emit(event='FAILED', error=type(exc).__name__+': '+str(exc))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--sky-cache', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    recover(args.cache, args.sky_cache, args.receipt)
