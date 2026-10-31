"""Independent literal-source references and complete pw2dn native readback.

Two electrical terminals only. No physical isolation, complete RF envelope,
measured-silicon, reliability or family qualification is asserted.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sys
import time

PACKAGE='0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4'
MODEL='sky130_fd_pr__model__parasitic__rf_diode_pw2dn'
KEY='sky130_fd_pr/diode__'+MODEL+'.sym'
PREFIX='libs.tech/ngspice/icstudio-rf-pw2dn/'
POINTS=((2,2,4,8),(4,2,8,12),(10,10,100,40))
CONDITIONS=tuple((c,t) for c in ('nominal','ss','ff') for t in (-40,27,125))
FAULTS=('polarity','area','perimeter')
DERIVATIVE_HEADER=(b'* IC Design Studio derivative: add the explicit perimeter to branch dp.\n'
    b'* Original source is retained under original/. Requires stable unscaled AREA/PJ runtime behavior.\n')
INCLUDE=re.compile(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)([^\n]*)')

def require(value,message):
    if not value:raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def load(path):return json.loads(Path(path).read_bytes())

def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def inventory(root):
    result={}
    for path in sorted(Path(root).rglob('*')):
        require(not path.is_symlink() and not path.is_junction(),'Linked native evidence.')
        if path.is_file():result[path.relative_to(root).as_posix()]=sha(path)
    return result

def python_identity():
    import PySide6,PySide6.QtCore
    metadata={}
    for name in ('PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','numpy','scipy','klayout','cryptography'):
        try:
            dist=importlib.metadata.distribution(name)
            metadata[name]={'version':dist.version,'records':{str(p):sha(dist.locate_file(p)) for p in dist.files or () if str(p).endswith('.dist-info/RECORD')}}
        except importlib.metadata.PackageNotFoundError:metadata[name]={'installed':False}
    return {'executable':sys.executable,'resolved_executable':str(Path(sys.executable).resolve()),'executable_sha256':sha(sys.executable),
        'version':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,'packages':metadata,
        'package_scope':'RECORD metadata identity; actual loaded module files are separately hashed, not all installed package files.',
        'pyside_version':PySide6.__version__,'qt_version':PySide6.QtCore.qVersion(),'qtcore_sha256':sha(PySide6.QtCore.__file__)}

def modules():
    return {str(Path(m.__file__).resolve()):sha(m.__file__) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).is_file()}

def statements(text):return [x for x in text.splitlines() if x.strip() and not x.lstrip().startswith('*')]

def same_environment(left,right):
    # Windows environment keys are case-insensitive; os.environ canonicalizes
    # SystemRoot to SYSTEMROOT when passing the actual native process context.
    if os.name!='nt':return left==right
    require(len({k.upper() for k in left})==len(left) and len({k.upper() for k in right})==len(right),'Ambiguous Windows environment keys.')
    return {k.upper():v for k,v in left.items()}=={k.upper():v for k,v in right.items()}

def candidate(root):
    root=Path(root).absolute()
    def no_links(path):
        require(all(not p.is_symlink() and not p.is_junction() for p in (path,*path.parents)),'Linked candidate path.')
    no_links(root);root=root.resolve();require(sha(root/'package.json')==PACKAGE,'Wrong externally selected candidate.')
    package=load(root/'package.json')
    require(package['revision']=='47dbd4fe43bfa7e4' and len(package['files'])==433,'Wrong candidate scope.')
    for name,value in package['files'].items():
        p=root/name;no_links(p);require(p.resolve().is_relative_to(root) and sha(p)==value,'Changed candidate asset: '+name)
    return package

def staged_closure(root,package):
    """Reconstruct each captured include from original locked bytes independently."""
    expected={};mapping={};visited={};root=Path(root).resolve()
    def visit(relative):
        require(relative in package['files'],'Unlocked staged dependency: '+relative)
        if relative in visited:return visited[relative]
        name='pdk-models/'+hashlib.sha256((relative+'\0'+package['files'][relative]).encode()).hexdigest()[:24]+'.spice'
        visited[relative]=name;mapping[name]=relative
        data=(root/relative).read_bytes();parts=[]
        for line in data.splitlines(keepends=True):
            try:parts.append(line.decode('utf-8'))
            except UnicodeDecodeError:
                require(line.lstrip().startswith(b'*'),'Non-UTF8 circuit statement.');parts.append(line.decode('latin-1'))
        def replace(match):
            if match[1].lower()=='.lib' and not match[3].strip():return match[0]
            target=(root/relative).parent/match[2].strip('"\'')
            require(target.resolve().is_relative_to(root),'Escaping staged dependency.')
            rel=target.resolve().relative_to(root).as_posix()
            return match[1]+' '+visit(rel)+match[3]
        expected[name]=INCLUDE.sub(replace,''.join(parts)).encode()
        return name
    includes=[]
    for item in package['technology']['simulation']['includes']:
        includes.append((item,visit(item['path'])))
    return expected,mapping,includes

def app_lines(includes,corner,temperature,analysis,fault=None):
    lines=[]
    for item,name in includes:
        section=item.get('sections',{}).get(corner,item.get('section'))
        lines.append(('.lib '+name+' '+section) if section else '.include '+name)
    lines.append('VG drive 0 DC 0 AC 1')
    for i,(_,_,area,perim) in enumerate(POINTS):
        lines.append(f'VD{i} d{i} drive DC 0 AC 0')
        pins=f'0 d{i}' if fault=='polarity' else f'd{i} 0'
        a=f'{area*.5:g}' if fault=='area' else str(area)
        p=f'{perim*1.5:g}' if fault=='perimeter' else str(perim)
        lines.append(f'X_D{i} {pins} {MODEL} area={a} perim={p}')
    return lines+[f'.temp {temperature}', '.dc VG 0 0.6 0.025' if analysis=='dc' else '.ac dec 5 1000 1000000000','.end']

def literal_inputs(root,corner,temperature,analysis):
    root=Path(root)
    original=(root/(PREFIX+'original/'+MODEL+'.model.spice')).read_bytes()
    require(original.count(b'area = 1.0e-18')==1,'Wrong original public perimeter branch.')
    derivative=DERIVATIVE_HEADER+original.replace(b'area = 1.0e-18',b'area = 1.0e-18 pj = {perim}')
    require((root/(PREFIX+MODEL+'.model.spice')).read_bytes()==derivative,'Wrong reviewed PJ derivative.')
    primitive=MODEL.replace('rf_diode_','diode_')+'_noresistor.model.spice'
    raw=(root/(PREFIX+'original/'+primitive)).read_bytes()+b'\n'+derivative
    section='tt' if corner=='nominal' else corner
    corner_file=root/f'libs.tech/ngspice/corners/{section}/nonfet.spice'
    parameters=[line for line in corner_file.read_text().splitlines() if not line.startswith('*') and 'diode_pw2dn__' in line]
    require(len(parameters)==2,'Changed literal corner parameter count.')
    lines=['* Independent literal pw2dn source calls','.param',*parameters,'.include public-models.spice','.option scale=1u','VG drive 0 0 AC 1']
    for i,(_,_,area,perim) in enumerate(POINTS):lines += [f'VD{i} d{i} drive 0 AC 0',f'X_D{i} d{i} 0 {MODEL} area={area} perim={perim}']
    lines += [f'.temp {temperature}', '.dc VG 0 .6 .025' if analysis=='dc' else '.ac dec 5 1k 1g','.end','']
    return '\n'.join(lines),raw

def fixture_project(path,selected):
    """Bind the executed positive project to the actual saved GUI specimen."""
    project=load(path);expected=json.loads(json.dumps(selected));expected['name']='Saved GUI pw2dn native verification'
    require(len(project['cells'])==1 and len(project['cells'][0]['devices'])==7,'Wrong actual application specimen count.')
    actual=project['cells'][0]['devices'];by_name={d['name']:d for d in actual}
    require(len(by_name)==7 and len({d['id'] for d in actual})==7,'Duplicated fixture identity.')
    original=selected['cells'][0]['devices'][0]
    for name,pins,ac in [('VG',{'p':'drive','n':'0'},'1'),*[(f'VD{i}',{'p':f'd{i}','n':'drive'},'0') for i in range(3)]]:
        v=by_name[name];require(v['kind']=='V' and v['nets']==v['net_labels']==pins and str(v['value'])=='0' and
            v['source']['type']=='dc' and str(v['source']['ac'])==ac,'Changed saved application stimulus.')
    for i,(w,l,_,_) in enumerate(POINTS):
        d=by_name['D'+str(i)];want=json.loads(json.dumps(original));want.update(id='pw2dn-specimen-'+str(i),name='D'+str(i),x=400+i*400,y=300)
        want['model_params'].update(w=w,l=l);want['nets']={'d0':'d'+str(i),'d1':'0'};want['net_labels']=dict(want['nets'])
        require(d==want,'Executed saved application DUT differs from actual GUI specimen.')
    expected['cells'][0].update(devices=actual,labels=[],wires=[],junctions=[])
    require(project==expected,'Executed saved project/cell/package differs from actual GUI source.')

def matrix(raw,analysis):
    from icstudio.engines import parse_raw
    variables,rows,complex_data=parse_raw(raw)
    axis=[i*.025 for i in range(25)] if analysis=='dc' else [1000*10**(i/5) for i in range(31)]
    require(complex_data==(analysis=='ac') and len(rows)==len(axis),'Changed analysis/sample count.')
    require(len(variables)==len(set(variables)) and all(all(math.isfinite(abs(v)) for v in row) for row in rows),'Duplicate/nonfinite native matrix.')
    require(all(math.isclose(row[0].real,x,rel_tol=1e-9,abs_tol=1e-12) for row,x in zip(rows,axis)),'Changed real native coordinate.')
    # CKTacDump sets only IFvalue.rValue for frequency. OUTpData writes
    # cValue in a complex plot, including an uninitialized imaginary slot.
    # The inherited real independent coordinate is checked; all complex DUT
    # current components remain finite and are compared without alteration.
    result={}
    for i in range(3):
        name='i(vd'+str(i)+')';require(variables.count(name)==1,'Missing specimen current: '+name)
        result[name]=[row[variables.index(name)] for row in rows]
    return result

def compare(left,right,analysis):
    a,b=matrix(left,analysis),matrix(right,analysis)
    return {name:max(abs(x-y)/(1e-16+1e-6*abs(y)) for x,y in zip(a[name],b[name])) for name in b}

def completed(folder,analysis,engine,env,origin,deck_name,raw_name,behavior=False):
    from icstudio.engines import parse_raw
    folder=Path(folder);rec=load(folder/'native-invocation.json')
    fields={'schema','command','cwd','environment','timeout','status','analysis','raw_sha256','deck_sha256','returncode','console_sha256','seconds'}
    require(set(rec)==fields and rec['schema']==1 and rec['status']=='PASS' and type(rec['returncode']) is int and rec['returncode']==0,'Native return-code/schema differs.')
    require(rec['analysis']==analysis and rec['timeout']==180 and math.isfinite(rec['seconds']) and rec['seconds']>0,'Changed native timing/analysis contract.')
    prefix=[str(engine),'-n','-D','ngbehavior=hsa','-D','filetype=ascii','-b','-r'] if behavior else [str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r']
    command=rec['command'];require(command==prefix+[str(Path(origin)/raw_name),str(Path(origin)/deck_name)],'Changed full native argv/origin.')
    require(same_environment(rec['environment'],env) and rec['cwd']==str(origin),'Changed native cwd/environment.')
    deck=folder/deck_name;raw=folder/raw_name
    require(sha(deck)==rec['deck_sha256'] and sha(raw)==rec['raw_sha256'] and sha(folder/'engine.log')==rec['console_sha256'],'Changed native command input/output bytes.')
    log=(folder/'engine.log').read_text(encoding='utf-8')
    require(not re.search(r'(?im)^\s*(?:error\b|fatal\b|doAnalyses\s*:|run\s+simulation(?:\(s\)|s)?\s+aborted\b)',log),'Native console reports failure.')
    require(re.findall(r'(?im)^Circuit:\s*(.*?)\s*$',log)==[deck.read_text().splitlines()[0].casefold()] and
        re.findall(r'ASCII raw file "([^"]+)"',log)==[command[-2]],'Native console title/path differs.')
    variables,rows,_=parse_raw(raw)
    require(re.findall(r'No\. of Data Columns\s*:\s*(\d+)',log)==[str(len(variables))] and re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log)==[str(len(rows))],'Native console dimensions differ.')
    for marker in ('Total analysis time','Total elapsed time'):
        values=re.findall(re.escape(marker)+r'\s*\(seconds\)\s*=\s*([\d.eE+-]+)',log)
        require(len(values)==1 and math.isfinite(float(values[0])) and float(values[0])>=0,'Missing/duplicate completion timing.')
    if analysis!='op':matrix(raw,analysis)
    else:require(len(rows)==1 and all(all(math.isfinite(abs(v)) for v in row) for row in rows),'Incomplete behavior matrix.')
    return raw,deck

def measured_guard(folder,engine,env,origin):
    from icstudio.engines import parse_raw
    from icstudio.diode_runtime import deck,validate,AC_CASES
    paths=list(Path(folder).glob('rf-runtime-*/rf-acceptance.json'))
    require(len(paths)==1,'Missing/duplicate automatic runtime guard.')
    root=paths[0].parent;accept=load(paths[0]);report=load(root/'report.json')
    guard_origin=Path(origin)/root.name
    require(accept['status']=='PASS' and accept['circuit_rewritten'] is False and accept['calls'] and report['status']=='PASS' and
        report['engine_sha256']==sha(engine) and type(report['exit']) is int and report['exit']==0 and report['behavior']['mode']=='unscaled-explicit-area','Wrong measured guard identity/status.')
    require((root/'input.cir').read_bytes()==deck('unscaled-explicit-area').encode(),'Changed analytical guard deck.')
    require(report['relative_tolerance']==1e-6 and report['absolute_tolerance_a']==1e-18,'Changed analytical guard tolerances.')
    require(report['command']==[str(engine),'-n','-D','ngbehavior=hsa','-b','input.cir'],'Changed analytical guard argv.')
    log=(root/'engine.log').read_text()
    require(not re.search(r'(?im)^\s*(?:error\b|fatal\b|doAnalyses\s*:|run\s+simulation(?:\(s\)|s)?\s+aborted\b)',log) and
        len(re.findall(r'(?im)^ngspice-\S+ done\s*$',log))==1,'Analytical guard log lacks healthy completion.')
    names=('op','dc',*AC_CASES)
    require([r['name'] for r in report['checks']]==list(names),'Missing/duplicate guard raw observations.')
    for name,row in zip(names,report['checks']):
        raw=root/(name+'.raw');read=validate(*parse_raw(raw),name)
        require(row==dict(name=name,**read,raw_sha256=sha(raw)),'Analytical guard raw verdict differs.')
    behavior=load(root/'diode-geometry-probe/behavior.json')
    require(behavior==report['behavior'] and behavior['mode']=='unscaled-explicit-area','Behavior profile differs.')
    variables,rows,cplx=parse_raw(root/'diode-geometry-probe/out.raw')
    require(not cplx and len(rows)==1 and all(math.isfinite(x) for x in rows[0]),'Incomplete behavior raw.')
    vals=dict(zip(variables,rows[0]));ratio=vals['i(va)']/vals['i(vb)'];require(math.isclose(ratio,1e12,rel_tol=1e-5),'Wrong actual AREA scaling.')
    require(behavior['currents']==vals and behavior['area_ratio']==ratio and behavior['engine']=={'path':str(engine),'sha256':sha(engine)},'Behavior raw/identity fields differ.')
    behavior_deck='''* Explicit-area versus width/length level-3 behavior
.option scale=1e-6 gmin=1e-30
.model probe_d D level=3 is=1e-12
Va a 0 1
Vb b 0 1
Da 0 a probe_d area=1e12
Db 0 b probe_d w=1e6 l=1e6
.op
.save i(va) i(vb)
.end
'''
    require((root/'diode-geometry-probe/input.cir').read_bytes()==behavior_deck.encode(),'Changed actual behavior input deck.')
    completed(root/'diode-geometry-probe','op',engine,env,guard_origin/'diode-geometry-probe','input.cir','out.raw',behavior=True)

def reference_inventory(root):
    return {k:v for k,v in inventory(root).items() if k not in ('expected-inputs.json','verification.json','files.json','failure.json')}

def reference_identity(root,engine,expected):
    from icstudio.acceptance_runtime import runtime
    require(sha(Path(root)/'reference-report.json')==expected['reference_report_sha256'] and reference_inventory(root)==expected['reference_inventory'],'Independent reference external inventory differs.')
    report=load(Path(root)/'reference-report.json');require(report['schema']=='pw2dn-independent-references-v1' and report['status']=='PASS_REFERENCE_PRODUCTION_ONLY','Incomplete literal reference production.')
    env=dict(expected['runtime']['environment']);origin=Path(expected['reference_origin'])/'environment'
    env.update(HOME=str(origin/'empty-home'),USERPROFILE=str(origin/'empty-home'),TMP=str(origin/'temporary'),TEMP=str(origin/'temporary'))
    require(report['native_environment']==env,'Independent reference environment differs from trusted execution origin.')
    baseline=dict(expected['runtime']);baseline['environment']=env
    require(report['runtime_before']==report['runtime_after']==baseline,'Independent reference runtime differs.')
    binding={'mode':'installed' if expected['mode']=='installed' else 'source-pilot','resource_root':expected.get('resource_root','')}
    require(runtime(binding,engine,env)==baseline,'Actual independent reference runtime changed.')
    require(report['python_before']==report['python_after']==python_identity(),'Independent reader Python environment changed.')
    require(all(Path(p).is_file() and sha(p)==value for p,value in report['python_modules_before'].items()),'Independent loaded Python module changed.')
    return env

def source_identity(expected):
    root=Path(expected['source_root']).resolve()
    require(bool(expected['source_files']) and bool(expected['reader_files']),'Missing explicit source/reader closure.')
    for name,value in expected['source_files'].items():
        path=root/name;require(path.resolve().is_relative_to(root) and sha(path)==value,'Changed externally selected source file: '+name)
    for name,value in expected['reader_files'].items():require(sha(name)==value,'Changed externally selected reader file.')
    if expected['mode']=='installed':
        from scripts.installed_mim_inputs import candidate_sources
        candidate_sources(expected['source_files'],expected['commit'])

def readback(native_root,gui_root,engine,expected,reference_root):
    native_root,gui_root,reference_root=map(Path,(native_root,gui_root,reference_root));engine=Path(engine).resolve()
    require(expected['mode'] in ('source','installed'),'Unknown native evidence mode.')
    source_identity(expected)
    require(sha(native_root/'report.json')==expected['native_report_sha256'] and inventory(native_root)==expected['native_inventory'],'Native externally captured inventory differs.')
    report=load(native_root/'report.json');package=candidate(expected['candidate_root'])
    statuses=('PASS_NATIVE_PRODUCTION_ONLY',) if expected['mode']=='installed' else ('PASS_NATIVE_PRODUCTION_ONLY','PASS_SOURCE_NATIVE_PRODUCTION_ONLY')
    require(expected['package_manifest_sha256']==PACKAGE and report['schema']=='pw2dn-native-producer-v1' and report['status'] in statuses,'Wrong candidate/native report.')
    conditions=CONDITIONS[:1] if expected.get('pilot') is True and expected['mode']=='source' else CONDITIONS
    require(report['execution_id']==expected['execution_id'] and report['frozen'] is (expected['mode']=='installed') and report['conditions']==[list(c) for c in conditions] and
        report['geometries']==[list(p) for p in POINTS] and report['faults']==list(FAULTS) and report['application_runs']==5*len(conditions),'Changed native finite selection/provenance.')
    require(report['engine']==str(engine) and sha(engine)==report['engine_sha256']==expected['engine_sha256'] and report['runtime_before']==report['runtime_after']==expected['runtime'],'Native runtime identity differs.')
    require(report['native_environment']==expected['runtime']['environment'],'Native environment differs.')
    from icstudio.acceptance_runtime import runtime
    binding={'mode':'installed' if expected['mode']=='installed' else 'source-pilot','resource_root':expected.get('resource_root','')}
    require(runtime(binding,engine,expected['runtime']['environment'])==expected['runtime'],'Actual selected native runtime changed.')
    gui=load(gui_root/'report.json');require(sha(gui_root/'report.json')==expected['gui_report_sha256'] and
        sha(gui_root/'new/project.icproj')==report['selected_project_sha256']==expected['selected_project_sha256'] and
        sha(gui_root/'new/schematic.spice')==expected['selected_export_sha256'],'Actual GUI inputs differ.')
    require(report['selected_project']==expected['selected_project'] and report.get('resource_root')==expected['resource_root'],'Selected project/resource origin differs.')
    from icstudio.model import digest
    selected=load(gui_root/'new/project.icproj');lock={k:package[k] for k in ('id','revision','files')};lock['manifest_hash']=digest(package)
    require(selected['pdk']['package_lock']==gui['new']['package_lock']==lock,'Actual GUI candidate lock differs.')
    require(len(selected['cells'])==1 and len(selected['cells'][0]['devices'])==1,'Wrong saved GUI specimen count.')
    dut=selected['cells'][0]['devices'][0]
    require(dut['model_ref']=={'pdk':'sky130A','revision':package['revision'],'device':KEY} and dut['nets']=={'d0':'A','d1':'K'} and
        {k:float(v) for k,v in dut['model_params'].items()}=={'w':4.,'l':2.},'Saved actual GUI specimen differs.')
    # The GUI reader separately verifies the complete GUI export/lock/history.
    if expected['mode']=='installed':
        require(re.fullmatch('[0-9a-f]{40}',expected['commit']) and report['build']==gui['build'] and report['build']['frozen'] is True and
            report['build']['dirty'] is False and report['build']['commit']==expected['commit'],'Installed native build identity differs.')
        require(Path(expected['resource_root'])==Path(expected['executable']).parent/'_internal' and engine.parent==Path(expected['resource_root'])/'icstudio/assets/runtime/ngspice','Native resource/engine escaped executable.')
        require(sha(expected['gui_verification_path'])==expected['gui_verification_sha256'],'Actual GUI verification file changed.')
        gui_verdict=load(expected['gui_verification_path'])
        require(gui_verdict['status']=='PASS_FROZEN_GUI_LIFECYCLE_ONLY' and gui_verdict['report_sha256']==expected['gui_report_sha256'],'Actual GUI verification verdict differs.')
        py=report['python_before'];require(py==report['python_after'],'Embedded Python receipt changed.')
        require(py['resolved_executable']==str(Path(expected['executable']).resolve()) and py['executable_sha256']==sha(expected['executable']),'Embedded executable identity differs.')
        before,after=report['python_modules_before'],report['python_modules_after'];require(bool(before) and all(after.get(p)==value for p,value in before.items()),'Embedded loaded-module receipts differ.')
        for path,value in after.items():
            actual=Path(path);require((actual.resolve().is_relative_to(Path(expected['resource_root']).resolve()) or actual.resolve()==Path(expected['executable']).resolve()) and sha(actual)==value,'Embedded loaded module escaped/changed.')
        qt=[value for p,value in before.items() if Path(p).name.casefold().startswith('qtcore.')]
        shiboken=[value for p,value in before.items() if Path(p).name.casefold().startswith('shiboken.')]
        require(qt==[py['qtcore_sha256']] and shiboken==[py['shiboken_sha256']],'Embedded Qt/Shiboken bytes differ.')
    elif 'build' in report:require(report['build']==expected['build'],'Source native build receipt differs.')
    reference_env=reference_identity(reference_root,engine,expected)
    closure,mapping,includes=staged_closure(expected['candidate_root'],package)
    checks=[]
    require([(r['corner'],r['temperature_c']) for r in report['cases']]==list(conditions),'Missing/duplicate native cases.')
    for row in report['cases']:
        corner,temp=row['corner'],row['temperature_c'];folder=native_root/(corner+'-'+str(temp));refbase=reference_root/folder.name
        require(row['analyses']==['dc','ac'] and row['faults']==list(FAULTS),'Wrong per-case matrix.')
        for analysis,fault,rel in [('dc',None,'dc/application'),('ac',None,'ac/application'),*[( 'dc',f,f) for f in FAULTS]]:
            dest=folder/rel
            if fault is None:fixture_project(dest/'input.icproj',selected)
            origin=Path(expected['native_origin'])/folder.name/rel
            raw,deck=completed(dest,analysis,engine,expected['runtime']['environment'],origin,'fault.cir' if fault else 'input.cir','deck.raw' if fault else 'result.raw')
            require(statements(deck.read_text())==app_lines(includes,corner,temp,analysis,fault),'Changed complete actual application deck/stimulus/section.')
            require(load(dest/'pdk-model-files.json')==mapping and {p.relative_to(dest).as_posix():sha(p) for p in (dest/'pdk-models').rglob('*') if p.is_file()}==
                {name:hashlib.sha256(data).hexdigest() for name,data in closure.items()},'Changed actual staged model closure.')
            measured_guard(dest,engine,expected['runtime']['environment'],origin)
            ref=refbase/analysis/'independent';expected_deck,expected_models=literal_inputs(expected['candidate_root'],corner,temp,analysis)
            require((ref/'reference.cir').read_bytes()==expected_deck.encode() and (ref/'public-models.spice').read_bytes()==expected_models,'Changed independent literal model/corner/stimulus.')
            ref_origin=Path(expected['reference_origin'])/folder.name/analysis/'independent'
            reference_raw,_=completed(ref,analysis,engine,reference_env,ref_origin,'reference.cir','deck.raw')
            measured_guard(ref,engine,reference_env,ref_origin)
            errors=compare(raw,reference_raw,analysis)
            require(all(v>1 for v in errors.values()) if fault else all(v<=1 for v in errors.values()),'Native per-specimen current comparison failed: '+str((corner,temp,analysis,fault,errors)))
            checks.append({'corner':corner,'temperature_c':temp,'analysis':analysis,'fault':fault,'errors':errors})
    actual_invocations=[load(p) for p in native_root.rglob('native-invocation.json')]
    declared=report['invocations']
    require(len(declared)==len(actual_invocations)==10*len(conditions) and
        sorted(declared,key=lambda r:r['cwd'])==sorted(actual_invocations,key=lambda r:r['cwd']),'Native report invocation summary differs from actual captured receipts.')
    return {'status':'PASS_FROZEN_NATIVE_ELECTRICAL' if expected['mode']=='installed' else 'PASS_SOURCE_NATIVE_ELECTRICAL','conditions':len(conditions),
        'geometries':3,'application_runs':5*len(conditions),'literal_runs':2*len(conditions),'detected_faulted_instances':9*len(conditions),
        'qualified':False,'chunk_complete':False,'scope':__doc__,'checks':checks,
        'native_python_scope':'Installed executable and reported file-backed modules are byte-bound; embedded interpreter/version and RECORD metadata strings remain producer observations. Source prelaunch identity has its separately stated scope; virtual PYZ modules are excluded from the file list.'}

def verify(native_root,gui_root,engine,expected,reference_out):
    """Required external stage: produce literals, then read all actual evidence."""
    from icstudio.acceptance_runtime import native_environment,runtime
    from icstudio import engines
    native_root,gui_root,out=map(lambda p:Path(p).resolve(),(native_root,gui_root,reference_out));engine=Path(engine).resolve()
    require(not out.exists(),'Use a new independent reference directory.')
    require(inventory(native_root)==expected['native_inventory'] and sha(native_root/'report.json')==expected['native_report_sha256'],'Native evidence changed before reference execution.')
    source_identity(expected)
    candidate(expected['candidate_root']);require(sha(engine)==expected['engine_sha256'],'Selected simulator changed.')
    out.mkdir(parents=True);started=time.monotonic();binding={'mode':'installed' if expected['mode']=='installed' else 'source-pilot','resource_root':expected.get('resource_root','')}
    environment=out/'environment';environment.mkdir();env=native_environment(binding,engine,environment)
    before=runtime(binding,engine,env);expected_runtime=dict(expected['runtime']);expected_runtime['environment']=env
    require(before==expected_runtime,'Independent reference runtime differs from prelaunch runtime.')
    py=python_identity();loaded=modules();report={'schema':'pw2dn-independent-references-v1','status':'RUNNING','native_environment':env,'runtime_before':before,'python_before':py,'python_modules_before':loaded,'cases':[]}
    write(out/'reference-prelaunch.json',report);oldenv=dict(os.environ);original=engines.execute
    def capture(command,cwd,*args,**kwargs):
        tick=time.monotonic();record={'schema':1,'command':list(map(str,command)),'cwd':str(cwd),'environment':kwargs.get('env') or dict(os.environ),'timeout':kwargs.get('timeout',180),'status':'RUNNING'}
        try:
            log=original(command,cwd,*args,**kwargs);(Path(cwd)/'engine.log').write_bytes(log.encode('utf-8'))
            raw=Path(record['command'][record['command'].index('-r')+1]);deck=Path(record['command'][-1]);text=deck.read_text()
            analysis='ac' if re.search(r'(?im)^\.ac\b',text) else 'dc' if re.search(r'(?im)^\.dc\b',text) else 'op'
            record.update(status='PASS',returncode=0,analysis=analysis,raw_sha256=sha(raw),deck_sha256=sha(deck),console_sha256=sha(Path(cwd)/'engine.log'))
            return log
        except BaseException as exc:record.update(status='FAIL',error=repr(exc));raise
        finally:record['seconds']=time.monotonic()-tick;write(Path(cwd)/'native-invocation.json',record)
    try:
        os.environ.clear();os.environ.update(env);engines.execute=capture
        selected=load(gui_root/'new/project.icproj');conditions=CONDITIONS[:1] if expected.get('pilot') is True and expected['mode']=='source' else CONDITIONS
        for corner,temp in conditions:
            for analysis in ('dc','ac'):
                dest=out/(corner+'-'+str(temp))/analysis/'independent';dest.mkdir(parents=True)
                text,models=literal_inputs(expected['candidate_root'],corner,temp,analysis)
                (dest/'public-models.spice').write_bytes(models);(dest/'reference.cir').write_bytes(text.encode())
                result=engines.run_deck(selected,selected['top'],{'deck':str(dest/'reference.cir'),'analysis':{'type':analysis}},str(engine),dest)
                write(dest/'result.json',result);report['cases'].append({'corner':corner,'temperature_c':temp,'analysis':analysis})
        report.update(status='PASS_REFERENCE_PRODUCTION_ONLY',runtime_after=runtime(binding,engine,env),python_after=python_identity(),python_modules_after=modules())
        require(report['runtime_after']==before and report['python_after']==py and all(sha(p)==v for p,v in loaded.items()),'Independent runtime/Python closure changed.')
        write(out/'reference-report.json',report)
        audit_expected={**expected,'reference_origin':str(out),'reference_report_sha256':sha(out/'reference-report.json'),'reference_inventory':reference_inventory(out)}
        write(out/'expected-inputs.json',audit_expected)
        verdict=readback(native_root,gui_root,engine,audit_expected,out)
        verdict.update(seconds=time.monotonic()-started,expected=audit_expected,reference_report_sha256=sha(out/'reference-report.json'),reader_sha256=sha(__file__))
        write(out/'verification.json',verdict);write(out/'files.json',inventory(out));return verdict
    except BaseException as exc:
        write(out/'failure.json',{'status':'FAIL','error':repr(exc),'seconds':time.monotonic()-started});raise
    finally:engines.execute=original;os.environ.clear();os.environ.update(oldenv)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('native-root','gui-root','engine','expected','reference-out','source'):p.add_argument('--'+name,required=True)
    a=p.parse_args();sys.path.insert(0,str(Path(a.source).resolve()))
    result=verify(a.native_root,a.gui_root,a.engine,load(a.expected),a.reference_out)
    print(json.dumps({k:result[k] for k in ('status','seconds','conditions')},indent=2))
