"""Capture exact Linux scalar-runtime dependencies and distribution provenance.

This is dependency evidence, never frozen-application or numerical acceptance.
Release verification requires retained Debian source packages for redistributed
libraries; package metadata and download locations alone cannot satisfy it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ENGINE = '67399d2db139e9a8e7bfd118cab8acfa290bb6db003c996333e55ed682a65d25'
UBUNTU_KEYRING = '80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31'
SYSTEM = frozenset(('libc.so.6', 'libm.so.6', 'ld-linux-x86-64.so.2'))
SONAMES = SYSTEM | frozenset(('libgcc_s.so.1', 'libgomp.so.1', 'libstdc++.so.6', 'libreadline.so.8', 'libtinfo.so.6'))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key.')
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique)


def write(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode())


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Linked evidence input.')
    require(path.is_file(), 'Missing regular evidence input: '+str(path))
    return path


def confined(root, name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name and
            all(p not in ('', '.', '..') for p in name.split('/')), 'Unsafe evidence member.')
    path = Path(root)/name
    require(path.absolute().is_relative_to(Path(root).absolute()), 'Evidence member escaped root.')
    return regular(path)


def inventory(root):
    result = {}
    for path in Path(root).rglob('*'):
        require(not path.is_symlink(), 'Linked dependency evidence.')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
        else:
            require(path.is_dir(), 'Nonregular dependency evidence.')
    return result


def command(argv, env):
    result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, 'Dependency command failed: '+repr(argv)+'\n'+result.stderr)
    return result.stdout


def environment(resource_root=None):
    result = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
    if resource_root is not None:
        result['LD_LIBRARY_PATH'] = str(Path(resource_root).resolve())
    return result


def parse_ldd(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-f]+\)', line):
            continue
        match = re.fullmatch(r'(\S+) => (/\S+) \(0x[0-9a-f]+\)', line)
        if match:
            name, path = match.groups()
        else:
            match = re.fullmatch(r'(/\S+) \(0x[0-9a-f]+\)', line)
            require(match is not None, 'Unresolved or unreviewed dependency line: '+line)
            path = match[1]; name = Path(path).name
        require(name in SONAMES and name not in result, 'Unexpected or duplicate dependency: '+name)
        result[name] = path
    require(set(result) == SONAMES, 'Incomplete exact dependency closure.')
    return result


def resolution(engine, resource_root=None):
    engine = regular(engine)
    require(sha(engine) == ENGINE and engine.read_bytes()[:4] == b'\x7fELF', 'Unreviewed scalar executable.')
    if resource_root is not None:
        require(engine == Path(resource_root).absolute()/'icstudio/assets/runtime/ngspice/ngspice',
                'Deployment engine is outside its reviewed resource layout.')
    env = environment(resource_root)
    text = command(['/usr/bin/ldd', str(engine)], env)
    found = parse_ldd(text)
    records = {}
    for name, lexical in found.items():
        path = Path(lexical).resolve(strict=True)
        require(path.is_file(), 'Missing resolved ELF dependency.')
        inside = resource_root is not None and path.is_relative_to(Path(resource_root).resolve())
        if resource_root is not None:
            require(inside == (name not in SYSTEM), 'Frozen library resolution escaped its required origin: '+name)
        records[name] = dict(path=str(path), loader_path=lexical, sha256=sha(path), bytes=path.stat().st_size,
                             distribution='system' if name in SYSTEM else 'bundled')
    return env, text, records


def package_metadata(path):
    env = environment(); path = Path(path).resolve()
    # Resolve merged-/usr aliases only when the exact resolved byte file agrees.
    choices = [str(path)]
    if str(path).startswith('/usr/lib/'):
        choices.append(str(path)[4:])
    owner = None
    for choice in choices:
        if not Path(choice).is_file() or Path(choice).resolve() != path:
            continue
        run = subprocess.run(['/usr/bin/dpkg-query', '-S', choice], env=env, capture_output=True, text=True, timeout=30)
        if run.returncode:
            continue
        rows = [line.rsplit(': ', 1) for line in run.stdout.splitlines()]
        rows = [row for row in rows if len(row) == 2 and row[1] == choice and re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?', row[0])]
        require(len(rows) == 1, 'Ambiguous dependency package ownership.')
        owner = rows[0][0]; break
    require(owner is not None, 'Dependency lacks exact local package ownership: '+str(path))
    fmt = '${binary:Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}\n'
    raw = command(['/usr/bin/dpkg-query', '-W', '-f='+fmt, owner], env)
    parts = raw.strip().split('\t')
    require(len(parts) == 5 and all(parts), 'Missing exact binary/source package metadata.')
    binary, version, arch, source, source_version = parts
    copyright_path = Path('/usr/share/doc')/binary.split(':')[0]/'copyright'
    require(copyright_path.is_file(), 'Missing dependency copyright: '+binary)
    return dict(binary_package=binary, binary_version=version, architecture=arch,
                source_package=source, source_version=source_version, query=raw,
                copyright_path=str(copyright_path.resolve()))


def license_names(text):
    # Debian copyright prose may terminate a bare pathname with a full stop.
    return {name.rstrip('.') for name in re.findall(r'/usr/share/common-licenses/([A-Za-z0-9.+-]+)', text)}


def retain_licenses(meta, output):
    source = Path(meta['copyright_path']); base = output/'licenses'/meta['binary_package'].replace(':', '_')
    base.mkdir(parents=True, exist_ok=True)
    (base/'copyright').write_bytes(source.read_bytes())
    # Preserve referenced common-license files, including symlink targets' bytes.
    names = license_names(source.read_text(errors='strict'))
    for name in names:
        path = Path('/usr/share/common-licenses')/name
        require(path.is_file(), 'Referenced common license missing: '+name)
        (base/name).write_bytes(path.read_bytes())
    return {p.relative_to(output).as_posix(): sha(p) for p in base.iterdir()}


def source_package(dsc, expected_source, expected_version):
    """Require a complete local .dsc and every SHA256-referenced source member."""
    dsc = regular(dsc); text = dsc.read_text(encoding='utf-8')
    def field(name):
        values = re.findall(r'^'+re.escape(name)+r': (.+)$', text, re.M)
        require(len(values) == 1, 'Missing/duplicate source descriptor field: '+name)
        return values[0]
    require(field('Source') == expected_source and field('Version') == expected_version,
            'Source descriptor package/version differs.')
    match = re.search(r'^Checksums-Sha256:\n((?:[ \t]+[^\n]+\n)+)', text+'\n', re.M)
    require(match is not None, 'Source descriptor lacks SHA256 member closure.')
    members = {dsc.name: dsc}
    for row in match[1].splitlines():
        pieces = row.split(); require(len(pieces) == 3, 'Malformed source member.')
        digest, size, name = pieces
        require(re.fullmatch(r'[0-9a-f]{64}', digest) and size.isdigit() and
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.~-]*', name) and name not in members,
                'Unsafe/duplicate source member.')
        path = regular(dsc.parent/name)
        require(path.stat().st_size == int(size) and sha(path) == digest, 'Changed source package member.')
        members[name] = path
    require(len(members) > 1, 'Empty source package.')
    return members


def source_metadata(text, source, version, members):
    """Match retained source bytes to exact local APT source-index metadata."""
    matches = []
    for paragraph in re.split(r'\n\s*\n', text):
        if (re.findall(r'^Package: (.+)$', paragraph, re.M) == [source] and
                re.findall(r'^Version: (.+)$', paragraph, re.M) == [version]):
            matches.append(paragraph)
    require(len(matches) == 1, 'Missing/ambiguous exact APT source package/version.')
    paragraph = matches[0]
    match = re.search(r'^Checksums-Sha256:\n((?:[ \t]+[^\n]+\n)+)', paragraph+'\n', re.M)
    require(match is not None, 'APT source metadata lacks SHA256 closure.')
    declared = {}
    for line in match[1].splitlines():
        fields = line.split(); require(len(fields) == 3, 'Malformed APT source checksum.')
        digest, size, name = fields
        require(name not in declared and re.fullmatch(r'[0-9a-f]{64}', digest) and size.isdigit(), 'Invalid APT source checksum.')
        declared[name] = (digest, int(size))
    require(set(declared) == set(members), 'APT/source descriptor file closure differs.')
    require(all((sha(path), path.stat().st_size) == declared[name] for name, path in members.items()),
            'Source bytes differ from exact local APT metadata.')
    return paragraph+'\n'


def authenticated_index(entry):
    require(set(entry) == {'release', 'index', 'index_path', 'keyring'}, 'Incomplete signed source-index inputs.')
    release, index, keyring = (regular(entry[k]) for k in ('release','index','keyring'))
    require(sha(keyring) == UBUNTU_KEYRING, 'Unreviewed Ubuntu archive keyring.')
    require(entry['index_path'] in ('main/source/Sources','universe/source/Sources'), 'Unreviewed source index component.')
    status = command(['/usr/bin/gpgv','--keyring',str(keyring),'--status-fd','1',str(release)], environment())
    require('[GNUPG:] VALIDSIG ' in status, 'Missing valid archive signature.')
    text = release.read_text(encoding='utf-8')
    require(re.findall(r'^Origin: (.+)$',text,re.M) == ['Ubuntu'] and
            re.findall(r'^Codename: (.+)$',text,re.M) == ['noble'] and
            re.findall(r'^Suite: (.+)$',text,re.M) in (['noble'],['noble-updates'],['noble-security']),
            'Unexpected signed source repository.')
    table = re.search(r'^SHA256:\n((?:[ \t]+[^\n]+\n)+)',text+'\n',re.M)
    require(table is not None, 'Signed release lacks SHA256 index table.')
    matches = [line.split() for line in table[1].splitlines() if line.split()[-1] == entry['index_path']]
    require(len(matches) == 1 and len(matches[0]) == 3, 'Missing/duplicate signed source-index entry.')
    digest,size,_ = matches[0]
    require(size.isdigit() and index.stat().st_size == int(size) and sha(index) == digest,
            'Source index differs from signed Ubuntu release.')
    return index.read_text(encoding='utf-8'),status


def retain_sources(packages, source_index, out):
    index = load(source_index) if source_index else {}
    require(isinstance(index, dict), 'Source input must map exact package@version to local authenticated files.')
    kept = {}; missing = []
    for key, meta in sorted(packages.items()):
        if key not in index:
            missing.append(key); continue
        entry=index[key]
        require(isinstance(entry,dict) and set(entry)=={'dsc','authentication'}, 'Source package lacks signed-index provenance.')
        members = source_package(entry['dsc'], meta['source_package'], meta['source_version'])
        raw_index,status = authenticated_index(entry['authentication'])
        index_text = source_metadata(raw_index, meta['source_package'], meta['source_version'], members)
        target = out/'sources'/hashlib.sha256(key.encode()).hexdigest()
        target.mkdir(parents=True)
        for name, path in members.items():
            (target/name).write_bytes(path.read_bytes())
        (target/'apt-source-index.txt').write_bytes(index_text.encode())
        auth={}
        for kind in ('release','index','keyring'):
            path=regular(entry['authentication'][kind]);dest=out/'source-auth'/sha(path)
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():dest.write_bytes(path.read_bytes())
            auth[kind]=dest.relative_to(out).as_posix()
        auth['index_path']=entry['authentication']['index_path']
        kept[key] = dict(dsc=str((target/Path(entry['dsc']).name).relative_to(out)),
                         files={str((target/name).relative_to(out)): sha(target/name) for name in members},
                         apt_source_index=str((target/'apt-source-index.txt').relative_to(out)),
                         authentication=auth,signature_status=status,
                         metadata_scope='Full source index SHA256/size verified against Ubuntu InRelease signature using the exact pinned archive keyring; source package/member hashes verified against that index.')
    require(set(index) <= set(packages), 'Unrelated source package supplied.')
    return kept, missing


def verify(root, expected_report_sha256, *, release=False, live=False):
    root = Path(root); require(sha(regular(root/'report.json')) == expected_report_sha256, 'External dependency report anchor differs.')
    report = load(root/'report.json'); files = load(root/'files.json')
    require(files == {**report['files'], 'report.json': expected_report_sha256} and
            inventory(root) == {**files, 'files.json': sha(root/'files.json')}, 'Dependency evidence inventory differs.')
    require(report['schema'] == 1 and report['engine_sha256'] == ENGINE and set(report['dependencies']) == SONAMES,
            'Unreviewed dependency receipt.')
    require(report['phase'] in ('build', 'deployment'), 'Unknown dependency phase.')
    if report['phase'] == 'build':
        require(report.get('resource_root') is None and report.get('predecessor_report_sha256') is None,
                'Build/deployment provenance crossed.')
    else:
        require(isinstance(report.get('resource_root'), str) and report['resource_root'] and
                re.fullmatch(r'[0-9a-f]{64}', report.get('predecessor_report_sha256') or ''),
                'Deployment lacks its exact resource/predecessor identity.')
        previous = confined(root, 'predecessor-report.json')
        require(sha(previous) == report['predecessor_report_sha256'], 'Deployment predecessor receipt changed.')
        prior = load(previous)
        require(prior['phase'] == 'build' and prior['engine_sha256'] == ENGINE, 'Wrong deployment predecessor.')
        for name in SONAMES-SYSTEM:
            require(all(report['dependencies'][name][k] == prior['dependencies'][name][k]
                        for k in ('sha256', 'bytes', 'package', 'licenses')),
                    'Deployment bytes/package mapping differs from build: '+name)
    required = {}
    for name, row in report['dependencies'].items():
        meta = row['package']; key = meta['source_package']+'@'+meta['source_version']
        require(all(meta.get(k) for k in ('binary_package','binary_version','architecture','source_package','source_version','query')), 'Incomplete package provenance.')
        require(row['licenses'] and all(files.get(p) == h for p, h in row['licenses'].items()), 'Missing exact dependency notices.')
        if name not in SYSTEM:
            required[key] = meta
    require(set(report['sources']) | set(report['missing_sources']) == set(required) and
            not (set(report['sources']) & set(report['missing_sources'])), 'Source availability accounting differs.')
    for key, item in report['sources'].items():
        meta = required[key]; members = source_package(confined(root,item['dsc']), meta['source_package'], meta['source_version'])
        require({str(path.relative_to(root)): sha(path) for path in members.values()} == item['files'], 'Retained source package inventory differs.')
        auth={key:str(confined(root,value)) if key!='index_path' else value for key,value in item['authentication'].items()}
        index_text,status=authenticated_index(auth)
        require(status==item['signature_status'],'Archive signature identity changed.')
        paragraph=source_metadata(index_text,meta['source_package'],meta['source_version'],members)
        require(paragraph==confined(root,item['apt_source_index']).read_text(),'Captured source paragraph differs from signed index.')
    require(report['release_source_ready'] is (not report['missing_sources']), 'Overclaimed source availability.')
    if release:
        require(report['phase'] == 'deployment' and report['release_source_ready'], 'Public release blocked: exact redistributed-library source provenance is incomplete.')
    if live or release:
        env, text, rows = resolution(report['engine'], report['resource_root'])
        require(env == report['environment'] and all(all(row[k] == report['dependencies'][name][k] for k in row) for name, row in rows.items()), 'Live dependency closure changed.')
    return report


def capture(engine, out, *, resource_root=None, predecessor=None, predecessor_sha256=None, source_index=None):
    require(os.name == 'posix', 'Linux dependency capture requires native Linux.')
    out = Path(out).absolute(); require(not out.exists(), 'Use a fresh dependency output.')
    out.mkdir(parents=True)
    env, listing, rows = resolution(engine, resource_root)
    prior = verify(predecessor, predecessor_sha256) if predecessor else None
    require((resource_root is None) == (prior is None), 'Deployment requires externally anchored build dependency receipt.')
    if prior:
        require(prior['phase'] == 'build', 'Deployment predecessor is not a build receipt.')
        (out/'predecessor-report.json').write_bytes((Path(predecessor)/'report.json').read_bytes())
    packages = {}
    for name, row in rows.items():
        if prior and name not in SYSTEM:
            original = prior['dependencies'][name]
            require(row['sha256'] == original['sha256'] and row['bytes'] == original['bytes'], 'Bundled dependency differs from captured source-package bytes: '+name)
            meta = original['package']; licenses = original['licenses']
            for relative, digest in licenses.items():
                path = Path(predecessor)/relative; require(sha(path) == digest, 'Build license changed.')
                target = out/relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
        else:
            meta = package_metadata(row['path']); licenses = retain_licenses(meta, out)
        row.update(package=meta, licenses=licenses)
        if name not in SYSTEM:
            packages[meta['source_package']+'@'+meta['source_version']] = meta
    sources, missing = retain_sources(packages, source_index, out)
    (out/'ldd.txt').write_bytes(listing.encode())
    report = dict(schema=1, phase='deployment' if prior else 'build', engine=str(Path(engine).absolute()),
                  engine_sha256=ENGINE, resource_root=str(Path(resource_root).resolve()) if resource_root else None,
                  environment=env, dependencies=rows, sources=sources, missing_sources=missing,
                  release_source_ready=not missing, predecessor_report_sha256=predecessor_sha256,
                  files=inventory(out),
                  frozen_application_verified=False, numerical_acceptance=False,
                  scope='Exact ELF dependency and local package/source/notice capture only; no frozen application or numerical acceptance.')
    write(out/'report.json', report); write(out/'files.json', inventory(out))
    verify(out, sha(out/'report.json'), live=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    c = sub.add_parser('capture'); c.add_argument('--engine', required=True, type=Path); c.add_argument('--out', required=True, type=Path)
    c.add_argument('--resource-root', type=Path); c.add_argument('--predecessor', type=Path); c.add_argument('--predecessor-sha256'); c.add_argument('--source-index', type=Path)
    v = sub.add_parser('verify'); v.add_argument('--root', type=Path, required=True); v.add_argument('--report-sha256', required=True); v.add_argument('--release', action='store_true'); v.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if args.action == 'capture':
        result = capture(args.engine,args.out,resource_root=args.resource_root,predecessor=args.predecessor,predecessor_sha256=args.predecessor_sha256,source_index=args.source_index)
    else:
        result = verify(args.root,args.report_sha256,release=args.release,live=args.live)
    print(json.dumps({'phase':result['phase'],'release_source_ready':result['release_source_ready'],'missing_sources':result['missing_sources']}, indent=2))


if __name__ == '__main__':
    main()
