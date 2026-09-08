"""Import continued edits to Studio-generated Xschem packages.

Symbols resolve against the package's project metadata. Unknown symbols fail
explicitly. Opaque graphics and properties are retained as review metadata.
"""
from pathlib import Path
import json,re,shlex,math
from .model import load_project,clone,uid,validate,scalar
from .interchange import pin_positions

def records(text):
    out=[];record=[];token=[];depth=0;quote=False;escaped=False
    for ch in text+'\n':
        if escaped:token.extend(('\\',ch));escaped=False;continue
        if ch=='\\':escaped=True;continue
        if ch=='"' and not depth:quote=not quote;token.append(ch);continue
        if not quote:
            if ch=='{':depth+=1
            elif ch=='}':
                depth-=1
                if depth<0:raise ValueError('Unbalanced Xschem property block.')
        if ch.isspace() and not depth and not quote:
            if token:
                word=''.join(token);record.append(word[1:-1] if word.startswith('{') and word.endswith('}') else word);token=[]
            if ch=='\n' and record:out.append(record);record=[]
        else:token.append(ch)
    if depth or quote:raise ValueError('Unterminated Xschem record.')
    return out

def properties(text):
    lex=shlex.shlex(text,posix=True);lex.whitespace_split=True;lex.commenters=''
    return {key:re.sub(r'\\([{}])',r'\1',value) for key,value in (token.split('=',1) for token in lex if '=' in token)}

def source_value(d,text):
    upper=text.upper();ac=re.search(r'\bAC\s+([^\s]+)',text,re.I)
    if ac:d['source']['ac']=str(scalar(ac[1]))
    wave=re.search(r'(PULSE|SIN)\(([^)]*)\)',text,re.I)
    if wave:
        nums=[scalar(x) for x in wave[2].split()]
        if wave[1].upper()=='PULSE':
            if len(nums)!=7:raise ValueError('Only seven-parameter PULSE sources are supported.')
            low,high,delay,rise,fall,width,period=nums
            if not math.isclose(rise,max(period*1e-5,1e-15),rel_tol=1e-5) or not math.isclose(fall,rise,rel_tol=1e-5):raise ValueError('Independent pulse rise/fall times cannot be represented by this source model.')
            d['source'].update(type='pulse',low=str(low),high=str(high),delay=str(delay),period=str(period),duty=str(width/period))
        else:
            if len(nums)!=4 or nums[2]<=0:raise ValueError('Only four-parameter SIN sources are supported.')
            d['source'].update(type='sine',low=str(nums[0]),high=str(nums[0]+nums[1]),period=str(1/nums[2]),delay=str(nums[3]))
    else:
        part=re.sub(r'^DC\s+','',text,flags=re.I).split()[0];d['value']=str(scalar(part));d['source']['type']='dc'

def import_package(path):
    path=Path(path).resolve();root=path if path.is_dir() else path.parent;project=root/'project.icproj'
    if not project.is_file():raise ValueError('This importer needs a Studio-generated Xschem package with project.icproj metadata. Arbitrary external symbol libraries are not supported.')
    lock=root/'symbols.lock.json';explicit_ports=False
    if lock.exists():
        from .model import file_digest
        locked_symbols=json.loads(lock.read_text());explicit_ports='symbols/_studio_iopin.sym' in locked_symbols
        for rel,sha in locked_symbols.items():
            target=(root/rel).resolve()
            if not target.is_relative_to(root) or not target.is_file() or file_digest(target)!=sha:raise ValueError('An exported symbol changed or is missing: '+rel+'. Reconcile symbol changes in the native symbol editor before importing.')
    p=load_project(project);prototypes={d['id']:clone(d) for c in p['cells'] for d in c['devices']};report=[];seen=set()
    for cell in p['cells']:
        file=root/(cell['name']+'.sch')
        if not file.is_file():raise ValueError('Referenced schematic file is missing: '+file.name)
        recs=records(file.read_text(encoding='utf-8'));wires=[];components=[];opaque=[];net_symbols=[];port_symbols=[]
        for r in recs:
            if r[0]=='N':
                if len(r)!=6:raise ValueError('Unsupported wire record.')
                wires.append(([float(x) for x in r[1:5]],properties(r[5]).get('lab')))
            elif r[0]=='C':
                if r[1] in ('symbols/_studio_label.sym','symbols/_studio_iopin.sym'):
                    if len(r)!=7:raise ValueError('Malformed exported label or port.')
                    props=properties(r[6]);net_symbols.append(([float(r[2]),float(r[3])],props.get('lab','')))
                    if r[1].endswith('_studio_iopin.sym'):port_symbols.append(props.get('lab',''))
                else:components.append(r)
            elif r[0] not in ('v','G','K','V','S','E'):opaque.append(r)
        if len(wires)>5000:raise ValueError('Import supports at most 5,000 wire segments per cell.')
        parent=list(range(len(wires)))
        def find(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        def on(pt,seg):
            x,y=pt;x1,y1,x2,y2=seg
            return abs((x-x1)*(y2-y1)-(y-y1)*(x2-x1))<1e-6 and min(x1,x2)-1e-6<=x<=max(x1,x2)+1e-6 and min(y1,y2)-1e-6<=y<=max(y1,y2)+1e-6
        for i,(a,_) in enumerate(wires):
            for j in range(i):
                b=wires[j][0]
                if on(a[:2],b) or on(a[2:],b) or on(b[:2],a) or on(b[2:],a):parent[find(i)]=find(j)
        labels={}
        for i,(_,lab) in enumerate(wires):
            if lab:labels.setdefault(find(i),set()).add(lab)
        for point,lab in net_symbols:
            if not lab:raise ValueError('An exported net label is empty.')
            for i,(seg,_) in enumerate(wires):
                if on(point,seg):labels.setdefault(find(i),set()).add(lab)
        if (port_symbols or explicit_ports) and (len(port_symbols)!=len(cell['ports']) or set(port_symbols)!=set(cell['ports'])):
            raise ValueError('External cell ports changed. Reconcile the component interface in Studio before importing.')
        if any(len(names)>1 for names in labels.values()):raise ValueError('A connected wire group has conflicting net labels.')
        devices=[]
        for r in components:
            if len(r)!=7:raise ValueError('Unsupported component record.')
            props=properties(r[6]);key=props.get('studio_id',Path(r[1]).stem)
            if key not in prototypes:raise ValueError('Unrecognized symbol: '+r[1]+'. Import requires a symbol from this generated package.')
            d=clone(prototypes[key]);d.update(name=props.get('name',d['name']),x=float(r[2]),y=float(r[3]),rotation=int(r[4])*90)
            if int(r[5]) not in (0,1):raise ValueError('Invalid mirror flag.')
            d['mirror']=bool(int(r[5]))
            if d['id'] in seen:d['id']=uid()
            seen.add(d['id'])
            if d.get('model_ref'):
                from .catalog import binding_for
                binding=binding_for(p['pdk'],d)
                if props.get('model',binding['model'])!=binding['model']:raise ValueError('Model changed externally. Choose a catalog device in Studio before importing this instance.')
                from .catalog import import_emitted_parameters
                import_emitted_parameters(binding,d,{k:props[k] for k in binding.get('emit_parameters',{}) if k in props})
            elif d['kind']=='X':
                child=next(c for c in p['cells'] if c['id']==d['cell'])
                d['parameters']={key:props.get(key,d.get('parameters',{}).get(key,raw)) for key,raw in child.get('parameters',{}).items()}
            elif d['kind'] in ('V','I'):source_value(d,props.get('value',d['value']))
            elif d['kind'] not in ('X','NMOS','PMOS','PDK'):d['value']=props.get('value',d['value'])
            elif d['kind'] in ('NMOS','PMOS'):
                for key in ('w','l'):d['params'][key]=props.get(key,d['params'][key])
            child=next((c for c in p['cells'] if c['id']==d.get('cell')),None)
            view={**d,'symbol':child['symbol']} if child and child.get('symbol') else d
            for pin,pt in pin_positions(view).items():
                groups={find(i) for i,(seg,_) in enumerate(wires) if on(pt,seg)};names={lab for g in groups for lab in labels.get(g,set())}
                names.update(lab for point,lab in net_symbols if all(abs(a-b)<1e-6 for a,b in zip(pt,point)))
                if len(names)>1:raise ValueError(d['name']+'.'+pin+' touches conflicting net labels.')
                if names:d['nets'][pin]=next(iter(names))
                elif groups:d['nets'][pin]='imported_net_'+str(min(groups))
                else:d['nets'][pin]='open_'+d['name']+'_'+pin
            d['xschem_properties']=props;devices.append(d)
        old=cell['devices'];cell['devices']=devices;ids={d['id'] for d in devices};cell['layout_pins']=[pin for pin in cell.get('layout_pins',[]) if pin['device_id'] in ids]
        # Imported geometry replaces the old paths; stale native geometry must
        # never override edits made in the external schematic.
        if cell.get('labels'):report.append(cell['name']+': placed label artwork becomes native pin labels; electrical net names are retained.')
        cell['labels']=[]
        cell['wires']=[{'id':uid(),'points':[seg[:2],seg[2:]]} for seg,_ in wires if seg[:2]!=seg[2:]];cell['junctions']=[]
        from .wiring import graph,rebuild
        for d in devices:d['net_labels']={}
        topology=graph(cell,p,labels=False);assigned=set()
        for d in devices:
            for pin,net in d['nets'].items():
                group=topology[(d['id'],pin)]
                if group not in assigned:d['net_labels'][pin]=net;assigned.add(group)
        from .net_labels import add
        for i,(segment,lab) in enumerate(wires):
            if lab and segment[:2]!=segment[2:]:
                match=next(w for w in cell['wires'] if w['points']==[segment[:2],segment[2:]])
                group=topology[('wire',match['id'])]
                if group not in assigned:add(cell,lab,{'kind':'wire','id':match['id'],'point':segment[:2]},p);assigned.add(group)
        rebuild(cell,p)
        for shape in cell['shapes']:
            if shape.get('device_id') not in ids:shape['device_id']=''
        if opaque:cell['xschem_opaque_records']=opaque;report.append(cell['name']+': retained '+str(len(opaque))+' opaque graphics records as metadata; they are not drawn in Studio.')
        report.append(f'{cell["name"]}: {len(old)} → {len(devices)} components. Names, values, placements, rotations and connected pin nets imported.')
    validate(p);report.append('Generic source/model coverage only. Independent pulse edges, arbitrary libraries and script execution are unsupported.');return p,report
