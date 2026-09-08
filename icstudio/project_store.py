"""Immutable per-cell snapshots published by an atomic project manifest."""
from pathlib import Path
import json
from .model import validate,clone,digest,atomic_write,file_digest

def save_directory(p,directory):
    validate(p);root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    cell_refs=[]
    for cell in p['cells']:
        sha=digest(cell);rel=f'cells/{cell["id"]}/{sha}.json';atomic_write(root/rel,json.dumps(cell,indent=2,ensure_ascii=False,allow_nan=False));cell_refs.append({'id':cell['id'],'path':rel,'hash':sha})
    snapshot={k:v for k,v in p.items() if k!='cells'};snapshot['cell_files']=cell_refs
    lock={'schema':1,'pdk_hash':digest(p['pdk']),'technology':p['pdk'].get('package_lock'), 'application_schema':p['schema']}
    lock_path='locks/'+digest(lock)+'.json';atomic_write(root/lock_path,json.dumps(lock,indent=2));snapshot['dependency_lock']=lock_path
    # This is the only commit point. An interrupted write leaves the previous manifest valid.
    atomic_write(root/'project.icstudio',json.dumps(snapshot,indent=2,ensure_ascii=False,allow_nan=False))
    return root/'project.icstudio'

def load_directory(directory):
    root=Path(directory);manifest=root if root.is_file() else root/'project.icstudio';root=manifest.parent.resolve();p=json.loads(manifest.read_text(encoding='utf-8'))
    def safe(rel):
        path=(root/rel).resolve()
        if not path.is_relative_to(root):raise ValueError('Project file escapes the project directory.')
        return path
    cells=[]
    for ref in p.pop('cell_files'):
        cell=json.loads(safe(ref['path']).read_text(encoding='utf-8'))
        if digest(cell)!=ref['hash'] or cell['id']!=ref['id']:raise ValueError('Cell snapshot checksum mismatch.')
        cells.append(cell)
    lock=json.loads(safe(p.pop('dependency_lock')).read_text(encoding='utf-8'))
    if lock['pdk_hash']!=digest(p['pdk']):raise ValueError('Dependency lock does not match the project technology.')
    p['cells']=cells
    package=p.get('pdk',{}).get('package_root')
    if package and not Path(package).is_absolute():p['pdk']['package_root']=str((root/package).resolve())
    return validate(p)
