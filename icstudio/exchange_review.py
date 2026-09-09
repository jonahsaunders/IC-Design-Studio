"""Reviewable Xschem changes and explicit unsupported records before import."""
from pathlib import Path
from .model import load_project,clone,file_digest
from .xschem_io import import_package,records,properties


def package_stamp(root):
    root=Path(root);files=list(root.glob('*.sch'))+[root/'project.icproj',root/'symbols.lock.json']+list((root/'symbols').glob('*.sym'))
    return {str(path.relative_to(root)):file_digest(path) for path in files if path.is_file()}


def review(path):
    path=Path(path).resolve();root=path if path.is_dir() else path.parent;out={'candidate':None,'changes':[],'warnings':[],'errors':[],'root':str(root),'stamp':package_stamp(root)}
    try:
        base=load_project(root/'project.icproj')
        for file in root.glob('*.sch'):
            for r in records(file.read_text()):
                if r[0] in ('G','K','V','S','E') and len(r)>1 and r[1].strip():out['warnings'].append(file.name+': schematic control/netlist text is retained only in the external package; it is not executed or imported into the simulation setup.')
                if r[0] not in ('v','G','K','V','S','E','N','C'):out['warnings'].append(file.name+': '+r[0]+' graphic record is retained as opaque metadata.')
        candidate,report=import_package(path);out['warnings'].extend(report);out['candidate']=candidate
        for before in base['cells']:
            after=next(c for c in candidate['cells'] if c['id']==before['id']);old={d['id']:d for d in before['devices']};new={d['id']:d for d in after['devices']}
            for key in old.keys()|new.keys():
                a,b=old.get(key),new.get(key)
                if a is None:out['changes'].append({'cell':before['name'],'object':b['name'],'change':'Add device','before':'','after':str(b['nets'])})
                elif b is None:out['changes'].append({'cell':before['name'],'object':a['name'],'change':'Remove device','before':str(a['nets']),'after':''})
                else:
                    for field in ('name','x','y','rotation','mirror','value','params','source','nets','parameters'):
                        if a.get(field)!=b.get(field):out['changes'].append({'cell':before['name'],'object':b['name'],'change':field,'before':str(a.get(field,'')),'after':str(b.get(field,''))})
            if before.get('wires')!=after.get('wires'):out['changes'].append({'cell':before['name'],'object':'Wiring','change':'Replace paths','before':str(len(before.get('wires',[])))+' paths','after':str(len(after.get('wires',[])))+' paths'})
        if not out['changes']:out['warnings'].append('No native device or wire changes were detected.')
    except (ValueError,OSError,KeyError,TypeError) as exc:out['errors'].append(str(exc))
    return out


def apply_review(record):
    if record['errors'] or record['candidate'] is None:raise ValueError('Resolve the blocking exchange errors before importing.')
    if package_stamp(record['root'])!=record['stamp']:raise ValueError('The Xschem package changed after review. Preview it again before applying.')
    return clone(record['candidate'])
