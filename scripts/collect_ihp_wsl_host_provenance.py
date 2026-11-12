"""Reconstructed, unexecuted Ubuntu provenance reader; not historical collector bytes.

Pure readers consume retained inputs. The separately selected capture driver is
source-prepared and has not been run as part of reconstruction validation.
Capture downloads official packages but never installs them. Signature verification
invokes the official local gpgv tool.
No package installation, model loading, or native numerical acceptance occurs.
"""
import argparse
import json
from pathlib import Path
import re
import tarfile
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import linux_ngspice_dependencies as deps

require = deps.require
ENGINE = deps.ENGINE
UBUNTU_KEYRING = deps.UBUNTU_KEYRING
MAX_INDEX = 512 * 1024 * 1024
MAX_TAR = 2 * 1024 * 1024 * 1024


def paragraphs(text):
    result = []
    for block in text.strip().split('\n\n'):
        fields = {}; previous = None
        for line in block.splitlines():
            if line.startswith((' ', '\t')):
                require(previous is not None, 'Orphan index continuation.')
                fields[previous] += '\n' + line
                continue
            require(':' in line, 'Malformed index field.')
            key, value = line.split(':', 1)
            require(re.fullmatch(r'[A-Za-z][A-Za-z0-9-]*', key) and key not in fields,
                    'Duplicate/invalid index field.')
            fields[key] = value.strip(); previous = key
        if fields:
            result.append(fields)
    return result


def binary_index(release, index, index_path, keyring):
    release, index, keyring = map(deps.regular, (release, index, keyring))
    require(deps.sha(keyring) == UBUNTU_KEYRING, 'Unreviewed Ubuntu archive keyring.')
    require(index_path in ('main/binary-amd64/Packages', 'universe/binary-amd64/Packages'),
            'Unreviewed binary index.')
    require(release.stat().st_size <= 16 * 1024 * 1024 and index.stat().st_size <= MAX_INDEX,
            'Oversized signed index.')
    status = deps.command(['/usr/bin/gpgv', '--keyring', str(keyring), '--status-fd', '1', str(release)], deps.environment())
    require('[GNUPG:] VALIDSIG ' in status, 'Missing archive signature.')
    text = release.read_text(encoding='utf-8')
    for field, choices in [('Origin', ['Ubuntu']), ('Codename', ['noble']),
                           ('Suite', ['noble', 'noble-updates', 'noble-security'])]:
        values = re.findall(r'^' + field + r': (.+)$', text, re.M)
        require(len(values) == 1 and values[0] in choices, 'Unexpected signed repository.')
    table = re.findall(r'^SHA256:\n((?:[ \t]+[^\n]+\n)+)', text+'\n', re.M)
    require(len(table) == 1, 'Missing/duplicate SHA256 table.')
    rows = [line.split() for line in table[0].splitlines()]
    require(all(len(row) == 3 for row in rows), 'Malformed release checksum row.')
    selected = [row for row in rows if row[2] == index_path]
    require(len(selected) == 1, 'Missing/duplicate signed index.')
    digest, size, _ = selected[0]
    require(re.fullmatch('[0-9a-f]{64}', digest) and size.isdigit() and
            index.stat().st_size == int(size) and deps.sha(index) == digest, 'Changed signed index.')
    return index.read_text(encoding='utf-8'), {'release_sha256': deps.sha(release),
        'index_sha256': digest, 'index_path': index_path, 'keyring_sha256': UBUNTU_KEYRING,
        'signature_status': status}


def binary_match(text, package, version, deb):
    require(re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::amd64)?', package), 'Unsafe package name.')
    package = package.split(':')[0]
    matches = [row for row in paragraphs(text)
               if row.get('Package') == package and row.get('Version') == version]
    require(len(matches) == 1, 'Missing/ambiguous exact binary package.')
    row = matches[0]; deb = deps.regular(deb)
    require(row.get('Architecture') == 'amd64', 'Wrong binary architecture.')
    require(re.fullmatch('[0-9a-f]{64}', row.get('SHA256', '')) and row.get('Size', '').isdigit(),
            'Missing binary checksum.')
    require(deb.stat().st_size == int(row['Size']) and deps.sha(deb) == row['SHA256'], 'Changed binary package.')
    name = row.get('Filename', '')
    require(name.startswith('pool/') and '\\' not in name and ':' not in name and
            all(x not in ('', '.', '..') for x in name.split('/')), 'Unsafe binary package path.')
    return row


def signed_source(row):
    package, version = row.get('Package', ''), row.get('Version', '')
    require(re.fullmatch('[a-z0-9][a-z0-9+.-]*', package) and version and not any(c.isspace() for c in version),
            'Malformed binary identity.')
    source = row.get('Source')
    if source is None:
        return package, version
    match = re.fullmatch(r'([a-z0-9][a-z0-9+.-]*)(?: \(([^\s()]+)\))?', source)
    require(match is not None, 'Malformed signed Source relation.')
    return match[1], match[2] or version


def tar_name(name):
    if name.startswith('./'):
        name = name[2:]
    name = name[:-1] if name.endswith('/') else name
    require(name and '\\' not in name and ':' not in name and
            all(x not in ('', '.', '..') for x in name.split('/')), 'Unsafe tar member.')
    return name


def prove_tar_members(tar, files):
    """Verify path→SHA256 map against regular members without extraction/link following."""
    tar = deps.regular(tar)
    require(tar.stat().st_size <= MAX_TAR and isinstance(files, dict) and files, 'Invalid tar proof inputs.')
    expected = {tar_name(n.lstrip('/')): h for n, h in files.items()}
    require(len(expected) == len(files) and all(re.fullmatch('[0-9a-f]{64}', h) for h in expected.values()),
            'Invalid expected members.')
    seen = set(); found = {}; linked = set(); names = set(); total = 0
    with tarfile.open(tar, 'r:') as archive:
        for number, member in enumerate(archive):
            require(number < 100000, 'Too many tar members.')
            if member.name in ('.', './') and member.isdir():
                continue
            name = tar_name(member.name)
            require(name.casefold() not in seen, 'Duplicate/case-colliding tar member.')
            seen.add(name.casefold()); names.add(name)
            if member.issym() or member.islnk(): linked.add(name)
            total += member.size
            require(total <= MAX_TAR, 'Oversized tar contents.')
            if name in expected:
                require(member.isfile(), 'Required member is not regular.')
                import hashlib
                stream = archive.extractfile(member)
                require(stream is not None, 'Missing tar stream.')
                with stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                require(digest == expected[name], 'Binary member differs from installed bytes.')
                found[name] = digest
    require(not any(n.startswith(parent + '/') for parent in linked for n in names), 'Member beneath tar link.')
    require(found == expected, 'Missing binary member.')
    return found


def acquisition_plan(root):
    """Explicit nonexecuting isolated-APT preparation, not a completed collector."""
    root = Path(root).absolute()
    return {'schema': 1, 'status': 'SOURCE_PREPARATION_ONLY_NOT_EXECUTED', 'qualified': False,
            'engine_sha256': ENGINE, 'keyring_sha256': UBUNTU_KEYRING,
            'suite': ['noble', 'noble-updates', 'noble-security'],
            'origins': ['https://archive.ubuntu.com/ubuntu', 'https://security.ubuntu.com/ubuntu'],
            'isolated_apt_root': str(root), 'system_install': False,
            'required_steps': ['Bind canonical engine and eight dependency hashes before acquisition',
                'Use isolated APT lists/cache/state and pinned Ubuntu archive keyring',
                'Retain InRelease and signed uncompressed Packages and Sources indexes',
                'Match exact installed binary package/version and signed .deb bytes',
                'Decode deb data tar with streaming size cap; compare canonical library bytes',
                'Resolve signed Source relation and retain complete DSC/Sources checksum closure including glibc',
                'Recheck canonical engine and dependency paths/hashes; retain licenses and all command receipts'],
            'blocker': 'Acquisition execution/driver and full end-to-end host closure require independent review; no host proof exists.'}


def tool_source_identities():
    paths = [Path(__file__).resolve(), Path(deps.__file__).resolve()] + [Path('/usr/bin')/n for n in ('apt-get','gpgv','dpkg-deb','dpkg-query','ldd')]
    return {str(p): {'canonical_path': str(p.resolve(strict=True)), 'sha256': deps.sha(deps.regular(p.resolve(strict=True)))} for p in paths}


def capture(engine, output, *, base_archive_sha256, image, build_inputs_sha256):
    """Source-prepared driver. Requires separate reviewed host execution approval."""
    require(sys.platform.startswith('linux'), 'Linux host required.')
    for digest in (base_archive_sha256, build_inputs_sha256):
        require(re.fullmatch('[0-9a-f]{64}', digest), 'Invalid external identity.')
    require(isinstance(image, dict), 'Retained image identity required.')
    root = Path(output).absolute()
    require(not root.exists() and re.fullmatch(r'/[A-Za-z0-9_./-]+', str(root)) and
            not any(p.is_symlink() for p in root.parents), 'Fresh unlinked output required.')
    engine = deps.regular(engine); engine_before = deps.sha(engine)
    _, ldd_before, rows = deps.resolution(engine)
    for row in rows.values():
        row['package'] = deps.package_metadata(row['path'])
    key = deps.regular('/usr/share/keyrings/ubuntu-archive-keyring.gpg')
    require(deps.sha(key) == UBUNTU_KEYRING, 'Unreviewed keyring.')
    identity_before = tool_source_identities()
    root.mkdir(parents=True)
    deps.write(root/'identity-before.json', identity_before)
    for name in ('apt/lists/partial','apt/cache/archives/partial','apt/log','apt/empty','downloads','licenses'):
        (root/name).mkdir(parents=True)
    shutil.copyfile(key, root/'keyring.gpg'); key = root/'keyring.gpg'
    apt = root/'apt'
    sources = ''
    for host, suites in [('archive.ubuntu.com','noble noble-updates'),('security.ubuntu.com','noble-security')]:
        sources += f'Types: deb deb-src\nURIs: https://{host}/ubuntu/\nSuites: {suites}\nComponents: main universe\nSigned-By: {key}\n\n'
    (apt/'sources.sources').write_text(sources)
    (apt/'empty.conf').write_text('')
    config = ''.join(f'Dir::{k} "{v}";\n' for k,v in {
        'Etc::sourcelist':apt/'sources.sources','Etc::sourceparts':apt/'empty',
        'Etc::parts':apt/'empty','Etc::main':apt/'empty.conf','State::lists':apt/'lists',
        'Cache':apt/'cache','Log':apt/'log'}.items())
    config += 'Acquire::AllowInsecureRepositories "false";\nAcquire::AllowDowngradeToInsecureRepositories "false";\nAcquire::GzipIndexes "false";\nAPT::Architecture "amd64";\n'
    (apt/'apt.conf').write_text(config)
    env = {**deps.environment(), 'APT_CONFIG':str(apt/'apt.conf')}; invocations=[]
    def run(argv, name):
        start=time.perf_counter_ns(); code=None
        try:
            with (root/name).open('wb') as log:
                result=subprocess.run(argv,cwd=root/'downloads',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
            code=result.returncode
        finally:
            invocations.append({'argv':argv,'returncode':code,'seconds':(time.perf_counter_ns()-start)/1e9,'log':name})
            deps.write(root/'invocations.json',invocations)
        require(code==0,'Acquisition command failed; retained log.')
    def relative_auth(a):
        return {k:str(Path(v).relative_to(root)) if k!='index_path' else v for k,v in a.items()}
    try:
        run(['/usr/bin/apt-get','update'],'update.log')
        indexes=[]; signatures=[]
        for suite,host in [('noble','archive.ubuntu.com'),('noble-updates','archive.ubuntu.com'),('noble-security','security.ubuntu.com')]:
            for component in ('main','universe'):
                for kind in ('binary-amd64/Packages','source/Sources'):
                    prefix=host+'_ubuntu_dists_'+suite
                    path=apt/'lists'/(prefix+'_'+component+'_'+kind.replace('/','_'))
                    if not path.is_file(): continue
                    auth={'release':str(apt/'lists'/(prefix+'_InRelease')),'index':str(path),
                          'index_path':component+'/'+kind,'keyring':str(key)}
                    text,signature = binary_index(**auth) if kind.startswith('binary') else deps.authenticated_index(auth)
                    signatures.append({'authentication': relative_auth(auth), 'readback': signature})
                    deps.write(root/'signature-readbacks.json', signatures)
                    indexes.append((kind,auth,text))
        packages={}
        for row in rows.values():
            meta=row['package']; keyid=(meta['binary_package'],meta['binary_version'])
            require(meta['architecture']=='amd64','Wrong installed architecture.')
            require(re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::amd64)?',keyid[0]) and
                    re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]*',keyid[1]),'Unsafe installed package identity.')
            packages.setdefault(keyid,{})[row['path']]=row['sha256']
            shutil.copyfile(meta['copyright_path'],root/'licenses'/(keyid[0].replace(':','_')+'.copyright'))
        binaries=[]; source_ids=set()
        for (package,version), files in packages.items():
            run(['/usr/bin/apt-get','download',package+'='+version], 'binary-'+str(len(binaries))+'.log')
            matches=[]
            for kind,auth,text in indexes:
                if not kind.startswith('binary'): continue
                for deb in (root/'downloads').glob('*.deb'):
                    try: signed=binary_match(text,package.split(':')[0],version,deb)
                    except ValueError: continue
                    matches.append((auth,deb,signed))
            require(matches,'No signed exact binary bytes.')
            require(len({deps.sha(x[1]) for x in matches})==1,'Conflicting signed binary bytes.')
            auth,deb,signed=matches[0]; source=signed_source(signed); source_ids.add(source)
            require(all((r['package']['source_package'],r['package']['source_version'])==source for r in rows.values()
                        if r['package']['binary_package']==package),'Signed/installed source relation differs.')
            tar=root/('binary-'+str(len(binaries))+'.tar')
            def cap():
                import resource
                resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_TAR,MAX_TAR))
            with tar.open('wb') as stream:
                result=subprocess.run(['/usr/bin/dpkg-deb','--fsys-tarfile',str(deb)],stdout=stream,
                                      stderr=subprocess.DEVNULL,timeout=60,env=deps.environment(),preexec_fn=cap)
            require(result.returncode==0,'Bounded binary decoder failed.')
            prove_tar_members(tar,files)
            binaries.append({'package':package,'version':version,'archive':str(deb.relative_to(root)),
                             'authentication':relative_auth(auth),'files':files})
        sources=[]
        for package,version in sorted(source_ids):
            require(re.fullmatch('[a-z0-9][a-z0-9+.-]*',package) and re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]*',version),'Unsafe signed source identity.')
            run(['/usr/bin/apt-get','--download-only','--only-source','source',package+'='+version], 'source-'+str(len(sources))+'.log')
            matches=[]
            for dsc in (root/'downloads').glob('*.dsc'):
                try: members=deps.source_package(dsc,package,version)
                except ValueError: continue
                for kind,auth,text in indexes:
                    if kind!='source/Sources': continue
                    try: deps.source_metadata(text,package,version,members)
                    except ValueError: continue
                    matches.append((dsc,members,auth))
            require(matches and len({deps.sha(m[0]) for m in matches})==1,'Missing/ambiguous signed source closure.')
            dsc,members,auth=matches[0]
            sources.append({'package':package,'version':version,'dsc':str(dsc.relative_to(root)),
                            'authentication':relative_auth(auth),'members':{str(p.relative_to(root)):deps.sha(p) for p in members.values()}})
        _,ldd_after,after=deps.resolution(engine)
        require(engine_before==deps.sha(engine)==ENGINE and
                after=={k:{n:v for n,v in row.items() if n!='package'} for k,row in rows.items()},'Engine/dependency mutation.')
        identity_after = tool_source_identities()
        deps.write(root/'identity-after.json', identity_after)
        require(identity_before == identity_after, 'Source/tool identity changed.')
        report={'status':'AUTHENTICATED_NEW_HOST_BASELINE','numerical_execution':False,'qualified':False,
                'engine_sha256':ENGINE,'base_archive_sha256':base_archive_sha256,'image':image,
                'build_inputs_sha256':build_inputs_sha256,'rows':rows,
                'dependencies':{r['path']:r['sha256'] for r in rows.values()},
                'binary_proofs':binaries,'source_proofs':sources,'ldd_before':ldd_before,'ldd_after':ldd_after,
                'collector_reconstruction':'NEW_IMPLEMENTATION_NOT_HISTORICAL_HASH_EQUIVALENT'}
        deps.write(root/'report.json',report)
        deps.write(root/'files.json',deps.inventory(root))
        return report
    except BaseException as error:
        try: deps.write(root/'identity-after-failure.json', tool_source_identities())
        except (OSError, ValueError): pass
        deps.write(root/'failure.json',{'status':'FAILED','type':type(error).__name__,'numerical_execution':False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-root')
    parser.add_argument('--engine'); parser.add_argument('--output')
    parser.add_argument('--base-archive-sha256'); parser.add_argument('--image')
    parser.add_argument('--build-inputs-sha256')
    args = parser.parse_args()
    if args.plan_root:
        print(json.dumps(acquisition_plan(args.plan_root), indent=2)); return
    require(all((args.engine,args.output,args.base_archive_sha256,args.image,args.build_inputs_sha256)),'Incomplete capture arguments.')
    capture(args.engine,args.output,base_archive_sha256=args.base_archive_sha256,
            image=deps.load(args.image),build_inputs_sha256=args.build_inputs_sha256)


if __name__ == '__main__':
    main()
