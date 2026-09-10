"""Direct, declarative Xschem project exchange. Never evaluates Tcl or xschemrc.

The reader constructs native geometry first, then converts an explicit SPICE
representation through the same validated importer used by File / Import SPICE.
Original records and dependency bytes remain in the project for portable export.
"""
from pathlib import Path
import hashlib,json,math,os,re
from .model import clone,uid,device,example,validate,scalar,digest,file_digest,atomic_write,save_project,load_project,now,NAME,NET,PINS
from .xschem_io import records,properties
from .spice_import import import_spice,tokens,assignments
from .symbol_io import import_symbol,symbol_text
from .interchange import pin_positions,source_spec
from .wiring import rebuild,graph,pins as cell_pins,on_segment
from .xschem_paths import default_libraries,library_folders,dependency_hint


def properties(text):
    """Xschem attributes, including nested escaped quotes in library templates.

    Shell tokenization is unsuitable: upstream symbols use doubled backslashes
    before quoted strings inside format/template attributes.
    """
    result={};i=0;n=len(text)
    while i<n:
        while i<n and text[i].isspace():i+=1
        match=re.match(r'([^\s=]+)=',text[i:])
        if not match:
            while i<n and not text[i].isspace():i+=1
            continue
        key=match[1];i+=len(match[0]);value=[];quote=i<n and text[i]=='"'
        if quote:i+=1
        closed=not quote
        while i<n:
            ch=text[i]
            if ch=='\\':
                start=i
                while i<n and text[i]=='\\':i+=1
                count=i-start
                if i<n and text[i] in ('"','{','}'):
                    value.append(text[i]);i+=1;continue
                value.append('\\'*((count+1)//2));continue
            if quote and ch=='"':i+=1;closed=True;break
            if not quote and ch.isspace():break
            value.append(ch);i+=1
        if not closed:raise ValueError('Unterminated quoted Xschem attribute: '+key)
        result[key]=''.join(value)
    return result


def quoted(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('{','\\{').replace('}','\\}')+'"'


def property_text(props):
    return ' '.join(k+'='+quoted(v) for k,v in props.items())


def record_text(r):
    # The parser removes only each field's outer braces. Backslash escapes inside
    # records remain intact, so unknown record contents survive serialization.
    brace={'v':{1},'G':{1},'K':{1},'V':{1},'S':{1},'E':{1},'F':{1},
           'C':{1,6},'N':{5},'L':{6},'B':{6},'A':{7},'T':{1,8},'P':{len(r)-1}}
    return ' '.join('{'+v+'}' if i in brace.get(r[0],set()) else v for i,v in enumerate(r))


def expression(raw):
    """Normalize numeric SPICE parameter expressions to native bounded syntax."""
    raw=str(raw).strip()
    try:scalar(raw);return raw
    except ValueError:pass
    body=raw.strip("'\"{}").strip()
    body=re.sub(r'(?<![\w.])(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:meg|[tgkmunpf])\b',lambda m:repr(scalar(m[0])),body,flags=re.I)
    return '{'+body.lower()+'}'


def substitute(fmt,props,order,nets,symname):
    if any(s in fmt for s in ('tcleval','[',']',';','\n','\r')):raise ValueError('Executable or multiline netlisting templates need an external Xschem workflow.')
    props={**props,'pinlist':' '.join(nets[p] for p in order),'symname':symname}
    def replace(m):
        token=m[0]
        if token.startswith('@@'):
            if token[2:] not in nets:raise ValueError('Unknown terminal in netlisting template: '+token)
            return nets[token[2:]]
        key=token[1:]
        if key not in props:
            if key=='spiceprefix':raise ValueError('Conditional spiceprefix needs an explicit instance value.')
            if token.startswith('%'):return key
            raise ValueError('Missing netlisting parameter: '+key)
        result=str(props[key])
        if 'tcleval' in result or '\n' in result or '\r' in result:raise ValueError('Executable or multiline component values are unsupported for native simulation.')
        return result
    return re.sub(r'@@?[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*',replace,fmt)


class Reader:
    def __init__(self,path,libraries,technology,file_locations=None):
        self.top=Path(path).resolve();self.locations={ref:Path(p).resolve() for ref,p in (file_locations or {}).items()};self.roots=list(dict.fromkeys([self.top.parent]+[Path(p) for p in library_folders(libraries)]+[p.parent for p in self.locations.values()]));self.technology=technology
        if technology and technology.get('package_root'):self.roots.append(Path(technology['package_root']).resolve())
        self.files={};self.deps=[];self.errors=[];self.warnings=[];self.cells={};self.symbols={};self.stack=[];self.names=set();self.models={};self.control=[];self.model_visiting=set();self.total_bytes=0;self.corner=None

    def resolve(self,ref,parent,kind):
        ref=ref.strip('"\'');parent=Path(parent)
        scoped=str(parent.resolve())+'::'+ref
        location=self.locations.get(scoped,self.locations.get(ref))
        dynamic=location is None and any(x in ref for x in ('$','[',']','tcleval','\n','\r'))
        candidates=([location] if location is not None else [] if dynamic else [(parent.parent/ref).resolve()]+[(root/ref).resolve() for root in self.roots])
        target=next((p for p in candidates if any(p.is_relative_to(root) for root in self.roots) and p.is_file()),None)
        row={'kind':kind,'reference':ref,'parent':str(parent),'path':str(target) if target else '', 'status':('Located' if location is not None else 'Found') if target else 'Missing','hint':('Dynamic path: locate the resolved file explicitly. ' if dynamic else '')+dependency_hint(ref) if target is None else '','searched':[str(p) for p in candidates]}
        if row not in self.deps:self.deps.append(row)
        if target is None:self.errors.append(f'{parent.name}: missing {kind} {ref}. '+row['hint'])
        return target

    def preflight(self,source_records,path):
        """Expose static embedded-code dependencies even if its symbol is absent.

        This is diagnostic only. Conversion still interprets the value according
        to the resolved symbol's type and applies all existing model checks.
        """
        for r in source_records:
            if r[0]!='C' or len(r)!=7:continue
            props=properties(r[6]);value=props.get('value','')
            if '\n' not in value:continue
            in_control=False;unsupported=set()
            for line in value.splitlines():
                line=line.strip()
                if not line or line.startswith('*'):continue
                part=tokens(line);cmd=part[0].lower()
                if cmd=='.control':in_control=True;continue
                if cmd=='.endc':in_control=False;continue
                if not in_control and ((cmd in ('.include','.inc') and len(part)==2) or (cmd=='.lib' and len(part)==3)):
                    self.resolve(part[1],path,'Model library' if cmd=='.lib' else 'Model / include')
                if in_control and cmd not in ('op','ac','tran','save','plot','print','write','set','setplot','display','echo'):
                    unsupported.add(cmd)
            if unsupported:self.warnings.append(path.name+': embedded ngspice control program uses '+', '.join(sorted(unsupported))+'. This program requires an external Xschem/ngspice workflow; native setup conversion is not supported. Resolving symbol files alone will not make this project importable.')

    def read(self,path,kind):
        path=Path(path)
        if path in self.files:return self.files[path]['text']
        data=path.read_bytes();self.total_bytes+=len(data)
        # The pinned SKY130 primitive corner closure is about 34 MB. Retain a
        # bounded import while allowing that standard open PDK to be portable.
        if len(data)>10_000_000 or self.total_bytes>64_000_000 or len(self.files)>=1000:raise ValueError('Xschem import is limited to 1,000 files, 10 MB per file and 64 MB total.')
        text=data.decode('utf-8');self.files[path]={'text':text,'kind':kind,'sha256':hashlib.sha256(data).hexdigest()};return text

    def symbol(self,path):
        if path not in self.symbols:
            text=self.read(path,'Symbol');s,_,notes=import_symbol(path,preserve_case=True)
            attrs=next((properties(r[1]) for r in records(text) if r[0]=='K'),{});attrs.pop('studio_symbol_v2',None);s['attributes']=clone(attrs)
            self.symbols[path]=(s,attrs);self.warnings.extend(path.name+': '+n for n in notes)
        return self.symbols[path]

    def include(self,ref,parent):
        path=self.resolve(ref,parent,'Model / include')
        if path is None:return
        if path in self.model_visiting:raise ValueError('Recursive model include: '+path.name)
        if path in self.files:return
        self.model_visiting.add(path)
        tech=self.technology or {};root=Path(tech.get('package_root',self.top.parent)).resolve();lock=tech.get('package_lock',{}).get('files',{});rel=path.relative_to(root).as_posix() if path.is_relative_to(root) else None
        text=self.read(path,'Model / include')
        if rel in lock or self.files[path]['sha256'] in lock.values():
            if rel in lock and file_digest(path)!=lock[rel]:raise ValueError('A linked PDK model file changed: '+str(path))
            # PDK model bodies are handled by their existing locked catalog adapter.
            # Copy static nested includes for export without interpreting model code.
            for line in re.sub(r'\n\s*\+\s*',' ',text).splitlines():
                part=tokens(line.strip())
                if part and ((part[0].lower() in ('.include','.inc') and len(part)==2) or (part[0].lower()=='.lib' and len(part)==3)):self.include(part[1],path)
            self.warnings.append(path.name+': electrical model supplied by the linked PDK catalog.')
        else:self.directives(text,path,None)
        self.model_visiting.remove(path)

    def directives(self,text,parent,cell):
        in_control=False
        for line in re.sub(r'\n\s*\+\s*',' ',text).splitlines():
            line=line.strip()
            if not line or line.startswith('*'):continue
            part=tokens(line);cmd=part[0].lower()
            if cmd=='.control':in_control=True;continue
            if cmd=='.endc':in_control=False;continue
            if in_control and cmd in ('op','ac','tran'):cmd='.'+cmd;line='.'+line
            if cmd in ('.include','.inc') and len(part)==2:self.include(part[1],parent)
            elif cmd=='.model':
                if len(part)<3:raise ValueError('Malformed .model in '+str(parent))
                key=part[1].casefold()
                if key in self.models and self.models[key]!=line:raise ValueError('Conflicting model definitions: '+part[1])
                self.models[key]=line
            elif cmd=='.param' and cell is not None:
                cell.setdefault('parameters',{}).update({k:expression(v) for k,v in assignments(part[1:]).items()})
            elif cmd in ('.op','.ac','.tran','.temp') and cell is not None:
                self.control.append(line)
            elif cmd in ('.save','.print','.plot','.end') or (in_control and cmd in ('save','plot','print','write','set','setplot','display','echo')):
                self.warnings.append(parent.name+': output/display command retained for Xschem; Studio uses its own saved results: '+part[0])
            elif cmd=='.lib' and len(part)==3:
                # A linked PDK supplies its reviewed include sections and exact model bindings.
                path=self.resolve(part[1].strip('"\''),parent,'Model library')
                if path:
                    self.include(part[1],parent)
                    tech=self.technology or {};root=Path(tech.get('package_root',self.top.parent)).resolve();rel=path.relative_to(root).as_posix() if path.is_relative_to(root) else ''
                    if not rel:rel=next((key for key,sha in tech.get('package_lock',{}).get('files',{}).items() if sha==self.files[path]['sha256']),'')
                    item=next((v for v in tech.get('simulation',{}).get('includes',[]) if v['path']==rel),{})
                    aliases=[key for key,val in item.get('sections',{}).items() if val==part[2]]
                    if aliases:self.corner='nominal' if 'nominal' in aliases else aliases[0]
                    elif item.get('section')!=part[2]:self.errors.append(parent.name+': model section is not declared in the linked PDK.')
                if not self.technology:self.errors.append(parent.name+': .lib sections require a linked PDK catalog.')
            else:self.errors.append(parent.name+': unsupported circuit/control statement '+part[0]+'. Preserve it in Xschem or replace it with a supported native setup.')

    def load_cell(self,path,interface=None):
        if path in self.stack:raise ValueError('Recursive schematic hierarchy: '+path.name)
        if len(self.stack)>12:raise ValueError('Schematic hierarchy exceeds 12 levels.')
        if path in self.cells:
            c=self.cells[path]
            if interface and (c['ports']!=interface['pin_order'] or c['symbol']['pins']!=interface['pins']):raise ValueError('Conflicting symbol interfaces for '+path.name)
            return c
        if len(self.cells)>=100:raise ValueError('Import supports at most 100 cells.')
        stem=re.sub('[^A-Za-z0-9_.$-]','_',path.stem)[:54]
        if not stem or not NAME.fullmatch(stem):stem='cell_'+stem
        name=stem;i=2
        while name.casefold() in self.names:name=stem+'_'+str(i);i+=1
        self.names.add(name.casefold());c={'id':uid(),'name':name,'ports':list(interface['pin_order']) if interface else [],'parameters':{},'devices':[],'shapes':[],'wires':[],'labels':[],'junctions':[],'xschem':{'path':str(path),'records':records(self.read(path,'Schematic')),'components':[]}}
        if interface:
            c['symbol']=clone(interface);c['parameters']={k.lower():expression(v) for k,v in properties(interface.get('attributes',{}).get('template','')).items() if k!='name'}
        self.cells[path]=c;self.stack.append(path);ports=[]
        self.preflight(c['xschem']['records'],path)
        for index,r in enumerate(c['xschem']['records']):
            try:
                if r[0]=='N':
                    if len(r)!=6:raise ValueError('Malformed wire record.')
                    pts=[list(map(float,r[1:3])),list(map(float,r[3:5]))]
                    if pts[0]!=pts[1]:c['wires'].append({'id':uid(),'points':pts})
                    if properties(r[5]).get('lab'):self.warnings.append(path.name+': wire lab property retained; electrical names come from label symbols.')
                elif r[0]=='C':
                    if len(r)!=7:raise ValueError('Malformed component record.')
                    sympath=self.resolve(r[1],path,'Symbol')
                    if sympath is None:continue
                    s,a=self.symbol(sympath);props={**properties(a.get('template','')),**properties(r[6])};kind=a.get('type','').lower()
                    x,y=float(r[2]),float(r[3]);rot,mirror=int(r[4])*90,int(r[5])
                    if rot not in (0,90,180,270) or mirror not in (0,1):raise ValueError('Invalid rotation or mirror.')
                    info={'record_index':index,'symbol_path':str(sympath),'symbol_text':self.files[sympath]['text'],'properties':props,'original_properties':properties(r[6]),'symbol':clone(s),'kind':kind}
                    if kind in ('label','ipin','opin','iopin'):
                        if len(s['pins'])!=1:raise ValueError('Labels and ports must have one terminal.')
                        lab=props.get('lab',a.get('lab',''))
                        if kind=='label' and lab.casefold()=='gnd':lab='0'
                        if not NET.fullmatch(lab):raise ValueError('Unsupported net or bus label: '+lab)
                        if props.get('global',a.get('global')) in ('true','1') and lab!='0':raise ValueError('Global nets use the native capture importer.')
                        view=device('X',props.get('name','label'),x,y,rotation=rot,mirror=bool(mirror),symbol=s,nets={p:lab for p in s['pins']});point=list(next(iter(pin_positions(view).values())))
                        ident=uid();c['labels'].append({'id':ident,'name':lab,'kind':'ground' if lab=='0' else 'net_label','anchor':{'kind':'point','point':point},'offset':[0,0] if lab=='0' else [10,-12],'rotation':rot})
                        info['label_id']=ident
                        if kind!='label':ports.append((lab,props.get('sim_pinnumber'),info))
                    elif kind=='netlist_commands':self.directives(props.get('value',''),path,c)
                    elif kind in ('launcher','logo','graph','probe','ngprobe') or (props.get('spice_ignore',a.get('spice_ignore')) in ('true','open')):
                        self.warnings.append(path.name+': '+props.get('name',kind)+' retained for Xschem; its non-electrical artwork/action is not active in Studio.')
                    else:
                        if not s['pins']:raise ValueError('Electrical symbol has no terminals.')
                        name=props.get('name','')
                        if not NAME.fullmatch(name):raise ValueError('Invalid or vector instance name: '+name)
                        if props.get('spice_ignore',a.get('spice_ignore'))=='short':raise ValueError('Shorted symbols require explicit native wires.')
                        child=None
                        if kind=='subcircuit' and not a.get('spice_sym_def') and props.get('spice_primitive',a.get('spice_primitive'))!='true':
                            ref=props.get('schematic',a.get('schematic',sympath.stem+'.sch'))
                            childpath=self.resolve(ref,sympath,'Child schematic')
                            if childpath:child=self.load_cell(childpath,s)
                        d=device('X',name,x,y,rotation=rot,mirror=bool(mirror),symbol=clone(s),nets={pin:'open' for pin in s['pin_order']})
                        d['xschem']=info;info['device_id']=d['id']
                        if child:d['cell']=child['id']
                        c['devices'].append(d)
                    c['xschem']['components'].append(info)
                elif r[0] in ('S',) and len(r)>1 and r[1].strip():self.directives(r[1],path,c)
                elif r[0]=='T' and len(r)>=9:
                    if len(r[1])<=2000:c.setdefault('annotations',[]).append({'id':uid(),'text':r[1],'x':float(r[2]),'y':float(r[3]),'xschem_record':index})
                elif r[0] not in ('v','G','K','V','E','F'):
                    self.warnings.append(path.name+': '+r[0]+' graphics preserved for export.')
            except (ValueError,KeyError,IndexError,TypeError,OSError) as exc:self.errors.append(f'{path.name}, record {index+1}: {exc}')
        declared=[p[0] for p in ports]
        if interface and (set(declared)!=set(c['ports']) or len(declared)!=len(c['ports'])):self.errors.append(path.name+': schematic ports do not match its symbol interface.')
        if not interface and ports:
            if all(p[1] is not None for p in ports):
                if len({int(p[1]) for p in ports})!=len(ports):self.errors.append(path.name+': duplicate port order.')
                ports.sort(key=lambda p:int(p[1]))
            c['ports']=[p[0] for p in ports]
        self.stack.pop();return c

    def convert(self):
        top=self.load_cell(self.top)
        if self.errors:return None
        shell=example('empty');shell['cells']=list(self.cells.values());shell['top']=top['id'];by={c['id']:c for c in shell['cells']}
        if self.technology:shell['pdk']=clone(self.technology)
        deck=['* Direct Xschem import'];needed_models=set();rows={}
        for c in shell['cells']:
            rebuild(c,shell)
            text=[]
            if c is not top:text.append('.subckt '+c['name']+' '+' '.join(c['ports'])+' '+ ' '.join(k+'='+v for k,v in c['parameters'].items()))
            elif c['parameters']:text.append('.param '+' '.join(k+'='+v for k,v in c['parameters'].items()))
            for d in c['devices']:
                info=d['xschem'];s=info['symbol'];a=s['attributes'];props=info['properties'];child=by.get(d.get('cell'));order=s['pin_order'];symname=child['name'] if child else Path(info['symbol_path']).stem
                fmt=a.get('format','')
                compact=re.sub(r'\s+','',fmt.replace('\\',''))
                if a.get('type')=='vsource' and compact=='tcleval([expr{@savecurrent?"@name@pinlist@value.saveI(?1@name)":"@name@pinlist@value"}])':
                    fmt='@name @pinlist @value';self.warnings.append(c['name']+': standard voltage-source current-probe template mapped declaratively; no Tcl was executed.')
                if a.get('type') in ('nmos','pmos'):
                    props.setdefault('extra','');props.setdefault('spiceprefix','')
                line=substitute(fmt,props,order,d['nets'],symname)
                if not line.strip():raise ValueError(d['name']+': missing SPICE netlisting template.')
                sentinels={pin:'studio_terminal_'+str(i) for i,pin in enumerate(order)}
                probe=tokens(substitute(fmt,props,order,sentinels,symname));inverse={v:k for k,v in sentinels.items()}
                terminal_tokens=probe[1:1+len(order)]
                if set(terminal_tokens)!=set(inverse) or len(set(terminal_tokens))!=len(order):raise ValueError(d['name']+': template must emit each terminal once before its value or model.')
                emitted_order=[inverse[v] for v in terminal_tokens]
                if child and emitted_order!=order:raise ValueError(d['name']+': reordered subcircuit template pins need a matching symbol interface.')
                part=tokens(line);kind=part[0][0].upper()
                if child:
                    # Explicit child path overrides @symname in upstream instances.
                    end=next((i for i,t in enumerate(part) if '=' in t or t.lower()=='params:'),len(part));part[end-1]=child['name']
                if kind in ('R','C','L','M'):
                    # Unit multiplicity has no electrical effect; all other factors
                    # remain explicit and must be supported by the native adapter.
                    part=[t for t in part if not re.fullmatch(r'(?:m|nf)=1(?:\.0*)?',t,re.I)]
                if kind in ('R','C','L') and len(part)>3:part[3]=expression(part[3])
                if kind=='M' and len(part)>5:needed_models.add(part[5].lower())
                for i,t in enumerate(part):
                    if i and '=' in t:
                        key,val=t.split('=',1);part[i]=key.lower()+'='+expression(val)
                line=' '.join(part);text.append(line);info['emitted_name']=part[0];info['electrical_order']=emitted_order;rows[(c['name'].lower(),part[0].lower())]=d
            if c is not top:text.append('.ends '+c['name'])
            deck.extend(text)
        # Only models referenced by generic MOS instances are needed by the native
        # teaching adapter; other model cards remain preserved in dependency files.
        catalog=(self.technology or {}).get('simulation',{}).get('catalog',{})
        bound={e.get('model','').lower() for e in catalog.values() if not e.get('unavailable')}
        for key in needed_models-bound:
            if key not in self.models:raise ValueError('Missing MOS model '+key+'. Include a level-1 model or link a PDK catalog.')
            deck.append(self.models[key])
        deck+=self.control+['.end']
        p,notes=import_spice(self.top, self.technology,text='\n'.join(deck),top_name=top['name']);self.warnings.extend(notes);p['name']=self.top.stem
        if self.corner:p['analysis']['corner']=self.corner
        imported={c['name'].lower():c for c in p['cells']}
        root=next(c for c in p['cells'] if c['id']==p['top']);root['name']=top['name'];imported[top['name'].lower()]=root
        idmap={c['id']:imported[c['name'].lower()]['id'] for c in shell['cells']}
        for c in shell['cells']:
            topology=graph(c,shell,labels=False);named={topology[('label',l['id'])] for l in c['labels']}
            target=imported[c['name'].lower()];target['xschem']=c['xschem'];target['ports']=c['ports'];target['wires']=c['wires'];target['labels']=c['labels'];target['junctions']=[];target['annotations']=c.get('annotations',[])
            if c.get('symbol'):target['symbol']=c['symbol']
            for d in target['devices']:
                original=rows[(c['name'].lower(),d['name'].lower())];info=original['xschem'];native=list(d['nets']);order=info['electrical_order']
                if len(native)!=len(order):raise ValueError(d['name']+': terminal count does not match the native device.')
                mapping=dict(zip(order,native));s=clone(original['symbol']);s['pins']={mapping[k]:v for k,v in s['pins'].items()};s['pin_order']=[mapping[k] for k in order];s['pin_meta']={mapping[k]:v for k,v in s.get('pin_meta',{}).items()}
                d.update(id=original['id'],x=original['x'],y=original['y'],rotation=original['rotation'],mirror=original['mirror'],symbol=s,xschem=info)
                d['name']=info['properties']['name'];info['pin_mapping']=mapping;info['native_symbol_hash']=digest(s);info['snapshot']={k:clone(d[k]) for k in ('name','value','params','source','nets')};info['snapshot']['parameters']=clone(d.get('parameters',{}))
                d['symbol_context']={k:v for k,v in info['properties'].items() if k not in ('name','value','w','l') and k not in d.get('parameters',{})};d['symbol_context']['symname']=Path(info['symbol_path']).stem
                d['net_labels']={}
                for oldpin,nativepin in mapping.items():
                    group=topology[(d['id'],oldpin)]
                    if group not in named:d['net_labels'][nativepin]=d['nets'][nativepin];named.add(group)
            positions=cell_pins(target,p)
            for label in target['labels']:
                point=label['anchor']['point'];hit=next((key for key,pt in positions.items() if pt==point),None)
                if hit:label['anchor']={'kind':'pin','id':hit[0],'pin':hit[1]}
                else:
                    wire=next((w for w in target['wires'] if any(on_segment(point,a,b) for a,b in zip(w['points'],w['points'][1:]))),None)
                    if wire:label['anchor']={'kind':'wire','id':wire['id'],'point':point}
            rebuild(target,p)
            # Compare the actual imported geometry against the explicit netlist.
            for d in target['devices']:
                if d['nets']!=d['xschem']['snapshot']['nets']:raise ValueError(d['name']+': imported geometry disagrees with the source terminal mapping.')
        files={str(path):data for path,data in self.files.items()}
        p['xschem_exchange']={'version':1,'source_top':str(self.top),'source_files':files,'libraries':[str(p) for p in self.roots],'resolved_dependencies':clone(self.deps),'warnings':list(dict.fromkeys(self.warnings)),'source_netlist':'\n'.join(deck)+'\n','import_analysis':clone(p['analysis']),'import_parameters':clone(p.get('parameters',{}))}
        validate(p);return p


def review_schematic(path,library_paths=(),technology=None,file_locations=None):
    reader=Reader(path,library_paths,technology,file_locations);candidate=None
    extra={}
    try:
        manifest=reader.top.parent/'studio-exchange.json';base=None
        if manifest.is_file():
            data=json.loads(manifest.read_text());native=reader.top.parent/'studio-project.icproj'
            if data.get('version')!=1 or not native.is_file() or data.get('project_sha256')!=file_digest(native):raise ValueError('The native exchange metadata is missing or changed. Restore the matching metadata pair or import a copy containing only the Xschem source assets.')
            base=load_project(native);extra={str(manifest):file_digest(manifest),str(native):file_digest(native)};reader.deps.append({'kind':'Native metadata','reference':native.name,'parent':str(reader.top),'path':str(native),'status':'Found'})
            if reader.technology is None and base['pdk'].get('package_lock'):reader.technology=clone(base['pdk']);reader.roots.append(Path(base['pdk']['package_root']).resolve())
        candidate=reader.convert()
        if candidate and base:candidate=restore_native_metadata(candidate,base,reader.warnings)
    except (ValueError,OSError,KeyError,TypeError,IndexError,SyntaxError,ZeroDivisionError) as exc:reader.errors.append(str(exc))
    return {'mode':'direct','root':str(reader.top.parent),'source':str(reader.top),'candidate':candidate if not reader.errors else None,'dependencies':reader.deps,'library_paths':[str(p) for p in reader.roots],'warnings':list(dict.fromkeys(reader.warnings)),'errors':list(dict.fromkeys(reader.errors)),'stamp':{**{str(path):v['sha256'] for path,v in reader.files.items()},**extra},'changes':[{'cell':c['name'],'object':'Schematic','change':'Import','before':'','after':f"{len(c['devices'])} devices, {len(c.get('wires',[]))} wires"} for c in (candidate or {}).get('cells',[])]}


def restore_native_metadata(candidate,base,warnings):
    """Reconcile stable exported identities; keep native views and specifications."""
    oldcells={c['id']:c for c in base['cells']};mapping={};matches={};used=set()
    for c in candidate['cells']:
        tag=next((properties(r[1]).get('studio_cell_id') for r in c['xschem']['records'] if r[0]=='K'),None)
        if tag not in oldcells:continue
        if tag in used:raise ValueError('Multiple schematics claim the same native cell identity.')
        used.add(tag);mapping[c['id']]=tag;matches[c['id']]=oldcells[tag];old={d['id']:d for d in oldcells[tag]['devices']};groups={}
        for d in c['devices']:groups.setdefault(d['xschem']['properties'].get('studio_id'),[]).append(d)
        for ident,items in groups.items():
            if ident not in old:continue
            exact=[d for d in items if d['name']==old[ident]['name']]
            chosen=items[0] if len(items)==1 else exact[0] if len(exact)==1 else None
            if chosen:mapping[chosen['id']]=ident
            if len(items)>1:warnings.append(c['name']+': copied components received new identities; the original named instance retains its native links.')
    def remap(value):
        if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
        if isinstance(value,list):return [remap(v) for v in value]
        return mapping.get(value,value) if isinstance(value,str) else value
    q=remap(candidate);merged=clone(base);updated=[]
    for before,c in zip(candidate['cells'],q['cells']):
        prior=matches.get(before['id'])
        if prior:
            row=clone(prior);old={d['id']:d for d in row['devices']};row.update({k:v for k,v in c.items() if k!='shapes'})
            for d in row['devices']:
                if d['id'] in old:
                    restored=clone(old[d['id']])
                    for key in ('model_ref','model_params','model_mode'):restored.pop(key,None)
                    restored.update(d);d.clear();d.update(restored)
            kept={d['id'] for d in row['devices']}
            row['layout_pins']=[pin for pin in row.get('layout_pins',[]) if pin['device_id'] in kept]
            for shape in row['shapes']:
                if shape.get('device_id') and shape['device_id'] not in kept:shape['device_id']=''
            updated.append(row)
        else:updated.append(c)
    updated.extend(clone(c) for c in base['cells'] if c['id'] not in {v['id'] for v in updated})
    old_import=base.get('xschem_exchange',{}).get('import_analysis')
    analysis=base['analysis'] if q['analysis']==old_import else q['analysis']
    merged.update(cells=updated,top=q['top'],analysis=clone(analysis),xschem_exchange=q['xschem_exchange'],revision=base['revision']+1,modified=now())
    if q.get('parameters',{})!=base.get('xschem_exchange',{}).get('import_parameters',{}):merged['parameters']=clone(q.get('parameters',{}))
    try:validate(merged)
    except ValueError as exc:raise ValueError('Native views need reconciliation before applying these external edits: '+str(exc)) from exc
    warnings.append('Restored native identities, physical views, specifications and saved setups from the matching exchange metadata.')
    return merged


def apply_review(record):
    if record.get('errors') or record.get('candidate') is None:raise ValueError('Resolve the import errors and review the project again.')
    if any(not Path(path).is_file() or file_digest(path)!=sha for path,sha in record['stamp'].items()):raise ValueError('A schematic, symbol or model file changed after review. Review again before importing.')
    return clone(record['candidate'])


def export_project(project,directory):
    """Export native edits to a new self-contained Xschem directory."""
    if project.get('xschem_exchange',{}).get('mode')=='compatible':
        from .xschem_compat import export_capture
        return export_capture(project,directory)
    p=clone(project);validate(p);dest=Path(directory)
    if dest.exists() and any(dest.iterdir()):raise ValueError('Choose an empty export directory to keep existing files intact.')
    by={c['id']:c for c in p['cells']};source=p['xschem_exchange'];files=source['source_files'];mapping={}
    for path,data in files.items():
        name=Path(path).name;tag=data['sha256'][:12]
        mapping[path]=('symbols/'+tag+'/'+name if data['kind']=='Symbol' else 'model_'+tag+'_'+name if data['kind'].startswith('Model') else 'source_'+tag+'_'+name)
    for c in p['cells']:
        if c.get('xschem'):mapping[c['xschem']['path']]=c['name']+'.sch'
        for d in c['devices']:
            if d['kind']=='X' and d.get('xschem'):mapping[d['xschem']['symbol_path']]=by[d['cell']]['name']+'.sym'
    def rewrite(text,parent):
        def replace(m):
            ref=m[2].strip('"\'');located=[d['path'] for d in source.get('resolved_dependencies',[]) if d['parent']==parent and d['reference']==ref];candidates=located+[str((Path(parent).parent/ref).resolve())]+[str((Path(root)/ref).resolve()) for root in source['libraries']]
            path=next((v for v in candidates if v in mapping),None)
            return m[1]+' '+quoted(mapping[path]) if path else m[0]
        text=re.sub(r'(?im)(\.include|\.inc|\.lib)\s+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)',replace,text)
        # The current native global definitions are emitted once in the top S
        # block. Remove the old copies in its original code records.
        if parent==by[p['top']].get('xschem',{}).get('path'):text=re.sub(r'(?im)^\s*\.param\s+[^\n]*','',text)
        return text
    output={mapping[path]:rewrite(data['text'],path) for path,data in files.items() if data['kind']!='Schematic'}
    report=[];models=[]
    label_symbol='symbols/studio_label.sym';port_symbol='symbols/studio_port.sym'
    for target,kind in ((label_symbol,'label'),(port_symbol,'iopin')):
        output[target]='v {xschem version=3.4.4 file_version=1.2}\nG {}\nK {type='+kind+' format="*.'+kind+' @lab" template="name=p lab=net"}\nV {}\nS {}\nE {}\nB 5 -2 -2 2 2 {name=p dir=inout}\nT {@lab} 8 -8 0 0 0.2 0.2 {}\n'
    from .design_ops import parameters,resolved_device
    from .catalog import binding_for,parameter_values
    for c in p['cells']:
        if 'xschem' not in c:raise ValueError('New hierarchy cells must be exported through a native handoff first; this exchange retains the imported hierarchy.')
        rebuild(c,p);ctx=parameters(c.get('parameters',{}),parameters(p.get('parameters',{})));meta=c['xschem'];original=meta['records'];components={row['record_index']:row for row in meta['components']};devices={d['id']:d for d in c['devices']};labels={l['id']:l for l in c['labels']};lines=[];done=set();done_labels=set();port_names=set();annotation_records={n.get('xschem_record'):n for n in c.get('annotations',[]) if 'xschem_record' in n}
        def emit_device(d,info=None):
            info=info or {};snap=info.get('snapshot',{});props=clone(info.get('original_properties',{}));resolved=resolved_device(d,ctx);s=clone(d.get('symbol') or __import__('icstudio.symbol_io',fromlist=['device_symbol']).device_symbol(d));target=mapping.get(info.get('symbol_path'), 'symbols/new_'+d['id']+'.sym');kind=d['kind'];binding=binding_for(p['pdk'],d)
            props['name']=d['name'];fmt='@name @pinlist @value';order=list(d['nets'])
            props['studio_id']=d['id']
            if kind=='X':
                child=by[d['cell']];s=clone(child.get('symbol') or s);target=child['name']+'.sym';props['schematic']=child['name']+'.sch';props.update({k:str(d.get('parameters',{}).get(k,v)) for k,v in child.get('parameters',{}).items()});fmt='@name @pinlist @symname'+''.join(' '+k+'=@'+k for k in child.get('parameters',{}));order=child['ports']
            elif binding and d.get('model_ref'):
                props['model']=binding['model'];vals=parameter_values(binding,resolved);props.update({k:str(vals[v]) for k,v in binding.get('emit_parameters',{}).items()});fmt='@name @pinlist @model'+''.join(' '+k+'=@'+k for k in binding.get('emit_parameters',{}));order=binding['pin_order']
            elif kind in ('NMOS','PMOS'):
                props.update(w=d['params']['w'],l=d['params']['l']);fmt='@name @pinlist @model w=@w l=@l'
                changed=not info or any(d['params'][k]!=snap.get('params',{}).get(k) for k in ('kp','vto','lambda'))
                if changed:
                    name='studio_model_'+d['id'];pa=resolved['params'];props['model']=name;models.append(f'.model {name} {kind} (level=1 vto={(-1 if kind=="PMOS" else 1)*scalar(pa["vto"]):.12g} kp={pa["kp"]} lambda={pa["lambda"]})')
                else:props['model']=info['properties'].get('model','')
            elif kind in ('V','I'):
                if d['source']!=snap.get('source') or d['value']!=snap.get('value'):props['value']=source_spec(resolved)
            else:props['value']=d['value']
            if info and kind!='X' and digest(s)==info.get('native_symbol_hash'):
                # Preserve the exact symbol (including ignored attributes and art).
                # Instances keep their explicit properties plus edited native fields.
                output[target]=rewrite(info['symbol_text'],info['symbol_path'])
            else:
                if info and kind!='X':
                    target='symbols/edited_'+d['id']+'/'+Path(info['symbol_path']).name
                    inverse={v:k for k,v in info['pin_mapping'].items()};s['pins']={inverse[k]:v for k,v in s['pins'].items()};s['pin_order']=[inverse[k] for k in s.get('pin_order',order)];s['pin_meta']={inverse[k]:v for k,v in s.get('pin_meta',{}).items()};order=[inverse[k] for k in order]
                s.setdefault('attributes',{}).update(type='subcircuit' if kind=='X' else 'primitive')
                if kind=='X':s['attributes']['schematic']=by[d['cell']]['name']+'.sch'
                output[target]=symbol_text(s,d['name'],fmt,order)
                if info:report.append(d['name']+': symbol exported from its current native geometry.')
            if kind=='X':
                rr=records(output[target]);attrs=properties(next(r[1] for r in rr if r[0]=='K'));child=by[d['cell']];attrs.update(type='subcircuit',schematic=child['name']+'.sch',format=fmt,template='name=X1 '+ ' '.join(k+'='+quoted(v) for k,v in child.get('parameters',{}).items()))
                for r in rr:
                    if r[0]=='K':r[1]=property_text(attrs)
                output[target]='\n'.join(record_text(r) for r in rr)+'\n'
            done.add(d['id']);return f'C {{{target}}} {d["x"]:g} {d["y"]:g} {d["rotation"]//90} {int(d.get("mirror",False))} {{{property_text(props)}}}'
        from .net_labels import point as label_point
        for index,r0 in enumerate(original):
            r=clone(r0)
            if r[0]=='N':continue
            if r[0]=='C':
                info=components.get(index)
                if not info:raise ValueError('Missing component preservation metadata.')
                if info.get('device_id'):
                    if info['device_id'] in devices:lines.append(emit_device(devices[info['device_id']],info))
                    continue
                if info.get('label_id'):
                    label=labels.get(info['label_id'])
                    if not label:continue
                    props=clone(info['original_properties']);props['lab']=label['name'];r[1]=mapping[info['symbol_path']];r[6]=property_text(props)
                    old_view=device('X','label',0,0,rotation=int(r[4])*90,mirror=bool(int(r[5])),symbol=info['symbol'],nets={pin:label['name'] for pin in info['symbol']['pins']});offset=next(iter(pin_positions(old_view).values()));point=label_point(label,c,p);r[2]=str(point[0]-offset[0]);r[3]=str(point[1]-offset[1]);done_labels.add(label['id'])
                    if info['kind'] in ('ipin','opin','iopin'):
                        if label['name'] not in c['ports']:raise ValueError('An imported interface label was renamed without updating its cell port.')
                        props['sim_pinnumber']=str(c['ports'].index(label['name'])+1);r[6]=property_text(props);port_names.add(label['name'])
                else:
                    r[1]=mapping[info['symbol_path']];props=properties(r[6]);
                    if 'value' in props:props['value']=rewrite(props['value'],meta['path'])
                    r[6]=property_text(props)
            elif r[0]=='T':
                note=annotation_records.get(index)
                if not note:continue
                r[1]=note['text'].replace('\\','\\\\').replace('{','\\{').replace('}','\\}');r[2]=str(note['x']);r[3]=str(note['y'])
            elif r[0]=='S':
                r[1]=rewrite(r[1],meta['path'])
                if c['id']==p['top'] and p.get('parameters'):r[1]+='\n.param '+' '.join(k+'='+str(v) for k,v in p['parameters'].items())
            elif r[0]=='K':
                attrs=properties(r[1]);attrs['studio_cell_id']=c['id'];r[1]=property_text(attrs)
            lines.append(record_text(r))
        for d in c['devices']:
            if d['id'] not in done:lines.append(emit_device(d))
        if c['id']==p['top'] and p.get('parameters') and not any(r[0]=='S' for r in original):lines.append(record_text(['S','.param '+' '.join(k+'='+str(v) for k,v in p['parameters'].items())]))
        for i,port in enumerate(c['ports']):
            if port not in port_names:lines.append(f'C {{{port_symbol}}} -120 {i*40} 0 0 {{name=studio_port{i} lab={quoted(port)} sim_pinnumber={i+1}}}')
        for note in c.get('annotations',[]):
            if 'xschem_record' not in note:lines.append(record_text(['T',note['text'].replace('{','\\{').replace('}','\\}'),str(note['x']),str(note['y']),'0','0','0.2','0.2','']))
        for label in labels.values():
            if label['id'] not in done_labels:
                x,y=label_point(label,c,p);lines.append(f'C {{{label_symbol}}} {x:g} {y:g} 0 0 {{name=studio_l{label["id"]} lab={quoted(label["name"])}}}')
        # Native hidden pin labels carry names across moves and disconnected
        # segments; export one real label per physical group, not per pin.
        physical=graph(c,p,labels=False);named_groups={physical[('label',l['id'])] for l in c['labels']};positions=cell_pins(c,p)
        for d in c['devices']:
            for pin,name in d['nets'].items():
                group=physical[(d['id'],pin)]
                if group not in named_groups:
                    x,y=positions[(d['id'],pin)];lines.append(f'C {{{label_symbol}}} {x:g} {y:g} 0 0 {{name=studio_n{d["id"]}_{pin} lab={quoted(name)}}}');named_groups.add(group)
        for wire in c['wires']:
            for a,b in zip(wire['points'],wire['points'][1:]):
                split=[a]+sorted([pt for pt in c['junctions'] if pt not in (a,b) and on_segment(pt,a,b)],key=lambda pt:math.dist(a,pt))+[b]
                for x,y in zip(split,split[1:]):lines.append(f'N {x[0]:g} {x[1]:g} {y[0]:g} {y[1]:g} {{}}')
        output[c['name']+'.sch']='\n'.join(lines)+'\n'
    if models:
        output['studio_models.spice']='\n'.join(models)+'\n'
        top=by[p['top']]['name']+'.sch';output[top]+='C {symbols/studio_code.sym} 0 -200 0 0 {name=studio_models only_toplevel=false value=".include studio_models.spice"}\n';output['symbols/studio_code.sym']='v {xschem version=3.4.4 file_version=1.2}\nK {type=netlist_commands format="@value" template="name=code value=\\"\\""}\n'
    output['README.txt']='Open '+by[p['top']]['name']+'.sch in Xschem. Add this directory to XSCHEM_LIBRARY_PATH. All resolved source assets are copied; paths are rewritten within this directory. Import this top schematic into Studio to continue editing. Original Tcl startup files are neither imported nor executed. Read exchange-report.json for preservation details.\n'
    output['exchange-report.json']=json.dumps({'version':1,'top':by[p['top']]['name']+'.sch','preserved':['hierarchy','ordered terminals','component placements','values and parameter overrides','wire connectivity','original symbol attributes and unchanged artwork','schematic graphics and code records','resolved model files'],'notes':report,'import_warnings':source['warnings']},indent=2)
    # Build every output before writing, so a validation error cannot leave a
    # partially populated destination masquerading as a successful export.
    for relative,text in output.items():atomic_write(dest/relative,text)
    save_project(p,dest/'studio-project.icproj')
    atomic_write(dest/'studio-exchange.json',json.dumps({'version':1,'project_sha256':file_digest(dest/'studio-project.icproj')},indent=2))
    return {'directory':str(dest),'top':by[p['top']]['name']+'.sch','files':len(output),'notes':report}
