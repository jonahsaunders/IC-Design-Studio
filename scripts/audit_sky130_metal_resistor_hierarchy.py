"""Independent readback of selected imported SKY130 resistor hierarchy.

Reads original stream/project/native artifacts; never imports the producer or
constructs a positive device to replace a missing extraction. This finite source
integration check is not array, electrical, installed or foundry qualification.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_frozen_mim import require, sha, load, inventory, file_map, design_hash
from scripts.audit_sky130_li_case import magic_log, native_script, tcl_literal, check_netgen_inputs

MODELS = ('l1', 'm1', 'm2', 'm3', 'm4')
LAYERS = dict(zip(MODELS, (67, 68, 69, 70, 71)))
PORTS = ('A1', 'B1', 'A2', 'B2')
TOP, LEAF = 'res_pair', 'res_leaf'
FAULTS = ('merged-reference-terminal', 'missing-reference-instance', 'second-reference-width', 'physical-cross-instance-short')
EXCHANGE = ('missing-instance', 'lost-mirror', 'lost-rotation', 'renamed-top-terminal', 'changed-leaf-mask')
STAGES = ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')
PHYSICAL_SHA = '531c0a4263b839b693d171ad223d01f1484130113f0fcb9010bf99b4c2da9417'
CONTRACT_SHA = 'dbe672e65ee2533e93a37c94366b54332a6c0f4d00754a4b00796a6ebfc97929'
LAUNCHERS = {'/opt/icstudio/bin/magic':'359bd5dbfccf21114b2f18e2ffa008debf159bd0d1ab78e01738d2af9500b223',
    '/opt/icstudio/bin/netgen':'209cc0bab75420d13094a99de13e94af05d735e744e06d817fac022ac74401d3',
    '/opt/icstudio/physical/installed/bin/magic':'4b74020f201fd8b09b4984614249f3602dd1f4b2a3731e087dfe88eeacc887c5'}
NATIVE_TREES = {'/opt/icstudio/physical/installed':'12a0cae4b96c59dddbd3e8d4470973871fab052ef047fb0e98c3040c8f52eb8f',
    '/usr/share/tcltk':'18d3ef2d1f0c3c3d253a05c4bf0c7c189de54f8384ef926dd18178cc1b34bc9e',
    '/usr/lib/tcltk':'1ca2ada63b252a96da6f6a98c63301aed76e48dcba7c2b343314d00d1f77b1d5'}


def placements(angle):
    require(angle in (0, 90), 'Unsupported whole-top rotation.')
    return [(0, False, 0, 0), (90, True, 40000, 0)] if angle == 0 else [(90, False, 0, 0), (180, True, 0, 40000)]


def transform(point, placement):
    angle, mirror, x, y = placement; px, py = point
    if mirror: py = -py
    for _ in range(angle//90): px, py = -py, px
    return px+x, py+y


def cell_regions(layout, cell):
    """Copy polygons, avoiding borrowed storage after a Layout is released."""
    import klayout.db as db
    masks, labels = {}, []
    for index in layout.layer_indexes():
        info = layout.get_info(index); key = (info.layer, info.datatype); region = db.Region()
        for shape in cell.shapes(index).each():
            if shape.is_text(): labels.append((key, shape.text.string, shape.text.x, shape.text.y))
            elif shape.is_box(): region.insert(db.Polygon(shape.box))
            elif shape.is_polygon() or shape.is_simple_polygon(): region.insert(shape.polygon.dup())
            elif shape.is_path(): region.insert(shape.path.polygon())
            else: raise ValueError('Unsupported retained shape.')
        region.merge()
        if not region.is_empty(): masks[key] = region
    return masks, sorted(labels)


def same_masks(actual, expected):
    require(set(actual) == set(expected) and all((actual[k] ^ expected[k]).is_empty() for k in actual),
            'Written mask geometry/layer set differs.')


def leaf(path, model):
    import klayout.db as db
    layout = db.Layout(); layout.read(str(path))
    require(layout.dbu == .001 and layout.cells() == 1 and len(list(layout.top_cells())) == 1,
            'Native leaf grid/hierarchy differs.')
    cell = layout.top_cell(); require(not list(cell.each_inst()), 'Native leaf unexpectedly contains children.')
    masks, labels = cell_regions(layout, cell); layer = LAYERS[model]
    require((layer, 13) in masks and masks[layer,13].count() == 1 and masks[layer,13].area() == 10000000 and
            masks[layer,13].bbox().width() == 2000 and masks[layer,13].bbox().height() == 5000,
            'Leaf marker is not one exact 2x5 um rectangle.')
    require((masks[layer,13] ^ db.Region(masks[layer,13].bbox())).is_empty(), 'Nonrectangular resistor marker.')
    require(set(masks) == {(layer,20),(layer,13)}, 'Unexpected native leaf masks.')
    ends = (masks[layer,20]-masks[layer,13]).merged()
    require(ends.count() == 2 and len(labels) == 2 and {n for _,n,_,_ in labels} == {'R1','R2'} and
            all(pair == (layer,5) for pair,_,_,_ in labels), 'Leaf terminal structure differs.')
    for number,poly in enumerate(sorted(ends.each(),key=lambda p:p.bbox().center().y),1):
        point = poly.bbox().center()
        require(poly.inside(point) and ((layer,5),'R'+str(number),point.x,point.y) in labels, 'Leaf terminal anchor differs.')
    return masks, labels


def expected_flat(base, angle):
    import klayout.db as db
    masks, labels = base; result = {}; top_labels = []
    for number,place in enumerate(placements(angle),1):
        tr = db.ICplxTrans(1,*place)
        for key,region in masks.items(): result.setdefault(key,db.Region()).insert(region.transformed(tr))
        for key,name,x,y in labels:
            px,py = transform((x,y),place); top_labels.append((key,('A' if name=='R1' else 'B')+str(number),px,py))
    return {k:v.merged() for k,v in result.items()}, sorted(top_labels)


def bridge_masks(base, angle=0):
    import klayout.db as db
    require(angle == 0, 'Cross-instance control is selected only at rotation zero.')
    masks, labels = expected_flat(base,0); points = {name:(x,y) for _,name,x,y in labels}
    a,b = points['A1'],points['A2']; y=min(a[1],b[1])-4000; escape=b[0]-1000
    boxes = [(a[0]-200,y-200,a[0]+200,a[1]),
             (min(a[0],escape)-200,y-200,max(a[0],escape)+200,y+200),
             (escape-200,y-200,escape+200,b[1]+200),
             (escape-200,b[1]-200,b[0],b[1]+200)]
    addition=db.Region()
    for box in boxes: addition.insert(db.Box(*box))
    key=next(k for k in masks if k[1]==20)
    require((addition & masks[key[0],13]).is_empty(), 'Short control intrudes into a resistor body.')
    result={k:v.dup() for k,v in masks.items()}; result[key]=(result[key]+addition).merged()
    return result,labels,addition.merged()


def stream(path, model, angle, base, *, private=False, short=False, corruption=None):
    import klayout.db as db
    layout=db.Layout();layout.read(str(path)); require(layout.dbu==.001,'Written stream grid differs.')
    require([c.name for c in layout.top_cells()]==[TOP],'Written stream top differs.')
    top=layout.cell(TOP); direct,labels=cell_regions(layout,top)
    expected,expected_labels=expected_flat(base,angle)
    if short:expected,expected_labels,addition=bridge_masks(base,angle)
    if private:
        require(layout.cells()==1 and not list(top.each_inst()),'Private verification stream must be flat.')
        same_masks(direct,expected);require(labels==expected_labels,'Private native labels lost or merged.')
        return dict(cells=1,instances=0,terminal_anchors=[[a,b,n,x,y] for (a,b),n,x,y in labels])
    require({c.name for c in layout.each_cell()}=={TOP,LEAF},'Editable hierarchy was lost or substituted.')
    child=layout.cell(LEAF); require(not list(child.each_inst()),'Unexpected nested leaf hierarchy.')
    child_masks,child_labels=cell_regions(layout,child); expected_child={k:v.dup() for k,v in base[0].items()}
    if corruption=='changed-leaf-mask':expected_child[LAYERS[model],20].insert(db.Box(100000,100000,100500,100500))
    same_masks(child_masks,expected_child);require(child_labels==base[1],'Child labels changed.')
    desired=placements(angle)
    if corruption=='missing-instance':desired=desired[:1]
    elif corruption=='lost-mirror':desired=[desired[0],(desired[1][0],False,*desired[1][2:])]
    elif corruption=='lost-rotation':desired=[desired[0],(0,desired[1][1],*desired[1][2:])]
    instances=list(top.each_inst()); actual=[]
    for item in instances:
        t=item.cplx_trans
        require(item.cell_index==child.cell_index() and t.mag==1 and max(1,item.na)==max(1,item.nb)==1,
                'Child target, scale or array multiplicity differs.')
        actual.append((t.angle,t.is_mirror(),t.disp.x,t.disp.y))
    require(sorted(actual)==sorted(desired),'Written child transforms differ.')
    if corruption=='renamed-top-terminal':expected_labels=[(p,'A1' if n=='A2' else n,x,y) for p,n,x,y in expected_labels]
    require(labels==sorted(expected_labels),'Written top-terminal anchors differ.')
    same_masks(direct,{(LAYERS[model],20):addition} if short else {})
    return dict(sha256=sha(path),cells=2,reused_leaf=LEAF,instances=2,
        placements=[list(p) for p in sorted(placements(angle))],
        terminal_anchors=[[a,b,n,x,y] for (a,b),n,x,y in sorted(expected_labels)],
        marker_width_um=2,marker_length_um=5,model=model)


def project(path,model,angle,base,package,*,short=False):
    import klayout.db as db
    value=load(path);cells={r['name']:r for r in value['cells']}
    require(len(value['cells'])==2 and set(cells)=={TOP,LEAF} and value['top']==cells[TOP]['id'] and
            cells[TOP]['ports']==list(PORTS),'Saved project hierarchy/interface differs.')
    require(value['pdk']['package_lock']=={k:package[k] for k in ('id','revision','files')},'Saved physical package lock differs.')
    layers={r['name']:(r['gds'],r['datatype']) for r in value['pdk']['layers']}
    require(len(layers)==len(value['pdk']['layers']),'Duplicate project layer.')
    for name,cell in cells.items():
        require(not cell['devices'] and not cell.get('layout_ports') and not cell.get('layout_pins'),
                'Imported geometry was replaced with created device/pin objects.')
        masks={}
        for shape in cell['shapes']:
            require(shape['kind'] in ('rect','polygon'),'Unsupported imported project shape.')
            poly=db.Polygon(db.Box(*shape['points'][0],*shape['points'][1])) if shape['kind']=='rect' else db.Polygon([db.Point(*p) for p in shape['points']])
            for hole in shape.get('holes',[]):poly.insert_hole([db.Point(*p) for p in hole])
            masks.setdefault(layers[shape['layer']],db.Region()).insert(poly)
        masks={k:v.merged() for k,v in masks.items()}
        expected=base[0] if name==LEAF else {(LAYERS[model],20):bridge_masks(base,angle)[2]} if short else {}
        same_masks(masks,expected)
        expected_labels=base[1] if name==LEAF else expected_flat(base,angle)[1]
        labels=sorted((layers[r['layer']],r['text'],r['x'],r['y']) for r in cell.get('layout_texts',[]))
        require(labels==expected_labels,'Saved project terminal anchors differ.')
    require(not cells[LEAF]['layout_instances'],'Saved leaf contains instances.')
    rows=cells[TOP]['layout_instances']
    require(len(rows)==2 and len({r['id'] for r in rows})==2 and all(r['cell']==cells[LEAF]['id'] and r['nx']==r['ny']==1 for r in rows),
            'Saved project did not retain two references to one leaf.')
    require(sorted((r['rotation'],r['mirror'],r['x'],r['y']) for r in rows)==sorted(placements(angle)),
            'Saved project instance transform differs.')
    return value


def native_circuit(path,model,short=False):
    text=re.sub(r'\n[ \t]*\+[ \t]*',' ',Path(path).read_text())
    rows=[r.split() for r in text.splitlines() if r.strip() and not r.lstrip().startswith('*')]
    require(len(rows)==4 and rows[0][:2]==['.subckt',TOP] and rows[-1] in (['.ends'],['.ends',TOP]),
            'Native extraction top, directives or device count differs.')
    require(len({row[0].casefold() for row in rows[1:3]})==2,'Duplicate native resistor instance name.')
    pairs=[]
    for row in rows[1:3]:
        require(len(row) in (6,7) and re.fullmatch(r'[Rr][A-Za-z0-9_.$:]+',row[0]) and
                row[3]=='sky130_fd_pr__res_generic_'+model,'Wrong native primitive/model.')
        values={}
        for item in row[4:]:
            key,value=item.split('=');require(key.lower() not in values,'Duplicate extracted parameter.');values[key.lower()]=float(value)
        require(set(values) in ({'w','l'},{'w','l','m'}) and all(math.isfinite(v) for v in values.values()) and
                values['w']==2 and values['l']==5 and values.get('m',1)==1,'Native dimensions/multiplicity differ.')
        require(len(set(row[1:3]))==2,'Native resistor was shorted across itself.');pairs.append(frozenset(row[1:3]))
    ports=rows[0][2:]
    require(len(set(ports))==len(ports),'Duplicate native interface.')
    if not short:
        require(ports==list(PORTS) and set(pairs)=={frozenset(('A1','B1')),frozenset(('A2','B2'))},'Native hierarchy nets merged/substituted.')
    else:
        common=pairs[0]&pairs[1]
        require(len(common)==1 and common<={'A1','A2'} and {tuple(sorted(p-common)) for p in pairs}=={('B1',),('B2',)},
                'Physical control is not precisely the A-terminal bridge.')
        missing='A2' if common=={'A1'} else 'A1'
        require(ports in (list(PORTS),[n for n in PORTS if n!=missing]),'Physical short has an unrelated interface failure.')
    return dict(sha256=sha(path),devices=2,terminal_pairs=[sorted(p) for p in pairs],top_ports=ports,
                model=model,width_um=2,length_um=5)


def reference_text(model,fault=None):
    require(fault in (None,*FAULTS),'Unknown reference fault.')
    full='sky130_fd_pr__res_generic_'+model
    rows=['.subckt resistor_leaf A B',f'RLEAF A B {full} w=2 l=5 m=1','.ends resistor_leaf']
    if fault=='second-reference-width':rows+=['.subckt changed_leaf A B',f'RLEAF A B {full} w=3 l=5 m=1','.ends changed_leaf']
    rows+=['.subckt res_pair A1 B1 A2 B2','X1 A1 B1 resistor_leaf']
    if fault!='missing-reference-instance':rows+=['X2 '+('A1' if fault=='merged-reference-terminal' else 'A2')+' B2 '+('changed_leaf' if fault=='second-reference-width' else 'resistor_leaf')]
    return '\n'.join([*rows,'.ends res_pair',''])


def scripts(folder,origin,pdk):
    old=''.join(f'if {{![port "R{n}" exists]}} {{error "Missing layout port R{n}"}}\nport "R{n}" index {n}\n' for n in (1,2))
    new=''.join(f'if {{![port "{name}" exists]}} {{error "Missing layout port {name}"}}\nport "{name}" index {n}\n' for n,name in enumerate(PORTS,1))
    for stage in ('drc','lvs-extraction'):
        expected=native_script(origin,stage).replace('load "coupon"','load "res_pair"').replace(old,new)
        require((folder/stage/'run.tcl').read_text()==expected,'Native script settings/input differs.')
        require((folder/stage/'startup.tcl').read_text()=='tech load '+tcl_literal(pdk/'libs.tech/magic/sky130A.tech')+'\ndrc euclidean on\n',
                'Native startup PDK differs.')


def width_mismatch(log,model):
    """Both observed Netgen conclusions retain the same explicit 3-vs-2 width error."""
    rows=re.findall(r'^[ \t]+w circuit1: (\S+)[ \t]+circuit2: (\S+)[ \t]+\(delta=40%, cutoff=1%\)$',log,re.M)
    require(len(rows)==1 and tuple(map(float,rows[0]))==(3.,2.),'Wrong-width control lacks exact 3-to-2 width mismatch.')
    full='sky130_fd_pr__res_generic_'+model
    require(f'changed_leaf:2/{full}:LEAF vs. {full}:1:' in log and
            re.findall(r'^The following cells had property errors:\n ([^\n]+)$',log,re.M)==[TOP],
            'Wrong-width property error is not bound to the selected model/top.')
    final=re.findall(r'^Final result: (.+)$',log,re.M)
    require(final==['Circuits match uniquely.'] and 'Property errors were found.' in log or
            final==['Top level cell failed pin matching.'] and 'Netlists match with 2 symmetries with property errors.' in log,
            'Wrong-width control has an unrelated native conclusion.')


def native(folder,origin,pdk,model,angle,base,package,tools,fault=None):
    record=load(folder/'report.json');stages=record['stages']
    require([r['name'] for r in stages]==list(STAGES),'Missing/duplicate native stages.')
    states=[r['status'] for r in stages];short=fault=='physical-cross-instance-short'
    require(record['status']==('failed' if fault else 'passed') and record['drc_engine']==record['lvs_extractor']=='magic' and
            record['magic_drc_style']=='drc(full)','Wrong native outcome/tool/style.')
    require(states==['passed']*6 if fault is None else states in
            (['passed']*4+['failed','passed'],['passed']*3+['failed','not_run','not_run']) if short else
            states==['passed']*4+['failed','passed'],'Fault failed at an unrelated stage.')
    assets={str(pdk/name):value for name,value in package['files'].items() if name.startswith(('libs.tech/magic/','libs.tech/netgen/'))}
    require(stages[0]['evidence']['assets']==assets and stages[0]['evidence']['tools']==tools,'Native tool/PDK binding differs.')
    saved=project(folder/'input.icproj',model,angle,base,package,short=short)
    require(record['design_hash']==design_hash(saved) and record['cell_name']==TOP,'Native design identity differs.')
    stream(folder/'original.gds',model,angle,base,short=short)
    stream(folder/'layout.gds',model,angle,base,private=True,short=short)
    ref=reference_text(model,fault)
    for name in ('schematic.spice','schematic-lvs.spice'):require((folder/name).read_text()==ref,'Retained reference changed beyond the named fault.')
    require(record['reference']==dict(top=TOP,ports=list(PORTS),sha256=hashlib.sha256(ref.encode()).hexdigest()),'Reference receipt differs.')
    scripts(folder,origin,pdk);drc=magic_log(folder/'drc/console.log');magic_log(folder/'lvs-extraction/console.log')
    require(re.findall(r'^STUDIO_DRC_COUNT (\d+)$',drc,re.M)==['0'] and
            re.findall(r'^STUDIO_DRC_STYLE (.+)$',drc,re.M)==['drc(full)'] and record['drc_count']==record['magic_drc_count']==0 and
            (folder/'drc/findings.tsv').read_text()=='','Actual full DRC failed or did not complete.')
    extracted=native_circuit(folder/'lvs-extraction/extracted.spice',model,short=short)
    require((folder/'lvs-extraction/res_pair.ext').is_file(),'Missing original Magic extraction database.')
    if states[3]=='failed':
        error=stages[3].get('error','')
        require(short and error.startswith('Extracted port order differs from the schematic: ') and extracted['top_ports']!=list(PORTS) and
                not (folder/'lvs/lvs.log').exists(),'Short did not cause precisely the extracted-interface rejection.')
    else:
        settings=dict(hierarchy=True,blackbox=False,merge='none',scale=False,capacitance_threshold='infinite',resistance_threshold='infinite',distributed_resistance=False)
        require(stages[3]['evidence']==dict(deck='lvs-extraction/extracted.spice',sha256=extracted['sha256'],settings=settings),'Extraction settings/digest differ.')
        log=(folder/'lvs/lvs.log').read_text();console=(folder/'lvs/console.log').read_text();check_netgen_inputs(console,origin,pdk)
        require(not re.search(r'invalid command|could not open|cannot open|Error in|Traceback',log+console,re.I),'LVS infrastructure failed.')
        if fault:
            require(re.search(r'netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching',log,re.I),
                    'No actual native graph/property mismatch.')
            if fault=='second-reference-width':width_mismatch(log,model)
        else:
            require(re.findall(r'^Final result: (.+)$',log,re.M)==['Circuits match uniquely.'] and 'Cell pin lists are equivalent.' in log and
                    not re.search(r'Property errors|do not match|disconnected node|no matching pin|altered',log,re.I),'Native circuits do not match uniquely.')
        integrity=stages[-1]['evidence'];require(integrity['verified'] is True and integrity['assets']==assets and integrity['tools']==tools,'Native integrity binding differs.')
        file_map(folder,integrity['files'])
    return dict(detected=True,fault=fault,native=extracted,stages={r['name']:r['status'] for r in stages},report_sha256=sha(folder/'report.json'))


def runtime(root,report):
    before=load(root/'runtime-before.json');after=load(root/'runtime-after.json')
    require(before==after and report['runtime_before_sha256']==sha(root/'runtime-before.json') and
            report['runtime_after_sha256']==sha(root/'runtime-after.json'),'Captured native runtime changed.')
    require(before['profile']=='linux-x86_64-headless-icstudio-v1' and before['bytecode_cache_prefix']=='/__icstudio_li_development_no_bytecode__',
            'Unreviewed runtime profile.')
    for name,expected in LAUNCHERS.items():require(before['files'][name]['sha256']==expected,'Unreviewed native launcher.')
    for name,expected in NATIVE_TREES.items():
        actual=hashlib.sha256((json.dumps(before['trees'][name],sort_keys=True,indent=2,allow_nan=False)+'\n').encode()).hexdigest()
        require(actual==expected,'Unreviewed native Tcl/dependency tree.')
    require(before['environment']==dict(PATH='/opt/icstudio/bin:/usr/bin:/bin',HOME='/__icstudio_li_development_no_home__',LANG='C',LC_ALL='C',TZ='UTC',
        PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONHASHSEED='0'),'Native environment differs.')
    require('no_user_site=1' in before['python_flags'] and 'dont_write_bytecode=1' in before['python_flags'] and 'hash_randomization=0' in before['python_flags'],
            'Python startup identity differs.')
    tools={name:dict(path='/opt/icstudio/bin/'+name,sha256=LAUNCHERS['/opt/icstudio/bin/'+name]) for name in ('magic','netgen')}
    require(report['tools']==tools,'Native tool selection differs.')
    return tools


def audit(root,reviewed_source=None):
    root=Path(root).resolve();report=load(root/'qualification.json');manifest=load(root/'manifest.json')
    require(manifest==inventory(root,('manifest.json','audit.json')),'Complete evidence inventory differs.')
    require(report.get('schema')==1 and report.get('suite')=='sky130-metal-resistor-hierarchy-v1' and report.get('status')=='PASS' and
        all(report.get(k) is False for k in ('qualified','full_family','release_ready','signoff','installed','chunk_complete')) and
        not report.get('error') and not report.get('traceback'),'Incomplete/overclaimed hierarchy report.')
    require(re.fullmatch('[0-9a-f]{32}',report['execution_id']) and PurePosixPath(report['execution_root']).is_absolute(), 'Invalid original execution identity.')
    origin=PurePosixPath(report['execution_root']);models=report['selected_models']
    require(models and len(set(models))==len(models) and all(m in MODELS for m in models) and report['full_models']==list(MODELS),'Invalid model selection.')
    contract=load(root/'acceptance-contract.json')
    require(report['contract']==contract and report['acceptance_contract_sha256']==sha(root/'acceptance-contract.json')==CONTRACT_SHA and
        contract['models']==list(MODELS) and contract['width_um']==2 and contract['length_um']==5 and contract['child_instances']==2 and
        contract['top_ports']==list(PORTS) and contract['top_rotations']==[0,90] and contract['faults']==list(FAULTS) and contract['exchange_faults']==list(EXCHANGE) and
        contract['child_transforms']==[dict(rotation=0,mirror=False,x_nm=0,y_nm=0),dict(rotation=90,mirror=True,x_nm=40000,y_nm=0)] and contract['clean_drc_count']==0,
        'Acceptance contract differs.')
    sources=load(root/'source-files.json');require(report['source_files_sha256']==sha(root/'source-files.json') and inventory(root/'source')==sources,'Source capture differs.')
    required={'scripts/qualify_sky130_metal_resistor_hierarchy.py','scripts/audit_sky130_metal_resistor_hierarchy.py',
        'tests/test_sky130_metal_resistor_hierarchy.py','tests/test_sky130_metal_resistor_hierarchy_audit.py','examples/sky130-qualification-lock.json'}
    require(required<=sources.keys(),'Missing producer/auditor/source lock.')
    if reviewed_source is not None:
        require(all(sha(Path(reviewed_source)/name)==value for name,value in sources.items()),'Captured source differs from reviewed source.')
    package=load(root/'package.json');require(sha(root/'package.json')==PHYSICAL_SHA,'Physical package differs.')
    require(report['process']['target']=='sky130A' and report['process']['manifest_sha256']==PHYSICAL_SHA and
            report['process']['revision']==package['revision'],'Declared process identity differs.')
    pdk_files=load(root/'physical-package-files.json');require(report['physical_package_files_sha256']==sha(root/'physical-package-files.json'),'Physical inventory digest differs.')
    require(pdk_files['package.json']['sha256']==PHYSICAL_SHA and all(pdk_files[n]['sha256']==h for n,h in package['files'].items()),'Physical asset identities differ.')
    pdk=PurePosixPath(pdk_files['package.json']['resolved']).parent
    require(pdk.is_absolute() and all(PurePosixPath(pdk_files[n]['resolved'])==pdk/n for n in package['files']),'Physical files reference another root.')
    require(report['guards']==dict(source=True,physical_package=True,runtime=True),'Missing final input guards.')
    tools=runtime(root,report);require([r['model'] for r in report['cases']]==models,'Missing/duplicate case.')
    clean=faults=exchanges=0
    for model,row in zip(models,report['cases']):
        folder=root/model;require(load(folder/'record.json')==row and row['status']=='PASS' and row['execution_id']==report['execution_id'],'Case record differs.')
        generator=folder/'generator';log=(generator/'console.log').read_text()
        require(len(re.findall(r'^GENERATOR_COMPLETE$',log,re.M))==1 and not re.search(r'GENERATOR_FAILED|\d+ problems occurred|invalid command|could not open',log,re.I),'Native generator failed.')
        script=f'''tech load {{{pdk}/libs.tech/magic/sky130A.tech}}
scalegrid 1 2
source {{{pdk}/libs.tech/magic/sky130A.tcl}}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [sky130::sky130_fd_pr__res_generic_{model}_defaults] [dict create w 2 l 5 m 1 nx 1 snake 0]]
if {{[catch {{sky130::sky130_fd_pr__res_generic_{model}_draw $parameters}} err]}} {{puts stderr "GENERATOR_FAILED $err"; quit -noprompt}}
select top cell
box select
save coupon
gds write coupon.gds
puts GENERATOR_COMPLETE
quit -noprompt
'''
        require((generator/'generate.tcl').read_text()==script and (generator/'empty.magicrc').read_bytes()==b'' and (generator/'coupon.mag').is_file(),'Native leaf generator settings differ.')
        base=leaf(folder/'leaf.gds',model)
        import klayout.db as db
        generated=db.Layout();generated.read(str(generator/'coupon.gds'))
        require(generated.dbu==.001 and generated.cells()==1 and generated.top_cell().name=='coupon','Original generated stream differs.')
        same_masks(cell_regions(generated,generated.top_cell())[0],base[0])
        require([r['rotation'] for r in row['layouts']]==[0,90] and [r['fault'] for r in row['faults']]==list(FAULTS) and
            [r['fault'] for r in row['exchange_controls']]==list(EXCHANGE),'Missing orientations or controls.')
        for angle,summary in zip((0,90),row['layouts']):
            dest=folder/f'r{angle}';require(summary['execution_id']==report['execution_id'] and summary['project_sha256']==sha(dest/'saved.icproj'),'Saved orientation identity differs.')
            require(summary['geometry']==stream(dest/'input.gds',model,angle,base),'Declared stream geometry differs.')
            project(dest/'saved.icproj',model,angle,base,package)
            for name in ('export.gds','export.oas','reimported.gds'):stream(dest/name,model,angle,base)
            require(set(summary['exchange'])=={'gds','oasis','reimported'} and all(v['status']=='passed' for v in summary['exchange'].values()),'Recorded exchange failed.')
            checked=native(dest/'physical',origin/model/f'r{angle}'/'physical',pdk,model,angle,base,package,tools)
            require(summary['native']==checked['native'] and summary['report_sha256']==checked['report_sha256'],'Clean extracted summary differs.');clean+=1
        for fault,summary in zip(FAULTS,row['faults']):
            dest=folder/'r0'/fault;project(folder/'r0'/(fault+'.icproj'),model,0,base,package,short=fault==FAULTS[-1])
            checked=native(dest,origin/model/'r0'/fault,pdk,model,0,base,package,tools,fault)
            require(summary==checked,'Fault summary differs from raw result.');faults+=1
        for fault,summary in zip(EXCHANGE,row['exchange_controls']):
            path=folder/'r0'/(fault+'.gds');require(summary['rejected'] is True and summary['error'] and summary['sha256']==sha(path),'Exchange fault receipt differs.')
            stream(path,model,0,base,corruption=fault)
            try:stream(path,model,0,base)
            except ValueError:pass
            else:raise ValueError('Corrupt exchange accepted.')
            exchanges+=1
    return dict(schema=1,status='PASS',suite=report['suite'],execution_id=report['execution_id'],original_execution_root=str(origin),
        qualification_sha256=sha(root/'qualification.json'),manifest_sha256=sha(root/'manifest.json'),source_files_sha256=sha(root/'source-files.json'),
        qualified=False,full_family=False,installed=False,release_ready=False,signoff=False,chunk_complete=False,
        counts=dict(models=len(models),clean_layouts=clean,native_faults=faults,exchange_controls=exchanges),
        full_selected_models=models==list(MODELS),source_binding='captured sources matched reviewed files' if reviewed_source else 'self-contained captured source inventory',
        scope=__doc__,runtime_scope='Captured before/after reviewed runtime closure; no fresh engine execution or live post-run OS requalification.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--reviewed-source',type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=audit(args.root,args.reviewed_source);text=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.out:require(not args.out.exists(),'Use a fresh audit receipt.');args.out.write_text(text)
    print(text)


if __name__=='__main__':main()
