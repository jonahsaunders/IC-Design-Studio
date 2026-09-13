"""Explicit file locks for digital technology libraries and ORFS installations."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .digital import relative_path
from .model import file_digest, digest

MAX_PLATFORM_BYTES = 1024 * 1024 * 1024


def inventory(root, paths):
    root = Path(root).resolve(); records = []; total = 0
    for name in sorted(set(paths)):
        relative_path(name); path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('Platform file is missing or escapes its root: '+name)
        total += path.stat().st_size
        if total>MAX_PLATFORM_BYTES or len(records)>=10000:raise ValueError('Platform capture exceeds 1 GiB or 10,000 files.')
        records.append({'path':name,'sha256':file_digest(path),'bytes':path.stat().st_size})
    return records


def validate(platform):
    if not isinstance(platform,dict) or platform.get('version') != 1:raise ValueError('Choose a version-1 digital platform manifest.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',platform.get('name','')):raise ValueError('Invalid platform name.')
    if not isinstance(platform.get('revision'),str) or not platform['revision'].strip():raise ValueError('A digital platform needs a revision label.')
    if not isinstance(platform.get('root'),str) or not platform['root']:raise ValueError('A digital platform needs its installation root.')
    relative_path(platform.get('directory','.'),directory=True)
    records = platform.get('files',[])
    if not isinstance(records,list) or not 1<=len(records)<=10000:raise ValueError('Digital platform has no captured files.')
    names=set()
    for item in records:
        if not isinstance(item,dict) or type(item.get('bytes')) is not int or item['bytes']<0:raise ValueError('Invalid platform file lock.')
        name=relative_path(item['path'])
        if name.casefold() in names or not re.fullmatch('[0-9a-f]{64}',item.get('sha256','')):raise ValueError('Invalid platform file lock.')
        names.add(name.casefold())
    if sum(item['bytes'] for item in records)>MAX_PLATFORM_BYTES:raise ValueError('Platform capture exceeds 1 GiB.')
    corners=platform.get('corners',{})
    if not isinstance(corners,dict) or not 1<=len(corners)<=20:raise ValueError('Define 1–20 named Liberty corners.')
    for name, files in corners.items():
        if not re.fullmatch('[A-Za-z0-9_-]{1,80}',name) or not isinstance(files,list) or not files:raise ValueError('Invalid Liberty corner.')
        if any(not isinstance(f,str) or f.casefold() not in names for f in files):raise ValueError('A Liberty corner references an uncaptured file.')
    if platform.get('corner') not in corners:raise ValueError('Choose a captured Liberty corner.')
    if platform.get('fingerprint') != digest(records):raise ValueError('Digital platform manifest checksum changed. Import the platform again.')
    return platform


def verify(platform):
    validate(platform); root=Path(platform['root']).resolve()
    for record in platform['files']:
        path=(root/record['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=record['sha256']:
            raise ValueError('The locked digital platform changed: '+record['path']+'. Import the intended revision explicitly.')
    return platform['fingerprint']


def read_manifest(path):
    path=Path(path).resolve(); data=json.loads(path.read_text())
    paths=data.pop('files',[])
    if not all(isinstance(p,str) for p in paths):raise ValueError('The import manifest lists relative platform filenames.')
    data['root']=str(path.parent);data['files']=inventory(path.parent,paths)
    data['fingerprint']=digest(data['files']);return validate(data)


def from_orfs(root, name='sky130hd'):
    """Capture the complete selected platform, not Studio's analog model subset."""
    import subprocess
    root=Path(root).resolve()
    if root.name == 'flow':root=root.parent
    folder=root/'flow/platforms'/name
    if name not in ('sky130hd','nangate45'):raise ValueError('Automatic platform discovery currently supports sky130hd and nangate45. Use a manifest for other platforms.')
    if not folder.is_dir():raise ValueError('Choose an OpenROAD Flow Scripts checkout with the complete platform.')
    revision=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    paths=[p.relative_to(folder.parent).as_posix() for p in folder.rglob('*') if p.is_file()]
    files=inventory(folder.parent,paths)
    lib='lib/sky130_fd_sc_hd__tt_025C_1v80.lib' if name=='sky130hd' else 'lib/NangateOpenCellLibrary_typical.lib'
    data={'version':1,'name':name,'revision':'ORFS '+revision,'root':str(folder.parent),'directory':name,'corner':'typical',
          'corners':{'typical':[name+'/'+lib]},'files':files,'fingerprint':digest(files)}
    return validate(data)


def stage(platform, destination):
    verify(platform); destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for record in platform['files']:
        target=destination/record['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(platform['root'])/record['path'],target)
        if file_digest(target)!=record['sha256']:raise ValueError('Platform changed during capture: '+record['path'])


def pin_flow(path):
    root=Path(path).resolve();root=root/'flow' if (root/'flow/Makefile').is_file() else root
    if not (root/'Makefile').is_file():raise ValueError('Select the OpenROAD Flow Scripts checkout or its flow directory.')
    names=['Makefile']
    for folder in ('scripts','util'):
        names += [p.relative_to(root).as_posix() for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files=inventory(root,names)
    return {'root':str(root),'files':files,'fingerprint':digest(files)}


def verify_flow(flow):
    if digest(flow['files']) != flow['fingerprint']:raise ValueError('Invalid ORFS source lock.')
    root=Path(flow['root']).resolve()
    for record in flow['files']:
        path=(root/relative_path(record['path'])).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=record['sha256']:
            raise ValueError('OpenROAD Flow Scripts changed. Prepare a new run with the intended checkout.')
    return flow['fingerprint']
