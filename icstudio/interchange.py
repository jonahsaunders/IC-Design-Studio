from __future__ import annotations
import base64,csv,json,math,re
from pathlib import Path
from xml.etree.ElementTree import Element,SubElement,ElementTree
from .model import PINS,uid,clone,flatten,scalar,digest,file_digest,atomic_write,save_project,load_project,validate,example,device
from .layout import kdb,polygon,shape_from_polygon

PIN_POS={'p':(0,-50),'n':(0,50),'d':(20,-50),'g':(-50,0),'s':(20,50),'b':(50,0)}
def pin_positions(d):
    raw=d['symbol']['pins'] if d.get('symbol') else PIN_POS if d['kind'] not in ('X','PDK') else {p:(-60 if i%2==0 else 60,-40+40*(i//2)) for i,p in enumerate(d['nets'])}
    if d.get('mirror'):raw={pin:(-pt[0],pt[1]) for pin,pt in raw.items()}
    a=math.radians(d['rotation']);co=round(math.cos(a));si=round(math.sin(a))
    return {p:(d['x']+raw[p][0]*co-raw[p][1]*si,d['y']+raw[p][0]*si+raw[p][1]*co) for p in d['nets']}

def spice_name(d):
    name=d['name'].replace('/','_');pre='M' if d['kind'] in ('NMOS','PMOS') else d['kind']
    return name if name.upper().startswith(pre) else pre+'_'+name

def source_spec(d):
    s=d['source'];ac=scalar(s['ac'])
    if s['type']=='dc': return f'DC {scalar(d["value"]):.12g} AC {ac:.12g}'
    if s['type']=='sine': return f'SIN({scalar(s["low"]):.12g} {scalar(s["high"])-scalar(s["low"]):.12g} {1/scalar(s["period"]):.12g} {scalar(s["delay"]):.12g}) AC {ac:.12g}'
    period=scalar(s['period']);edge=max(period*1e-5,1e-15)
    return f'PULSE({scalar(s["low"]):.12g} {scalar(s["high"]):.12g} {scalar(s["delay"]):.12g} {edge:.12g} {edge:.12g} {period*scalar(s["duty"]):.12g} {period:.12g}) AC {ac:.12g}'

def spice(p,cid=None,settings=None,hierarchical=True):
    if p.get("spice",{}).get("version")==1:raise ValueError("Use File → Export SPICE deck to export the native circuit with its model files.")
    if p.get('xschem_exchange',{}).get('mode')=='compatible':raise ValueError('Use File → Export SPICE deck to export this Xschem circuit with its preserved model files.')
    validate(p);cid=cid or p['top'];by={c['id']:c for c in p['cells']};lines=[f'* IC Design Studio / {p["name"]} / revision {p["revision"]}',f'* design-sha256 {digest(p)}','* Generic level-1 models. Not a qualified PDK netlist.'];models=[]
    from .components import require_implementations
    require_implementations(p,cid)
    from .pdks import model_lines
    if p['pdk'].get('simulation',{}).get('devices') or p['pdk'].get('simulation',{}).get('catalog'):lines[2]='* Explicit locked PDK model bindings. Qualification depends on the validated reference flow.'
    lines+=model_lines(p['pdk'],(settings or {}).get('corner','nominal'))
    if p.get('global_nets'):lines.append('.global '+' '.join(p['global_nets']))
    if any(c.get('parameters') or any(d.get('parameters') for d in c['devices']) for c in p['cells']) or p.get('parameters'):hierarchical=False
    from .catalog import binding_for,parameter_values
    bindings=p['pdk'].get('simulation',{}).get('devices',{})
    def emit(ds):
        for d in ds:
            k=d['kind'];name=spice_name(d);nets=' '.join(d['nets'][pin] for pin in (by[d['cell']]['ports'] if k=='X' else list(d['nets']) if k=='PDK' else PINS[k]));suffix=''
            binding=binding_for(p['pdk'],d)
            if binding and d.get('model_ref'):
                from .catalog_migration import instance_name
                values=parameter_values(binding,d);name=instance_name(d,binding);nets=' '.join(d['nets'][pin] for pin in binding['pin_order']);suffix=binding['model']
                suffix+=''.join(f' {key}={values[source]:.12g}' for key,source in binding.get('emit_parameters',{}).items())
            elif binding and k!='X':
                model=binding['model'];order=binding.get('pin_order',PINS[k]);prefix=binding.get('prefix','M' if k in ('NMOS','PMOS') else k)
                if set(order)!=set(PINS[k]) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_.]*',model) or prefix not in ('X','M','R','C','L'):raise ValueError('Invalid PDK device binding.')
                name=prefix+'_'+d['name'].replace('/','_');nets=' '.join(d['nets'][pin] for pin in order);suffix=model
                if k in ('NMOS','PMOS'):suffix+=f' W={scalar(d["params"]["w"])*scalar(binding.get("parameter_scale",{}).get("w",1)):.12g} L={scalar(d["params"]["l"])*scalar(binding.get("parameter_scale",{}).get("l",1)):.12g}'
                else:suffix+=f' {scalar(d["value"]):.12g}'
            elif k in ('R','C','L'):suffix=f'{scalar(d["value"]):.12g}'
            elif k in ('V','I'):suffix=source_spec(d)
            elif k=='X':suffix=by[d['cell']]['name']
            else:
                pa=d['params'];m='model_'+d['id']+'_'+digest(pa)[:10];suffix=f'{m} W={scalar(pa["w"]):.12g} L={scalar(pa["l"]):.12g}';pol=-1 if k=='PMOS' else 1
                models.append(f'.model {m} {k} (LEVEL=1 VTO={pol*scalar(pa["vto"]):.12g} KP={scalar(pa["kp"]):.12g} LAMBDA={scalar(pa["lambda"]):.12g})')
            lines.append(f'{name} {nets} {suffix}')
    if hierarchical:
        # Dependency definitions first, top-level instances last.
        reached=set()
        def deps(cell):
            for d in cell['devices']:
                if d['kind']=='X' and d['cell'] not in reached: reached.add(d['cell']);deps(by[d['cell']]);lines.append('.subckt '+by[d['cell']]['name']+' '+' '.join(by[d['cell']]['ports']));emit(by[d['cell']]['devices']);lines.append('.ends '+by[d['cell']]['name'])
        deps(by[cid]);emit(by[cid]['devices'])
    else: emit(flatten(p,cid))
    lines+=list(dict.fromkeys(models))
    if settings:
        s=settings;t=s['type'];temperature=scalar(s.get('temperature',27))
        if temperature<=-273.15:raise ValueError('Temperature must exceed absolute zero.')
        lines.append(f'.temp {temperature:.12g}')
        if t=='op':lines.append('.op')
        elif t=='tran':lines.append(f'.tran {scalar(s["step"]):.12g} {scalar(s["stop"]):.12g}')
        elif t=='dc':
            d=next((d for d in flatten(p,cid) if d['name']==s['source']),None)
            if not d or d['kind'] not in ('V','I'):raise ValueError('Invalid DC source.')
            lines.append(f'.dc {spice_name(d)} {scalar(s["dc_start"]):.12g} {scalar(s["dc_stop"]):.12g} {scalar(s["dc_step"]):.12g}')
        elif t=='ac':
            # ngspice uses points/decade; record settings remain explicit.
            lines.append(f'.ac dec {int(s["points"])} {scalar(s["start"]):.12g} {scalar(s["end"]):.12g}')
        elif t=='noise':
            output=s.get('output','');source=s.get('noise_source',s.get('source',''))
            if not __import__('icstudio.model',fromlist=['NET']).NET.fullmatch(output) or not any(d['name']==source and d['kind']=='V' for d in flatten(p,cid)):raise ValueError('Noise requires an output net and an independent voltage source.')
            source=spice_name(next(d for d in flatten(p,cid) if d['name']==source and d['kind']=='V'))
            lines.append(f'.noise V({output}) {source} dec {int(s["points"])} {scalar(s["start"]):.12g} {scalar(s["end"]):.12g}')
        else:raise ValueError('Unsupported external analysis.')
    lines.append('.end');return '\n'.join(lines)+'\n'

def export_layout(p,path):
    db=kdb();ly=db.Layout();ly.dbu=p['pdk']['dbu_um'];layers={l['name']:ly.layer(l['gds'],l['datatype']) for l in p['pdk']['layers']}
    by={c['id']:ly.create_cell(c['name']) for c in p['cells']}
    for c in p['cells']:
        cell=by[c['id']];cell.set_property(125,'icstudio:'+c['id'])
        for key,value in c.get('external_properties',[]):
            if key!=125:cell.set_property(key,value)
    for c in p['cells']:
        cell=by[c['id']]
        for inst in c.get('layout_instances',[]):
            tr=db.ICplxTrans(1,inst.get('rotation',0),inst.get('mirror',False),inst['x'],inst['y'])
            item=cell.insert(db.CellInstArray(by[inst['cell']].cell_index(),tr,db.Vector(*inst.get('a',[inst.get('dx',0),0])),db.Vector(*inst.get('b',[0,inst.get('dy',0)])),inst.get('nx',1),inst.get('ny',1)));item.set_property(126,'icstudio:'+inst['id'])
            item.set_property(125,'icstudio:'+c['id'])
            for key,value in inst.get('external_properties',[]):
                if key not in (125,126):item.set_property(key,value)
        for text in c.get('layout_texts',[]):
            label=db.Text(text['text'],db.Trans(text.get('rotation',0)//90,text.get('mirror',False),text['x'],text['y']))
            label.size=text.get('size',0);label.font=text.get('font',-1)
            label.halign=type(label.halign)(text.get('halign',-1));label.valign=type(label.valign)(text.get('valign',-1))
            item=cell.shapes(layers[text['layer']]).insert(label)
            item.set_property(125,'icstudio:'+c['id'])
            for key,value in text.get('external_properties',[]):
                if key!=125:item.set_property(key,value)
        for s in c['shapes']:
            item=cell.shapes(layers[s['layer']]).insert(polygon(s));item.set_property(127,'icstudio:'+s['id'])
            item.set_property(125,'icstudio:'+c['id'])
            for key,value in s.get('external_properties',[]):
                if key not in (125,126,127,'icstudio_id'):item.set_property(key,value)
            if s.get('net') and c.get('layout_label_mode')!='explicit':
                x,y=s['points'][0];cell.shapes(layers[s['layer']]).insert(db.Text(s['net'],db.Trans(x,y)))
    ly.write(str(path));side=Path(str(path)+'.icstudio.json');save_project(p,side)
    atomic_write(str(path)+'.report.json',json.dumps({'format':Path(path).suffix,'design_hash':digest(p),'file_hash':file_digest(path),'preserved':['polygon geometry','holes','layer/datatype','cell names','1 nm units','net text labels'],'limits':['Explicit physical cell instances and arrays are preserved; schematic-only instances have no implicit physical placement.','PCell generators are flattened to geometry.','Sidecar retains device links and editable application metadata.'],'sidecar':side.name},indent=2))
    from .interoperability import project_contract
    atomic_write(str(path)+'.exchange.json',json.dumps({'version':1,'baseline_hash':file_digest(side),
                 'layout_hash':file_digest(path),'contract':project_contract(p)},indent=2))

def import_layout(path):
    path=Path(path);side=Path(str(path)+'.icstudio.json');report=Path(str(path)+'.report.json')
    if side.exists() and report.exists():
        r=json.loads(report.read_text())
        manifest=Path(str(path)+'.exchange.json')
        if manifest.is_file():
            metadata=json.loads(manifest.read_text())
            if metadata.get('version')!=1 or metadata.get('baseline_hash')!=file_digest(side):raise ValueError('The exchange baseline is missing or changed. Restore the original metadata files.')
        if r.get('file_hash')==file_digest(path):return load_project(side),['Unchanged export restored with sidecar metadata.']
        if Path(str(path)+'.exchange.json').is_file():
            from .layout_exchange import review
            record=review(load_project(side),path)
            if record['conflicts'] or record['errors']:raise ValueError('Open the original project and review the external layout conflicts before importing.')
            return record['candidate'],record['notes']
    from .layout_import import read_layout
    project,notes=read_layout(path)
    from .layout_source import retain
    retain(project,path)
    return project,notes

def export_xschem(p,directory):
    if p.get("spice",{}).get("version")==1:
        from .native_exchange import export_project
        return export_project(p,directory)
    if p.get('xschem_exchange',{}).get('mode')=='compatible':
        from .xschem_compat import export_capture
        return export_capture(p,directory)
    if p.get('xschem_exchange'):
        from .xschem_project import export_project
        return export_project(p,directory)
    dest=Path(directory);dest.mkdir(parents=True,exist_ok=True);symbols=dest/'symbols';symbols.mkdir(exist_ok=True);by={c['id']:c for c in p['cells']}
    from .catalog import binding_for,parameter_values
    from .symbol_io import symbol_text
    def quoted(value):
        # Xschem balances braces even inside a quoted property value.
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('{','\\{').replace('}','\\}')+'"'
    written_symbols={}
    # Wire lab properties alone are not net-label symbols in Xschem. Emit actual
    # labels/ports so its own netlister sees the same connectivity and interface.
    for kind in ('label','iopin'):
        atomic_write(symbols/('_studio_'+kind+'.sym'),'v {xschem version=3.4.7 file_version=1.2}\nG {}\nK {type='+kind+' format="*.'+kind+' @lab" template="name=p lab=net" net_name=true}\nV {}\nS {}\nE {}\nB 5 -1 -1 1 1 {name=p dir=inout}\nT {@lab} 5 -8 0 0 0.2 0.2 {}\n')
    for c in p['cells']:
        lines=['v {xschem version=3.4.7 file_version=1.2}','G {}','K {}','V {}','S {}','E {}']
        label_count=0
        def label(net,x,y):
            nonlocal label_count
            label_count+=1;lines.append(f'C {{symbols/_studio_label.sym}} {x} {y} 0 0 {{name=studio_lab{label_count} lab={net}}}')
        for i,port in enumerate(c['ports'],1):lines.append(f'C {{symbols/_studio_iopin.sym}} -120 {i*40} 0 0 {{name=studio_port{i} lab={port} sim_pinnumber={i}}}')
        for original in c['devices']:
            d={**original,'symbol':by[original['cell']]['symbol']} if original['kind']=='X' and by[original['cell']].get('symbol') else original
            key=d['id'];pins=list(d['nets']);positions=pin_positions({**d,'x':0,'y':0,'rotation':0,'mirror':False});spins=' '.join('@'+pin for pin in [])
            if d['kind']=='X':fmt='@name @pinlist @symname'
            elif d['kind'] in ('NMOS','PMOS'):fmt='@name @pinlist @model W=@w L=@l'
            else:fmt='@name @pinlist @value'
            sym=['v {xschem version=3.4.7 file_version=1.2}','G {}',f'K {{type={"subcircuit" if d["kind"]=="X" else "primitive"} format="{fmt}" template="name={spice_name(d)}"}}','V {}','S {}','E {}','B 4 -28 -28 28 28 {}',f'T {{{d["kind"]}}} -15 -10 0 0 0.25 0.25 {{}}','T {@name} 35 -25 0 0 0.2 0.2 {}']
            for pin,(x,y) in positions.items():sym += [f'B 5 {x-2.5} {y-2.5} {x+2.5} {y+2.5} {{name={pin} dir=inout}}',f'L 4 {x} {y} {max(-28,min(28,x))} {max(-28,min(28,y))} {{}}']
            binding=binding_for(p['pdk'],d)
            name=spice_name(d);props=f'name={name} value='+quoted(source_spec(d) if d['kind'] in ('V','I') else d['value'])
            if binding:
                name=binding.get('prefix','X')+'_'+d['name'].replace('/','_');order=binding['pin_order'];values=parameter_values(binding,d) if d.get('model_ref') else {k:scalar(d['params'][k])*binding.get('parameter_scale',{}).get(k,1) for k in ('w','l')}
                emitted=binding.get('emit_parameters',{'w':'w','l':'l'});fmt='@name @pinlist @model'+''.join(' '+k+'=@'+k for k in emitted)
                props=f'name={name} model={binding["model"]}'+''.join(f' {k}={values[source]:.12g}' for k,source in emitted.items())
            else:
                order=by[d['cell']]['ports'] if d['kind']=='X' else list(d['nets'])
                if d['kind']=='X':
                    defaults=by[d['cell']].get('parameters',{});fmt+=''.join(' '+k+'=@'+k for k in defaults);props+=''.join(' '+k+'='+quoted(d.get('parameters',{}).get(k,v)) for k,v in defaults.items())
                if d['kind'] in ('NMOS','PMOS'):props+=f' model=model_{d["id"]} w={d["params"]["w"]} l={d["params"]["l"]}'
            if d.get('symbol'):
                sym_text=symbol_text(d['symbol'],name,fmt,order)
            elif binding or d['kind']=='X':
                # Generic artwork with explicit PDK terminal order and format.
                symbol={'primitives':[{'kind':'rect','points':[[-28,-28],[28,28]]}],'pins':{}};symbol['pins']={pin:list(positions[pin]) for pin in order};sym_text=symbol_text(symbol,name,fmt,order)
            else:sym_text='\n'.join(sym)+'\n'
            if d['kind']!='X':sym_text=sym_text.replace('type=subcircuit','type=primitive')
            symbol_path=dest/(by[d['cell']]['name']+'.sym') if d['kind']=='X' else symbols/(key+'.sym')
            if d['kind']=='X':
                props+=' studio_id='+d['id']
                # Shared cell symbols must have identical geometry for every use.
                defaults=''.join(' '+k+'='+str(v) for k,v in by[d['cell']].get('parameters',{}).items())
                sym_text=sym_text.replace('template="name='+name+'"','template='+quoted('name=X1'+defaults))
                if symbol_path in written_symbols and written_symbols[symbol_path]!=sym_text:raise ValueError('Instances of '+by[d['cell']]['name']+' have different symbol geometry. Synchronize the component symbol in Studio before export.')
                written_symbols[symbol_path]=sym_text
            atomic_write(symbol_path,sym_text)
            lines.append(f'C {{{symbol_path.relative_to(dest).as_posix()}}} {d["x"]} {d["y"]} {d["rotation"]//90} {int(d.get("mirror",False))} {{{props}}}')
            for pin,(x,y) in pin_positions(d).items():
                from .wiring import on_segment
                connected=any(on_segment((x,y),a,b) for w in c.get('wires',[]) for a,b in zip(w['points'],w['points'][1:]))
                if not connected:
                    lines.append(f'N {x} {y} {x+10} {y} {{}}');label(d['nets'][pin],x,y)
        for wire in c.get('wires',[]):
            for a,b in zip(wire['points'],wire['points'][1:]):
                # Split at explicit junctions for destination-tool topology.
                points=[a]+sorted([pt for pt in c.get('junctions',[]) if pt not in (a,b) and on_segment(pt,a,b)],key=lambda pt:(pt[0]-a[0])**2+(pt[1]-a[1])**2)+[b]
                for start,end in zip(points,points[1:]):lines.append(f'N {start[0]} {start[1]} {end[0]} {end[1]} {{}}')
            label(wire['net'],*wire['points'][0])
        atomic_write(dest/(c['name']+'.sch'),'\n'.join(lines)+'\n')
    save_project(p,dest/'project.icproj');atomic_write(dest/'simulation.cir',spice(p,settings=p['analysis']));atomic_write(dest/'symbols.lock.json',json.dumps({str(f.relative_to(dest)):file_digest(f) for f in list(symbols.glob('*.sym'))+list(dest.glob('*.sym'))},indent=2))
    atomic_write(dest/'README.txt','Generated Xschem symbols and schematics. Open the top .sch from this directory, and include this folder in XSCHEM_LIBRARY_PATH. Named nets use actual label symbols; components use explicit ordered interface ports. PDK devices use primitive symbols; native hierarchical cells have sibling .sym/.sch files. Use simulation.cir for the complete Studio model/testbench deck. Netlisting the .sch with Xschem produces circuit connectivity; configure model includes and analysis in your external testbench. Studio imports edits to these schematics with their project metadata; symbol changes require explicit reconciliation. See UPDATE_0.8.md for executed exchange coverage.\n')

def export_technology(p,dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);root=Element('layer-properties')
    for l in p['pdk']['layers']:
        v=SubElement(root,'properties')
        for tag,text in [('name',l['name']),('source',f'{l["gds"]}/{l["datatype"]}@1'),('fill-color',l['color']),('frame-color',l['color']),('visible','true')]:SubElement(v,tag).text=text
    ElementTree(root).write(dest/'layers.lyp',encoding='utf-8',xml_declaration=True)
    atomic_write(dest/'technology.json',json.dumps(p['pdk'],indent=2))
    from .interoperability import export_technology as export_contract
    export_contract(p['pdk'],dest)

def export_handoff(p,dest):
    dest=Path(dest)
    if dest.exists() and any(dest.iterdir()):raise ValueError('Choose a new or empty directory so an existing handoff is not overwritten.')
    dest.mkdir(parents=True,exist_ok=True)
    if p['pdk'].get('package_lock'):
        import shutil
        from .pdks import model_lines
        model_lines(p['pdk'],p['analysis'].get('corner','nominal'));p=clone(p);source_root=Path(p['pdk']['package_root']);asset_root=dest/'technology'/'package'
        for rel in p['pdk']['package_lock']['files']:
            target=asset_root/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_root/rel,target)
        p['pdk']['package_root']=str(asset_root.resolve())
    save_project(p,dest/'project.icproj');atomic_write(dest/'simulation.cir',spice(p,settings=p['analysis']));export_layout(p,dest/'layout.gds');export_layout(p,dest/'layout.oas');export_xschem(p,dest/'xschem');export_technology(p,dest/'technology')
    atomic_write(dest/'dependencies.lock.json',json.dumps({'app':__import__('icstudio').__version__,'schema':1,'pdk':p['pdk'],'engine':'teaching solver 0.1.0','design_hash':digest(p)},indent=2))
    if p['pdk'].get('package_lock'):
        root=str(dest.resolve()).replace('\\','/')+'/'
        for deck in dest.rglob('*.cir'):
            # Deck paths are relative to their own working directory.
            import os
            relroot=os.path.relpath(dest.resolve(),deck.parent.resolve()).replace('\\','/')+'/'
            atomic_write(deck,deck.read_text().replace(root,relroot))
        for project_file in list(dest.rglob('project.icproj'))+list(dest.rglob('*.icstudio.json')):
            portable=clone(p);portable['pdk']['package_root']=os.path.relpath(Path(p['pdk']['package_root']),project_file.parent.resolve()).replace('\\','/');save_project(portable,project_file)
        for manifest in dest.glob('*.exchange.json'):
            metadata=json.loads(manifest.read_text());side=Path(str(manifest).removesuffix('.exchange.json')+'.icstudio.json')
            metadata['baseline_hash']=file_digest(side);atomic_write(manifest,json.dumps(metadata,indent=2))
    files={str(f.relative_to(dest)):file_digest(f) for f in dest.rglob('*') if f.is_file()}
    atomic_write(dest/'preservation-report.json',json.dumps({'revision':p['revision'],'files':files,'status':'engineering-preview','not_qualified':['arbitrary-design DRC/LVS and extraction correctness','unrestricted external-library round trips','Windows binary','fabrication signoff'],'verification':'An export does not certify this design. See UPDATE_0.8.md for the executed custom-inverter and external-edit fixtures; rerun physical verification after changes.','magic':'Generate native .mag through the separately installed Magic engine with a matching technology file.'},indent=2))

def export_csv(result,path):
    names=list(result['traces']);lines=[]
    import io
    f=io.StringIO();writer=csv.writer(f);writer.writerow([result['x_label']]+names)
    for i,x in enumerate(result['x']):writer.writerow([x]+[result['traces'][n][i] for n in names])
    atomic_write(path,f.getvalue())
