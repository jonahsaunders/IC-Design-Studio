"""Local project-launcher inventory; opening it never installs or relinks a PDK."""
import json
from pathlib import Path
from .model import clone,digest,example,validate


def inventory(registry,bundled=None):
    from .bundled_pdks import packages
    from .pdk_import import FAMILIES
    rows=[];notes=[];known={};families=set()
    def entry(manifest,path,status,key):
        ident=manifest['id'];family=manifest.get('family') or next((f for f in FAMILIES if ident.casefold().startswith(f)),ident)
        catalog=manifest['technology'].get('simulation',{}).get('catalog',{})
        return {'key':key,'id':ident,'name':manifest['technology'].get('name',ident),
                'family':family,'revision':manifest['revision'],'status':status,'path':str(path),
                'models':sum(not d.get('unavailable') for d in catalog.values()),'manifest':manifest}
    try:registrations=registry.entries()
    except (ValueError,OSError) as exc:registrations=[];notes.append('Installed PDK registry: '+str(exc))
    for index,manifest in enumerate(registrations):
        if not isinstance(manifest,dict) or not isinstance(manifest.get('id'),str) or not isinstance(manifest.get('revision'),str):
            notes.append('Unreadable PDK registration '+str(index+1)+'. Restore its package manifest to see its revision.');continue
        ident=manifest['id'];key=ident+'@'+manifest['revision']
        try:
            if manifest.get('error'):raise ValueError(manifest['error'])
            registry.manifest(key)  # Validate the registry identity before resolving its location.
            path=Path(manifest.get('source_root',registry.root/key)).resolve()
            row=entry(manifest,path,'Installed' if path.is_dir() else 'Folder missing',key)
        except (ValueError,OSError,KeyError,TypeError,AttributeError) as exc:
            row={'key':key,'id':ident,'name':ident,'family':ident,'revision':manifest['revision'],
                 'status':'Needs repair','path':'','models':0,'error':str(exc)}
        rows.append(row);known[key]=row;families.add(row['family'])
    try:included=packages() if bundled is None else bundled
    except (OSError,ValueError,KeyError) as exc:included=[];notes.append('Included PDK packages: '+str(exc))
    for package in included:
        try:
            path=Path(package['path']).resolve();manifest=json.loads((path/'package.json').read_text(encoding='utf-8'))
            key=manifest['id']+'@'+manifest['revision']
            if key in known:continue
            row=entry(manifest,path,'Available offline',key);rows.append(row);known[key]=row;families.add(row['family'])
        except (ValueError,OSError,KeyError,TypeError,AttributeError) as exc:notes.append(package.get('name','PDK package')+': '+str(exc))
    for family,info in FAMILIES.items():
        if family not in families:
            rows.append({'key':'setup:'+family,'id':info['root'],'name':info['name'],'family':family,
                         'revision':'Not installed','status':'Add installation','path':'','models':0})
    rows.sort(key=lambda r:(r['id'].casefold(),r['revision']))
    rows.append({'key':'generic','id':'Generic','name':'Generic teaching models','family':'generic',
                 'revision':'Built in','status':'Built in','path':'','models':7})
    return rows,notes


def preview(row):
    if row['key']=='generic':return example('empty')['pdk']
    if row['status'] not in ('Installed','Available offline'):
        raise ValueError(row.get('error') or 'Add or locate this PDK installation before creating a project.')
    manifest=row['manifest'];technology=clone(manifest['technology'])
    technology['package_root']=row['path']
    technology['package_lock']={k:clone(manifest[k]) for k in ('id','revision','files')}
    technology['package_lock']['manifest_hash']=digest(manifest)
    return technology


def build_project(registry,row,name,kind,supply='1.8',nmos=None,pmos=None):
    """Validate choices, then install/verify the exact revision before use."""
    from .project_templates import TEMPLATES,create
    from .catalog import link_technology
    if not name.strip():raise ValueError('Enter a project name.')
    def build(technology):
        cid=bench=None
        if kind in TEMPLATES:project,cid,bench=create(technology,kind,supply,nmos,pmos)
        elif kind in ('empty','rc'):project=example(kind);link_technology(project,technology)
        else:raise ValueError('Choose an available circuit template.')
        project['name']=name.strip()
        from .engine_selection import selected
        project['analysis']['engine']=selected(project)
        return {'project':validate(project),'cell':cid,'testbench':bench}
    candidate=build(preview(row))
    if row['key']=='generic':return candidate
    if row['status']=='Available offline':
        # Refuse to install a different manifest than the one the user reviewed.
        manifest=json.loads((Path(row['path'])/'package.json').read_text(encoding='utf-8'))
        if digest(manifest)!=digest(row['manifest']):raise ValueError('PDK package changed. Refresh the hub and select its revision again.')
        registry.install(Path(row['path'])/'package.json')
    technology=registry.technology(row['key'])
    if (digest({k:v for k,v in technology.items() if k not in ('package_lock','package_root')})!=digest(row['manifest']['technology'])
            or technology['package_lock']['files']!=row['manifest']['files']):
        raise ValueError('PDK package changed. Refresh the hub and review the revision again.')
    return build(technology)
