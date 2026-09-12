"""Declarative native/Xschem exchange with reviewed identity reconciliation."""
import hashlib, json, re
from pathlib import Path
from .model import clone, validate, atomic_write, save_project, load_project, file_digest, digest, now

MANIFEST='native-exchange.json'


def export_project(project,directory):
    from .native_spice import asset_path
    from .symbol_io import symbol_text,device_symbol
    from .xschem_project import property_text,record_text
    from .wiring import rebuild,graph,pins,on_segment
    from .net_labels import point as label_point
    from .interchange import source_spec,spice_name
    from .model import scalar
    import math
    p=clone(project);validate(p);root=Path(directory).resolve()
    from .catalog_migration import check_embedded_catalog
    check_embedded_catalog(p)
    if root.exists() and any(root.iterdir()):raise ValueError('Choose an empty Xschem export directory.')
    by={c['id']:c for c in p['cells']};output={};definitions=set();notes=[]
    for ident,asset in p['spice']['assets'].items():
        if hashlib.sha256(asset['text'].encode()).hexdigest()!=asset['sha256']:raise ValueError('Embedded model checksum mismatch.')
        output[asset_path(ident)]=asset['text']
    for kind in ('label','iopin'):
        output['symbols/studio_'+kind+'.sym']='v {xschem version=3.4.7 file_version=1.2}\nK {type='+kind+' format="*.'+kind+' @lab" template="name=p lab=net"}\nB 5 -2 -2 2 2 {name=p dir=inout}\nT {@lab} 8 -8 0 0 0.2 0.2 {}\n'
    for c in p['cells']:
        rebuild(c,p);statements=list(c.get('spice_statements',[]))
        if c['id']==p['top']:
            if p.get('global_nets'):statements.append('.global '+' '.join(p['global_nets']))
            defaults={**p.get('parameters',{}),**c.get('spice_parameters',{}),**c.get('parameters',{})}
            if defaults:statements.append('.param '+' '.join(k+'='+str(v) for k,v in defaults.items()))
        lines=['v {xschem version=3.4.7 file_version=1.2}','G {}','K {'+property_text({'studio_cell_id':c['id']})+'}','V {}',record_text(['S','\n'.join(statements)]),'E {}']
        for d in c['devices']:
            s=clone(d.get('symbol') or device_symbol(d));info=d.get('native_spice');props={'name':d['name'],'studio_id':d['id']};attrs={};fmt='@name @pinlist @value';stem='device';definition=''
            if info:
                stem=info.get('model_name','program')
                if info['type']=='program':
                    fmt='@value';attrs.update(type='netlist_commands');props.update(value=info['text'],only_toplevel='true' if info.get('only_toplevel') else 'false')
                else:
                    pieces=[]
                    for token in info['tokens']:
                        kind=token['kind'];value=token.get('value','')
                        if kind=='literal':
                            if re.search(r'[@%][A-Za-z_]',value):raise ValueError(d['name']+': literal text resembles an Xschem substitution; export this device as SPICE instead.')
                            pieces.append(value)
                        else:pieces.append({'instance':'@name','terminals':'@pinlist','terminal':'@@'+value,'parameter':'@'+value,'cell':'@symname'}[kind])
                    fmt=''.join(pieces);props.update(info['parameters']);definition=info.get('definition','')
                    if info.get('lvs_tokens'):
                        attrs['lvs_format']=''.join(t.get('value','') if t['kind']=='literal' else {'instance':'@name','terminals':'@pinlist','terminal':'@@'+t.get('value',''),'parameter':'@'+t.get('value',''),'cell':'@symname'}[t['kind']] for t in info['lvs_tokens'])
            elif d.get('model_ref'):
                from .catalog import binding_for
                from .catalog_migration import instance_name,emitted_parameters
                binding=binding_for(p['pdk'],d)
                alias=instance_name(d,binding);prefix=alias[:-len(d['name'])]
                props.update(emitted_parameters(d,p['pdk']))
                fmt=prefix+'@name '+' '.join('@@'+pin for pin in binding['pin_order'])+' '+binding['model']+''.join(' '+key+'=@'+key for key in binding.get('emit_parameters',{}))
                stem=binding['model']
                if d['model_ref'].get('lvs'):
                    from .catalog_migration import symbol_context
                    lvs=d['model_ref']['lvs'];context=symbol_context(d,p['pdk'])
                    required={token['value'] for token in lvs['tokens'] if token['kind']=='parameter'}
                    props.update({k:context.get(k,v) for k,v in lvs['parameters'].items() if k in required and k not in props})
                    attrs['lvs_format']=''.join(t.get('value','') if t['kind']=='literal' else {'instance':'@name','terminals':'@pinlist','terminal':'@@'+t.get('value',''),'parameter':'@'+t.get('value',''),'cell':'@symname'}[t['kind']] for t in lvs['tokens'])
            elif d['kind'] in ('R','C','L'):props['value']=d['value']
            elif d['kind'] in ('V','I'):props['value']=source_spec(d)
            elif d['kind'] in ('NMOS','PMOS'):
                name='studio_'+d['id'];pa=d['params'];pol=-1 if d['kind']=='PMOS' else 1
                definition=f'.model {name} {d["kind"]} (level=1 vto={pol*scalar(pa["vto"])} kp={scalar(pa["kp"])} lambda={scalar(pa["lambda"])})'
                props.update(model=name,w=pa['w'],l=pa['l']);fmt='@name @pinlist @model w=@w l=@l'
            elif d['kind']!='X':raise ValueError(d['name']+': no declared Xschem emission format.')
            if not info and not d.get('model_ref'):
                alias=spice_name(d)
                if alias!=d['name']:fmt=alias[:-len(d['name'])]+'@name'+fmt[len('@name'):]
            if d['kind']=='X':
                # Xschem resolves the schematic override through the project
                # search path, not relative to this per-device symbol folder.
                child=by[d['cell']];stem=child['name'];attrs.update(type='subcircuit',schematic=child['name']+'.sch')
                defaults={**child.get('spice_parameters',{}),**child.get('parameters',{})}
                props.update({k:str(v) for k,v in d.get('parameters',{}).items()})
                if not info:fmt='@name @pinlist @symname'+''.join(' '+k+'=@'+k for k in defaults);props.update({k:str(props.get(k,v)) for k,v in defaults.items()})
                attrs['template']=property_text({'name':'X1',**defaults})
            else:attrs.setdefault('type','primitive')
            if definition:definitions.add(definition)
            if not re.fullmatch(r'[A-Za-z0-9_.$-]+',stem):raise ValueError('Unsupported symbol filename: '+stem)
            path='symbols/'+d['id']+'/'+stem+'.sym';s['attributes']={**attrs,'format':fmt,'template':attrs.get('template',property_text({'name':d['name'],**(info.get('parameters',{}) if info else {})}))}
            # Embedded model definitions retain root-relative dependencies.
            if definition:s['attributes']['spice_sym_def']=definition
            output[path]=symbol_text(s,d['name'],fmt)
            serialized = property_text(props)
            if info and info['type'] == 'program':
                # Xschem consumes one escape level while loading an instance and
                # another when substituting @value. Keep literal SPICE quotes.
                serialized = serialized.replace(chr(92)+'"', chr(92)*2+'"')
            lines.append(record_text(['C',path,str(d['x']),str(d['y']),str(d['rotation']//90),str(int(d.get('mirror',False))),serialized]))
        port_points={}
        def label(name,pt,kind='label',index=0):
            # Reuse a port's own net label, keeping the port records in declared
            # order below. Fixed coordinates can short a different nearby net;
            # adding another port label on every export also accumulates copies.
            if kind=='label' and name in c['ports'] and name not in port_points:
                port_points[name]=pt;return
            lines.append(record_text(['C','symbols/studio_'+kind+'.sym',str(pt[0]),str(pt[1]),'0','0',property_text({'name':'studio_label'+str(len(lines)),'lab':name,'sim_pinnumber':str(index+1)})]))
        physical=graph(c,p,labels=False);named=set();positions=pins(c,p)
        for lab in c['labels']:
            label(lab['name'],label_point(lab,c,p));named.add(physical[('label',lab['id'])])
        for d in c['devices']:
            for pin,name in d['nets'].items():
                group=physical[(d['id'],pin)]
                if group not in named:label(name,positions[(d['id'],pin)]);named.add(group)
        # Ports without a named contact stay electrically isolated. Place them
        # beyond all pins, wire vertices and label anchors, including negatives.
        port_x=-120
        if any(port not in port_points for port in c['ports']):
            contacts=list(positions.values())+[pt for w in c['wires'] for pt in w['points']]+[label_point(lab,c,p) for lab in c['labels']]
            port_x=min([0]+[pt[0] for pt in contacts])-120
        for i,port in enumerate(c['ports']):label(port,port_points.get(port,[port_x,i*40]),'iopin',i)
        for wire in c['wires']:
            for a,b in zip(wire['points'],wire['points'][1:]):
                points=[a]+sorted([pt for pt in c['junctions'] if pt not in (a,b) and on_segment(pt,a,b)],key=lambda pt:math.dist(a,pt))+[b]
                for x,y in zip(points,points[1:]):lines.append(record_text(['N',str(x[0]),str(x[1]),str(y[0]),str(y[1]),'']))
        for note in c.get('annotations',[]):lines.append(record_text(['T',note['text'].replace('{','\\{').replace('}','\\}'),str(note['x']),str(note['y']),'0','0','0.2','0.2','']))
        output[c['name']+'.sch']='\n'.join(lines)+'\n'
    top=by[p['top']]['name']+'.sch'
    output['README.txt']='Open '+top+' in Xschem. Add this directory to XSCHEM_LIBRARY_PATH and use it as the netlist/simulation directory so models/ paths resolve. Symbols, native model assets and declarative programs are included. Tcl startup scripts are not exported. Reopen the top .sch in Studio to review edits and restore linked native views from the matching metadata. External edits to device terminals, model definitions and removed devices may require physical-view reconciliation.\n'
    output['exchange-report.json']=json.dumps({'version':1,'top':top,'supported':['native electrical tokens and numeric/expression parameters','ordered scalar pins','hierarchy and instance parameters','wires, labels and placements','symbol artwork','ngspice programs and embedded models','reviewed stable identities and linked native metadata'],'limits':['No arbitrary Tcl execution or vector-bus semantics.','Model-level numerical equivalence requires circuit regression.','Native-only physical views and requirements travel in the metadata sidecar.']},indent=2)
    for path,text in output.items():atomic_write(root/path,text)
    save_project(p,root/'studio-project.icproj')
    atomic_write(root/MANIFEST,json.dumps({'version':1,'top':top,'project_sha256':file_digest(root/'studio-project.icproj')},indent=2))
    return {'directory':str(root),'top':top,'files':len(output)+2,'notes':notes}


def review_project(path,library_paths=(),file_locations=None):
    from .xschem_compat import CaptureReader
    from .xschem_project import properties
    from .native_migration import review
    path=Path(path).resolve();root=path.parent;reader=CaptureReader(path,[root,*library_paths],None,file_locations or {})
    record={'mode':'native','source':str(path),'root':str(root),'candidate':None,'dependencies':reader.deps,'library_paths':[str(root)],'warnings':[],'errors':[],'stamp':{},'changes':[]}
    try:
        meta=json.loads((root/MANIFEST).read_text());basepath=root/'studio-project.icproj'
        if meta.get('version')!=1 or meta.get('top')!=path.name or file_digest(basepath)!=meta.get('project_sha256'):raise ValueError('The matching native exchange metadata is missing or changed. Restore the original metadata pair.')
        base=load_project(basepath);capture=reader.capture();capture['xschem_exchange']['library_lock']=clone(base['spice'].get('library_lock',{}))
        if reader.errors:raise ValueError('; '.join(reader.errors))
        oldcells={c['id']:c for c in base['cells']};mapping={};used=set()
        for c in capture['cells']:
            ident=next((properties(r[1]).get('studio_cell_id') for r in c['xschem']['records'] if r[0]=='K'),None)
            if ident not in oldcells:continue
            if ident in used:raise ValueError('Two schematics claim the same native cell identity.')
            mapping[c['id']]=ident;used.add(ident);old={d['id']:d for d in oldcells[ident]['devices']};groups={}
            for d in c['devices']:groups.setdefault(d['xschem']['properties'].get('studio_id'),[]).append(d)
            for did,items in groups.items():
                if did not in old:continue
                exact=[d for d in items if d['name']==old[did]['name']];chosen=items[0] if len(items)==1 else exact[0] if len(exact)==1 else None
                if chosen:mapping[chosen['id']]=did
                if len(items)>1:record['warnings'].append('Copied devices receive new identities; only an unambiguous original retains physical links.')
        def remap(v):
            if isinstance(v,dict):return {k:remap(x) for k,x in v.items()}
            if isinstance(v,list):return [remap(x) for x in v]
            return mapping.get(v,v) if isinstance(v,str) else v
        converted=review(remap(capture))
        if converted['candidate'] is None or converted['status']!='Complete':raise ValueError('; '.join(r['detail'] for r in converted['items'] if r['status']!='Migrated'))
        q=converted['candidate']
        if base.get('spice',{}).get('catalog_binding'):
            from .catalog_migration import review as catalog_review,rebase_embedded_proof
            q['spice']['catalog_binding']=rebase_embedded_proof(base,q)
            choices={d['id']:d['model_ref']['device'] for c in base['cells'] for d in c['devices'] if d.get('model_ref')}
            rebound=catalog_review(q,base['pdk'],choices,require_complete=False)
            q=rebound['candidate']
            for cell in q['cells']:
                for d in cell['devices']:
                    if d['id'] in choices and not d.get('model_ref'):
                        raise ValueError(d['name']+': external model changes require a new catalog migration review.')
        merged=clone(base);cells=[]
        for c in q['cells']:
            prior=oldcells.get(c['id'])
            if prior:
                row=clone(prior);old={d['id']:d for d in prior['devices']}
                row.update({k:v for k,v in c.items() if k in ('name','ports','symbol','devices','wires','labels','junctions','annotations','spice_statements','spice_parameters','parameters')})
                kept={d['id'] for d in row['devices']}
                if any(did not in kept for did in old if any(s.get('device_id')==did for s in row['shapes']) or any(pin['device_id']==did for pin in row.get('layout_pins',[]))):raise ValueError('An externally deleted device has linked physical geometry. Remove or detach its layout in Studio before repeating the exchange.')
                for d in row['devices']:
                    prev=old.get(d['id'])
                    if prev and prev.get('component_source'):d['component_source']=prev['component_source']
                    if prev and set(prev['nets'])!=set(d['nets']) and any(pin['device_id']==d['id'] for pin in row.get('layout_pins',[])):raise ValueError(d['name']+': terminal edits require physical pin reconciliation in Studio.')
                    if prev and prev.get('physical_binding'):d['physical_binding']=clone(prev['physical_binding'])
                    fields=('name','x','y','rotation','mirror','nets','native_spice','model_ref','model_params','params')
                    def parameters(device):return device.get('params',{})|device.get('model_params',{})|device.get('native_spice',{}).get('parameters',{})
                    record['changes'].append({'cell':c['name'],'object':d['name'],'change':'Added' if not prev else 'Changed' if digest({k:prev.get(k) for k in fields})!=digest({k:d.get(k) for k in fields}) else 'Unchanged','before':str(parameters(prev)) if prev else '', 'after':str(parameters(d))})
                    def describe(obj):
                        if not obj:return ''
                        info=obj.get('native_spice',{});value={'parameters':parameters(obj),'nets':obj['nets'],'position':[obj['x'],obj['y']],'rotation':obj['rotation'],'mirror':obj.get('mirror',False)}
                        if obj.get('model_ref'):value['model_ref']=obj['model_ref']
                        if info.get('type')=='program':value['program']=info['text']
                        return json.dumps(value,ensure_ascii=False)
                    record['changes'][-1].update(before=describe(prev),after=describe(d))
                for did,prev in old.items():
                    if did not in kept:record['changes'].append({'cell':c['name'],'object':prev['name'],'change':'Deleted','before':prev['name'],'after':''})
                cells.append(row)
            else:cells.append(c)
        cells += [clone(c) for c in base['cells'] if c['id'] not in {v['id'] for v in cells}]
        merged.update(cells=cells,top=q['top'],parameters=clone(q.get('parameters',{})),spice=q['spice'],native_migration=q['native_migration'],revision=base['revision']+1,modified=now())
        if q.get('global_nets'):merged['global_nets']=clone(q['global_nets'])
        else:merged.pop('global_nets',None)
        validate(merged);record['candidate']=merged;record['warnings']+=reader.warnings
        record['stamp']={**{str(k):v['sha256'] for k,v in reader.files.items()},str(root/MANIFEST):file_digest(root/MANIFEST),str(basepath):file_digest(basepath)}
    except (ValueError,OSError,KeyError,TypeError) as exc:record['errors'].append(str(exc))
    return record
