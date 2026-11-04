"""Fetch exact observed dependency sources using an isolated authenticated APT cache.

No administrator privileges, installed packages or system configuration changes.
The caller supplies an externally anchored dependency receipt. Every downloaded
source member is checked against a signed Ubuntu source index before returning.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import linux_ngspice_dependencies as deps


def expected_packages(report):
    result = {}
    for name,row in report['dependencies'].items():
        if name in deps.SYSTEM:
            continue
        meta=row['package']; package,version=meta['source_package'],meta['source_version']
        deps.require(re.fullmatch(r'[a-z0-9][a-z0-9+.-]*',package) and
                     re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]*',version), 'Unsafe source package identity.')
        result[package+'@'+version]=(package,version)
    return result


def fetch(receipt, expected_sha256, output):
    deps.require(sys.platform.startswith('linux'), 'Authenticated source retrieval requires Linux.')
    report=deps.verify(receipt,expected_sha256,live=True)
    packages=expected_packages(report)
    root=Path(output).absolute()
    deps.require(not root.exists() and re.fullmatch(r'/[A-Za-z0-9_./-]+',str(root)), 'Use a fresh safe user-owned source directory.')
    deps.require(not any(p.is_symlink() for p in root.parents), 'Linked source-cache ancestor.')
    keyring=Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg')
    deps.require(deps.sha(keyring)==deps.UBUNTU_KEYRING,'Unreviewed Ubuntu archive keyring.')
    root.mkdir(parents=True)
    for name in ('lists/partial','cache/archives/partial','log','empty','downloads'):(root/name).mkdir(parents=True)
    (root/'sources.sources').write_text('Types: deb-src\nURIs: https://archive.ubuntu.com/ubuntu/\nSuites: noble noble-updates\nComponents: main universe\nSigned-By: '+str(keyring)+'\n\nTypes: deb-src\nURIs: https://security.ubuntu.com/ubuntu/\nSuites: noble-security\nComponents: main universe\nSigned-By: '+str(keyring)+'\n')
    (root/'empty.conf').write_bytes(b'')
    config=(f'Dir::Etc::sourcelist "{root}/sources.sources";\nDir::Etc::sourceparts "{root}/empty";\n'
            f'Dir::Etc::parts "{root}/empty";\nDir::Etc::main "{root}/empty.conf";\n'
            f'Dir::State::lists "{root}/lists";\nDir::Cache "{root}/cache";\nDir::Log "{root}/log";\n'
            'APT::Get::List-Cleanup "false";\nAcquire::AllowInsecureRepositories "false";\n'
            'Acquire::AllowDowngradeToInsecureRepositories "false";\n')
    (root/'apt.conf').write_bytes(config.encode())
    env={**deps.environment(),'APT_CONFIG':str(root/'apt.conf')}; invocations=[]
    def run(args,name):
        start=time.monotonic()
        with (root/name).open('wb') as log:
            result=subprocess.run(args,cwd=root/'downloads',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        invocations.append(dict(command=args,environment=env,returncode=result.returncode,seconds=time.monotonic()-start,log=name,log_sha256=deps.sha(root/name)))
        deps.write(root/'invocations.json',invocations)
        deps.require(result.returncode==0,'Source retrieval failed; see '+str(root/name))
    run(['/usr/bin/apt-get','update'],'apt-update.log')
    run(['/usr/bin/apt-get','--download-only','--only-source','source',
         *[name+'='+version for name,version in packages.values()]],'apt-source.log')
    candidates=[]
    for suite,host in (('noble','archive.ubuntu.com'),('noble-updates','archive.ubuntu.com'),('noble-security','security.ubuntu.com')):
        prefix=host+'_ubuntu_dists_'+suite
        for component in ('main','universe'):
            index=root/'lists'/(prefix+'_'+component+'_source_Sources')
            release=root/'lists'/(prefix+'_InRelease')
            if not index.is_file():
                continue
            auth=dict(release=str(release),index=str(index),index_path=component+'/source/Sources',keyring=str(keyring))
            text,status=deps.authenticated_index(auth)
            candidates.append((auth,text))
    selected={}
    for key,(package,version) in packages.items():
        descriptors=[]
        for path in (root/'downloads').glob('*.dsc'):
            try:members=deps.source_package(path,package,version)
            except ValueError as error:
                if str(error)=='Source descriptor package/version differs.':continue
                raise
            descriptors.append((path,members))
        deps.require(len(descriptors)==1,'Missing/ambiguous exact downloaded source descriptor: '+key)
        path,members=descriptors[0];matching=[]
        for auth,text in candidates:
            try:deps.source_metadata(text,package,version,members)
            except ValueError as error:
                if str(error)=='Missing/ambiguous exact APT source package/version.':continue
                raise
            matching.append(auth)
        deps.require(bool(matching),'Downloaded source has no matching signed archive index: '+key)
        selected[key]={'dsc':str(path),'authentication':matching[0]}
    deps.write(root/'source-inputs.json',selected)
    deps.write(root/'fetch-report.json',dict(status='PASS_AUTHENTICATED_SOURCE_FETCH',dependency_report_sha256=expected_sha256,
               packages=list(packages),source_inputs_sha256=deps.sha(root/'source-inputs.json'),keyring_sha256=deps.sha(keyring),
               files=deps.inventory(root),scope='Exact source archives authenticated through pinned Ubuntu keyring and signed indexes; no installed application acceptance.'))
    return root/'source-inputs.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--report-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(fetch(a.receipt,a.report_sha256,a.output))
