"""Reconcile bundled primitive symbols with complete, pinned public source views.

This verifies file coverage and source identity, not model terminal semantics,
device operating envelopes, other tool views or electrical/physical behavior.
GitHub recursive tree responses must reconstruct the pinned Git tree object.
The SKY130 archive is streamed without extracting files. Requires zstandard.
"""
import argparse, hashlib, json, re, sys, tarfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest

LOCKS={
    'ihp-sg13g2':dict(repository='https://github.com/IHP-GmbH/IHP-Open-PDK',
        commit='5e6d592e4002946a4616f798c357f0f3c06cf3b6',tree='beb3a89679354eb0753f8f825c31265d924fc388',
        prefix='ihp-sg13g2/libs.tech/xschem/sg13g2_pr/'),
    'gf180mcu':dict(repository='https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr',
        commit='4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c',tree='97d931bbcd862069285d20b3b73613233b8842f9',
        prefix='cells/xschem/gf180mcu_fd_pr/')}
SKY_SHA256='c7c155596a1fd1fcf6d5414dfcffcbbcf4e35b2b33160af97f4340e763c97406'


def git_hash(kind,data):
    return hashlib.sha1(kind.encode()+b' '+str(len(data)).encode()+b'\0'+data).hexdigest()


def verified_tree(document,expected):
    if document.get('truncated') is not False or document.get('sha')!=expected:
        raise ValueError('Incomplete or wrong upstream Git tree.')
    rows={};children=defaultdict(list)
    for row in document['tree']:
        path=row['path'];parts=PurePosixPath(path)
        if path in rows or parts.is_absolute() or '..' in parts.parts or str(parts)!=path:
            raise ValueError('Duplicate or unsafe Git tree path.')
        if (row['mode'],row['type']) not in (('040000','tree'),('100644','blob'),('100755','blob'),('120000','blob'),('160000','commit')):
            raise ValueError('Unsupported Git object mode.')
        if not re.fullmatch('[0-9a-f]{40}',row['sha']):raise ValueError('Invalid Git object identity.')
        rows[path]=row;children[str(parts.parent) if str(parts.parent)!='.' else ''].append(row)
    for directory in children:
        if directory and (directory not in rows or rows[directory]['type']!='tree'):
            raise ValueError('Missing upstream directory object.')
    for directory in ['',*(p for p,v in rows.items() if v['type']=='tree')]:
        entries=sorted(children[directory],key=lambda r:(PurePosixPath(r['path']).name+('/' if r['type']=='tree' else '')).encode())
        data=b''.join(r['mode'].lstrip('0').encode()+b' '+PurePosixPath(r['path']).name.encode()+b'\0'+bytes.fromhex(r['sha']) for r in entries)
        if git_hash('tree',data)!=(expected if directory=='' else rows[directory]['sha']):
            raise ValueError('Git tree content differs: '+directory)
    return rows


def sky_symbols(path):
    import zstandard
    if file_digest(path)!=SKY_SHA256:raise ValueError('Changed SKY130 common archive.')
    rows={};views=Counter();prefix='sky130A/libs.tech/xschem/sky130_fd_pr/'
    with Path(path).open('rb') as stream,zstandard.ZstdDecompressor().stream_reader(stream) as decoded,tarfile.open(fileobj=decoded,mode='r|') as archive:
        for item in archive:
            if not item.name.endswith('.sym'):continue
            views[str(PurePosixPath(item.name).parent)]+=1
            if item.name.startswith(prefix):
                name=item.name[len(prefix):]
                if '/' in name or name in rows or not item.isfile():raise ValueError('Unexpected SKY130 primitive archive member.')
                data=archive.extractfile(item).read()
                rows[name]=dict(source=item.name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
    if file_digest(path)!=SKY_SHA256:raise ValueError('SKY130 archive changed during reading.')
    if not rows:raise ValueError('No upstream SKY130 primitives.')
    return rows,dict(views)


def compare(folder,expected,identity='git_blob_sha1'):
    folder=Path(folder);package=json.loads((folder/'package.json').read_bytes())
    for name,h in package['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or file_digest(path)!=h:raise ValueError('Changed bundled asset: '+name)
    by={};rows=[]
    for key,entry in package['technology']['simulation']['catalog'].items():
        name=PurePosixPath(entry['source']).name
        if name in by:raise ValueError('Ambiguous catalog source basename.')
        by[name]=(key,entry)
    if set(by)!=set(expected):
        raise ValueError('Primitive inventory differs: '+json.dumps(dict(missing=sorted(set(expected)-set(by)),extra=sorted(set(by)-set(expected)))))
    for name,(key,entry) in sorted(by.items()):
        data=(folder/entry['source']).read_bytes();actual=git_hash('blob',data) if identity=='git_blob_sha1' else hashlib.sha256(data).hexdigest()
        if actual!=expected[name][identity]:raise ValueError('Changed primitive symbol: '+key)
        rows.append(dict(device=key,source=expected[name]['source'],source_identity=actual,
            bundled_sha256=hashlib.sha256(data).hexdigest(),model=entry.get('model'),unavailable=entry.get('unavailable','')))
    return dict(status='PASS',revision=package['revision'],manifest_sha256=file_digest(folder/'package.json'),
                upstream_symbols=len(expected),catalog_entries=len(by),missing=[],extra=[],changed=[],devices=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ihp-tree',type=Path,required=True);p.add_argument('--gf180-tree',type=Path,required=True)
    p.add_argument('--sky130-common',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a new inventory output path.')
    report=dict(schema=1,chunk=7,status='PASS',chunk_complete=False,qualified=False,scope=__doc__,sources={},targets={})
    for family,path in [('ihp-sg13g2',a.ihp_tree),('gf180mcu',a.gf180_tree)]:
        lock=LOCKS[family];raw=path.read_bytes();tree=verified_tree(json.loads(raw),lock['tree']);expected={}
        for name,row in tree.items():
            if name.startswith(lock['prefix']) and name.endswith('.sym'):
                short=name[len(lock['prefix']):]
                if '/' in short or row['type']!='blob':raise ValueError('Unexpected primitive source object.')
                expected[short]=dict(source=name,git_blob_sha1=row['sha'])
        report['sources'][family]=dict(**lock,response_sha256=hashlib.sha256(raw).hexdigest(),git_tree_verified=True,
            all_symbol_views=dict(Counter(str(PurePosixPath(n).parent) for n in tree if n.endswith('.sym'))))
        for target in (('gf180mcuC','gf180mcuD') if family=='gf180mcu' else (family,)):
            report['targets'][target]=compare(ROOT/'icstudio/assets/pdks'/target,expected)
    expected,views=sky_symbols(a.sky130_common)
    report['sources']['sky130A']=dict(release='sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392',archive_sha256=SKY_SHA256,all_symbol_views=views)
    report['targets']['sky130A']=compare(ROOT/'icstudio/assets/pdks/sky130A',expected,'sha256')
    report['runner_sha256']=file_digest(__file__)
    a.output.write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({k:dict(upstream=v['upstream_symbols'],bundled=v['catalog_entries'],unavailable=sum(bool(d['unavailable']) for d in v['devices'])) for k,v in report['targets'].items()},indent=2))


if __name__=='__main__':main()
