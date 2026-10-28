"""Preserve authenticated finite IHP resistor recipe resources in native jobs."""
import json,shutil
from pathlib import Path
from .model import digest,file_digest

ASSET_PATH='assets/qualification/ihp-resistor-templates'
ASSET_NAMES={'templates.json','provenance.json','UPSTREAM-LOCK.json','LICENSE','README.txt'}

def require(condition,message):
    if not condition:raise ValueError(message)

def unlinked(path):
    path=Path(path).absolute()
    for component in (path,*path.parents):
        require(not component.is_symlink() and not (hasattr(component,'is_junction') and component.is_junction()),'Linked IHP backend resource path.')
    return path

def copy_assets(source,destination):
    source=unlinked(source);destination=unlinked(destination)
    if not (source/'ihp_resistors.py').is_file():return {}
    from .ihp_resistors import TEMPLATE_HASH
    folder=unlinked(source/ASSET_PATH)
    require(folder.is_dir() and not folder.is_symlink(),'Missing reviewed IHP resistor backend assets.')
    require({p.name for p in folder.iterdir()}==ASSET_NAMES,'Unexpected IHP resistor backend asset inventory.')
    records={}
    for name in sorted(ASSET_NAMES):
        path=folder/name
        require(path.is_file() and not path.is_symlink() and not (hasattr(path,'is_junction') and path.is_junction()),'Linked or missing IHP resistor backend asset.')
        records[name]=file_digest(path)
    require(records['templates.json']==TEMPLATE_HASH,'Changed reviewed IHP resistor backend templates.')
    target=destination/ASSET_PATH;target.mkdir(parents=True,exist_ok=True)
    for name,expected in records.items():
        shutil.copy2(folder/name,target/name)
        require(file_digest(target/name)==expected,'IHP resistor backend asset changed during transfer.')
    return records

def copy_linked_manifest(project,source,destination):
    specs=[r.get('spec',{}) for cell in project['cells'] for r in cell.get('pdk_layouts',[])
           if r.get('spec',{}).get('recipe')=='ihp-resistor-selected-v1']
    if not specs:return None
    from .ihp_resistors import MANIFEST_SEMANTIC_HASH
    lock=project['pdk']['package_lock'];source=unlinked(Path(source)/'package.json')
    require(lock.get('id')=='ihp-sg13g2' and source.is_file() and not source.is_symlink(),'Missing reviewed linked IHP package manifest.')
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate IHP manifest field.');result[key]=value
        return result
    captured=source.read_bytes();data=json.loads(captured,object_pairs_hook=pairs)
    require(digest(data)==MANIFEST_SEMANTIC_HASH and all(data.get(k)==lock.get(k) for k in ('id','revision','files')),
            'Linked IHP package manifest differs from reviewed lock.')
    require(all(spec.get('package_manifest_semantic_sha256')==MANIFEST_SEMANTIC_HASH for spec in specs),
            'Linked IHP resistor spec manifest identity differs.')
    import hashlib
    target=unlinked(Path(destination)/'package.json');target.parent.mkdir(parents=True,exist_ok=True)
    expected=hashlib.sha256(captured).hexdigest();target.write_bytes(captured)
    require(file_digest(source)==file_digest(target)==expected,'Linked IHP package manifest changed during transfer.')
    return dict(sha256=expected,semantic_sha256=MANIFEST_SEMANTIC_HASH)
