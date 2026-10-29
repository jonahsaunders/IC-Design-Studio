"""Independent written-mask/native/raw audit of bounded parallel resistor arrays.

This source integration does not qualify continuous device envelopes, array
transient/noise, matching, installed delivery, reliability or manufacturing.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path,PurePosixPath
import posixpath
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.verify_frozen_mim import require,sha,load,inventory,design_hash,file_map,relative
from scripts.audit_sky130_metal_resistors_linked import read_raw,model_resistance,transfer,normalized_error
from scripts.verify_frozen_metal_resistors import stream,same_stream,project_binding,project_geometry,native_scripts
from scripts.audit_sky130_li_case import magic_log,check_netgen_inputs
from scripts.audit_sky130_metal_resistors_linked import physical_context,compare_summary
from scripts.audit_sky130_mim_mismatch_aliases import runtime as electrical_runtime

MODELS=('l1','m1','m2','m3','m4')
LAYERS=dict(zip(MODELS,(67,68,69,70,71)))
BOUNDARIES=((.5,.5),(.5,10.),(10.,.5),(10.,10.))
ELECTRICAL_COUNTS=(2,3,16)
PORTS=('R1','R2')
STAGES=('preflight','layout_export','drc','lvs_extraction','lvs','integrity')
HISTORICAL_SIMULATION_SHA='840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe'
HISTORICAL_CONTRACT='docs/qualification/sky130-metal-resistor-parallel-v1.json'
HISTORICAL_CONTRACT_SHA='66b905bcde6cc53fd94a5408fd5ae76f71387ae41d8c7a0c5357961c6bc64472'
from scripts import sky130_contract_versions as versions
CURRENT_CONTRACT=versions.selected('parallel')
CONTRACT,CONTRACT_SHA=CURRENT_CONTRACT['path'],CURRENT_CONTRACT['sha256']
SIMULATION_SHA=CURRENT_CONTRACT['package_sha256']
FAULTS=('missing-unit','broken-branch','bus-short','one-unit-width','reference-count')
FIXED={
    'l1':dict(rsh=12.2,tol=0.,dw=17e-9,tc1=6.045e-4,tc2=-3.693e-7,tnom=30.),
    'm1':dict(rsh=.125,tol=0.,dw=-39e-9,tc1=3.179e-3,tc2=3.094e-7,tnom=30.),
    'm2':dict(rsh=.125,tol=0.,dw=-39e-9,tc1=3.161e-3,tc2=-7.272e-7,tnom=30.),
    'm3':dict(rsh=.047,tol=0.,dw=-25e-9,tc1=3.424e-3,tc2=-7.739e-7,tnom=30.),
    'm4':dict(rsh=.047,tol=0.,dw=-25e-9,tc1=3.424e-3,tc2=-7.739e-7,tnom=30.),
}
COEFFICIENTS={}
for _model,_fixed in FIXED.items():
    _layer='li' if _model=='l1' else _model
    COEFFICIENTS.update({'r'+_model:_fixed['rsh'],'tol_'+_layer:_fixed['tol'],_layer+'_dw':_fixed['dw'],
                         'tc1r'+_model:_fixed['tc1'],'tc2r'+_model:_fixed['tc2']})
COEFFICIENTS.update(mc_mm_switch=0.,mc_pr_switch=0.)


def model_closure(root,manifest,simulation_sha=SIMULATION_SHA):
    """Only relative include rewrites are permitted in the exact public models."""
    package_root=root/'original-package';require(sha(package_root/'package.json')==simulation_sha,'Array simulation package differs.')
    package=load(package_root/'package.json');files={'package.json':simulation_sha,**package['files']}
    require(load(root/'package-files.json')==files and inventory(package_root)==files,'Array original simulation closure differs.')
    mapping=load(root/'pdk-model-files.json');require(mapping and len(set(mapping.values()))==len(mapping),'Duplicate staged model mapping.')
    reverse={v:k for k,v in mapping.items()}
    require(set(mapping)=={n for n in manifest if n.startswith('pdk-models/')} and
            load(root/'staged-model-files.json')=={n[len('pdk-models/'):]:manifest[n] for n in mapping},'Array staged model inventory differs.')
    pattern=re.compile(r'''(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|'[^'\n]+'|[^\s]+)([^\n]*)''')
    for staged,original in mapping.items():
        require(original in package['files'] and staged=='pdk-models/'+hashlib.sha256((original+'\0'+package['files'][original]).encode()).hexdigest()[:24]+'.spice',
                'Unbound staged model or dependency name.')
        def rewrite(match):
            if match[1].lower()=='.lib' and not match[3].strip():return match[0]
            dependency=posixpath.normpath(posixpath.join(posixpath.dirname(original),match[2].strip('"\'')))
            require(dependency in reverse,'Missing staged model dependency.')
            return match[1]+' '+reverse[dependency]+match[3]
        expected=pattern.sub(rewrite,(package_root/relative(original)).read_bytes().decode('utf-8')).encode()
        require((root/relative(staged)).read_bytes()==expected,'Array model changed beyond include relocation.')
    selected={'tt':'\n'.join('.lib '+reverse[i['path']]+' '+i['sections']['tt'] if 'sections' in i else '.include '+reverse[i['path']]
                            for i in package['technology']['simulation']['includes'])}
    require(load(root/'selected-model-lines.json')==selected,'Array model section differs.')
    return package,selected


def electrical_observation(path,title,analysis,model,width,length,count):
    """Check all three actual paths against the fixed public primitive equation."""
    require(analysis in ('dc','ac') and model in MODELS and (width,length)==(2,5) and count in ELECTRICAL_COUNTS,
            'Electrical context is outside the predefined array selection.')
    raw=read_raw(path,title,'DC transfer characteristic' if analysis=='dc' else 'AC Analysis',complex_values=analysis=='ac')
    data=raw['values'];scale='v(v-sweep)' if analysis=='dc' else 'frequency'
    expected={scale,'v(input)',*[v for tag in ('a','n','c') for v in (f'v(in_{tag})',f'v(out_{tag})',f'i(vs_{tag})')],
              *['v(par_'+name+')' for name in COEFFICIENTS]}
    require(set(raw['names'])==expected and raw['names'][0]==scale,'Array electrical raw channel coverage differs.')
    x=[complex(v).real for v in data[scale]]
    grid=[-.001+i*.0001 for i in range(21)] if analysis=='dc' else [1000*10**(i/3) for i in range(22)]
    require(len(x)==len(grid) and all(math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12 if analysis=='dc' else 0) for a,b in zip(x,grid)),
            'Array electrical stimulus grid differs.')
    def error(actual,wanted,relative=1e-6,absolute=1e-10):
        value=normalized_error(actual,wanted,relative_tolerance=relative,absolute_tolerance=absolute)
        require(math.isfinite(value) and value<=1,'Array electrical response exceeds the fixed tolerance.')
        return value
    parameters={}
    for name,value in COEFFICIENTS.items():
        error(data['v(par_'+name+')'],[value]*len(x),1e-10,1e-24);parameters[name]=float(complex(data['v(par_'+name+')'][0]).real)
    drive=x if analysis=='dc' else [1]*len(x);error(data['v(input)'],drive)
    r=model_resistance(width,length,count,27.,FIXED[model],scale=1e-6)
    wanted=[v/(1+r) for v in x] if analysis=='dc' else [transfer(r,1,1e-9,f) for f in x]
    branches={}
    for tag in ('a','n','c'):
        vin=data[f'v(in_{tag})'];out=data[f'v(out_{tag})'];current=data[f'i(vs_{tag})']
        error(vin,drive)
        branches[tag]=dict(resistance_ohm=r,maximum_normalized_error=error(out,wanted),
            current_normalized_error=error(current,[(a-b)/r for a,b in zip(vin,out)],absolute=1e-12),
            kcl_normalized_error=error(current,[v*(1+(2j*math.pi*f*1e-9 if analysis=='ac' else 0)) for f,v in zip(x,out)],absolute=1e-12))
    return dict(raw_sha256=sha(path),analysis=analysis,samples=len(x),parameters=parameters,branches=branches)


def physical_cases():
    result=[]
    for model in MODELS:
        for w,l,counts in [(2.,5.,range(1,17)),*[(w,l,ELECTRICAL_COUNTS) for w,l in BOUNDARIES]]:
            for count in counts:
                result.append(dict(name=f'{model}-w{w:g}-l{l:g}-m{count}',model=model,width_um=w,length_um=l,multiplicity=count))
    return result


def electrical_cases():
    return [{**row,'rotation':angle} for row in physical_cases()
            if (row['width_um'],row['length_um'])==(2,5) and row['multiplicity'] in ELECTRICAL_COUNTS
            for angle in (0,90)]


def expected_geometry(model,width,length,count,rotation=0):
    """Literal independently specified straight units and two same-layer buses."""
    import klayout.db as db
    require(model in MODELS and type(count) is int and 1<=count<=16 and rotation in (0,90),'Unknown array geometry.')
    require(all(math.isfinite(v) for v in (width,length)),'Nonfinite array unit dimensions.')
    w,l=round(width*1000),round(length*1000)
    require(all(500<=v<=10000 and v%5==0 for v in (w,l)) and
            abs(width*1000-w)<1e-6 and abs(length*1000-l)<1e-6,'Unreviewed unit size/grid.')
    pitch=w+3000;cx=5*(w//10);conductor=db.Region();marker=db.Region()
    for n in range(count):
        x=n*pitch
        conductor.insert(db.Box(x,-500,x+w,l+500));marker.insert(db.Box(x,0,x+w,l))
    if count>1:
        for y in (-250,l+250):conductor.insert(db.Box(cx-200,y-200,(count-1)*pitch+cx+200,y+200))
    tr=db.ICplxTrans(1,rotation,False,0,0);layer=LAYERS[model]
    masks={(layer,20):conductor.merged().transformed(tr),(layer,13):marker.merged().transformed(tr)}
    labels=[]
    for name,y in zip(PORTS,(-250,l+250)):
        point=tr*db.Point(cx,y);labels.append(((layer,5),name,point.x,point.y))
    return masks,sorted(labels)


def array_geometry(path,model,width,length,count,rotation=0):
    found=stream(path,'coupon');expected=expected_geometry(model,width,length,count,rotation)
    same_stream(found,expected)
    layer=LAYERS[model];conductor,marker=found[0][layer,20],found[0][layer,13]
    ends=list((conductor-marker).merged().each())
    require(marker.count()==count and len(ends)==2,'Array has wrong body count or shorted/open terminal buses.')
    assigned=[]
    import klayout.db as db
    for _,_,x,y in found[1]:
        ids=[i for i,p in enumerate(ends) if p.inside(db.Point(x,y))]
        require(len(ids)==1,'Array terminal is not on exactly one bus.');assigned.extend(ids)
    require(len(set(assigned))==2,'Array ports alias the same bus.')
    return dict(sha256=sha(path),model=model,width_um=width,length_um=length,multiplicity=count,
                rotation=rotation,marker_count=count,terminal_components=2)


def text_presentation(path):
    import klayout.db as db
    layout=db.Layout();layout.read(str(path));result=[]
    require(layout.cells()==1,'Unexpected presentation hierarchy.')
    for index in layout.layer_indexes():
        info=layout.get_info(index)
        for shape in layout.top_cell().shapes(index).each():
            if not shape.is_text():continue
            t=shape.text
            result.append((info.layer,info.datatype,t.string,t.x,t.y,t.trans.angle,t.trans.is_mirror(),t.size,t.font,int(t.halign),int(t.valign)))
    return sorted(result)


def native_array(path,model,width,length,count):
    """Read each native primitive; an aggregated R with m=N is not an array proof."""
    require(model in MODELS and type(count) is int and 1<=count<=16,'Unknown native array context.')
    text=re.sub(r'\n[ \t]*\+[ \t]*',' ',Path(path).read_text())
    rows=[line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(rows)==count+2 and rows[0]==['.subckt','coupon',*PORTS] and
            rows[-1] in (['.ends'],['.ends','coupon']),'Native array unit count/interface/directives differ.')
    names=set();units=[]
    for row in rows[1:-1]:
        require(len(row) in (6,7) and re.fullmatch(r'R\S+',row[0],re.I) and row[0].lower() not in names,
                'Duplicate, malformed or non-resistor native instance.')
        names.add(row[0].lower())
        require(set(row[1:3])==set(PORTS) and row[1]!=row[2] and row[3]=='sky130_fd_pr__res_generic_'+model,
                'Native array terminal graph/model differs.')
        params={}
        for token in row[4:]:
            parts=token.split('=');require(len(parts)==2 and parts[0] not in params,'Duplicate/malformed native parameter.')
            params[parts[0]]=float(parts[1])
        require(set(params) in ({'w','l'},{'w','l','m'}) and all(math.isfinite(v) for v in params.values()) and
                params['w']==width and params['l']==length and params.get('m',1)==1,
                'Native array unit dimensions/multiplicity differ.')
        units.append(dict(name=row[0],terminals=row[1:3],model=row[3],width_um=width,length_um=length,multiplicity=1))
    return dict(sha256=sha(path),top='coupon',ports=list(PORTS),unit_count=count,units=units)


def application_reference(path,model,width,length,count):
    rows=[line.split() for line in Path(path).read_text().splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(rows)==3 and rows[0]==['.subckt','coupon',*PORTS] and rows[-1] in (['.ends'],['.ends','coupon']),
            'Application array reference has extra/missing statements.')
    row=rows[1]
    require(len(row)==7 and re.fullmatch(r'R\S+',row[0],re.I) and row[1:3]==list(PORTS) and
            row[3]=='sky130_fd_pr__res_generic_'+model,'Application array reference model/terminals differ.')
    params={}
    for token in row[4:]:
        parts=token.split('=');require(len(parts)==2 and parts[0] not in params,'Duplicate application parameter.')
        params[parts[0]]=float(parts[1])
    require(params==dict(w=width,l=length,m=count),'Application array reference dimensions/count differ.')
    return dict(sha256=sha(path),model=row[3],width_um=width,length_um=length,multiplicity=count)


def native_clean(folder,origin,pdk,row,angle,package,tools,reference):
    """Audit the actual exported array, all native stages and original execution paths."""
    folder=Path(folder);origin=PurePosixPath(origin);pdk=PurePosixPath(pdk)
    report=load(folder/'report.json');stages=report['stages']
    require([r['name'] for r in stages]==list(STAGES) and all(r['status']=='passed' for r in stages) and
            report['status']=='passed','Incomplete native clean-array verification.')
    require(report['drc_engine']==report['lvs_extractor']=='magic' and report['magic_drc_style']=='drc(full)',
            'Array native tools/style differ.')
    assets={str(pdk/name):value for name,value in package['files'].items() if name.startswith(('libs.tech/magic/','libs.tech/netgen/'))}
    require(stages[0]['evidence']['assets']==assets and stages[0]['evidence']['tools']==tools,'Native array input identity differs.')
    args=(row['model'],row['width_um'],row['length_um'],row['multiplicity'],angle)
    array_geometry(folder/'original.gds',*args);array_geometry(folder/'layout.gds',*args)
    saved=load(folder/'input.icproj');project_geometry(saved,stream(folder/'original.gds','coupon'))
    require(report['design_hash']==design_hash(saved) and report['cell_name']=='coupon','Native array saved design differs.')
    expected=Path(reference).read_bytes()
    application_reference(reference,*args[:4])
    for name in ('schematic.spice','schematic-lvs.spice'):require((folder/name).read_bytes()==expected,'Native reference differs from actual application export.')
    require(report['reference']==dict(top='coupon',ports=list(PORTS),sha256=hashlib.sha256(expected).hexdigest()),'Native array reference identity differs.')
    native_scripts(folder,origin,pdk,'coupon')
    log=magic_log(folder/'drc/console.log');magic_log(folder/'lvs-extraction/console.log')
    require(re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)==['0'] and
            re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)==['drc(full)'] and
            report['drc_count']==report['magic_drc_count']==0 and (folder/'drc/findings.tsv').read_text()=='',
            'Actual full native array DRC did not complete cleanly.')
    extraction=native_array(folder/'lvs-extraction/extracted.spice',*args[:4])
    require((folder/'lvs-extraction/coupon.ext').is_file(),'Missing original native array extraction database.')
    settings=dict(hierarchy=True,blackbox=False,merge='none',scale=False,capacitance_threshold='infinite',resistance_threshold='infinite',distributed_resistance=False)
    require(stages[3]['evidence']==dict(deck='lvs-extraction/extracted.spice',sha256=extraction['sha256'],settings=settings),
            'Array extraction settings/file binding differ.')
    log=(folder/'lvs/lvs.log').read_text();console=(folder/'lvs/console.log').read_text()
    check_netgen_inputs(console,origin,pdk)
    require(re.findall(r'^Final result: (.+)$',log,re.M)==['Circuits match uniquely.'] and 'Cell pin lists are equivalent.' in log and
            not re.search(r'Property errors|do not match|disconnected node|no matching pin|altered|invalid command|could not open|cannot open|Error in|Traceback',log+console,re.I),
            'Array native strict LVS did not match uniquely.')
    integrity=stages[-1]['evidence'];require(integrity['verified'] is True and integrity['assets']==assets and integrity['tools']==tools,
            'Array native post-execution identity differs.')
    file_map(folder,integrity['files'])
    return dict(report_sha256=sha(folder/'report.json'),native=extraction)


def fault_geometry(model,fault):
    """Exact predefined single fault applied to the nominal three-unit masks."""
    import klayout.db as db
    require(fault in FAULTS,'Unknown array fault.')
    masks,labels=expected_geometry(model,2,5,3);metal=(LAYERS[model],20);marker=(LAYERS[model],13)
    if fault=='missing-unit':
        ends=db.Region(db.Box(800,-450,11200,-50))+db.Region(db.Box(800,5050,11200,5450))
        masks[metal]-=db.Region(db.Box(10000,-500,12000,5500))-ends
        masks[marker]-=db.Region(db.Box(10000,0,12000,5000))
    elif fault=='broken-branch':masks[metal]-=db.Region(db.Box(10000,-30,12000,-20))
    elif fault=='bus-short':
        for box in ((-1200,-450,1200,-50),(-1200,-450,-800,5450),(-1200,5050,1200,5450)):
            masks[metal].insert(db.Box(*box))
    elif fault=='one-unit-width':
        masks[metal].insert(db.Box(12000,-500,13000,5500));masks[marker].insert(db.Box(12000,0,13000,5000))
    return {k:v.merged() for k,v in masks.items()},labels


def native_fault_array(path,model,fault):
    text=re.sub(r'\n[ \t]*\+[ \t]*',' ',Path(path).read_text())
    lines=[v.split() for v in text.splitlines() if v.strip() and not v.lstrip().startswith('*')]
    require(lines and lines[0][:2]==['.subckt','coupon'] and lines[-1] in (['.ends'],['.ends','coupon']),
            'Fault extraction top/directives differ.')
    header=lines[0][2:];count=2 if fault=='missing-unit' else 3
    require(len(lines)==count+2 and (header in (['R1'],['R2']) if fault=='bus-short' else header==list(PORTS)),
            'Fault native count/interface differs.')
    names=set();units=[]
    for row in lines[1:-1]:
        require(len(row) in (6,7) and re.fullmatch(r'R\S+',row[0],re.I) and row[0].lower() not in names and
                row[3]=='sky130_fd_pr__res_generic_'+model,'Fault primitive/model/name differs.')
        names.add(row[0].lower());params={}
        for token in row[4:]:
            fields=token.split('=');require(len(fields)==2 and fields[0] not in params,'Duplicate fault parameter.')
            params[fields[0]]=float(fields[1])
        require(set(params) in ({'w','l'},{'w','l','m'}) and all(math.isfinite(v) for v in params.values()) and
                params['l']==5 and params.get('m',1)==1,'Fault primitive length/multiplicity differs.')
        units.append(dict(name=row[0],terminals=row[1:3],model=row[3],width_um=params['w'],length_um=params['l']))
    require(sorted(v['width_um'] for v in units)==([2,2,3] if fault=='one-unit-width' else [2]*count),'Fault changed unexpected unit widths.')
    ordinary=[v for v in units if set(v['terminals'])==set(PORTS)]
    if fault=='bus-short':require(all(v['terminals']==header*2 for v in units),'Bus short has a wrong or floating common net.')
    elif fault=='broken-branch':
        require(len(ordinary)==2,'Broken branch did not preserve the other two units.')
        broken=next(v for v in units if v not in ordinary)
        require(len(set(broken['terminals']))==2 and len(set(broken['terminals'])&set(PORTS))==1,
                'Broken branch is not exactly one floating terminal.')
    else:require(len(ordinary)==count,'Fault unexpectedly changed parallel connectivity.')
    return dict(header=header,units=units,sha256=sha(path))


def parallel_property_mismatch(log,model,fault):
    """Netgen merges parallel properties; native per-unit parsing remains separate."""
    require(fault in ('missing-unit','one-unit-width','reference-count'),'Unknown parallel property control.')
    wanted={'missing-unit':(6.,4.),'one-unit-width':(6.,7.),'reference-count':(4.,6.)}[fault]
    pairs=re.findall(r'^[ \t]+w circuit1: (\S+)[ \t]+circuit2: (\S+)[ \t]+\(delta=[^\n]+\)$',log,re.M)
    require(len(pairs)==1 and tuple(map(float,pairs[0]))==wanted,'Parallel property control lacks exact aggregate width mismatch.')
    model_name='sky130_fd_pr__res_generic_'+model
    require(re.search(re.escape(model_name)+r':\S+ vs\. '+re.escape(model_name)+r':\S+:',log) and
            re.findall(r'^The following cells had property errors:\n ([^\n]+)$',log,re.M)==['coupon'],
            'Parallel property error is not bound to the selected model/top.')
    final=re.findall(r'^Final result: (.+)$',log,re.M)
    require(final==['Circuits match uniquely.'] and 'Property errors were found.' in log or
            final==['Top level cell failed pin matching.'] and re.search(r'Netlists match (?:with \d+ symmetries|uniquely) with property errors\.',log),
            'Parallel property control has an unrelated comparison conclusion.')


def native_fault(folder,origin,context,model,fault,reference):
    folder=Path(folder);origin=PurePosixPath(origin);record=load(folder/'report.json');stages=record['stages']
    require([v['name'] for v in stages]==list(STAGES) and record['status']=='failed' and
            record['drc_engine']==record['lvs_extractor']=='magic' and record['magic_drc_style']=='drc(full)',
            'Fault native stages/tool selection differ.')
    statuses=['passed','passed','failed' if fault=='broken-branch' else 'passed',
              'failed' if fault=='bus-short' else 'passed','not_run' if fault=='bus-short' else 'failed',
              'not_run' if fault=='bus-short' else 'passed']
    require([v['status'] for v in stages]==statuses,'Fault failed at an unrelated native stage.')
    require(stages[0]['evidence']['assets']==context['assets'] and stages[0]['evidence']['tools']==context['tools'],
            'Fault native inputs differ.')
    target=fault_geometry(model,fault)
    for name in ('original.gds','layout.gds'):same_stream(stream(folder/name,'coupon'),target)
    saved=load(folder/'input.icproj');project_geometry(saved,target)
    require(record['design_hash']==design_hash(saved) and record['cell_name']=='coupon','Fault saved geometry binding differs.')
    expected=Path(reference).read_bytes();application_reference(reference,model,2,5,2 if fault=='reference-count' else 3)
    for name in ('schematic.spice','schematic-lvs.spice'):require((folder/name).read_bytes()==expected,'Fault reference changed beyond predefined count.')
    require(record['reference']==dict(top='coupon',ports=list(PORTS),sha256=hashlib.sha256(expected).hexdigest()),'Fault reference receipt differs.')
    native_scripts(folder,origin,context['pdk'],'coupon')
    log=magic_log(folder/'drc/console.log');magic_log(folder/'lvs-extraction/console.log')
    counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)
    require(len(counts)==1 and re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)==['drc(full)'] and
            record['drc_count']==record['magic_drc_count']==int(counts[0]) and
            (int(counts[0])>0 if fault=='broken-branch' else int(counts[0])==0),'Fault DRC raw outcome differs.')
    require(bool((folder/'drc/findings.tsv').read_text().strip())==(fault=='broken-branch'),'Fault findings differ.')
    extracted=native_fault_array(folder/'lvs-extraction/extracted.spice',model,fault)
    require((folder/'lvs-extraction/coupon.ext').is_file(),'Missing fault native extraction database.')
    if fault=='bus-short':
        require(stages[3].get('error','').startswith('Extracted port order differs from the schematic: ') and
                not (folder/'lvs/lvs.log').exists(),'Bus short lacks exact extracted interface rejection.')
    else:
        settings=dict(hierarchy=True,blackbox=False,merge='none',scale=False,capacitance_threshold='infinite',resistance_threshold='infinite',distributed_resistance=False)
        require(stages[3]['evidence']==dict(deck='lvs-extraction/extracted.spice',sha256=extracted['sha256'],settings=settings),
                'Fault extraction settings/digest differ.')
        console=(folder/'lvs/console.log').read_text();log=(folder/'lvs/lvs.log').read_text()
        check_netgen_inputs(console,origin,context['pdk'])
        require(not re.search(r'invalid command|could not open|cannot open|Error in|Traceback',console+log,re.I) and
                re.search(r'netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching',log,re.I),
                'Fault has only an infrastructure failure or lacks native mismatch.')
        if fault in ('missing-unit','one-unit-width','reference-count'):parallel_property_mismatch(log,model,fault)
        integrity=stages[-1]['evidence']
        require(integrity['verified'] is True and integrity['assets']==context['assets'] and integrity['tools']==context['tools'],
                'Fault post-execution input identity differs.');file_map(folder,integrity['files'])
    native=(dict(native_header=extracted['header'],native_units=extracted['units']) if fault=='bus-short' else
            dict(sha256=extracted['sha256'],units=extracted['units']))
    return dict(name=fault,detected=True,drc_count=int(counts[0]),report_sha256=sha(folder/'report.json'),native=native)


def context_title(origin,case,analysis):
    identity=dict(execution_root=str(origin),case=case,analysis=analysis)
    return '* icstudio-metal-parallel-v1 '+hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def check_deck(path,origin,row,angle,analysis,selected):
    origin=PurePosixPath(origin);case=row['name']+'-r'+str(angle);folder=origin/'physical'/row['name']/f'r{angle}'
    r=model_resistance(2,5,row['multiplicity'],27.,FIXED[row['model']],scale=1e-6)
    lines=[context_title(origin,case,analysis),selected['tt'],'.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear',
        '.temp 27','VDRIVE input 0 DC .0005 AC 1','.subckt app_wrapper a b',f'.include {folder}/editor.spice',
        'X_BODY a b coupon','.ends app_wrapper','.subckt native_wrapper a b',f'.include {folder}/physical/lvs-extraction/extracted.spice',
        'X_BODY a b coupon','.ends native_wrapper']
    for tag,body in [('a','XA in_a out_a app_wrapper'),('n','XN in_n out_n native_wrapper'),('c',f'RC in_c out_c {r:.17g}')]:
        lines.extend([f'VS_{tag} input in_{tag} DC 0 AC 0',body,f'RL_{tag} out_{tag} 0 1',f'CL_{tag} out_{tag} 0 1n'])
    lines.extend(f'VP_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}' for key in COEFFICIENTS)
    channels=['v(input)',*[v for tag in ('a','n','c') for v in (f'v(in_{tag})',f'v(out_{tag})',f'i(vs_{tag})')],
              *['v(par_'+key+')' for key in COEFFICIENTS]]
    lines.extend(['.save '+' '.join(channels),'.dc VDRIVE -.001 .001 .0001' if analysis=='dc' else '.ac dec 3 1k 10g','.end'])
    require(Path(path).read_text()=='\n'.join(lines)+'\n','Array deck changed model/geometry/native input/stimulus/settings/context.')
    return lines[0]


def editor_project(project,package,row,angle=0,routes=None):
    """Read the actual saved device, parameter binding, shapes, ports and IDs."""
    import copy
    require(len(project['cells'])==1 and project['top']==project['cells'][0]['id'],'Unexpected editor hierarchy.')
    cell=project['cells'][0];require(cell['name']=='coupon' and cell['ports']==list(PORTS) and len(cell['devices'])==1,
            'Editor cell/device/interface differs.')
    lock=project['pdk']['package_lock']
    require({k:lock[k] for k in ('id','revision','files')}=={k:package[k] for k in ('id','revision','files')},'Editor package lock differs.')
    model=row['model'];w,l,n=row['width_um'],row['length_um'],row['multiplicity'];device=cell['devices'][0]
    key='sky130_fd_pr/res_generic_'+('li' if model=='l1' else model)+'.sym'
    require(device['kind']=='PDK' and device['model_ref']==dict(pdk='sky130A',revision=package['revision'],device=key) and
            device['nets']==dict(m='R1',p='R2') and device['model_params']==dict(w=w,l=l,mult=n),
            'Editor original model, dimensions, multiplicity or terminal mapping differs.')
    binding=project['pdk']['simulation']['catalog'][key]
    require(binding==package['technology']['simulation']['catalog'][key],'Editor model definition differs from exact package.')
    found=copy.deepcopy(project)
    if routes is not None:
        route_ids={r['id'] for r in routes}
        require([v for v in cell['shapes'] if v['id'] in route_ids]==routes,'Attached routes changed during multiplicity ECO.')
        found['cells'][0]['shapes']=[v for v in cell['shapes'] if v['id'] not in route_ids]
    project_geometry(found,expected_geometry(model,w,l,n,angle))
    shapes=found['cells'][0]['shapes'];roles=['metal_resistor:conductor','metal_resistor:marker']
    if n>1:
        roles += [f'parallel:{i}:metal_resistor:{r}' for i in range(1,n) for r in ('conductor','marker')]
        roles += ['metal_resistor:parallel_bus:m','metal_resistor:parallel_bus:p']
    require(len(shapes)==len(roles) and sorted(v['generator_role'] for v in shapes)==sorted(roles) and
            len({v['id'] for v in shapes})==len(shapes) and all(v['device_id']==device['id'] for v in shapes),
            'Editor generated unit/role identity differs.')
    pins=cell['layout_pins'];require(len(pins)==2 and {v['pin'] for v in pins}=={'m','p'} and len({v['id'] for v in pins})==2,
            'Editor pin count/identity differs.')
    import klayout.db as db
    tr=db.ICplxTrans(1,angle,False,0,0);cx=5*(round(w*1000)//10);layer_names={v['name']:(v['gds'],v['datatype']) for v in project['pdk']['layers']}
    for pin in pins:
        p=tr*db.Point(cx,-250 if pin['pin']=='m' else round(l*1000)+250)
        require(pin['point']==[p.x,p.y] and pin['device_id']==device['id'] and layer_names[pin['layer']]==(LAYERS[model],20),
                'Editor terminal anchor moved or changed layer.')
    records=cell['pdk_layouts'];require(len(records)==1 and records[0]['device_id']==device['id'],'Editor generated record differs.')
    spec=records[0]['spec'];require(spec['recipe']=='metal_resistor' and spec['model']==binding['model'] and
            spec['dimensions_nm']==dict(w=round(w*1000),l=round(l*1000)) and spec['values']==dict(w=w,l=l,mult=n),
            'Editor generated specification differs.')
    if n==1:
        require('multiplicity' not in spec and 'parallel_units' not in records[0],'Single-unit record gained array metadata.')
    else:
        require(spec['multiplicity']==n and records[0]['parallel_units']==dict(count=n,pitch_nm=round(w*1000)+3000,
                offsets_nm=[[i*(round(w*1000)+3000),0] for i in range(n)]),'Editor parallel-unit record differs.')
    return cell


def audit_qt(root,contract_sha256=None):
    """Separate source-Qt lifecycle readback; does not claim native/installed execution."""
    import copy
    root=Path(root);record=load(root/'report.json');review=versions.selected('parallel',contract_sha256)
    require(load(root/'files.json')==inventory(root,('files.json',)),'Qt evidence inventory differs.')
    require(record['schema']==1 and record['status']=='PASS' and record['mode']=='source-qt' and
            record['installed_acceptance'] is record['qualified'] is False and record['late_lock_rejections']==5 and
            [v['model'] for v in record['models']]==list(MODELS),'Qt lifecycle scope/outcome differs.')
    package_path=ROOT/'icstudio/assets/pdks/sky130A/package.json'
    require(sha(package_path)==record['simulation_manifest_sha256']==review['package_sha256'],'Qt simulation manifest differs.')
    package=load(package_path);events=0
    def content(value):
        result=copy.deepcopy({k:v for k,v in value.items() if k not in ('revision','modified')})
        # GUI commit initializes an absent empty schematic-label list.
        for cell in result['cells']:cell.setdefault('labels',[])
        return result
    for model,summary in zip(MODELS,record['models']):
        folder=root/model;initial=load(folder/'before.icproj');routes=summary['routes'];previous=initial
        row=dict(model=model,width_um=2,length_um=5,multiplicity=1)
        cell=editor_project(initial,package,row,routes=routes)
        layer=next(v['name'] for v in initial['pdk']['layers'] if (v['gds'],v['datatype'])==(LAYERS[model],20))
        expected_routes=[dict(id='route-a',kind='path',layer=layer,points=[[1000,-250],[-2000,-250]],width=400,net='R1',device_id=''),
                         dict(id='route-b',kind='path',layer=layer,points=[[1000,5250],[-2000,5250]],width=400,net='R2',device_id='')]
        require(routes==expected_routes and summary['status']=='PASS','Qt attached-route stimulus differs.')
        pins={v['pin']:v['id'] for v in cell['layout_pins']};first={v['generator_role']:v['id'] for v in cell['shapes'] if v.get('generator_role')}
        require(summary['initial_pin_ids']==pins and summary['initial_shape_roles']==first and
                [v['multiplicity'] for v in summary['events']]==[3,16,2,1],'Qt initial IDs or count sequence differ.')
        for count,event in zip((3,16,2,1),summary['events']):
            dest=folder/f'm{count}';states={k:load(dest/(k+'.icproj')) for k in ('before','requested','proposed','applied','undo','restored')}
            require(content(states['before'])==content(previous),'Qt count chain was replaced.')
            wanted=copy.deepcopy(states['before']);wanted['cells'][0]['devices'][0]['model_params']['mult']=count
            require(content(wanted)==content(states['requested']),'Qt request changed more than schematic count.')
            require(content(states['requested'])==content(states['undo']),'Qt undo failed to restore actual requested layout.')
            require(states['proposed']['cells']==states['applied']['cells']==states['restored']['cells'],
                    'Qt preview/apply/redo geometry or devices differ.')
            for kind in ('proposed','applied','restored'):
                current=editor_project(states[kind],package,{**row,'multiplicity':count},routes=routes)
                require({v['pin']:v['id'] for v in current['layout_pins']}==pins and
                        {v['generator_role']:v['id'] for v in current['shapes'] if v.get('generator_role') in first}==first,
                        'Qt regeneration lost first-unit shape or pin identity.')
            if count==3:require(content(load(dest/'late-locked.icproj'))==content(states['requested']),'Late locked layer allowed a partial apply.')
            require(event==dict(multiplicity=count,folder=f'm{count}',status='PASS',late_lock_rejected=count==3),'Qt event summary differs.')
            application_reference(dest/'application.spice',model,2,5,count);previous=states['restored'];events+=1
    return dict(schema=1,status='PASS',mode='source-qt',installed_acceptance=False,qualified=False,
                report_sha256=sha(root/'report.json'),files_sha256=sha(root/'files.json'),models=5,count_cycles=events,
                late_lock_rejections=5,scope='Actual retained preview/apply/undo/redo and attached-route source Qt integration.')


def audit(root,reviewed_source=None):
    root=Path(root).resolve();report=load(root/'qualification.json');manifest=load(root/'manifest.json');review=versions.selected('parallel',report['contract_sha256'],sha(root/'original-package/package.json'))
    require(manifest==inventory(root,('manifest.json','audit.json')),'Parallel evidence inventory differs.')
    require(report.get('schema')==1 and report.get('gate')==review['id'] and report.get('status')=='PASS' and
            report.get('mode')=='source-integration' and all(report.get(k) is False for k in
            ('qualified','installed_acceptance','full_family','chunk_complete','release_ready','signoff')) and not report.get('error'),
            'Incomplete or overclaimed array qualification.')
    execution=report['execution'];origin=PurePosixPath(execution['root'])
    require(origin.is_absolute() and str(origin)==execution['root'] and '..' not in origin.parts and
            not any(c.isspace() for c in str(origin)) and re.fullmatch('[0-9a-f]{32}',execution['nonce']),
            'Invalid original array execution identity.')
    require(type(report['pilot']) is bool,'Ambiguous pilot selection.')
    spec=load(root/'contract.json');require(sha(root/'contract.json')==report['contract_sha256']==review['sha256'] and spec['package']['manifest_sha256']==review['package_sha256'],'Changed array acceptance contract/package pair.')
    sources=load(root/'source-files.json');require(inventory(root/'source')==sources and sha(root/'source-files.json')==report['source_files_sha256'],
            'Captured array source inventory differs.')
    required={review['path'],'scripts/qualify_sky130_metal_resistor_parallel.py','scripts/audit_sky130_metal_resistor_parallel.py',
              'tests/test_sky130_metal_resistor_parallel.py','tests/test_sky130_metal_resistor_parallel_audit.py',
              'tests/gui_sky130_metal_resistor_parallel.py','icstudio/sky130_metal_resistors.py','examples/sky130-qualification-lock.json'}
    if review['sha256']==CURRENT_CONTRACT['sha256']:required.add('scripts/sky130_contract_versions.py')
    require(required<=sources.keys() and sources[review['path']]==review['sha256'],'Missing required array source identity.')
    for name,value in spec['sources'].items():require(sources.get(name)==value['sha256'],'Changed public array reference.')
    for name,value in spec['engine_sources'].items():
        path=root/'engine-reference'/relative(name)
        require(sha(path)==value['sha256'] and path.stat().st_size==value['bytes'],'Unbound primitive source/reference notice.')
    if reviewed_source is not None:
        require(all(sha(Path(reviewed_source)/relative(n))==d for n,d in sources.items()),'Captured array source differs from reviewed files.')
    require(report['guards']==dict(source=True,simulation_package=True,staged_models=True,physical_package=True,runtime=True),
            'Missing final native array input guards.')
    package,selected=model_closure(root,manifest,review['package_sha256']);context=physical_context(root,report);runtime=electrical_runtime(root,report)
    require(report['simulation_package']==spec['package'] and report['tools']=={k:v['path'] for k,v in context['tools'].items()},
            'Declared selected array inputs differ.')
    physical_package=load(root/'original-physical-package/package.json')
    selection=physical_cases()
    if report['pilot']:selection=[v for v in selection if v['model'] in ('l1','m1') and
            (v['width_um'],v['length_um'])==(2,5) and v['multiplicity'] in (3,16)]
    require(report['selected_cases']==[v['name'] for v in selection] and
            [v['name'] for v in report['physical']]==sorted(v['name'] for v in selection),'Missing/duplicate selected native array.')
    by_name={v['name']:v for v in report['physical']};clean=fault_count=0
    for row in selection:
        folder=root/'physical'/row['name'];saved=by_name[row['name']]
        require(load(folder/'record.json')==saved and saved['status']=='PASS' and all(saved[k]==v for k,v in row.items()) and
                [v['rotation'] for v in saved['layouts']]==[0,90],'Native case summary/selection differs.')
        for angle,layout in zip((0,90),saved['layouts']):
            dest=folder/f'r{angle}';require(layout['folder']==f'r{angle}','Native orientation folder differs.')
            files={'project_sha256':'editor.icproj','reference_sha256':'editor.spice','gds_sha256':'editor.gds',
                'oasis_sha256':'editor.oas','external_oasis_sha256':'external.oas','reimported_gds_sha256':'reimported.gds',
                'gds_reimported_sha256':'gds-reimported.gds','exchange_sha256':'exchange.json'}
            require(all(layout[k]==sha(dest/v) for k,v in files.items()),'Written editor/exchange file binding differs.')
            editor_project(load(dest/'editor.icproj'),package,row,angle)
            for name in ('editor.gds','gds-reimported.gds','editor.oas','external.oas','reimported.gds'):
                array_geometry(dest/name,row['model'],row['width_um'],row['length_um'],row['multiplicity'],angle)
            require(text_presentation(dest/'editor.gds')==text_presentation(dest/'gds-reimported.gds'),
                    'Native GDS text presentation changed during direct import/export.')
            checked=native_clean(dest/'physical',origin/'physical'/row['name']/f'r{angle}'/'physical',context['pdk'],row,angle,
                                 physical_package,context['tools'],dest/'editor.spice')
            units=[{k:v for k,v in u.items() if k!='multiplicity'} for u in checked['native']['units']]
            require(layout['report_sha256']==checked['report_sha256'] and layout['native_sha256']==checked['native']['sha256'] and
                    layout['native']==dict(sha256=checked['native']['sha256'],units=units),'Saved clean native summary differs.');clean+=1
        faults=list(FAULTS) if (row['width_um'],row['length_um'],row['multiplicity'])==(2,5,3) else []
        require([v['name'] for v in saved['faults']]==faults,'Missing native array fault coverage.')
        for fault,summary in zip(faults,saved['faults']):
            dest=folder/fault;reference=folder/'r0/editor.spice'
            if fault=='reference-count':
                reference=dest/'reference-editor.spice';changed=load(dest/'reference-editor.icproj');base=load(folder/'r0/editor.icproj')
                base['cells'][0]['devices'][0]['model_params']['mult']=2
                require(base==changed,'Reference-count fault changed other editor data.')
            checked=native_fault(dest/'physical',origin/'physical'/row['name']/fault/'physical',context,row['model'],fault,reference)
            require(summary==checked,'Saved fault summary differs from raw native outcome.');fault_count+=1
    electrical=[(v,a,k) for v in selection if (v['width_um'],v['length_um'])==(2,5) and v['multiplicity'] in ELECTRICAL_COUNTS
                for a in (0,90) for k in ('dc','ac')]
    require([v['name'] for v in report['electrical']]==sorted(r['name']+f'-r{a}-{k}' for r,a,k in electrical),
            'Missing/duplicate selected actual-array electrical context.')
    observed_cases={v['name']:v for v in report['electrical']};samples=0;maximum=0.
    for row,angle,analysis in electrical:
        name=row['name']+f'-r{angle}-{analysis}';folder=root/'electrical'/name;saved=observed_cases[name]
        require(load(folder/'record.json')==saved and saved['status']=='PASS' and saved['returncode']==0 and
                all(saved[k]==v for k,v in row.items() if k!='name') and saved['physical_case']==row['name'] and
                saved['rotation']==angle and saved['analysis']==analysis,'Electrical record/selection differs.')
        expected_origin=origin/'electrical'/name
        argv=[runtime['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(expected_origin/'result.raw'),str(expected_origin/'input.cir')]
        require(saved['command']==argv and saved['cwd']==str(origin) and saved['environment']==runtime['environment'],
                'Actual electrical execution context/runtime differs.')
        for key,local in (('application',PurePosixPath('physical')/row['name']/f'r{angle}'/'editor.spice'),
                          ('native',PurePosixPath('physical')/row['name']/f'r{angle}'/'physical/lvs-extraction/extracted.spice')):
            require(saved[key]==dict(path=str(origin/local),sha256=sha(root/str(local))),'Electrical array input was substituted.')
        require(saved['deck_sha256']==sha(folder/'input.cir') and saved['raw_sha256']==sha(folder/'result.raw') and
                saved['log_sha256']==sha(folder/'console.log'),'Electrical raw/deck/log digest differs.')
        require(not re.search(r'error|unknown parameter',(folder/'console.log').read_text(),re.I),'Native electrical log contains an error.')
        title=check_deck(folder/'input.cir',origin,row,angle,analysis,selected)
        observed=electrical_observation(folder/'result.raw',title,analysis,row['model'],2,5,row['multiplicity'])
        compare_summary(saved['observation'],observed);samples+=observed['samples']*3
        maximum=max(maximum,*[v[k] for v in observed['branches'].values() for k in
                    ('maximum_normalized_error','current_normalized_error','kcl_normalized_error')])
    return dict(schema=1,status='PASS',gate=report['gate'],pilot=report['pilot'],original_execution_root=str(origin),execution_id=execution['nonce'],
        qualification_sha256=sha(root/'qualification.json'),manifest_sha256=sha(root/'manifest.json'),source_files_sha256=sha(root/'source-files.json'),
        qualified=False,installed_acceptance=False,full_family=False,chunk_complete=False,release_ready=False,signoff=False,
        counts=dict(clean_layouts=clean,native_faults=fault_count,electrical_contexts=len(electrical)//2,electrical_analyses=len(electrical),
                    electrical_path_samples=samples),maximum_normalized_error=maximum,scope=__doc__,
        source_binding='captured sources matched reviewed files' if reviewed_source else 'self-contained captured source inventory')


def main():
    import argparse
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--reviewed-source',type=Path);ap.add_argument('--qt',action='store_true');ap.add_argument('--out',type=Path)
    args=ap.parse_args();result=audit_qt(args.root) if args.qt else audit(args.root,args.reviewed_source)
    text=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.out:require(not args.out.exists(),'Use a fresh independent audit receipt.');args.out.write_text(text)
    print(text)


if __name__=='__main__':main()
