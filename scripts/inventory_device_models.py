"""Inventory every definition in the locked public simulation include closure.

Distinguishes catalog models, source-symbol alternatives, unmapped top-level
definitions and internal implementation models. Resolves library sections for
each selectable application corner. Inventory coverage is not electrical,
physical, silicon or complete-upstream-PDK qualification.
"""
import argparse,hashlib,json,re,shlex,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from icstudio.pdk_import import dependencies


def logical_lines(text):
    current=None
    for number,line in enumerate(text.splitlines(),1):
        stripped=line.strip()
        if not stripped or stripped.startswith('*'):continue
        if stripped.startswith('+'):
            if current is None:raise ValueError('Orphan SPICE continuation.')
            current=(current[0],current[1]+' '+stripped[1:].strip())
        else:
            if current:yield current
            current=(number,stripped)
    if current:yield current


def parse(text,source):
    sections=[];subcircuits=[];definitions=[];includes=[];declared=[];diagnostics=[];conditions=[]
    for line,statement in logical_lines(text):
        if not statement.startswith('.'):continue
        op=statement.split(None,1)[0].lower()
        if op in ('.if','.elseif','.else','.endif'):
            if op=='.if':conditions.append([statement])
            elif not conditions:raise ValueError('Unmatched model condition: '+source)
            elif op=='.endif':conditions.pop()
            else:conditions[-1].append(statement)
            continue
        if op not in ('.lib','.endl','.include','.inc','.subckt','.ends','.model'):continue
        tokens=shlex.split(statement,comments=True)
        if op=='.lib' and len(tokens)==2:
            if subcircuits or sections:raise ValueError('Unsupported nested library section: '+source)
            sections.append(tokens[1].casefold());declared.append(tokens[1].casefold());continue
        if op=='.endl':
            if not sections or subcircuits or len(tokens)>2 or len(tokens)==2 and tokens[1].casefold()!=sections[-1]:
                raise ValueError('Unmatched library ending: '+source+':'+str(line))
            sections.pop();continue
        if op in ('.lib','.include','.inc'):
            if len(tokens)!=(3 if op=='.lib' else 2):raise ValueError('Unsupported include syntax: '+source+':'+str(line))
            includes.append(dict(line=line,path=tokens[1],selection=tokens[2].casefold() if op=='.lib' else None,
                                 section=sections[-1] if sections else None,parent=subcircuits[-1] if subcircuits else None))
            continue
        if op=='.ends':
            if not subcircuits or len(tokens)>2:
                raise ValueError('Unmatched subcircuit ending: '+source+':'+str(line))
            if len(tokens)==2 and tokens[1].casefold()!=subcircuits[-1]:
                diagnostics.append(dict(line=line,kind='ends-name-mismatch',declared=subcircuits[-1],ending=tokens[1]))
            subcircuits.pop();continue
        if len(tokens)<3:raise ValueError('Incomplete model definition: '+source+':'+str(line))
        name=tokens[1].casefold();kind=op[1:]
        row=dict(id=source+':'+str(line)+':'+kind+':'+name,source=source,line=line,name=name,kind=kind,
                 section=sections[-1] if sections else None,parent=subcircuits[-1] if subcircuits else None,
                 conditions=[list(c) for c in conditions])
        if op=='.subckt':
            pins=[]
            for token in tokens[2:]:
                if '=' in token or token.casefold() in ('params:','.param'):break
                pins.append(token)
            row.update(pins=pins,prefix='X',parameters=re.findall(r'(?<![\w])([a-zA-Z_]\w*)\s*=',statement))
            subcircuits.append(name)
        else:
            typ=tokens[2].split('(',1)[0].lower()
            row.update(model_type=typ,prefix={'d':'D','npn':'Q','pnp':'Q','r':'R','c':'C','l':'L','nmos':'M','pmos':'M'}.get(typ,'N'))
        definitions.append(row)
    if sections or subcircuits or conditions:raise ValueError('Unterminated library, condition or subcircuit: '+source)
    if len(declared)!=len(set(declared)):raise ValueError('Duplicate library section: '+source)
    return dict(definitions=definitions,includes=includes,sections=declared,diagnostics=diagnostics)


def active_definitions(root,parsed,roots):
    root=Path(root).resolve();seen=set();active=set();stack=[]
    def visit(path,selection,parent=None):
        path=path.resolve()
        if not path.is_relative_to(root):raise ValueError('Model include escapes the package.')
        rel=path.relative_to(root).as_posix();key=(rel,selection,parent)
        if key in stack:raise ValueError('Recursive model inclusion.')
        if key in seen:return
        if rel not in parsed:raise ValueError('Include absent from locked closure: '+rel)
        obj=parsed[rel]
        if selection is not None and selection not in obj['sections']:raise ValueError('Missing model library section: '+rel+' '+selection)
        seen.add(key);stack.append(key)
        for d in obj['definitions']:
            if d['section']==selection:active.add((d['id'],'.'.join(s for s in (parent,d['parent']) if s)))
        for inc in obj['includes']:
            if inc['section']==selection:visit(path.parent/inc['path'],inc['selection'],inc['parent'] or parent)
        stack.pop()
    for rel,selection in roots:visit(root/rel,selection)
    return [dict(id=i,scope=s) for i,s in sorted(active)]


def alternatives(entry):
    attrs=entry.get('symbol',{}).get('attributes',{});names=attrs.get('available_models','').split()
    if not names:return []
    # Only the literal model token in a declarative format is interpreted.
    fmt=' '.join(attrs.get('format','').replace('\n+',' ').split())
    match=re.search(r'@pinlist\s+([^\s]+)',fmt)
    if match is None or match[1] not in ('@model','sky130_fd_pr__@model'):
        raise ValueError('Unreviewed alternate model format.')
    result=[]
    for name in names:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.$-]*',name):raise ValueError('Nonliteral alternate model name.')
        literal=match[1].replace('@model',name).casefold()
        # available_models lists may already contain fully-qualified names
        # even when the format prepends the same literal namespace. Inventory
        # the declared identity and retain the incompatible literal expansion;
        # this does not authorize a runtime mapping or execute symbol scripts.
        identity=name.casefold() if name.startswith('sky130_fd_pr__') else literal
        result.append(dict(model=identity,declared_name=name,literal_format_expansion=literal,
                           requires_namespace_adapter=identity!=literal))
    if len({r['model'] for r in result})!=len(result):raise ValueError('Duplicate alternate model declaration.')
    return sorted(result,key=lambda r:r['model'])


def inventory(folder):
    folder=Path(folder).resolve();manifest=file_digest(folder/'package.json');package=json.loads((folder/'package.json').read_bytes())
    for rel,h in package['files'].items():
        p=(folder/rel).resolve()
        if not p.is_relative_to(folder) or not p.is_file() or file_digest(p)!=h:raise ValueError('Changed locked model asset: '+rel)
    sim=package['technology']['simulation'];masters=[folder/i['path'] for i in sim['includes']]
    hashes,texts=dependencies(folder,masters)
    if any(package['files'].get(rel)!=h for rel,h in hashes.items()):raise ValueError('Model dependency absent from lock.')
    parsed={rel:parse(text,rel) for rel,text in sorted(texts.items())};definitions=[d for p in parsed.values() for d in p['definitions']]
    by=defaultdict(list)
    for d in definitions:
        if d['parent'] is None:by[(d['name'],d['prefix'])].append(d)
    sets=[set(i['sections']) for i in sim['includes'] if i.get('sections')]
    corners=sorted(set.intersection(*sets)) if sets else ['nominal']
    active={corner:active_definitions(folder,parsed,[(i['path'],i.get('sections',{}).get(corner,i.get('section'))) for i in sim['includes']]) for corner in corners}
    globals_by_corner={corner:{r['id'] for r in rows if not r['scope']} for corner,rows in active.items()}
    catalog=[];choices=[];direct=set();alternate=set()
    for key,e in sorted(sim['catalog'].items()):
        name=e.get('model','').casefold();prefix=e.get('prefix');matches=by.get((name,prefix),[])
        ids=[d['id'] for d in matches];direct.update(ids)
        missing=[c for c,rows in globals_by_corner.items() if not rows.intersection(ids)]
        catalog.append(dict(device=key,model=name,prefix=prefix,unavailable=e.get('unavailable',''),definitions=ids,absent_in_corners=missing))
        for choice in alternatives(e):
            alt=choice['model']
            matched=by.get((alt,prefix),[]);ids=[d['id'] for d in matched];alternate.update(ids)
            choices.append(dict(**choice,device=key,prefix=prefix,current_default=alt==name,definitions=ids,
                                absent_in_corners=[c for c,rows in globals_by_corner.items() if not rows.intersection(ids)],
                                exposed_catalog_entries=sorted(k for k,v in sim['catalog'].items() if not v.get('unavailable') and v.get('model','').casefold()==alt and v.get('prefix')==prefix)))
    for d in definitions:
        d['role']='internal' if d['parent'] else 'catalog' if d['id'] in direct else 'symbol-alternative' if d['id'] in alternate else 'unmapped-top-level'
    if file_digest(folder/'package.json')!=manifest or any(file_digest(folder/rel)!=h for rel,h in package['files'].items()):raise ValueError('Package changed during model inventory.')
    missing_defaults=[r for r in catalog if not r['unavailable'] and r['absent_in_corners']]
    return dict(status='PASS' if not missing_defaults else 'GAPS',revision=package['revision'],manifest_sha256=manifest,
                scope=__doc__,qualified=False,files=hashes,definitions=definitions,definition_counts=dict(Counter(d['role'] for d in definitions)),
                active_definitions=active,catalog=catalog,alternatives=choices,missing_active_catalog_models=missing_defaults,
                source_diagnostics={rel:p['diagnostics'] for rel,p in parsed.items() if p['diagnostics']},
                condition_scope='All conditional branches are inventoried without evaluating expressions. Conditions are recorded per definition; section reachability is not proof of runtime activation.',
                unmapped_scope='Top-level does not imply a supported standalone device. Definition records preserve bins, helper circuits, parasitics and corner variants without treating them as missing catalog symbols.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a new inventory report.')
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,scope=__doc__,runner_sha256=file_digest(__file__),targets={})
    for t in ('sky130A','gf180mcuC','gf180mcuD','ihp-sg13g2'):
        r=inventory(a.input/t);report['targets'][t]=r
        print(t,r['status'],len(r['files']),'files',r['definition_counts'],len(r['alternatives']),'alternatives',len(r['missing_active_catalog_models']),'missing catalog models',flush=True)
    report['status']='PASS' if all(r['status']=='PASS' for r in report['targets'].values()) else 'GAPS'
    a.output.write_bytes((json.dumps(report,indent=2)+'\n').encode());return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
