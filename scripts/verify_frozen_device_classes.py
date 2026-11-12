"""Installed finite parallel-CMIM, shared MiM and MOS-grouping delivery checks.

Original electrical/public-DRC records keep their separate scopes. This extension
does not qualify a family, operating envelope, RC model or manufacturing process.
"""
import argparse,copy,hashlib,json,math,os,re,shlex,shutil,subprocess,sys,time,uuid
from collections import Counter
from decimal import Decimal
from pathlib import Path,PurePosixPath,PureWindowsPath

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import verify_frozen_ihp_cmim as prior
from scripts.verify_frozen_mim import require,sha,digest,git_blob,backend_binding,design_hash,expected_inputs
from scripts.verify_frozen_ihp_resistors import build_metadata,runtime_files,native_tool_paths,execute_job,stream,same_stream,project_stream
from icstudio.testbenches import native_subcircuit
from icstudio.model import load_project
load,write,inventory,file_map,safe=prior.load,prior.write,prior.inventory,prior.file_map,prior.safe
SCOPE='Finite installed GUI/project/runtime delivery of parallel CMIM, shared-bottom MiM and MOS grouping. No family, operating-envelope, public-DRC, model-accuracy or manufacturing qualification.'
HELPERS=('verify_frozen_device_classes','prepare_frozen_device_classes','check_ihp_cmim_parallel','audit_sky130_mim_shared',
 'qualify_standard_mos','qualify_ihp_cmim_multiplicity','qualify_ihp_mim_layout','qualify_sky130_mim_shared',
 'qualify_sky130_mim2','qualify_standard_mos_layout','qualify_ihp_hv_mos_layouts','qualify_mos_finger_layouts','qualification_geometry')
TARGETS=('ihp-sg13g2','gf180mcuC','gf180mcuD')

def modules():
    # Local sibling copies support reviewed scratch pilots; installed source has
    # precisely the same import identities authenticated by candidate().
    import importlib.util
    result=[]
    for name in ('check_ihp_cmim_parallel','audit_sky130_mim_shared'):
        path=Path(__file__).with_name(name+'.py');spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.ROOT=ROOT;result.append(module)
    return result

def candidate(commit):
    result=prior.candidate(commit)
    for name in HELPERS:
        path='scripts/'+name+'.py';raw=git_blob(commit,path);expected=hashlib.sha256(raw).hexdigest()
        require(sha(ROOT/path)==expected,'Checker/fixture helper differs from candidate: '+path);result['files'][path]=expected
    result['packages']={}
    for target in TARGETS:
        path='icstudio/assets/pdks/'+target+'/package.json';raw=git_blob(commit,path);result['packages'][target]=json.loads(raw);result['files'][path]=hashlib.sha256(raw).hexdigest()
        require(sha(ROOT/path)==result['files'][path],'Local fixture package manifest differs from candidate');file_map((ROOT/path).parent,result['packages'][target]['files'])
    result['sky130']=expected_inputs(commit)
    return result

def finite_cases():
    names=['cmim-'+s for s in ('m2-0','pair-0','m2-90','pair-90','m1-0','m3-0','wrong-width-0')]
    names += [f'mim-p{p}-{mode}-{angle}' for p in (1,2) for mode,angle in (('positive',0),('positive',90),('missing-contact-group',0),('wrong-width',0),('wrong-count',0))]
    for target,hv in [('gf180mcuC',False),('gf180mcuD',False),('ihp-sg13g2',False),('ihp-sg13g2',True)]:
        for polarity in ('n','p'):
            names += [f'mos-{target}-'+('hv' if hv else 'standard')+f'-{polarity}-{mode}' for mode in ('matching','wrong-fingers')]
            if target=='gf180mcuC' and polarity=='n':names += ['mos-saved-matching','mos-saved-wrong-fingers']
    return names

def case_spec(row):
    name=row['name'];require(name in finite_cases(),'Unknown case name')
    if name.startswith('cmim-'):
        mode,angle=name[5:].rsplit('-',1);facts=dict(family='cmim',mode=mode,angle=int(angle),expected='passed' if mode in ('m2','pair') else 'failed')
    elif name.startswith('mim-'):
        plate,mode,angle=name[4:].split('-',1)[0],name[4:].split('-',1)[1].rsplit('-',1)[0],name.rsplit('-',1)[1]
        facts=dict(family='shared-mim',plate=int(plate[1:]),mode=mode,angle=int(angle),expected='passed' if mode=='positive' else 'failed')
    elif name.startswith('mos-saved-'):
        mode=name[len('mos-saved-'):];facts=dict(family='mos-saved',mode=mode,target='gf180mcuC',hv=False,polarity='n',expected='passed' if mode=='matching' else 'failed')
    else:
        match=re.fullmatch(r'mos-(gf180mcuC|gf180mcuD|ihp-sg13g2)-(standard|hv)-([np])-(matching|wrong-fingers)',name);require(match is not None,'Invalid MOS identity')
        target,hv,polarity,mode=match.groups();facts=dict(family='mos',target=target,hv=hv=='hv',polarity=polarity,mode=mode,expected='passed' if mode=='matching' else 'failed')
    require(all(type(row.get(k)) is type(v) and row[k]==v for k,v in facts.items()),'Case name/conditions/outcome substituted')
    settings=row['settings'];require(settings.get('type')=='silicon' and settings.get('physical_toolchain')=='included' and settings.get('tools')=={},'Case tool/flow selection differs')
    if facts['family'] in ('cmim','mos-saved'):
        keys={'type','testbench','physical_toolchain','tools'}|({'physical_extraction'} if facts['family']=='cmim' else set())
        require(set(settings)==keys and isinstance(settings['testbench'],str) and settings['testbench'],'Saved bench settings changed')
        if facts['family']=='cmim':require(settings['physical_extraction']=={'mode':'capacitance'},'CMIM extraction selection changed')
    else:
        require(set(settings)=={'type','verification_mode','physical_toolchain','tools','reference'} and settings['verification_mode']=='drc_lvs','Reference flow settings changed')
        if facts['family']=='mos':
            from scripts.qualify_ihp_hv_mos_layouts import selected as hv_selected
            from scripts.qualify_mos_finger_layouts import selected as lv_selected
            fault=None if facts['mode']=='matching' else 'reference-fingers';size=(3.015,1.005,3,2)
            expected=hv_selected(facts['polarity'],size,fault) if facts['hv'] else lv_selected(facts['target'],facts['polarity'],size,fault)
        else:
            from scripts.qualify_sky130_mim2 import independent
            from icstudio.layout_verification import reference
            size=(3,10,2) if facts['mode']=='wrong-width' else (2,10,1) if facts['mode']=='wrong-count' else (2,10,2)
            expected=reference(independent(size,plate=facts['plate']),'device_coupon')
        require(settings['reference']==expected,'Fixed source reference/parameter fault substituted')
    return facts

def strict_stages(report):
    rows=report['stages'];require(isinstance(rows,list) and rows and len({r['name'] for r in rows})==len(rows),'Missing/duplicate stages')
    return {r['name']:r['status'] for r in rows}

def dut_stream(project):
    import klayout.db as db
    cells=[c for c in project['cells'] if c['id']==project['top']];require(len(cells)==1 and not cells[0].get('layout_instances'),'Unexpected physical DUT hierarchy');cell=cells[0]
    layers={v['name']:(v['gds'],v['datatype']) for v in project['pdk']['layers']};regions={};labels=[]
    for shape in cell['shapes']:
        require(shape['kind'] in ('rect','polygon','path') and all(len(p)==2 and all(type(v) is int for v in p) for p in shape['points']),'Unexpected finite DUT shape/coordinates')
        points=[db.Point(*v) for v in shape['points']]
        if shape['kind']=='path':
            require(type(shape.get('width')) is int and shape['width']>0 and not shape.get('holes'),'Unsupported finite path width/holes');poly=db.Path(points,shape['width']).polygon()
        elif shape['kind']=='rect':require(len(points)==2 and not shape.get('holes'),'Unsupported rectangle');poly=db.Polygon(db.Box(*shape['points'][0],*shape['points'][1]))
        else:
            poly=db.Polygon(points)
            for hole in shape.get('holes',[]):poly.insert_hole([db.Point(*v) for v in hole])
        regions.setdefault(layers[shape['layer']],db.Region()).insert(poly)
        if shape.get('net') and cell.get('layout_label_mode')!='explicit':labels.append((layers[shape['layer']],shape['net'],*shape['points'][0],0))
    for text in cell.get('layout_texts',[]):labels.append((layers[text['layer']],text['text'],text['x'],text['y'],text.get('rotation',0)//90))
    return {key:reg.merged() for key,reg in regions.items()},sorted(labels)

def written_dut(path,top,empty_cells=()):
    import klayout.db as db
    layout=db.Layout();layout.read(str(path));cell=layout.cell(top);require(layout.dbu==.001 and cell is not None and {c.name for c in layout.each_cell()}=={top,*empty_cells},'Written DUT cells/units differ')
    for name in empty_cells:
        other=layout.cell(name);require(other.child_instances()==0 and all(other.shapes(i).is_empty() for i in layout.layer_indexes()),'Saved electrical fixture acquired physical shapes/instances')
    require(cell.child_instances()==0,'Unexpected written physical hierarchy');regions={};labels=[]
    for index in layout.layer_indexes():
        info=layout.get_info(index);pair=(info.layer,info.datatype);reg=db.Region(cell.shapes(index)).merged()
        if not reg.is_empty():regions[pair]=reg
        for shape in cell.shapes(index).each():
            if shape.is_text():t=shape.text;labels.append((pair,t.string,t.x,t.y,t.trans.angle))
    return regions,sorted(labels)

def require_lvs(flow,match=True):
    text=(flow/'lvs/lvs.log').read_text(encoding='utf-8')
    if match:require('Final result: Circuits match uniquely.' in text and 'Property errors were found.' not in text,'Native strict LVS differs')
    else:require('Property errors were found.' in text,'Missing native property fault')

def rebased_source(project,package):
    p=copy.deepcopy(project);p['pdk']['package_root']=str(package);text=native_subcircuit(p,p['top']);tag='* design-sha256 '+digest(p)
    require(text.splitlines().count(tag)==1,'Rebased source lacks exact design identity')
    return text.replace(tag,'* design-sha256 '+digest(project))

def mos_readback(flow,row,report):
    """Independent finite raw-channel count, terminal and two-location grouping."""
    top='parallel_coupon';folder=flow/'mos-grouping';proof=load(folder/'proof.json');raw=folder/(top+'.ext')
    require(proof['status']==('PASS' if row['mode']=='matching' else 'FAIL'),'MOS grouping outcome differs')
    require(report['mos_grouping']==proof,'MOS grouping report/proof differs')
    require(proof['source_sha256']==sha(flow/'schematic.spice') and proof['stream_sha256']==sha(flow/'layout.gds') and proof['native_sha256']==sha(flow/'lvs-extraction/extracted.spice'),'MOS grouping input provenance differs')
    file_map(folder,proof['files']);require(proof['files']==inventory(folder,('proof.json',)),'Incomplete MOS proof artifacts')
    records=[shlex.split(line) for line in raw.read_text(encoding='utf-8').splitlines() if line.strip()]
    for key,value in [('version','8.3'),('tech',row['target']),('style','ngspice()')]:require([r for r in records if r[0]==key]==[[key,value]],'Raw MOS metadata differs: '+key)
    require(len([r for r in records if r[0]=='timestamp' and len(r)==2 and r[1].isdigit()])==1,'Raw MOS timestamp absent/ambiguous')
    ports=[r for r in records if r[0]=='port'];require(len(ports)==4 and {r[1]:r[2] for r in ports}=={'D':'1','G':'2','S':'3','B':'4'} and all(len(r)==8 and r[-1]=='m1' and all(re.fullmatch('-?[0-9]+',v) for v in r[2:7]) for r in ports),'Raw MOS ports absent/changed')
    nodes=[r for r in records if r[0] in ('node','substrate')];expected_nodes={('node',n) for n in ('D','G','S')}|({('substrate','B')} if row['polarity']=='n' else {('node','B'),('substrate','SUB')})
    require(len(nodes)==len(expected_nodes) and {(r[0],r[1]) for r in nodes}==expected_nodes,'Raw MOS node/substrate graph incomplete')
    for r in nodes:require(len(r)==(59 if row['target'].startswith('gf') else 31) and r[6]==('space' if r[1]=='SUB' else 'm1') and all(math.isfinite(float(v)) for v in r[2:6]+r[7:]),'Raw MOS node/substrate facts differ')
    require(all(r[0] in ('timestamp','version','tech','style','scale','resistclasses','parameters','port','node','substrate','cap','device') for r in records),'Unknown raw MOS record')
    scale=[r for r in records if r[0]=='scale'];require(scale==[['scale','1000','1','0.5']],'MOS native grid differs')
    channels=[r for r in records if r[0]=='device'];require(len(channels)==6,'Native MOS channel count differs')
    model=(row['polarity']+'fet_03v3') if row['target'].startswith('gf') else 'sg13_'+('hv' if row['hv'] else 'lv')+'_'+row['polarity']+'mos'
    locations=[]
    for r in channels:
        require(len(r)==19 and r[1:3]==['msubckt',model] and r[7:9]==['l=201','w=201'] and r[9:11]==['B','G'] and {r[13],r[16]}=={'D','S'},'Raw MOS model/dimension/terminal differs')
        locations.append(tuple(int(v) for v in r[3:7]))
    require(len(set(locations))==6,'Duplicate raw MOS channel location')
    groups={x:sorted(y for a,y,_,_ in locations if a==x) for x,_,_,_ in locations}
    require(len(groups)==2 and all(len(v)==3 and len(set(v))==3 for v in groups.values()) and len({tuple(v) for v in groups.values()})==1,'Raw MOS two-copy three-finger grouping differs')
    import klayout.db as db
    layout=db.Layout();layout.read(str(flow/'layout.gds'));cell=layout.cell(top);require(layout.dbu==.001 and cell is not None and len(layout.top_cells())==1,'MOS written-mask units/top differ')
    active_layer,poly_layer=(22,30) if row['target'].startswith('gf') else (1,5)
    active=db.Region(cell.begin_shapes_rec(layout.layer(active_layer,0))).merged();poly=db.Region(cell.begin_shapes_rec(layout.layer(poly_layer,0))).merged();channels_written=list((active&poly).merged().each());diffusions=list(active.each())
    require(len(channels_written)==6,'Written MOS channel count differs');used=set();diffusion_owners=[]
    for loc in locations:
        site=db.Region(db.Box(*(5*v for v in loc)));require(not site.is_empty(),'Empty native site')
        owners=[i for i,p in enumerate(channels_written) if (site-db.Region(p)).is_empty()];require(len(owners)==1 and owners[0] not in used,'Raw site does not identify one unused written channel');used.add(owners[0])
        owners=[i for i,p in enumerate(diffusions) if (db.Region(channels_written[next(iter(owners))])-db.Region(p)).is_empty()];require(len(owners)==1,'Channel lacks unique diffusion owner');diffusion_owners.append(owners[0])
    require(sorted(Counter(diffusion_owners).values())==[3,3],'Written diffusion grouping differs')
    cmim,_=modules()
    for export in (flow/'lvs-extraction/extracted.spice',folder/'extracted.spice'):
        lines=[r.split() for r in export.read_text(encoding='utf-8').splitlines() if r.strip() and not r.lstrip().startswith('*')]
        require(lines[0]==['.subckt',top,'D','G','S','B'] and lines[-1] in (['.ends'],['.ends',top]),'Exported MOS terminal order differs')
        names=set();count=0
        for r in lines[1:-1]:
            require(len(r)>=8 and r[0].startswith('X') and r[0].casefold() not in names and r[2]=='G' and r[4]=='B' and {r[1],r[3]}=={'D','S'} and r[5]==model,'Exported MOS topology/model differs');names.add(r[0].casefold())
            p=dict(t.split('=') for t in r[6:]);require(len(p)==len(r)-6 and {'w','l'}<=set(p)<= {'w','l','m','ad','as','pd','ps'},'Exported MOS parameters differ')
            require(cmim.number(p['w'])==cmim.number(p['l'])==Decimal('1.005e-6'),'Exported MOS dimensions differ');n=cmim.number(p.get('m','1'));require(n>0 and n==int(n),'Invalid exported MOS multiplicity');count+=int(n)
        require(count==6,'Exported MOS count differs')
    if row['mode']=='matching':
        require(proof['channels']==6 and proof['groups']==2 and proof['native_grid_um']=='0.005' and proof['group_contracts']==[dict(model=model,gate='g',body='b',drain_source=['d','s'],channel_width_m='0.000001005',length_m='0.000001005',fingers=3,copies=2)],'MOS contract receipt differs')
    else:require('MOS finger counts, diffusion groups or terminal-associated dimensions differ' in proof['reason'],'Wrong MOS failure reason')
    require_lvs(flow);return dict(native_channels=6,physical_groups=2,fingers_per_group=3,grouping=proof['status'])

def native_semantics(folder,row):
    case_spec(row)
    flow=folder/'physical-flow';report=load(flow/'report.json');stages=strict_stages(report);cmim,mim=modules()
    require(report['status']==row['expected'],'Unexpected native outcome')
    if row['family']=='cmim':
        require(tuple(stages)==('preflight','schematic_simulation','drc','lvs_extraction','lvs','capacitance_extraction','post_layout_simulation','integrity'),'CMIM stage contract differs')
        cmim.project_contract(load(folder/'input.json')['project'])
        units=cmim.netlist((flow/'schematic.spice').read_text(encoding='utf-8'),True)[0];standard=(Decimal('7e-6'),Decimal('7e-6'))
        expected=Counter({standard:int(row['mode'][1:])}) if row['mode'] in ('m1','m2','m3') else Counter({standard:2}) if row['mode']=='pair' else Counter({standard:1,(Decimal('7.2e-6'),Decimal('7e-6')):1})
        require(units==expected,'CMIM named multiplicity/width fault differs from actual source')
        if row['expected']=='passed':
            require(all(v=='passed' for v in stages.values()),'CMIM positive stage incomplete');require_lvs(flow)
            graph=cmim.read_native(folder,job_name='physical-flow');return graph|cmim.currents(folder,graph,job_name='physical-flow')
        require(stages['lvs']=='failed' and all(stages[n]=='not_run' for n in ('capacitance_extraction','post_layout_simulation','integrity')),'CMIM fault did not stop before downstream work');require_lvs(flow,False);return dict(native_property_fault=True)
    if row['family']=='shared-mim':
        require(tuple(stages)==('preflight','layout_export','drc','lvs_extraction','lvs','integrity'),'Shared MiM stage contract differs')
        if row['expected']=='passed':
            require(all(v=='passed' for v in stages.values()),'Shared MiM positive incomplete');return mim.native(folder,row['plate'],row['angle'],job_name='physical-flow')
        if row['mode']=='missing-contact-group':require(stages['lvs_extraction']=='failed' and stages['lvs']=='not_run' and report['error']=='Each shared MiM electrode needs a nonempty collinear bottom-contact group.','Expected shared contact ambiguity was not rejected')
        else:require(stages['lvs']=='failed','Shared reference fault was accepted');require_lvs(flow,False)
        return dict(rejected_stage='lvs_extraction' if row['mode']=='missing-contact-group' else 'lvs')
    require(row['family'] in ('mos','mos-saved'),'Unknown finite family')
    observed=mos_readback(flow,row,report)
    if row['family']=='mos':
        require(tuple(stages)==('preflight','layout_export','drc','lvs_extraction','lvs','integrity'),'MOS stage contract differs')
        require(all(v=='passed' for v in stages.values()),'MOS native stages did not complete independently of grouping')
    else:
        require(tuple(stages)==('preflight','schematic_simulation','drc','lvs_extraction','lvs','capacitance_extraction','post_layout_simulation','integrity'),'Saved MOS stage contract differs')
        if row['mode']=='wrong-fingers':require(all(stages[n]=='passed' for n in ('preflight','schematic_simulation','drc','lvs_extraction','lvs')) and all(stages[n]=='not_run' for n in ('capacitance_extraction','post_layout_simulation','integrity')),'Saved MOS grouping fault reached downstream work')
        else:require(all(v=='passed' for v in stages.values()),'Saved MOS positive has missing/failed stage')
    return observed

def audit_job(folder,row,project,runtime,records,manifest,workflow_hash=None,captured_source=None):
    job=load(folder/'input.json');expected=dict(project=project,cell=project['top'],engine='builtin',settings=copy.deepcopy(row['settings'])|{'physical_runtime':runtime})
    if workflow_hash is not None:expected['environment']=dict(workflow_hash=workflow_hash,engine='builtin')
    require(job==expected,'Worker source project/settings changed')
    result=load(folder/'result.json');host=result['silicon_report'];execution=host['execution'];directory=execution['native_directory']
    require(re.fullmatch('/var/tmp/icstudio-physical/[0-9a-f]{32}',directory) if runtime['kind']=='wsl' else Path(directory).is_absolute() and '/icstudio-physical-' in directory,'Invalid/reused native directory')
    require(execution['runtime']==runtime and execution['native_input_sha256']==sha(folder/'physical-backend-input.json'),'Managed execution binding differs')
    translated=copy.deepcopy(job);translated.pop('environment',None);translated['project']['pdk']['package_root']=directory+'/pdk';translated['settings'].pop('physical_runtime');translated['settings']['tools']=native_tool_paths(runtime)
    if row['family']=='cmim':
        from icstudio.osdi import managed_models
        selected=managed_models(project['pdk'],manifest);prefix=('/' if runtime['kind']=='wsl' else runtime['root'].rstrip('/')+'/')+'opt/icstudio/osdi/ihp-sg13g2/'
        translated['project'].setdefault('simulation_runtime',{})['osdi']=[dict(path=prefix+m['output'],sha256=m['sha256'],system='Linux',machine='x86_64') for m in selected]
    require(load(folder/'physical-backend-input.json')==translated,'Unexpected native input translation')
    artifacts=load(folder/'physical-artifacts.json');file_map(folder,artifacts)
    actual={'physical-flow/'+n:h for n,h in inventory(folder/'physical-flow').items()}|{'physical-backend-result.json':sha(folder/'physical-backend-result.json')}
    require(artifacts==actual==execution['received_files'],'Incomplete native transfer')
    flow=folder/'physical-flow';native=load(flow/'report.json');raw_result=load(folder/'physical-backend-result.json')
    require(raw_result['silicon_report']==native and load(flow/'input.icproj')==translated['project'] and native['design_hash']==design_hash(translated['project']),'Raw native input/report differs')
    require(result['settings']==job['settings'] and result['design_hash']==host['design_hash']==design_hash(project) and host['native_design_hash']==native['design_hash'],'Host result binding differs')
    require([(x['name'],x['status']) for x in host['stages']]==[(x['name'],x['status']) for x in native['stages']],'Host/native stage status differs')
    expected_source=row['settings'].get('reference',{}).get('text')
    if expected_source is None:
        expected_source=captured_source if captured_source is not None else native_subcircuit(project,project['top']);tag='* design-sha256 '+digest(project)
        require(expected_source.splitlines().count(tag)==1,'Captured circuit lacks exact design identity')
        expected_source=expected_source.replace(tag,'* design-sha256 '+digest(translated['project']))
    require((flow/'schematic.spice').read_text(encoding='utf-8')==expected_source,'Actual native circuit differs from captured source')
    for path,h in native.get('provenance',{}).get('files',{}).items():require(sha(prior.confined(flow,path))==h,'Native provenance member changed')
    top=next(c['name'] for c in project['cells'] if c['id']==project['top']);expected_stream=dut_stream(project)
    for name in ('original.gds','layout.gds'):
        if (flow/name).exists():same_stream(written_dut(flow/name,top),expected_stream,text_presentation=False)
    tools=next(r for r in native['stages'] if r['name']=='preflight')['evidence']['tools']
    for name,meta in tools.items():require(meta['path']==native_tool_paths(runtime)[name] and meta['sha256']==records['opt/icstudio/bin/'+name],'Unbound native tool')
    require(set(tools)==({'magic','netgen','ngspice'} if row['family'] in ('cmim','mos-saved') else {'magic','netgen'}),'Missing/extra preflight native tools')
    for stage in ('drc','lvs-extraction'):
        if stage=='lvs-extraction' and row['family']=='shared-mim' and row['mode']=='missing-contact-group':
            require(not (flow/stage/'console.log').exists(),'Ambiguous shared contact reached native extraction');continue
        log=(flow/stage/'console.log').read_text(encoding='utf-8');require(log.splitlines().count('STUDIO_MAGIC_COMPLETE')==1 and not re.search('STUDIO_MAGIC_ERROR|invalid command|contained errors|Malformed line',log,re.I),'Native Magic did not complete')
    log=(flow/'drc/console.log').read_text(encoding='utf-8');require(re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)==['0'] and 'STUDIO_DRC_STYLE drc(full)' in log and native['drc_count']==0 and native['magic_drc_style']=='drc(full)' and not (flow/'drc/findings.tsv').read_bytes(),'Raw full Magic DRC differs')
    return dict(name=row['name'],native_directory=directory,**native_semantics(folder,row))

def lifecycle(root,launch,inputs):
    probe=root/'probe';report=load(probe/'report.json');fixtures=load(root/'inputs/cases.json')
    require(report['status']=='passed' and report['frozen'] is True and report['managed'] is True and report['build'].get('commit')==launch['candidate'] and report['build'].get('dirty') is False and report['build'].get('frozen') is True,'Producer is not exact clean installed candidate')
    require(not report.get('error') and not report.get('errors'),'Producer retained an error')
    require(report['execution_id']==launch['execution_id'] and report['executable']==launch['executable'] and report['executable_sha256']==launch['executable_sha256'] and report['resource_root']==launch['resource_root'],'Producer executable/nonce differs')
    require(all(report.get(k) is False for k in ('qualified','installed_acceptance','full_family','release_ready','native_execution')),'Producer overclaims scope')
    require(report['input_manifest_sha256']==sha(root/'inputs/cases.json') and not fixtures['pilot'] and fixtures['qualified'] is False and fixtures['installed_acceptance'] is False,'Fixture manifest differs')
    require([r['name'] for r in fixtures['cases']]==[r['name'] for r in report['cases']]==finite_cases(),'Incomplete/duplicate finite case population')
    required_sources={prior.FIXTURE+'/'+n for n in ('mask-only.json','SOURCE.json','LICENSE')}
    require(set(fixtures['source_files'])==required_sources and all(h==inputs['files'][n] for n,h in fixtures['source_files'].items()),'Fixture source/notice identity differs from candidate')
    require(load(probe/'files.json')==inventory(probe,('report.json','files.json')) and sha(probe/'files.json')==report['files_sha256'],'Producer complete files differ')
    rows=[];expected_technologies={};verified_registry=set()
    for row,captured in zip(fixtures['cases'],report['cases']):
        case_spec(row)
        name=row['name'];folder=probe/name;prepared=load(root/'inputs'/row['project']);project=load(folder/'reopened.icproj')
        require(sha(root/'inputs'/row['project'])==row['project_sha256'] and sha(root/'inputs'/row['captured'])==row['captured_sha256'],'Prepared input changed')
        require(captured['settings']==row['settings'] and captured['family']==row['family'] and captured['expected']==row['expected'],'GUI case settings differ')
        require(sha(folder/'saved.icproj')==sha(folder/'reopened.icproj')==captured['project_sha256']==captured['reopened_sha256'],'GUI saved/reopened bytes differ')
        prepared['pdk']['package_root']=project['pdk']['package_root'];require(project==prepared==load(folder/'opened.icproj'),'GUI changed project outside explicit package root relocation')
        target=project['pdk']['package_lock']['id'];lock=load(root/'packages'/target/'package.json')
        cls=PureWindowsPath if launch['platform']=='Windows' else PurePosixPath;recorded=cls(project['pdk']['package_root']);origin=cls(launch['execution_root'])/'probe'
        require(recorded.is_absolute() and recorded.is_relative_to(origin/'profile') and captured['package_root']==str(recorded),'External/substituted registry package path')
        local_package=prior.confined(probe,recorded.relative_to(origin).as_posix())
        if local_package not in verified_registry:file_map(local_package,lock['files']);require(load(local_package/'package.json')==lock,'Registry package differs from retained source');verified_registry.add(local_package)
        want=inputs['sky130']['physical_sha256'] if target=='sky130A' else inputs['files']['icstudio/assets/pdks/'+target+'/package.json']
        require(sha(root/'packages'/target/'package.json')==want and project['pdk']['package_lock']=={k:lock[k] for k in ('id','revision','files')},'Project PDK source identity differs')
        if row['family'] in ('mos','mos-saved'):
            if target not in expected_technologies:
                from scripts.qualify_standard_mos import load_technology
                from icstudio.process_adapters import ADAPTERS
                technology,_=load_technology(target);ADAPTERS[target].implementation().prepare(technology);expected_technologies[target]=technology
            expected_pdk=copy.deepcopy(expected_technologies[target]);expected_pdk['package_root']=project['pdk']['package_root']
        else:expected_pdk=lock['technology']|{'package_lock':project['pdk']['package_lock'],'package_root':project['pdk']['package_root']}
        require(project['pdk']==expected_pdk,'Project PDK semantic/physical adapter differs')
        require(captured['registry_package_sha256']==sha(folder/'registry-package.json') and load(folder/'registry-package.json')==lock,'Registered package semantics/bytes differ')
        expected=rebased_source(project,local_package);require((folder/'captured.spice').read_text(encoding='utf-8')==expected and sha(folder/'captured.spice')==captured['captured_sha256'],'Captured circuit differs from GUI project')
        top=next(c['name'] for c in project['cells'] if c['id']==project['top'])
        empty_cells=[c['name'] for c in project['cells'] if c['id']!=project['top']]
        require(empty_cells==(['fixture'] if row['family'] in ('cmim','mos-saved') else []),'Unexpected saved project hierarchy')
        for ext in ('gds','oas'):same_stream(written_dut(folder/('layout.'+ext),top,empty_cells),dut_stream(project),text_presentation=False)
        rows.append((row,project))
    return report,rows

def readback(root,commit):
    root=safe(root).resolve();require(load(root/'files.json')==inventory(root,('verification.json','files.json')),'Incomplete/changed parent evidence inventory')
    inputs=candidate(commit);launch=load(root/'invocation.json');require(launch['candidate']==commit and launch['inputs']==inputs and launch['status']=='complete','Unaccepted candidate invocation')
    require(launch['platform'] in ('Windows','Linux') and re.fullmatch('[0-9a-f]{32}',launch['execution_id']),'Invalid host/nonce')
    require(launch['returncode']==0 and launch['log_sha256']==sha(root/'launcher.log'),'GUI invocation failure/log differs')
    expected_command=[launch['executable'],'--device-class-acceptance','--managed','--inputs',prior.host_path(launch,launch['execution_root'],'inputs','cases.json'),'--inputs-sha256',sha(root/'inputs/cases.json'),'--physical-pdk',launch['physical_pdk'],'--out',prior.host_path(launch,launch['execution_root'],'probe'),'--execution-id',launch['execution_id']]
    require(launch['command']==expected_command,'GUI command differs')
    report,rows=lifecycle(root,launch,inputs);runtime,records=prior.runtime_evidence(root/'probe',report,launch,inputs)
    require(load(root/'runtime-before.json')==load(root/'runtime-after.json'),'Runtime changed')
    full=load(root/'runtime-before.json')['files'];require(all(full.get(n)==h for n,h in records.items()) and set(full)<=set(records)|{'init','etc/wsl.conf'},'Incomplete full runtime readback')
    tree=load(root/'distribution.json');require(tree==launch['distribution'],'Distribution binding differs');files=tree['files']
    exe='ICDesignStudio.exe' if launch['platform']=='Windows' else 'ICDesignStudio';require(files.get(exe)==launch['executable_sha256'],'Frozen executable differs')
    for n,t in tree['links'].items():prior.link_endpoint(n,t,files,tree['links'])
    require(set(tree['installer_metadata'])<={'unins000.exe','unins000.dat','unins000.msg'} and (launch['platform']=='Windows' or not tree['installer_metadata']),'Invalid installer metadata exclusions')
    manifest=load(root/'probe/runtime/before/payload-manifest.json')
    require(files.get('_internal/icstudio/assets/runtime/digital/runtime.tar.gz')==manifest['sha256'] and files.get('_internal/icstudio/assets/runtime/digital/manifest.json')==launch['payload_manifest_sha256'],'Archive/manifest distribution mismatch')
    for n,h in report['managed_runtime_before']['backend_files'].items():require(files.get('_internal/icstudio/assets/runtime/digital/backend/icstudio/'+n)==h,'Backend distribution mismatch')
    prior.check_metadata(root/'backend-build-info.py',commit,inputs)
    for target in TARGETS:
        p='icstudio/assets/pdks/'+target;lock=inputs['packages'][target]
        require(files.get('_internal/'+p+'/package.json')==inputs['files'][p+'/package.json'],'Bundled package manifest differs')
        for n,h in lock['files'].items():require(files.get('_internal/'+p+'/'+prior.member(n))==h,'Bundled package member differs')
    jobs=[]
    for row,project in rows:
        folder=root/'native'/row['name'];attempt=load(folder/'invocation.json')
        command=[launch['executable'],'--worker',prior.host_path(launch,launch['execution_root'],'native',row['name'],'input.json'),prior.host_path(launch,launch['execution_root'],'native',row['name'],'result.json')]
        require(attempt['command']==command and attempt['executable_sha256']==launch['executable_sha256'] and attempt['input_sha256']==sha(folder/'input.json') and attempt['status']=='complete' and attempt['returncode']==0 and attempt['log_sha256']==sha(folder/'worker.log'),'Worker invocation changed or incomplete')
        captured=(root/'probe'/row['name']/'captured.spice').read_text(encoding='utf-8');jobs.append(audit_job(folder,row,project,runtime,records,manifest,inputs['workflow_hash'],captured))
    require(len({r['native_directory'] for r in jobs})==len(jobs),'Native directory reused')
    return dict(schema=1,status='PASS',gate='finite-installed-device-classes',scope=SCOPE,installed_acceptance=True,qualified=False,full_family=False,release_ready=False,candidate=commit,platform=launch['platform'],cases=len(jobs),files_sha256=sha(root/'files.json'),jobs=jobs)

def run(executable,distribution,out,commit,physical,timeout=1800):
    executable=safe(executable).resolve();distribution=safe(distribution).resolve();out=safe(out).resolve();physical=safe(physical).resolve()
    require(executable.parent==distribution and not out.exists() and not out.is_relative_to(distribution) and not distribution.is_relative_to(out) and math.isfinite(timeout) and timeout>0,'Fresh separate output/installed executable required')
    inputs=candidate(commit);out.mkdir(parents=True);started=time.monotonic();nonce=uuid.uuid4().hex
    try:
        platform='Windows' if os.name=='nt' else 'Linux';bundle=distribution/'_internal';payload=bundle/'icstudio/assets/runtime/digital'
        require(sha(physical/'package.json')==inputs['sky130']['physical_sha256'],'Wrong immutable SKY physical adapter');file_map(physical,load(physical/'package.json')['files'])
        tree=prior.distribution_tree(distribution,platform);backend=backend_binding(payload/'backend/icstudio',commit);build_metadata(payload/'backend/icstudio',commit,inputs)
        require(sha(payload/'runtime.tar.gz')==load(payload/'manifest.json')['sha256'],'Installed archive differs')
        shutil.copyfile(payload/'backend/icstudio/build_info.py',out/'backend-build-info.py');write(out/'distribution.json',tree)
        for target in (*TARGETS,'sky130A'):
            source=physical if target=='sky130A' else bundle/'icstudio/assets/pdks'/target;dest=out/'packages'/target;dest.mkdir(parents=True);shutil.copyfile(source/'package.json',dest/'package.json')
        from scripts.prepare_frozen_device_classes import prepare
        prepare(out/'inputs',physical)
        env=prior.git_environment()
        for key in list(env):
            if key.upper() in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','ICSTUDIO_DIGITAL_PAYLOAD','ICSTUDIO_DIGITAL_NATIVE','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):env.pop(key)
        env['QT_QPA_PLATFORM']='offscreen'
        command=[str(executable),'--device-class-acceptance','--managed','--inputs',str(out/'inputs/cases.json'),'--inputs-sha256',sha(out/'inputs/cases.json'),'--physical-pdk',str(physical),'--out',str(out/'probe'),'--execution-id',nonce]
        launch=dict(command=command,candidate=commit,expected_commit=commit,execution_id=nonce,executable=str(executable),executable_sha256=sha(executable),resource_root=str(bundle),execution_root=str(out),platform=platform,physical_pdk=str(physical),inputs=inputs,distribution=tree,payload_manifest_sha256=sha(payload/'manifest.json'),backend_build_info_sha256=sha(out/'backend-build-info.py'),status='RUNNING')
        write(out/'invocation.json',launch)
        with (out/'launcher.log').open('wb') as log:completed=subprocess.run(command,env=env,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=min(300,timeout),check=True)
        launch.update(status='complete',returncode=completed.returncode,log_sha256=sha(out/'launcher.log'));write(out/'invocation.json',launch)
        report,rows=lifecycle(out,launch,inputs);runtime,records=prior.runtime_evidence(out/'probe',report,launch,inputs);manifest=load(out/'probe/runtime/before/payload-manifest.json')
        write(out/'runtime-before.json',dict(files=runtime_files(runtime,records)))
        for row,project in rows:
            folder=out/'native'/row['name'];folder.mkdir(parents=True);job=dict(project=project,cell=project['top'],engine='builtin',environment=dict(workflow_hash=inputs['workflow_hash'],engine='builtin'),settings=copy.deepcopy(row['settings'])|{'physical_runtime':runtime})
            write(folder/'input.json',job);command=[str(executable),'--worker',str(folder/'input.json'),str(folder/'result.json')]
            attempt=dict(command=command,executable_sha256=launch['executable_sha256'],input_sha256=sha(folder/'input.json'),status='RUNNING')
            execute_job(folder,command,attempt,time.monotonic(),env,deadline=started+timeout,runtime=runtime);captured=(out/'probe'/row['name']/'captured.spice').read_text(encoding='utf-8');observed=audit_job(folder,row,project,runtime,records,manifest,inputs['workflow_hash'],captured);write(folder/'readback.json',observed)
        write(out/'runtime-after.json',dict(files=runtime_files(runtime,records)))
        require(prior.distribution_tree(distribution,platform)==tree and backend_binding(payload/'backend/icstudio',commit)==backend and candidate(commit)==inputs,'Candidate/distribution changed')
        write(out/'files.json',inventory(out,('verification.json','files.json')));result=readback(out,commit);write(out/'verification.json',result);return result
    except BaseException as error:write(out/'failure.json',dict(status='FAIL',installed_acceptance=False,error=str(error),seconds=time.monotonic()-started));raise

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',required=True);ap.add_argument('--executable',type=Path);ap.add_argument('--distribution-root',type=Path);ap.add_argument('--physical-pdk',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--readback',type=Path);ap.add_argument('--timeout',type=float,default=1800);a=ap.parse_args()
    if a.readback:result=readback(a.readback,a.candidate)
    else:
        require(all((a.executable,a.distribution_root,a.physical_pdk,a.output)),'Live acceptance arguments required');result=run(a.executable,a.distribution_root,a.output,a.candidate,a.physical_pdk,a.timeout)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
