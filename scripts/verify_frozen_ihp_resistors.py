"""Parent-owned frozen IHP resistor GUI/managed-native physical subgate.

Sixty actual Qt-generated coupons and 165 controls on their written geometry.
Finite physical recipes only; no operating envelope or complete family claim.
"""
import argparse,ast,copy,hashlib,json,math,os,re,subprocess,sys,time,uuid
from pathlib import Path,PurePosixPath
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from threading import Event

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.verify_frozen_mim import require,sha,digest,load,relative,unlinked,confined,inventory,file_map,git_environment,git_blob,backend_binding,design_hash,content_hash,check_runtime

MODELS=('rsil','rppd','rhigh')
SIZES=((.5,.5),(.5,20),(20,.5),(2,7),(7,2))
CASES=tuple(f'{m}-g{g}-v{v}-r{r}' for m in MODELS for g in range(5) for v in (0,1) for r in (0,90))
FAULTS=('terminal-open','body-open','terminal-short','reference-width','reference-model')
STAGES=('preflight','layout_export','drc','lvs_extraction','lvs','integrity')
ASSETS='icstudio/assets/qualification/ihp-resistor-templates'
LEGACY='icstudio/assets/qualification/ihp-resistor-legacy'
PDK='icstudio/assets/pdks/ihp-sg13g2'
SCOPE='Frozen IHP Qt lifecycle for60 finite straight resistor layouts and165 actual-geometry/reference controls through the shipped managed backend; no electrical/operating-envelope/full-family/manufacturing qualification.'
EXTRACTION=dict(hierarchy=True,blackbox=False,merge='none',scale=False,capacitance_threshold='infinite',resistance_threshold='infinite',distributed_resistance=False)

def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def candidate(commit):
    """Authenticate checker, all Python workflow bytes and relevant assets to Git."""
    listing=subprocess.check_output(['git','ls-tree','-rz',commit,'--','icstudio','scripts/verify_frozen_ihp_resistors.py','scripts/verify_frozen_mim.py','.github/workflows/build-desktop.yml'],cwd=ROOT,env=git_environment())
    selected=[]
    for entry in listing.split(b'\0'):
        if not entry:continue
        meta,name=entry.split(b'\t');name=name.decode()
        if (name.startswith('icstudio/') and name.count('/')==1 and name.endswith('.py') and name!='icstudio/build_info.py') or name.startswith((ASSETS+'/',LEGACY+'/')) or name in (PDK+'/package.json','icstudio/assets/pdks/collection.json','scripts/verify_frozen_ihp_resistors.py','scripts/verify_frozen_mim.py','.github/workflows/build-desktop.yml'):
            require(meta.split()[1]==b'blob','Expected regular candidate input.');selected.append((name,meta.split()[2]))
    require(selected,'Missing candidate inputs.')
    raw=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,env=git_environment(),input=b'\n'.join(v for _,v in selected)+b'\n')
    values={};offset=0
    for name,oid in selected:
        end=raw.index(b'\n',offset);header=raw[offset:end].split();size=int(header[2]);require(header[:2]==[oid,b'blob'],'Candidate blob differs.')
        values[name]=raw[end+1:end+1+size];offset=end+size+2
    for name in ('scripts/verify_frozen_ihp_resistors.py','scripts/verify_frozen_mim.py'):
        require(name in values and hashlib.sha256(values[name]).hexdigest()==sha(ROOT/name),'External checker differs from selected candidate: '+name)
    modules=sorted(name for name in values if name.startswith('icstudio/') and name.count('/')==1 and name.endswith('.py'))
    require('icstudio/ihp_resistors.py' in modules and 'icstudio/ihp_resistor_desktop_probe.py' in modules,'Candidate lacks IHP recipe/probe.')
    return dict(files={name:hashlib.sha256(value).hexdigest() for name,value in values.items()},
        workflow_hash=hashlib.sha256(b''.join(Path(name).name.encode()+values[name] for name in modules)).hexdigest(),
        engine_hash=hashlib.sha256(values['icstudio/simulation.py']).hexdigest(),
        package_sha256=hashlib.sha256(values[PDK+'/package.json']).hexdigest(),
        collection_sha256=hashlib.sha256(values['icstudio/assets/pdks/collection.json']).hexdigest())

def package(root,expected):
    root=unlinked(root).resolve();data=load(root/'package.json')
    require(sha(root/'package.json')==expected and data.get('id')=='ihp-sg13g2','Physical IHP package differs.')
    file_map(root,data['files']);return data

def build_metadata(folder,commit,inputs):
    values={}
    for node in ast.parse((folder/'build_info.py').read_text()).body:
        require(isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name),'Unexpected build metadata.')
        name=node.targets[0].id;require(name not in values,'Duplicate build metadata.');values[name]=ast.literal_eval(node.value)
    require(values.get('BUILD_COMMIT')==commit and values.get('BUILD_DIRTY') is False and values.get('WORKFLOW_SOURCE_HASH')==inputs['workflow_hash'] and values.get('ENGINE_SOURCE_HASH')==inputs['engine_hash'],'Candidate engine/workflow metadata differs.')
    return values

def assets_binding(bundle,inputs):
    selected={name:expected for name,expected in inputs['files'].items() if name.startswith((ASSETS+'/',LEGACY+'/'))}
    require(selected and ASSETS+'/templates.json' in selected,'Missing pinned template/legacy inputs.')
    for name,expected in selected.items():require(sha(unlinked(bundle/name))==expected,'Bundled recipe asset differs: '+name)
    return selected

def header(report,executable,commit,nonce,inputs,bundle):
    require(report.get('schema')==1 and report.get('status')=='passed' and report.get('mode')=='lifecycle' and report.get('frozen') is True and report.get('native_execution') is False,'Producer must be a frozen GUI-only lifecycle report.')
    require(report.get('execution_id')==nonce and re.fullmatch('[0-9a-f]{32}',nonce),'Stale execution nonce.')
    build=report.get('build',{});require(build.get('commit')==commit and build.get('dirty') is False and build.get('frozen') is True,'GUI build identity differs.')
    require(Path(report['executable']).resolve()==Path(executable).resolve() and report['executable_sha256']==sha(executable),'Frozen executable differs.')
    require(Path(report['resource_root']).resolve()==bundle.resolve() and Path(report['template_path']).resolve()==(bundle/ASSETS/'templates.json').resolve(),'Frozen app used external resources.')
    require(all(report.get(name) is False for name in ('qualified','release_ready','full_family','installed_acceptance')) and not report.get('error') and not report.get('errors'),'Producer overclaims or reports errors.')
    require(report['package_manifest_sha256']==inputs['package_sha256'] and report['bundle_collection_sha256']==inputs['collection_sha256'] and report['template_sha256']==inputs['files'][ASSETS+'/templates.json'],'Producer package/template identity differs.')

def scalar(value):
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([munp]?)',str(value))
    require(match is not None,'Invalid literal resistor parameter.')
    result=float(match[1])*{'':1,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12}[match[2]]
    require(math.isfinite(result),'Nonfinite resistor parameter.');return result

def same_parameters(actual,expected):
    return set(actual)==set(expected) and all(math.isclose(actual[key],expected[key],rel_tol=1e-12,abs_tol=1e-18) for key in expected)

def circuit(text,top,model,w,l,*,opened=None,schematic=False,expected_params=None):
    rows=[v.split() for v in re.sub(r'\n\s*\+\s*',' ',text).splitlines() if v.strip() and not v.lstrip().startswith('*')]
    ports=['R2','B'] if opened=='short' else ['R1','R2','B']
    require(len(rows)==3 and rows[0]==['.subckt',top,*ports] and rows[-1] in (['.ends'],['.ends',top]),'Native/reference circuit interface differs.')
    row=rows[1];require(len(row)>=7 and re.fullmatch('[xX]\\S+',row[0]) and row[4]==model,'Resistor model/element coverage differs.')
    if opened=='R1':require(row[1] not in ('R1','R2','B') and row[2:4]==['R2','B'],'R1 was not independently opened.')
    elif opened=='B':require(set(row[1:3])=={'R1','R2'} and row[3] not in ('R1','R2','B'),'B was not independently opened.')
    elif opened=='short':require(row[1:4]==['R2','R2','B'],'Actual resistor is not shorted.')
    else:require(row[1:4]==['R1','R2','B'] if schematic else set(row[1:3])=={'R1','R2'} and row[3]=='B','Ordered resistor/body terminals differ.')
    pairs=[v.split('=',1) for v in row[5:]];require(all(len(v)==2 for v in pairs),'Malformed resistor parameters.')
    params={k:scalar(v) for k,v in pairs};require(len(params)==len(pairs) and set(params)<=({'w','l','m','b','mm_ok'} if schematic else {'w','l'}),'Unexpected resistor parameters.')
    require(math.isclose(params.get('w',-1),w*1e-6,rel_tol=1e-12,abs_tol=1e-18) and math.isclose(params.get('l',-1),l*1e-6,rel_tol=1e-12,abs_tol=1e-18),'Actual resistor dimensions differ.')
    if schematic:require(params.get('m',1)==1 and params.get('b',0)==0,'Unexpected physical multiplicity/bend.')
    if expected_params is not None:require(same_parameters(params,expected_params),'Reference parameters differ from actual saved schematic.')
    return row[1:4]

def stream(path,top):
    import klayout.db as db
    ly=db.Layout();ly.read(str(path));cell=ly.top_cell();require(ly.dbu==.001 and len(ly.top_cells())==1 and cell.name==top,'Actual stream units/top differ.')
    cell.flatten(True);regions={};labels=[]
    for index in ly.layer_indexes():
        info=ly.get_info(index);pair=(info.layer,info.datatype);reg=db.Region(cell.begin_shapes_rec(index)).merged()
        if not reg.is_empty():regions[pair]=db.Region([p.dup() for p in reg.each()])
        for shape in cell.shapes(index).each():
            if shape.is_text():
                text=shape.text;labels.append((pair,text.string,text.x,text.y,text.trans.angle))
    return regions,sorted(labels)

def same_stream(left,right,text_presentation=True):
    a,b=(left[1],right[1]) if text_presentation else ([v[:4] for v in left[1]],[v[:4] for v in right[1]])
    require(set(left[0])==set(right[0]) and a==b and all((left[0][k]^right[0][k]).is_empty() for k in left[0]),'Actual GUI/project/native masks or labels differ.')

def project_stream(project):
    import klayout.db as db
    require(len(project['cells'])==1,'Unexpected GUI hierarchy.');cell=project['cells'][0]
    layers={v['name']:(v['gds'],v['datatype']) for v in project['pdk']['layers']};regions={}
    for shape in cell['shapes']:
        require(shape['kind'] in ('rect','polygon'),'Unexpected GUI primitive.')
        poly=db.Polygon(db.Box(*shape['points'][0],*shape['points'][1])) if shape['kind']=='rect' else db.Polygon([db.Point(*v) for v in shape['points']])
        for hole in shape.get('holes',[]):poly.insert_hole([db.Point(*v) for v in hole])
        regions.setdefault(layers[shape['layer']],db.Region()).insert(poly)
    labels=sorted(((layers[v['layer']][0],2),v['name'],*v['point'],0) for v in cell['layout_ports'])
    # Exported labels carry the project annotation rotation when transformed.
    texts={v['text']:v for v in cell.get('layout_texts',[])}
    labels=[(*v[:4],int(texts.get(v[1],{}).get('rotation',0))//90) for v in labels]
    return {key:reg.merged() for key,reg in regions.items()},sorted(labels)

def oracle(template,row,generation):
    import klayout.db as db
    records=generation;require(len(records)==1 and records[0]['origin']==[0,0],'Probe must use the selected zero-origin footprint.')
    trans=db.Trans(row['rotation']//90,False,0,0);regions={}
    for shape in template['shapes']:
        poly=db.Polygon(db.Box(*shape['points'][0],*shape['points'][1])) if shape['kind']=='rect' else db.Polygon([db.Point(*v) for v in shape['points']])
        for hole in shape.get('holes',[]):poly.insert_hole([db.Point(*v) for v in hole])
        regions.setdefault(tuple(shape['layer']),db.Region()).insert(poly.transformed(trans))
    labels=[]
    for port in template['ports']:
        point=trans*db.Point(*port['point']);labels.append(((port['layer'][0],2),port['name'],point.x,point.y,row['rotation']//90))
    return {key:reg.merged() for key,reg in regions.items()},sorted(labels)

def lifecycle(root,report,lock,templates):
    require([v.get('case') for v in report['lifecycle']]==list(CASES),'Missing, duplicated or reordered GUI cases.')
    require(Path(report['execution_root']).resolve()==root.resolve(),'GUI execution root differs.')
    rows=[]
    for row in report['lifecycle']:
        model,g,via,rotation=row['case'].split('-');g=int(g[1:]);via=int(via[1:]);rotation=int(rotation[1:]);w,l=SIZES[g]
        require((row['model'],row['geometry_index'],row['width_um'],row['length_um'],row['terminal_vias'],row['rotation'])==(model,g,w,l,bool(via),rotation) and type(row['terminal_vias']) is bool,'GUI case metadata differs.')
        top=f'ihp_{model}_g{g}_v{via}_r{rotation}_{report["execution_id"][:12]}';require(row['top']==top and row['nets']==dict(p='R1',m='R2',body='B'),'Nonce or ordered p/m/body mapping differs.')
        require(row['top_port_assignment']=='application cell-port dialog' and row['undo_redo'] is True,'Actual Qt lifecycle action missing.')
        for key in ('project','reopened_project','reference','schematic','gds','oasis'):
            require(sha(confined(root,row[key]))==row[key+'_sha256'],'GUI output changed: '+key)
        project=load(confined(root,row['project']));reopened=load(confined(root,row['reopened_project']))
        require(content_hash(project)==content_hash(reopened) and design_hash(project)==row['design_hash'],'Save/reopen project content differs.')
        require(project['pdk']['package_lock']==row['package_lock'] and all(project['pdk']['package_lock'][k]==lock[k] for k in ('id','revision','files')),'Saved IHP lock differs.')
        registry=confined(root,project['pdk']['package_root']);require(digest(load(registry/'package.json'))==digest(lock),'Saved registry package differs semantically.');file_map(registry,lock['files'])
        cell=project['cells'][0];require(len(project['cells'])==1 and project['top']==cell['id']==row['cell_id'] and cell['name']==top and cell['ports']==['R1','R2','B'] and len(cell['devices'])==1,'Saved GUI device/top interface differs.')
        device=cell['devices'][0];symbol='sg13g2_pr/'+model+'.sym';require(device['id']==row['instance_id'] and device['kind']=='PDK' and device['model_ref']==row['model_ref']==dict(pdk='ihp-sg13g2',revision=lock['revision'],device=symbol) and device['nets']==row['nets'],'Saved device identity differs.')
        binding=project['pdk']['simulation']['catalog'][symbol];original=lock['technology']['simulation']['catalog'][symbol]
        require(all(binding[k]==original[k] for k in ('model','prefix','pin_order','emit_parameters','parameter_scale','parameters')),'Saved selected catalog binding changed.')
        values={key:scalar(value) for key,value in device['model_params'].items()};expected={key:scalar(item['default']) for key,item in original['parameters'].items()}
        expected.update(w=w*1e-6,l=l*1e-6,m=1)
        if 'b' in expected:expected['b']=0
        require(same_parameters(values,expected),'Actual saved schematic parameters differ from selected geometry/reference.')
        require(device.get('physical_terminal_vias',False) is bool(via) and cell['pdk_layouts']==row['generation'] and cell['layout_pins']==row['layout_pins'] and cell['layout_ports']==row['layout_ports'],'Saved access/footprint/port identity differs.')
        pins={v['pin']:v for v in cell['layout_pins']};ports={v['name']:v for v in cell['layout_ports']};require(len(cell['layout_pins'])==len(cell['layout_ports'])==3 and set(pins)=={'p','m','body'} and set(ports)=={'R1','R2','B'},'Missing or duplicated independent body/terminal pin.')
        for pin,name in (('p','R1'),('m','R2'),('body','B')):
            layer='Metal2.drawing' if via and pin!='body' else 'Metal1.drawing'
            require(pins[pin]['device_id']==device['id'] and pins[pin]['layer']==ports[name]['layer']==layer and pins[pin]['point']==ports[name]['point'],'Actual access/body pin assignment differs.')
        spec=cell['pdk_layouts'][0]['spec'];require(spec['model']==model and spec['terminal_vias'] is bool(via) and spec['dimensions_nm']==dict(w=round(w*1000),l=round(l*1000)) and spec['nets']==row['nets'] and spec['template_sha256']==report['template_sha256'] and spec['source_hashes']==report['source_hashes'] and spec['package_manifest_semantic_sha256']==digest(lock),'Recipe contract/source identity differs.')
        require(same_parameters(spec['values'],expected),'Stored recipe parameters differ from actual schematic.')
        circuit(confined(root,row['reference']).read_text(),top,model,w,l,schematic=True,expected_params={name:expected[key] for name,key in original['emit_parameters'].items()})
        exported=confined(root,row['schematic']).read_text();primitive=re.findall(r'(?mi)^X\S+.*$',exported);reference_primitive=re.findall(r'(?mi)^X\S+.*$',confined(root,row['reference']).read_text())
        require(primitive==reference_primitive and len(primitive)==1 and not re.search(r'(?im)^\s*[rcqmdjblv]\S+\s',exported),'GUI schematic export differs from literal reference.')
        target=stream(confined(root,row['gds']),top);same_stream(target,project_stream(project));same_stream(target,stream(confined(root,row['oasis']),top),text_presentation=False)
        key=f'{model}:{w:g}:{l:g}:{via}';same_stream(target,oracle(templates['templates'][key],row,row['generation']))
        rows.append((row,project,target))
    return rows

def eco_binding(project,eco,lock,templates):
    cell=project['cells'][0];require(len(project['cells'])==1 and len(cell['devices'])==1 and len(cell['pdk_layouts'])==1,'Unexpected ECO project coverage.')
    device=cell['devices'][0];record=cell['pdk_layouts'][0];spec=record['spec']
    require(spec['model']=='rsil' and spec['dimensions_nm']==dict(w=2000,l=7000) and spec['terminal_vias'] is False and record['orientation']==eco['orientation'],'Saved rotated ECO differs from declared recipe.')
    require(device['model_ref']==dict(pdk='ihp-sg13g2',revision=lock['revision'],device='sg13g2_pr/rsil.sym') and device['nets']==spec['nets']==dict(p='R1',m='R2',body='B') and device.get('physical_terminal_vias',False) is False,'Saved ECO binding/access/nets differ.')
    defaults=lock['technology']['simulation']['catalog']['sg13g2_pr/rsil.sym']['parameters'];expected={key:scalar(value['default']) for key,value in defaults.items()};expected.update(w=2e-6,l=7e-6,m=1)
    require(same_parameters({key:scalar(value) for key,value in device['model_params'].items()},expected) and same_parameters(spec['values'],expected),'Actual ECO schematic dimensions differ.')
    target=oracle(templates['templates']['rsil:2:7:0'],dict(rotation=90),[record]);physical=copy.deepcopy(project);physical['cells'][0]['layout_ports']=[]
    actual=project_stream(physical);require(set(actual[0])==set(target[0]) and all((actual[0][key]^target[0][key]).is_empty() for key in actual[0]),'Actual ECO masks differ from new rotated template.')
    pins=cell['layout_pins'];require(len(pins)==3 and {v['pin'] for v in pins}=={'p','m','body'},'ECO terminal coverage differs.')
    expected_pins={v[1]:(v[0][0],[v[2],v[3]]) for v in target[1]}
    for pin in pins:
        name={'p':'R1','m':'R2','body':'B'}[pin['pin']];require(pin['device_id']==device['id'] and pin['layer']=='Metal1.drawing' and pin['point']==expected_pins[name][1],'Actual ECO pin anchor differs.')

def producer_controls(root,report,bundle,inputs):
    legacy=report['legacy'];require(len(legacy)==2,'Missing legacy recovery coverage.')
    names=[]
    for row in legacy:
        source=Path(row['source']);name=source.name;names.append(name)
        require(source.resolve()==(bundle/LEGACY/name).resolve() and sha(source)==row['source_sha256']==inputs['files'][LEGACY+'/'+name],'Legacy source is not a pinned pre-feature input.')
        saved=confined(root,row['saved']);require(sha(saved)==row['saved_sha256'],'Legacy saved artifact changed.')
        before=load(source);after=load(saved)
        require(all('physical_terminal_vias' not in device for project in (before,after) for cell in project['cells'] for device in cell['devices']),'Legacy recovery added a resistor access option.')
        def protected(project):
            cells=[]
            for cell in project['cells']:
                devices=copy.deepcopy(cell['devices'])
                for device in devices:device.pop('net_labels',None)
                cells.append({key:cell.get(key,{} if key=='parameters' else []) for key in ('id','name','ports','parameters','shapes','layout_pins','layout_ports','layout_texts','pdk_layouts')}|dict(devices=devices))
            return dict(id=project['id'],top=project['top'],parameters=project.get('parameters',{}),cells=cells)
        require(protected(before)==protected(after),'Legacy recovery changed physical/model/parameter semantics.')
    require(set(names)=={'mos.icproj','resistor.icproj'},'Legacy fixture identities differ.')
    controls=report['controls'];require([v['kind'] for v in controls]==['unsupported-preset','rotated-m2-to-m1-eco'],'GUI controls missing or reordered.')
    blocked=controls[0];path=confined(root,blocked['project']);require(sha(path)==blocked['project_sha256'] and blocked['before_hash']==blocked['after_hash'] and blocked['no_footprint'] is True,'Blocked preset changed the original design.')
    project=load(path);cell=next(c for c in project['cells'] if c['id']==blocked['cell_id']);require(digest(project)==blocked['before_hash']==blocked['after_hash'] and not cell.get('pdk_layouts') and not cell['shapes'] and len(cell['devices'])==1 and any('W/L' in value for value in blocked['error']),'Unsupported preset did not preserve an ungenerated device.')
    device=cell['devices'][0];require(device['model_ref']['device']=='sg13g2_pr/rsil.sym' and scalar(device['model_params']['w'])==1e-6 and scalar(device['model_params']['l'])==.5e-6 and scalar(device['model_params']['m'])==1,'Blocked preset is not the intended unsupported rsil geometry.')
    eco=controls[1];path=confined(root,eco['saved']);require(sha(path)==eco['saved_sha256'] and eco['orientation']==dict(rotation=90,mirror=False) and eco['stale_detected'] is True and eco['option_stale_detected'] is True and eco['terminal_vias'] is False,'Missing access/rotation stale control.')
    eco_binding(load(path),eco,load(bundle/PDK/'package.json'),load(bundle/ASSETS/'templates.json'))

def source_audit(root,resources):
    """Explicit read-only development audit; cannot enter installed verify()."""
    root=unlinked(root).resolve();resources=unlinked(resources).resolve();report=load(root/'report.json')
    require(report.get('frozen') is False and report.get('status')=='passed' and report.get('native_execution') is False and all(report.get(k) is False for k in ('qualified','installed_acceptance','release_ready','full_family')),'Source lifecycle report is incomplete or overclaims.')
    require(load(root/'files.json')==inventory(root,('report.json','files.json')) and sha(root/'files.json')==report['files_sha256'],'Source final post-exit inventory differs.')
    lock=package(resources/PDK,sha(resources/PDK/'package.json'));templates=load(resources/ASSETS/'templates.json')
    require(report['template_sha256']==sha(resources/ASSETS/'templates.json') and report['package_manifest_semantic_sha256']==digest(lock),'Reviewed source assets differ.')
    rows=lifecycle(root,report,lock,templates)
    files={str(path.relative_to(resources)).replace('\\','/'):sha(path) for path in (resources/LEGACY).iterdir() if path.is_file()};producer_controls(root,report,resources,dict(files=files))
    return dict(status='PASS',gate='ihp-resistor-source-gui-readback',qualified=False,release_ready=False,full_family=False,installed_acceptance=False,native_execution=False,gui_layouts=len(rows),report_sha256=sha(root/'report.json'),files_sha256=sha(root/'files.json'))

def mutation(project,fault):
    """Edit only the actual GUI project's selected cut/conductor masks."""
    import klayout.db as db
    changed=copy.deepcopy(project);cell=changed['cells'][0];layers={v['name']:(v['gds'],v['datatype']) for v in changed['pdk']['layers']};source=project_stream(project)
    ports={v['name']:v for v in cell['layout_ports']};point=ports['B' if fault=='body-open' else 'R1']['point']
    components=[v for v in source[0][8,0].each() if v.inside(db.Point(*point))];require(len(components)==1,'Control port must select one conductor.');selected=db.Region(components[0])
    if fault in ('terminal-open','body-open','missing-via'):
        pair=(19,0) if fault=='missing-via' else (6,0);removed=[]
        for shape in cell['shapes']:
            if layers[shape['layer']]!=pair:continue
            poly=db.Polygon(db.Box(*shape['points'][0],*shape['points'][1])) if shape['kind']=='rect' else db.Polygon([db.Point(*v) for v in shape['points']])
            if not (db.Region(poly)&selected).is_empty():removed.append(shape)
        require(removed,'Control removed no physical cut.');cell['shapes']=[v for v in cell['shapes'] if v not in removed]
    elif fault=='terminal-short':
        def rect(layer,x,y,w,h):return dict(id=uuid.uuid4().hex[:16],kind='rect',layer=layer,points=[[x,y],[x+w,y+h]],net='')
        a,b=[ports[name]['point'] for name in ('R1','R2')];cell['shapes'] += [rect('Metal1.drawing',min(a[0],b[0])-200,a[1]-200,abs(a[0]-b[0])+400,400),rect('Metal1.drawing',b[0]-200,min(a[1],b[1])-200,400,abs(a[1]-b[1])+400)]
    else:require(fault in ('reference-width','reference-model'),'Unknown physical control.')
    require(changed['cells'][0]['layout_ports']==project['cells'][0]['layout_ports'] and changed['cells'][0]['layout_pins']==project['cells'][0]['layout_pins'] and changed['cells'][0].get('layout_texts',[])==project['cells'][0].get('layout_texts',[]),'Fault changed terminal annotations.')
    return changed

def runtime_files(runtime,records):
    root=Path(runtime['root']);result={}
    required=('opt/icstudio/bin/magic','opt/icstudio/bin/netgen','opt/icstudio/physical/installed/lib/magic/tcl/magicdnull','opt/icstudio/physical/installed/lib/magic/tcl/tclmagic.so','opt/icstudio/physical/installed/lib/netgen/tcl/tclnetgen.so','usr/bin/tclsh8.6')
    require(all(name in records for name in required),'Runtime lacks locked physical ELF/interpreter inputs.')
    for name,expected in records.items():
        path=root/relative(name);require(path.is_file() and sha(path)==expected,'Runtime file changed: '+name);result[name]=expected
    for name in required[2:]:require((root/name).read_bytes()[:4]==b'\x7fELF','Runtime physical engine/interpreter is not the expected ELF input.')
    for name in ('init','etc/wsl.conf'):
        if (root/name).is_file():result[name]=sha(root/name)
    return result

def runtime_uid(runtime,env):
    code='import os; print(os.getuid())'
    command=['wsl.exe','--distribution',runtime['distro'],'--exec','/opt/icstudio/bin/python3','-c',code] if runtime['kind']=='wsl' else [str(Path(runtime['root'])/'opt/icstudio/bin/python3'),'-c',code]
    result=subprocess.run(command,env=env,capture_output=True,text=True,check=True,timeout=30);value=result.stdout.strip();require(re.fullmatch('[0-9]+',value) is not None,'Native UID query did not return one numeric identity.')
    return dict(uid=int(value),command=command,stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),privilege_claim=False)

def native_tool_paths(runtime):
    require(runtime['kind'] in ('linux','wsl'),'Unknown managed native platform.')
    root=PurePosixPath(runtime['root']) if runtime['kind']=='linux' else PurePosixPath('/')
    require(root.is_absolute(),'Native runtime root must be absolute.')
    return {name:str(root/'opt/icstudio/bin'/name) for name in ('magic','netgen','ngspice','klayout')}

def native_result(folder,item,expected_stream,physical,runtime,records,fault=None):
    report=load(folder/'physical-flow/report.json');stages={v['name']:v for v in report['stages']}
    require(tuple(v['name'] for v in report['stages'])==STAGES and report['drc_engine']==report['lvs_extractor']=='magic' and report['magic_drc_style']=='drc(full)','Native stage/engine contract differs.')
    for name in ('drc','lvs-extraction'):
        log=(folder/f'physical-flow/{name}/console.log').read_text();require(log.count('STUDIO_MAGIC_COMPLETE')==1 and not re.search('STUDIO_MAGIC_ERROR|invalid command|contained errors|Malformed line',log,re.I),'Native execution failed to complete.')
    log=(folder/'physical-flow/drc/console.log').read_text();counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)
    require(len(counts)==1 and int(counts[0])==report['drc_count'] and 'STUDIO_DRC_STYLE drc(full)' in log,'Native DRC raw count/style differs.')
    same_stream(stream(folder/'physical-flow/original.gds',item['top']),expected_stream);same_stream(stream(folder/'physical-flow/layout.gds',item['top']),expected_stream)
    actual=load(folder/'physical-backend-input.json');require(load(folder/'physical-flow/input.icproj')==actual['project'],'Native input project differs.')
    native_paths=native_tool_paths(runtime)
    tools={name:dict(path=native_paths[name],sha256=records['opt/icstudio/bin/'+name]) for name in ('magic','netgen')}
    native_pdk=PurePosixPath(actual['project']['pdk']['package_root']);require(native_pdk.is_absolute(),'Native package root must be absolute.')
    assets={str(native_pdk/name):value for name,value in physical['files'].items() if name.startswith(('libs.tech/magic/','libs.tech/netgen/'))}
    # Technology/setup aliases are included alongside the complete locked folders.
    assets[str(native_pdk/'libs.tech/magic/icstudio-ihp-sg13g2.tech')]=physical['files']['libs.tech/magic/icstudio-ihp-sg13g2.tech']
    require(stages['preflight']['evidence']['assets']==assets and stages['preflight']['evidence']['tools']==tools,'Native rules or tools differ from shipped locked inputs.')
    original_reference=(folder/'physical-flow/schematic.spice').read_text();proofs=[]
    def physical_reference(match):
        line=match[0];tokens=line.split();require(len(tokens)>=5 and tokens[4] in MODELS,'Unknown reference device projection.')
        values=re.findall(r'(?i)\smm_ok\s*=\s*(\S+)',line)
        if not values:return line
        require(len(values)==1 and re.fullmatch(r'(?:0(?:\.0*)?|1(?:\.0*)?)',values[0]),'Unknown statistical selector cannot be projected.')
        model=tokens[4];symbol=physical['technology']['simulation']['catalog']['sg13g2_pr/'+model+'.sym']['source']
        proofs.append(dict(instance=tokens[0],parameter='mm_ok',reason='Statistical selector omitted by the locked upstream resistor LVS format',proof=dict(source=symbol,sha256=physical['files'][symbol])))
        return re.sub(r'(?i)[ \t]+mm_ok[ \t]*=[ \t]*(?:0(?:\.0*)?|1(?:\.0*)?)(?=\s|$)','',line)
    comparison=re.sub(r'(?im)^[ \t]*x\S+[^\n]*',physical_reference,original_reference)
    require((folder/'physical-flow/schematic-lvs.spice').read_text()==comparison and report['reference_defaults']==proofs and stages['preflight']['evidence']['model_defaults']==proofs,'Native physical reference projection changed more than source-backed statistical selector.')
    extracted=(folder/'physical-flow/lvs-extraction/extracted.spice').read_text();opened='short' if fault=='terminal-short' else 'R1' if fault in ('terminal-open','missing-via') else 'B' if fault=='body-open' else None
    circuit(extracted,item['top'],item['model'],item['width_um'],item['length_um'],opened=opened)
    if fault=='terminal-short':
        require(report['status']=='failed' and stages['lvs_extraction']['status']=='failed' and stages['lvs']['status']=='not_run' and 'electrically shorted' in (folder/'physical-flow/lvs-extraction/console.log').read_text(),'Missing actual shorted-interface witness.')
    else:
        require(stages['lvs_extraction']['status']=='passed' and stages['lvs_extraction']['evidence']['settings']==EXTRACTION,'Native extraction settings differ.')
        text=(folder/'physical-flow/lvs/lvs.log').read_text()
        if fault:
            require(report['status']=='failed' and stages['lvs']['status']=='failed','Native fault was not rejected.')
            if fault=='reference-width':require('Property errors were found.' in text and ' w circuit1:' in text,'Missing native width-property witness.')
            else:require('Final result: Circuits match uniquely.' not in text and any(v in text.lower() for v in ('do not match','failed','mismatch')),'Missing native connectivity/model witness.')
        else:require(report['status']=='passed' and all(v['status']=='passed' for v in stages.values()) and counts==['0'] and 'Final result: Circuits match uniquely.' in text and 'Property errors were found.' not in text,'Native positive failed full DRC/strict LVS.')
        if fault=='missing-via':require(counts==['0'],'Missing-via control must be DRC clean and fail electrically.')
        file_map(folder/'physical-flow',stages['integrity']['evidence']['files'])
    received=load(folder/'physical-artifacts.json');file_map(folder,received)
    actual_inventory={'physical-flow/'+name:expected for name,expected in inventory(folder/'physical-flow').items()};actual_inventory['physical-backend-result.json']=sha(folder/'physical-backend-result.json')
    require(received==actual_inventory,'Native transfer artifact inventory incomplete.')
    return report

def prepare_job(executable,project,row,folder,runtime,inputs,physical,fault=None):
    folder.mkdir(parents=True,exist_ok=False);job_project=copy.deepcopy(project)
    reference=Path(row['reference']).read_text()
    if fault=='reference-width':
        reference=re.sub(r'(?i)\bw=\S+',f'w={row["width_um"]*1.2:g}u',reference)
    elif fault=='reference-model':reference=re.sub(r'\b'+re.escape(row['model'])+r'\b',MODELS[(MODELS.index(row['model'])+1)%3],reference)
    if fault and not fault.startswith('reference-'):job_project=mutation(job_project,fault)
    job_project['pdk']['package_root']=str(physical['root'])
    job_project['pdk']['package_lock']={k:physical['package'][k] for k in ('id','revision','files')}
    ref=dict(text=reference,top=row['top'],ports=['R1','R2','B'],sha256=hashlib.sha256(reference.encode()).hexdigest())
    job=dict(project=job_project,cell=job_project['top'],engine='builtin',environment=dict(workflow_hash=inputs['workflow_hash'],engine='builtin'),settings=dict(type='silicon',verification_mode='drc_lvs',drc_engine='magic',lvs_extractor='magic',physical_toolchain='included',physical_runtime=runtime,tools={},reference=ref))
    write(folder/'input.json',job)
    command=[str(executable),'--worker',str(folder/'input.json'),str(folder/'result.json')];tick=time.monotonic();attempt=dict(command=command,started_unix=time.time(),executable_sha256=sha(executable),input_sha256=sha(folder/'input.json'),status='RUNNING')
    write(folder/'invocation.json',attempt)
    return job,job_project,ref,command,attempt,tick


def signal_cancel(folder):
    try:(folder/'digital-cancel').write_text('cancel\n')
    except OSError as error:return str(error)
    return None


def native_shutdown(folder,runtime):
    """Read back supervisor exit after cancellation; never claim unknown cleanup."""
    metadata=folder/'physical-backend.json'
    if not metadata.is_file():return dict(status='not-recorded')
    receipt=load(metadata);require(runtime is not None and receipt.get('runtime')==runtime,'Cancellation runtime receipt differs.')
    native=PurePosixPath(receipt['native_directory'])
    if runtime['kind']=='wsl':
        require(native.parent==PurePosixPath('/var/tmp/icstudio-physical') and re.fullmatch('[0-9a-f]{32}',native.name),'Cancellation native directory differs.')
        work=Path(runtime['root'])/native.relative_to('/')
    else:
        require(runtime['kind']=='linux' and native.is_absolute() and native.parent in (PurePosixPath('/tmp'),PurePosixPath('/var/tmp')) and native.name.startswith('icstudio-physical-'),'Cancellation native directory differs.')
        work=Path(native)
    proof=work/'supervisor-exit.json';deadline=time.monotonic()+5
    while work.exists() and not proof.is_file() and time.monotonic()<deadline:time.sleep(.1)
    if proof.is_file():
        data=load(unlinked(proof));require(set(data)=={'returncode'} and type(data['returncode']) is int,'Cancellation supervisor receipt differs.')
        return dict(status='supervisor-exited',returncode=data['returncode'],receipt_sha256=sha(proof))
    return dict(status='removed' if not work.exists() else 'unconfirmed')


def execute_job(folder,command,attempt,tick,env,deadline=None,stopped=None,runtime=None):
    """Only process I/O runs off-thread; KLayout objects stay on the parent."""
    process=None
    with (folder/'worker.log').open('wb') as log:
        try:
            require(stopped is None or not stopped.is_set(),'Parent native execution cancelled.')
            remaining=300 if deadline is None else min(300,deadline-time.monotonic())
            require(remaining>0,'Parent physical deadline exceeded.')
            process=subprocess.Popen(command,env=env,cwd=folder,stdout=log,stderr=subprocess.STDOUT)
            expires=time.monotonic()+remaining
            while process.poll() is None:
                require(stopped is None or not stopped.is_set(),'Parent native execution cancelled.')
                left=expires-time.monotonic()
                if left<=0:raise subprocess.TimeoutExpired(command,remaining)
                try:process.wait(timeout=min(.1,left))
                except subprocess.TimeoutExpired:pass
            if process.returncode:raise subprocess.CalledProcessError(process.returncode,command)
            attempt.update(status='complete',returncode=process.returncode,seconds=time.monotonic()-tick)
        except BaseException as error:
            attempt['cancellation_error']=signal_cancel(folder)
            if process is not None and process.poll() is None:
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                # Staging may have cleared an early marker before termination.
                attempt['cancellation_error']=signal_cancel(folder) or attempt['cancellation_error']
            try:attempt['native_shutdown']=native_shutdown(folder,runtime)
            except Exception as cleanup_error:attempt['native_shutdown']=dict(status='unconfirmed',error=str(cleanup_error))
            attempt.update(status='failed',error=str(error),returncode=None if process is None else process.returncode,seconds=time.monotonic()-tick)
            raise
        finally:
            log.flush();attempt['log_sha256']=sha(folder/'worker.log');write(folder/'invocation.json',attempt)


def audit_job(folder,row,job,job_project,ref,runtime,physical,records,fault=None):
    require(load(folder/'input.json')==job,'Frozen worker changed captured job input.')
    result=load(folder/'result.json');execution=result['silicon_report']['execution'];require(execution['runtime']==runtime and execution['native_input_sha256']==sha(folder/'physical-backend-input.json'),'Managed runtime/input receipt differs.')
    backend_input=load(folder/'physical-backend-input.json');expected=copy.deepcopy(job);expected['project']['pdk']['package_root']=execution['native_directory']+'/pdk';expected.pop('environment')
    expected['settings'].pop('physical_runtime');expected['settings']['tools']=native_tool_paths(runtime)
    require(backend_input==expected and result['settings']==job['settings'],'Managed dispatch changed captured project/settings/reference/environment translation.')
    require(execution['received_files']==load(folder/'physical-artifacts.json') and load(folder/'physical-backend-result.json')['silicon_report']==load(folder/'physical-flow/report.json'),'Managed receipt/report differs.')
    report=native_result(folder,row,project_stream(job_project),physical['package'],runtime,records,fault)
    require(report['reference']=={k:v for k,v in ref.items() if k!='text'} and (folder/'physical-flow/schematic.spice').read_text()==ref['text'],'Native schematic reference substituted.')
    return dict(case=row['case'],fault=fault,input_sha256=sha(folder/'input.json'),result_sha256=sha(folder/'result.json'),native_report_sha256=sha(folder/'physical-flow/report.json'),execution=execution)

def run_job(executable,project,row,folder,env,runtime,inputs,physical,records,fault=None):
    job,job_project,ref,command,attempt,tick=prepare_job(executable,project,row,folder,runtime,inputs,physical,fault)
    execute_job(folder,command,attempt,tick,env,runtime=runtime)
    return audit_job(folder,row,job,job_project,ref,runtime,physical,records,fault)


def native_jobs(rows,out):
    """Keep the finite original case/control order independently of completion."""
    for row,project,_ in rows:
        yield row,project,out/'native'/row['case']/'positive',None
        if row['rotation']==0:
            for fault in FAULTS+(('missing-via',) if row['terminal_vias'] else ()):
                yield row,project,out/'native'/row['case']/fault,fault


def run_jobs(executable,rows,out,env,runtime,inputs,physical,records,nonce,deadline):
    """Overlap two fresh workers after serial setup, preserving every audit.

    Geometry preparation and independent checks remain on the parent thread.
    Each worker owns a separate evidence directory and native UUID directory.
    Never queue the matrix: stop new launches on failure/deadline, cancel active
    work, then join/reap every worker before the final evidence inventory.
    """
    selected=iter(enumerate(native_jobs(rows,out)));pending={};finished={};stopped=Event()
    pool=ThreadPoolExecutor(max_workers=2)
    try:
        exhausted=False
        while pending or not exhausted:
            while len(pending)<2 and not exhausted:
                require(time.monotonic()<deadline,'Parent physical deadline exceeded.')
                item=next(selected,None)
                if item is None:exhausted=True;break
                index,(row,project,folder,fault)=item
                prepared=prepare_job(executable,project,row,folder,runtime,inputs,physical,fault)
                job,job_project,ref,command,attempt,tick=prepared
                future=pool.submit(execute_job,folder,command,attempt,tick,env,deadline,stopped,runtime)
                pending[future]=(index,row,folder,fault,job,job_project,ref)
            if not pending:break
            done,_=wait(pending,timeout=max(0,deadline-time.monotonic()),return_when=FIRST_COMPLETED)
            require(done and time.monotonic()<deadline,'Parent physical deadline exceeded.')
            for future in sorted(done,key=lambda f:pending[f][0]):
                index,row,folder,fault,job,job_project,ref=pending.pop(future);future.result()
                finished[index]=audit_job(folder,row,job,job_project,ref,runtime,physical,records,fault)
                require(time.monotonic()<deadline,'Parent physical deadline exceeded.')
            write(out/'native-progress.json',dict(execution_id=nonce,jobs=[finished[k] for k in sorted(finished)]))
        return [finished[k] for k in sorted(finished)]
    finally:
        stopped.set()
        for future,(_,_,folder,*_) in pending.items():
            future.cancel()
            if not future.done():signal_cancel(folder)
        pool.shutdown(wait=True,cancel_futures=True)


def verify(executable,out,commit,timeout=3600):
    executable=unlinked(executable).resolve();out=unlinked(out).resolve();require(re.fullmatch('[0-9a-f]{40}',commit) and math.isfinite(timeout) and timeout>0,'Exact candidate and finite deadline required.')
    require(not out.is_relative_to(executable.parent) and not executable.is_relative_to(out),'Evidence output cannot overlap installed deliverable.')
    require(not out.exists(),'Use a fresh parent output directory.');out.mkdir(parents=True);nonce=uuid.uuid4().hex;started=time.monotonic()
    try:
        inputs=candidate(commit);bundle=executable.parent/'_internal';lock=package(bundle/PDK,inputs['package_sha256']);assets_binding(bundle,inputs)
        payload=bundle/'icstudio/assets/runtime/digital';payload_hash=sha(payload/'manifest.json');meta=load(payload/'manifest.json')
        require(meta['schema']==1 and meta['archive']=='runtime.tar.gz' and sha(payload/'runtime.tar.gz')==meta['sha256'],'Frozen payload archive changed.')
        backend=backend_binding(payload/'backend/icstudio',commit);build_metadata(payload/'backend/icstudio',commit,inputs)
        for name in inputs['files']:
            if name.startswith(ASSETS+'/'):require(sha(payload/'backend'/name)==inputs['files'][name],'Shipped native backend omitted recipe assets.')
        env=git_environment()
        for key in list(env):
            if key.upper() in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','ICSTUDIO_DIGITAL_PAYLOAD','ICSTUDIO_DIGITAL_NATIVE','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):env.pop(key)
        env['QT_QPA_PLATFORM']='offscreen'
        if not env.get('ICSTUDIO_DIGITAL_STATE'):
            base=Path(env['LOCALAPPDATA']) if os.name=='nt' else Path(env.get('XDG_DATA_HOME',str(Path.home()/'.local/share')));env['ICSTUDIO_DIGITAL_STATE']=str(base/'ICDesignStudio/digital')
        exe_hash=sha(executable);command=[str(executable),'--ihp-resistor-acceptance','--managed','--execution-id',nonce,'--out',str(out/'probe')]
        write(out/'invocation.json',dict(command=command,expected_commit=commit,execution_id=nonce,executable_sha256=exe_hash,expected_inputs=inputs,payload_manifest_sha256=payload_hash))
        launch=dict(command=command,expected_commit=commit,execution_id=nonce,executable_sha256=exe_hash,expected_inputs=inputs,payload_manifest_sha256=payload_hash,status='RUNNING',started_unix=time.time());write(out/'invocation.json',launch)
        try:
            with (out/'launcher.log').open('wb') as log:completed=subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,check=True)
            launch.update(status='complete',returncode=completed.returncode,seconds=time.monotonic()-started,log_sha256=sha(out/'launcher.log'));write(out/'invocation.json',launch)
        except BaseException as error:
            launch.update(status='failed',returncode=getattr(error,'returncode',None),error=str(error),seconds=time.monotonic()-started,log_sha256=sha(out/'launcher.log'));write(out/'invocation.json',launch);raise
        producer=out/'probe';report=load(producer/'report.json');header(report,executable,commit,nonce,inputs,bundle)
        require(sha(producer/'files.json')==report['files_sha256'] and load(producer/'files.json')==inventory(producer,('report.json','files.json')),'Producer final post-exit inventory differs.')
        producer_inventory=inventory(producer);write(out/'producer-receipt.json',producer_inventory)
        runtime,records=check_runtime(producer,report,bundle,backend,payload_hash)
        before=runtime_files(runtime,records);uid_before=runtime_uid(runtime,env);write(out/'runtime-before.json',dict(files=before,native=uid_before))
        rows=lifecycle(producer,report,lock,load(bundle/ASSETS/'templates.json'));producer_controls(producer,report,bundle,inputs);jobs=[]
        physical=dict(root=bundle/PDK,package=lock)
        jobs=run_jobs(executable,rows,out,env,runtime,inputs,physical,records,nonce,started+timeout)
        require(len(jobs)==225 and sum(v['fault'] is None for v in jobs)==60 and len({v['execution']['native_directory'] for v in jobs})==225,'Native job selection incomplete or reused a native directory.')
        after=runtime_files(runtime,records);uid_after=runtime_uid(runtime,env);write(out/'runtime-after.json',dict(files=after,native=uid_after));require(before==after and uid_before==uid_after and inventory(producer)==producer_inventory,'Runtime/UID or immutable GUI evidence changed during native execution.')
        require(sha(executable)==exe_hash and sha(payload/'manifest.json')==payload_hash and backend_binding(payload/'backend/icstudio',commit)==backend,'Frozen executable/backend changed.');assets_binding(bundle,inputs);package(bundle/PDK,inputs['package_sha256'])
        result=dict(schema=1,status='PASS',gate='ihp-resistor-installed-gui-managed-layout',scope=SCOPE,qualified=False,release_ready=False,full_family=False,installed_acceptance=True,expected_commit=commit,execution_id=nonce,executable_sha256=exe_hash,report_sha256=sha(producer/'report.json'),producer_receipt_sha256=sha(out/'producer-receipt.json'),counts=dict(gui_layouts=60,native_layouts=60,native_controls=165,fresh_managed_jobs=225),expected_inputs=inputs,runtime=runtime,native_identity=uid_before,runtime_identity_sha256=digest(before),jobs=jobs,seconds=time.monotonic()-started)
        write(out/'files.json',inventory(out,('verification.json','files.json')));result['files_sha256']=sha(out/'files.json');write(out/'verification.json',result);return result
    except Exception as error:
        failure=dict(schema=1,status='FAIL',scope=SCOPE,qualified=False,release_ready=False,full_family=False,installed_acceptance=False,expected_commit=commit,execution_id=nonce,error=str(error),seconds=time.monotonic()-started)
        try:write(out/'files.json',inventory(out,('verification.json','files.json')));failure['files_sha256']=sha(out/'files.json')
        except Exception as inventory_error:failure['inventory_error']=str(inventory_error)
        write(out/'verification.json',failure);raise

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--executable',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--expected-commit',required=True);ap.add_argument('--timeout',type=float,default=3600)
    args=ap.parse_args();print(json.dumps(verify(args.executable,args.out,args.expected_commit,args.timeout),indent=2))

if __name__=='__main__':main()
