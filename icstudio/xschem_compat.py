"""Editable Xschem capture, independent of the native numerical device subset."""
from pathlib import Path
import hashlib,json,re
from .model import clone,device,example,uid,NAME,NET,validate,digest,atomic_write,save_project,file_digest
from .xschem_project import Reader,properties,records,record_text,property_text,quoted,review_schematic,restore_native_metadata
from .interchange import pin_positions
from .wiring import rebuild,pins,on_segment,graph


class CaptureReader(Reader):
    def model_references(self, text, parent):
        for line in re.sub(r'\n\s*\+\s*', ' ', text).splitlines():
            m = re.match(r'^\s*\.(include|inc|lib)\s+("[^"]+"|\'[^\']+\'|\S+)(.*)$', line, re.I)
            if m and (m[1].lower() != 'lib' or m[3].strip()):
                self.model(m[2].strip('"\''), parent)

    def model(self,ref,parent):
        path=self.resolve(ref,parent,'Model / include')
        if path is None or path in self.files:return
        text=self.read(path,'Model / include')
        for line in re.sub(r'\n\s*\+\s*',' ',text).splitlines():
            m=re.match(r'^\s*\.(include|inc|lib)\s+("[^"]+"|\'[^\']+\'|\S+)(.*)$',line,re.I)
            if m and (m[1].lower()!='lib' or m[3].strip()):self.model(m[2].strip('"\''),path)

    def load(self,path,interface=None):
        path=Path(path)
        if path in self.stack:raise ValueError('Recursive schematic hierarchy: '+path.name)
        if path in self.cells:return self.cells[path]
        if len(self.stack)>12 or len(self.cells)>=100:raise ValueError('Schematic hierarchy exceeds the supported size.')
        raw=records(self.read(path,'Schematic'));name=re.sub('[^A-Za-z0-9_.$-]','_',path.stem)[:50]
        if not NAME.fullmatch(name):name='cell_'+name
        while name.casefold() in self.names:name+='_'+str(len(self.names))
        self.names.add(name.casefold());c={'id':uid(),'name':name,'ports':[],'parameters':{},'devices':[],'shapes':[],'wires':[],'labels':[],'junctions':[],'annotations':[],'xschem':{'path':str(path),'records':raw,'components':[]}}
        if interface:c['symbol']=clone(interface);c['ports']=list(interface['pin_order'])
        self.cells[path]=c;self.stack.append(path)
        for index,r in enumerate(raw):
            if r[0] == 'S' and len(r) > 1:
                self.model_references(r[1], path)
            if r[0]=='N':
                points=[list(map(float,r[1:3])),list(map(float,r[3:5]))]
                if points[0]!=points[1]:c['wires'].append({'id':uid(),'points':points})
            elif r[0]=='T' and r[1]:c['annotations'].append({'id':uid(),'text':r[1][:2000],'x':float(r[2]),'y':float(r[3]),'xschem_record':index})
            elif r[0]=='C':
                original=properties(r[6]);sympath=self.resolve(r[1],path,'Symbol');missing=sympath is None
                if missing:
                    s={'pins':{},'pin_order':[],'pin_meta':{},'attributes':{},'primitives':[{'kind':'rect','points':[[-35,-20],[35,20]]},{'kind':'text','points':[[-30,-10],[30,10]],'text':'Missing symbol','font_size':8}]};attrs={}
                else:
                    s,attrs=self.symbol(sympath)
                    self.model_references(attrs.get('spice_sym_def', ''), sympath)
                props={**properties(attrs.get('template','')),**original};kind=attrs.get('type','').lower();x,y=float(r[2]),float(r[3]);rot=int(r[4])*90;mirror=bool(int(r[5]))
                if not missing and props.get('spice_sym_def',attrs.get('spice_sym_def')):
                    from .xschem_semantics import ordered_symbol
                    self.model_references(props.get('spice_sym_def',attrs.get('spice_sym_def','')),sympath)
                    s=ordered_symbol(self,s,attrs,props,sympath)
                info={'record_index':index,'symbol_path':str(sympath) if sympath else '', 'reference':r[1],'properties':props,'original_properties':original,'symbol':clone(s),'kind':kind,'missing':missing}
                if kind in ('label','ipin','opin','iopin'):
                    lab=props.get('lab',attrs.get('lab',''));lab='0' if kind=='label' and lab.lower()=='gnd' else lab
                    from .xschem_vectors import net_name
                    lab=net_name(c,lab)
                    view=device('XS',props.get('name','label'),x,y,rotation=rot,mirror=mirror,symbol=s,nets={p:lab for p in s['pins']});point=list(next(iter(pin_positions(view).values())))
                    ident=uid();c['labels'].append({'id':ident,'name':lab,'kind':'ground' if lab=='0' else 'net_label','anchor':{'kind':'point','point':point},'offset':[0,0] if lab=='0' else [10,-12],'rotation':rot});info['label_id']=ident
                    if kind!='label' and not interface:c['ports'].append(lab)
                elif kind in ('launcher','logo','graph','probe','ngprobe') or props.get('spice_ignore',attrs.get('spice_ignore')) in ('true','open'):
                    pass  # Source record retained; imported actions are not executed.
                else:
                    name=props.get('name','component_'+str(index))
                    from .xschem_vectors import instance_names
                    expanded_names=instance_names(name)
                    name=expanded_names[0]
                    d=device('XS',name,x,y,rotation=rot,mirror=mirror,symbol=clone(s),nets={p:'open' for p in s['pin_order']},xschem=info)
                    if len(expanded_names)>1:d['_xschem_names']=expanded_names
                    d['symbol_context']=clone(props);d['symbol_context']['symname']=Path(r[1]).stem
                    if kind=='netlist_commands':
                        d['symbol']['primitives']=[{'kind':'rect','points':[[0,0],[180,45]]},{'kind':'text','points':[[8,8],[170,35]],'text':'@name: simulation program','font_size':9}];d['symbol']['pins']={};d['symbol']['pin_order']=[];d['symbol']['pin_meta']={};d['nets']={}
                        for line in props.get('value','').splitlines():
                            m=re.match(r'^\s*\.(include|inc|lib)\s+("[^"]+"|\'[^\']+\'|\S+)(.*)$',line,re.I)
                            if m and (m[1].lower()!='lib' or m[3].strip()):self.model(m[2].strip('"\''),path)
                    elif kind=='subcircuit' and not attrs.get('spice_sym_def') and props.get('spice_primitive',attrs.get('spice_primitive'))!='true':
                        childpath=self.resolve(props.get('schematic',attrs.get('schematic',Path(r[1]).stem+'.sch')),sympath or path,'Child schematic')
                        if childpath:
                            child=self.load(childpath,s);d.update(kind='X',cell=child['id'],parameters={})
                    info['device_id']=d['id'];info['snapshot']=clone(props);info['native_symbol_hash']=digest(d['symbol']);c['devices'].append(d)
                c['xschem']['components'].append(info)
        self.stack.pop();return c

    def capture(self):
        top=self.load(self.top);p=example('empty');p.update(name=self.top.stem,cells=list(self.cells.values()),top=top['id'])
        from .xschem_semantics import globals_in
        globals_=[]
        # Model-library .global statements remain in their selected .lib
        # sections; hoisting every corner's declarations would change scope.
        for c in p['cells']:
            for info in c['xschem']['components']:
                attrs=info['symbol'].get('attributes',{});props=info['properties']
                if info.get('label_id') and props.get('global',attrs.get('global')) in ('true','1'):
                    name=next(l['name'] for l in c['labels'] if l['id']==info['label_id'])
                    if name!='0':globals_.append(name)
                if info['kind']=='netlist_commands':globals_+=globals_in(props.get('value',''))
            for record in c['xschem']['records']:
                if record[0]=='S':globals_+=globals_in(record[1])
        if globals_:p['global_nets']=list(dict.fromkeys(globals_))
        for c in p['cells']:
            rebuild(c,p)
            from .xschem_vectors import expand
            expand(c,p)
            positions=pins(c,p)
            for label in c['labels']:
                point=label['anchor']['point'];hit=next((key for key,pt in positions.items() if pt==point),None)
                if hit:label['anchor']={'kind':'pin','id':hit[0],'pin':hit[1]}
                else:
                    wire=next((w for w in c['wires'] if any(on_segment(point,a,b) for a,b in zip(w['points'],w['points'][1:]))),None)
                    if wire:label['anchor']={'kind':'wire','id':wire['id'],'point':point}
            rebuild(c,p)
        p['xschem_exchange']={'version':2,'mode':'compatible','import_analysis':clone(p['analysis']),'source_top':str(self.top),'source_files':{str(path):data for path,data in self.files.items()},'libraries':[str(p) for p in self.roots],'resolved_dependencies':clone(self.deps),'unresolved':list(dict.fromkeys(self.errors))}
        validate(p);return p


def review_project(path,library_paths=(),technology=None,file_locations=None):
    from .native_exchange import MANIFEST
    if (Path(path).resolve().parent/MANIFEST).is_file():
        from .native_exchange import review_project as native_review
        return native_review(path,library_paths,file_locations)
    from .xschem_libraries import prepare
    roots,mapped,lock=prepare(path,library_paths,file_locations)
    # Keep the existing native conversion for supported teaching circuits.
    metadata=Path(path).resolve().parent/'capture-exchange.json'
    strict=review_schematic(path,roots,technology,mapped) if not lock['variant'] and not metadata.is_file() else None
    if strict and strict['candidate']:
        strict['candidate']['xschem_exchange']['library_lock']=lock;return strict
    reader=CaptureReader(path,roots,technology,mapped)
    try:
        extra={};base=None
        if metadata.is_file():
            from .model import load_project
            manifest=json.loads(metadata.read_text());native=metadata.parent/'studio-project.icproj'
            if manifest.get('version')!=2 or not native.is_file() or manifest.get('project_sha256')!=file_digest(native):raise ValueError('The matching native exchange metadata is missing or changed. Restore the matching pair or import a copy containing only the schematic and its assets.')
            base=load_project(native);extra={str(metadata):file_digest(metadata),str(native):file_digest(native)}
        p=reader.capture();p['xschem_exchange']['library_lock']=lock
        if base:
            p=restore_native_metadata(p,base,reader.warnings)
            # Exported model paths no longer contain an installation's variant.
            p['xschem_exchange']['library_lock']=clone(base['xschem_exchange'].get('library_lock',lock))
        return {'mode':'compatible','source':str(reader.top),'root':str(reader.top.parent),'candidate':p,'dependencies':reader.deps,'library_paths':[str(p) for p in reader.roots],'warnings':list(dict.fromkeys(reader.warnings))+reader.errors,'errors':[],'stamp':{**{str(path):data['sha256'] for path,data in reader.files.items()},**extra},'changes':[]}
    except (ValueError,OSError,KeyError,TypeError,IndexError) as exc:
        return {'mode':'compatible','source':str(reader.top),'candidate':None,'dependencies':reader.deps,'library_paths':[str(p) for p in reader.roots],'warnings':reader.warnings,'errors':[str(exc)],'stamp':{},'changes':[]}


def export_capture(project,directory):
    """Write editable capture and full source assets without converting models."""
    from .net_labels import point as label_point
    p=clone(project);validate(p);dest=Path(directory)
    if dest.exists() and any(dest.iterdir()):raise ValueError('Choose an empty export directory.')
    source=p['xschem_exchange'];files=source['source_files'];mapping={path:'assets/'+data['sha256'][:12]+'/'+Path(path).name for path,data in files.items()}
    for c in p['cells']:mapping[c['xschem']['path']]=c['name']+'.sch'
    def portable_properties(d):
        props=clone(d['xschem']['properties']);props['name']=d['name'];props['studio_id']=d['id']
        # Older upstream voltage-source symbols use @savecurrent inside Tcl;
        # newer Xschem releases consume that token before Tcl sees its boolean.
        # Emit the known source format explicitly so either version can netlist.
        attrs=d['xschem']['symbol'].get('attributes',{});fmt=attrs.get('format','');compact=re.sub(r'\s+','',fmt.replace('\\',''))
        if attrs.get('type')=='vsource' and compact=='tcleval([expr{@savecurrent?"@name@pinlist@value.saveI(?1@name)":"@name@pinlist@value"}])':
            props['format']='@name @pinlist @value'+('\n.save i(@name)' if props.get('savecurrent') in ('true','1') else '')
        return props
    def rewrite(text,parent):
        def one(m):
            ref=m[2].strip('"\'');matches=[d['path'] for d in source['resolved_dependencies'] if d['parent']==parent and d['reference']==ref]
            target=next((mapping[v] for v in matches if v in mapping),None)
            # All exported include paths are relative to the file containing them.
            if target:
                import posixpath
                target=posixpath.relpath(target,posixpath.dirname(mapping[parent]) or '.')
            return m[1]+' '+quoted(target) if target else m[0]
        return re.sub(r'(?im)(\.include|\.inc|\.lib)\s+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)',one,text)
    output={mapping[path]:rewrite(data['text'],path) for path,data in files.items() if data['kind']!='Schematic'}
    for c in p['cells']:
        rebuild(c,p);meta=c['xschem'];components={i['record_index']:i for i in meta['components']};devices={d['id']:d for d in c['devices']};labels={l['id']:l for l in c['labels']};notes={n.get('xschem_record'):n for n in c.get('annotations',[])};lines=[];done=set();done_labels=set()
        for index,original in enumerate(meta['records']):
            r=list(original)
            if r[0]=='N':continue
            if r[0]=='C':
                info=components.get(index)
                if not info:lines.append(record_text(r));continue
                if info.get('device_id'):
                    d=devices.get(info['device_id'])
                    if d is None:continue
                    props=portable_properties(d)
                    if 'value' in props:props['value']=rewrite(props['value'],meta['path'])
                    if d['kind']=='X':props['schematic']=mapping[next(cc['xschem']['path'] for cc in p['cells'] if cc['id']==d['cell'])]
                    r[2:6]=[str(d['x']),str(d['y']),str(d['rotation']//90),str(int(d.get('mirror',False)))];r[6]=property_text(props);done.add(d['id'])
                    if digest(d['symbol'])!=info['native_symbol_hash'] and info['kind']!='netlist_commands':
                        from .symbol_io import symbol_text
                        target='assets/edited_'+d['id']+'.sym';output[target]=symbol_text(d['symbol']);r[1]=target
                    else:r[1]=mapping.get(info['symbol_path'],info['reference'])
                elif info.get('label_id'):
                    label=labels.get(info['label_id'])
                    if label is None:continue
                    x,y=label_point(label,c,p);props=clone(info['properties']);props['lab']=label['name'];r[1]=mapping.get(info['symbol_path'],info['reference']);r[2:4]=[str(x),str(y)];r[6]=property_text(props);done_labels.add(label['id'])
                else:r[1]=mapping.get(info['symbol_path'],info['reference'])
            elif r[0]=='T':
                n=notes.get(index)
                if n:r[1]=n['text'];r[2:4]=[str(n['x']),str(n['y'])]
            elif r[0]=='S':r[1]=rewrite(r[1],meta['path'])
            elif r[0]=='K':r[1]=property_text({**properties(r[1]),'studio_cell_id':c['id']})
            lines.append(record_text(r))
        # Preserve the original import subset; duplicate/add ordinary Xschem
        # devices by emitting their complete saved properties and symbol.
        for d in c['devices']:
            if d['id'] in done:continue
            info=d.get('xschem')
            if not info:raise ValueError('Place or duplicate an Xschem library device in this project.')
            props=portable_properties(d)
            if 'value' in props:props['value']=rewrite(props['value'],meta['path'])
            lines.append(record_text(['C',mapping.get(info['symbol_path'],info['reference']),str(d['x']),str(d['y']),str(d['rotation']//90),str(int(d.get('mirror',False))),property_text(props)]))
        label_sym='assets/studio_label.sym';output[label_sym]='v {xschem version=3.4.4 file_version=1.2}\nG {}\nK {type=label format="*.alias @lab" template="name=p lab=net"}\nV {}\nS {}\nE {}\nB 5 -1 -1 1 1 {name=p dir=inout}\nT {@lab} 5 -8 0 0 0.2 0.2 {}\n'
        for label in labels.values():
            if label['id'] not in done_labels:
                x,y=label_point(label,c,p);lines.append(record_text(['C',label_sym,str(x),str(y),'0','0',property_text({'name':'label_'+label['id'],'lab':label['name']})]))
        for d in c['devices']:
            for pin,net in d.get('net_labels',{}).items():
                x,y=pin_positions(d)[pin];lines.append(record_text(['C',label_sym,str(x),str(y),'0','0',property_text({'name':'pin_'+d['id']+'_'+pin,'lab':net})]))
        for wire in c['wires']:
            for a,b in zip(wire['points'],wire['points'][1:]):lines.append(record_text(['N',str(a[0]),str(a[1]),str(b[0]),str(b[1]),'']))
        output[mapping[meta['path']]]='\n'.join(lines)+'\n'
    for rel,text in output.items():atomic_write(dest/rel,text)
    report={'version':2,'top':mapping[source['source_top']],'library_lock':source.get('library_lock',{}),'unresolved':source.get('unresolved',[]),'mode':'compatible','files':{rel:file_digest(dest/rel) for rel in output}}
    save_project(p,dest/'studio-project.icproj');report['project_sha256']=file_digest(dest/'studio-project.icproj');atomic_write(dest/'capture-exchange.json',json.dumps(report,indent=2));return report
