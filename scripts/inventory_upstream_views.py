"""Audit every file in pinned source trees and SKY130 common/primitive archives.

This is a file-identity inventory, not device, process-option or tool qualification.
Git trees are reconstructed, including all pinned submodule trees. Commit-to-tree
associations are pinned from GitHub's commit API; no signature verification is
claimed. Archives are streamed without extraction. Requires zstandard for SKY130.
"""

import argparse
import base64
import configparser
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest
from scripts.reconcile_primitive_inventory import LOCKS, git_hash, verified_tree

SUBMODULES = {
    'hneemann/IHP130': ('9a6e7c9d404f9f4334513a24788aa8454918d400', '649ac9a0b085af35176f27237d402bb1a83b5d40'),
    'IHP-GmbH/pycell4klayout-api': ('21c055516645d2f8f00335d81e92084e88b3c7b0', '6d32e2db230d97b2bc18809425b2361b595434d5'),
    'IHP-GmbH/pypreprocessor': ('cf1ff9bad0fb5338cf1c5b990b2b816b1ea01a64', '9c77a7dda764dcbafe6c0c4bf2571d0cfb5d5f46'),
    'VolkerMuehlhaus/openems_ihp_sg13g2': ('e29417aa1e5fb97b4ebd27dd1e4fcf043f97ef63', '15062df41412ec3cdd28c2b95521bbdd0a7c48a9'),
    'VolkerMuehlhaus/gds2palace_ihp_sg13g2': ('df29aa608be858f53fbce46f81238b5534812d9b', 'bb37794a0474dfd23cb74a319c18e9f2e3b38459'),
}
# These associations come from the exact commit API responses retained with the
# inventory inputs, not from branch names or a current upstream checkout.
ROOTS = {family: lock['repository'].removeprefix('https://github.com/') + '@' + lock['commit']
         for family, lock in LOCKS.items()}
REPOSITORIES = {
    **{lock['repository'].removeprefix('https://github.com/'): (lock['commit'], lock['tree'])
       for lock in LOCKS.values()}, **SUBMODULES}
SKY_RELEASE = 'sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392'
SKY_ARCHIVES = {
    'common.tar.zst': 'c7c155596a1fd1fcf6d5414dfcffcbbcf4e35b2b33160af97f4340e763c97406',
    'sky130_fd_pr.tar.zst': '41dc9098541ed3329eba4ec7f5dfd1422eb09e94b623ea1f6dc3895f9ccebf63',
}


def canonical(data):
    return (json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def compressed(data):
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode='wb', filename='', mtime=0) as stream:
        stream.write(canonical(data))
    return out.getvalue()


def safe_path(value):
    path = PurePosixPath(value)
    if (not value or value == '.' or path.is_absolute() or '..' in path.parts
            or str(path) != value or '\\' in value or ':' in value or '\0' in value):
        raise ValueError('Unsafe source path: ' + repr(value))
    return value


def verified_closure(bundle, roots=None, repositories=None):
    """Verify every repository, gitlink and pinned .gitmodules URL; omit none."""
    roots = ROOTS if roots is None else roots
    repositories = REPOSITORIES if repositories is None else repositories
    lock = bundle['lock.json']
    if lock['roots'] != roots:
        raise ValueError('Source roots differ from the reviewed pins.')
    wanted = {repo + '@' + commit for repo, (commit, _) in repositories.items()}
    if set(lock['entries']) != wanted:
        raise ValueError('Missing or extra repository in source closure.')
    trees = {}
    metadata = {}
    used = {'lock.json'}
    for key, entry in sorted(lock['entries'].items()):
        repo = entry['repository']
        if (repo not in repositories or tuple((entry['commit'], entry['tree'])) != repositories[repo]
                or key != repo + '@' + entry['commit']):
            raise ValueError('Changed repository commit/tree association.')
        commit_name, tree_name = (safe_path(entry[field]) for field in ('commit_file', 'tree_file'))
        if commit_name in used or tree_name in used or commit_name == tree_name:
            raise ValueError('Shared source metadata file.')
        used.update((commit_name, tree_name))
        commit = bundle[commit_name]
        if commit['sha'] != entry['commit'] or commit['tree']['sha'] != entry['tree']:
            raise ValueError('Wrong commit API response.')
        trees[key] = verified_tree(bundle[tree_name], entry['tree'])
        for path in trees[key]:
            safe_path(path)
        metadata[key] = dict(repository=repo, commit=entry['commit'], tree=entry['tree'],
                             git_tree_verified=True, commit_signature_verified=False,
                             commit_response_sha256=hashlib.sha256(canonical(commit)).hexdigest(),
                             tree_response_sha256=hashlib.sha256(canonical(bundle[tree_name])).hexdigest())
    edges = {}
    for edge in lock['edges']:
        pair = (edge['parent'], safe_path(edge['path']))
        if pair in edges or edge['child'] not in trees:
            raise ValueError('Duplicate or unknown submodule edge.')
        edges[pair] = edge['child']
    expected_edges = set()
    for key, tree in trees.items():
        links = {p: r for p, r in tree.items() if r['type'] == 'commit'}
        if not links:
            continue
        entry = lock['entries'][key]
        name = entry['commit_file'].removesuffix('-commit.json') + '-gitmodules.json'
        safe_path(name)
        used.add(name)
        blob = bundle[name]
        if blob['encoding'] != 'base64':
            raise ValueError('Unexpected .gitmodules encoding.')
        data = base64.b64decode(''.join(blob['content'].split()), validate=True)
        if tree['.gitmodules']['mode'] != '100644' or git_hash('blob', data) != tree['.gitmodules']['sha']:
            raise ValueError('Changed .gitmodules blob.')
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(data.decode('utf-8'))
        locations = {}
        for section in config.sections():
            path = safe_path(config[section]['path'])
            if path in locations:
                raise ValueError('Duplicate .gitmodules path.')
            match = re.fullmatch(r'https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?',
                                 config[section]['url'])
            if not match:
                raise ValueError('Unreviewed submodule URL.')
            locations[path] = match[1]
        if set(locations) != set(links):
            raise ValueError('.gitmodules and actual gitlinks differ.')
        for path, row in links.items():
            pair = (key, path)
            expected_edges.add(pair)
            expected = locations[path] + '@' + row['sha']
            if edges.get(pair) != expected:
                raise ValueError('Missing or incorrect submodule edge.')
    if set(edges) != expected_edges or set(bundle) != used:
        raise ValueError('Extra edge or missing/extra source metadata.')
    rows = []
    reached = set()

    def walk(family, key, prefix='', active=()):
        if key in active:
            raise ValueError('Cyclic submodule closure.')
        reached.add(key)
        for path, row in sorted(trees[key].items()):
            if row['type'] == 'tree':
                continue
            full = prefix + path
            if row['type'] == 'commit':
                walk(family, edges[(key, path)], full + '/', (*active, key))
            else:
                rows.append(dict(family=family, path=full, repository=key,
                                 repository_path=path, git_blob_sha1=row['sha'],
                                 bytes=row.get('size'), mode=row['mode']))
    for family, key in sorted(roots.items()):
        walk(family, key)
    if reached != set(trees):
        raise ValueError('Unreachable repository in source closure.')
    return rows, dict(repositories=metadata, edges=lock['edges'], roots=roots,
                     inputs_sha256=hashlib.sha256(canonical(bundle)).hexdigest())


def archive_rows(path, expected):
    """Hash every regular member; reject ambiguous or unsafe archive entries."""
    import zstandard
    if file_digest(path) != expected:
        raise ValueError('Changed SKY130 archive: ' + Path(path).name)
    rows = []
    seen = set()
    with Path(path).open('rb') as raw, zstandard.ZstdDecompressor().stream_reader(raw) as decoded:
        with tarfile.open(fileobj=decoded, mode='r|') as archive:
            for member in archive:
                name = safe_path(member.name)
                if name in seen or not member.isfile():
                    raise ValueError('Duplicate or nonregular archive member: ' + name)
                seen.add(name)
                family = name.split('/')[0]
                if family not in ('sky130A', 'sky130B'):
                    raise ValueError('Unexpected SKY130 process path.')
                sha = hashlib.sha256()
                git = hashlib.sha1(b'blob ' + str(member.size).encode() + b'\0')
                size = 0
                with archive.extractfile(member) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        size += len(block)
                        sha.update(block)
                        git.update(block)
                if size != member.size:
                    raise ValueError('Truncated archive member.')
                rows.append(dict(family=family, path=name, archive=Path(path).name,
                                 sha256=sha.hexdigest(), git_blob_sha1=git.hexdigest(),
                                 bytes=size, mode='100755' if member.mode & 0o111 else '100644'))
    if not rows or file_digest(path) != expected:
        raise ValueError('Empty or changed SKY130 archive.')
    return rows


def package_index(folder):
    folder = Path(folder).resolve()
    package = json.loads((folder / 'package.json').read_bytes())
    by_blob = defaultdict(list)
    for name, expected in sorted(package['files'].items()):
        safe_path(name)
        asset = folder / name
        path = asset.resolve()
        if not path.is_relative_to(folder) or asset.is_symlink() or not path.is_file():
            raise ValueError('Unsafe or missing bundled asset: ' + name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Changed bundled asset: ' + name)
        by_blob[git_hash('blob', data)].append(name)
    return dict(revision=package['revision'], manifest_sha256=file_digest(folder / 'package.json'),
                files=len(package['files'])), dict(by_blob)


def view(path):
    """Group by source directories, not inferred simulator/device semantics."""
    parts = PurePosixPath(path).parts
    for marker, width in (('libs.tech', 2), ('libs.ref', 3), ('libs.doc', 2)):
        if marker in parts:
            start = parts.index(marker)
            return '/'.join(parts[start:start + width])
    if parts[0] in ('cells', 'models', 'docs') and len(parts) > 1:
        return '/'.join(parts[:2])
    return parts[0] if len(parts) > 1 else '(repository root)'


def compare_files(rows, packages):
    targets = {'ihp-sg13g2': ('ihp-sg13g2',), 'gf180mcu': ('gf180mcuC', 'gf180mcuD'),
               'sky130A': ('sky130A',), 'sky130B': ()}
    seen = set()
    summary = defaultdict(Counter)
    matched_assets = defaultdict(set)
    result = []
    for source in sorted(rows, key=lambda r: (r['family'], r['path'])):
        identity = (source['family'], source['path'])
        if identity in seen:
            raise ValueError('Duplicate effective source path: ' + source['path'])
        seen.add(identity)
        row = dict(source, view=view(source['path']), comparisons={})
        for target in targets[source['family']]:
            matches = (packages[target].get(source['git_blob_sha1'], [])
                       if source['mode'] != '120000' else [])
            status = 'identical_bytes_bundled' if matches else 'no_identical_bundled_file'
            row['comparisons'][target] = dict(status=status, paths=matches)
            summary[(target, row['view'])][status] += 1
            matched_assets[target].update(matches)
        if not row['comparisons']:
            summary[(source['family'], row['view'])]['outside_target_process'] += 1
        result.append(row)
    groups = [dict(target=target, view=group, counts=dict(counts))
              for (target, group), counts in sorted(summary.items())]
    unmatched = {target: sorted(set(p for paths in index.values() for p in paths) - matched_assets[target])
                 for target, index in sorted(packages.items())}
    return result, groups, unmatched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree-inputs', type=Path, required=True,
                        help='Combined gzip JSON metadata or directory containing lock.json and API responses.')
    parser.add_argument('--sky130-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New .json.gz report')
    args = parser.parse_args()
    if args.output.exists() or args.output.suffixes[-2:] != ['.json', '.gz']:
        raise ValueError('Choose a new .json.gz output path.')
    if args.tree_inputs.is_dir():
        bundle = {p.name: json.loads(p.read_bytes()) for p in args.tree_inputs.glob('*.json')}
    else:
        bundle = json.loads(gzip.decompress(args.tree_inputs.read_bytes()))
    rows, sources = verified_closure(bundle)
    for name, digest in SKY_ARCHIVES.items():
        rows.extend(archive_rows(args.sky130_cache / name, digest))
    packages = {}
    identities = {}
    for target in ('sky130A', 'gf180mcuC', 'gf180mcuD', 'ihp-sg13g2'):
        identities[target], packages[target] = package_index(ROOT / 'icstudio/assets/pdks' / target)
    rows, groups, unmatched = compare_files(rows, packages)
    report = dict(schema=1, chunk=7, status='PASS', chunk_complete=False, qualified=False,
                  scope=__doc__, sources=sources, sky130=dict(release=SKY_RELEASE, archives=SKY_ARCHIVES),
                  exclusions=['SKY130 standard-cell and other library archives outside the two named inputs',
                              'GF180 repositories other than the named primitive repository',
                              'Device model semantics, operating envelopes and physical/electrical qualification',
                              'Availability or qualification of a tool is not inferred from source-file presence'],
                  comparison='Exact file bytes only; relocated originals match by Git blob identity. '
                             'Derivatives, other sources and generated files may be unmatched. '
                             'A match does not prove integration or executable behavior.',
                  targets=identities, file_counts=dict(Counter(row['family'] for row in rows)),
                  files=rows, views=groups, bundled_files_without_identical_source=unmatched,
                  runner_sha256=file_digest(__file__),
                  tree_verifier_sha256=file_digest(ROOT / 'scripts/reconcile_primitive_inventory.py'))
    args.output.write_bytes(compressed(report))
    print(json.dumps(dict(status=report['status'], file_counts=report['file_counts'],
                          repositories=len(sources['repositories']), submodules=len(sources['edges']),
                          report_sha256=file_digest(args.output), bytes=args.output.stat().st_size), indent=2))


if __name__ == '__main__':
    main()
