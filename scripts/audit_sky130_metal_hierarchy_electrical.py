"""Independent raw/deck/source readback of finite metal hierarchy integration.

Does not import the producer, regenerate physical positives or execute engines.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path,PurePosixPath,PureWindowsPath
import re
import sys
if '--source' in sys.argv:sys.path.insert(0,str(Path(sys.argv[sys.argv.index('--source')+1]).resolve()))
import icstudio
ROOT=Path(icstudio.__file__).resolve().parents[1]
CANDIDATE=Path(__file__).resolve().parents[1]
from scripts.verify_frozen_mim import require,sha,load,inventory
from scripts import audit_sky130_metal_resistor_hierarchy as physical
from scripts.audit_sky130_mim_passive_corners import verify_models
from scripts.audit_sky130_mim_mismatch_aliases import runtime_profile,native_path

CONTRACT_SHA='17447ec7c83259288e730b3f80cd6efdd0088a66f38b315def14d04e6204b20b'
EXECUTED_READER_SHA='aab0e2ca21ff33faeba3fc403e30c4ce85a0bb0f3fc0697ca454b958961b0129'
SOURCE_SHA='de53c5b24601242e64448a151eb6acf4ed2e57cf2c71d524b207f64f9b74e11b'
PHYSICAL_SHA='baf72d2878edd6952b8a30fbca6f794eca7e7f0b96aad81deee800e1939b07fa'
MODELS=('l1','m1','m2','m3','m4');SECTIONS=('tt','ll','hh','hl','lh')
PORTS=('a1','b1','a2','b2');PATHS=('app','reference','native','numeric','cross','missing','width')
FAULTS=('cross','missing','width')

def number(value):
    m=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)([u]?)',value,re.I)
    require(m is not None,'Nonliteral source coefficient.');return float(m[1])*(1e-6 if m[2] else 1)
def source_coefficients(root,spec):
    modelroot=root/'model-sources/libs.tech/ngspice'
    common=(modelroot/'sky130_fd_pr__model__r+c.model.spice').read_text()
    def literal(text,name):
        found=re.findall(r'(?im)^\s*(?:\.param\s+|\+\s*)'+re.escape(name)+r'\s*=\s*([^\s;]+)',text)
        require(len(found)==1,'Ambiguous source coefficient: '+name);return number(found[0])
    linked=load(root/'source/docs/qualification/sky130-metal-resistors-linked-v1.json')
    allcoeff={}
    for model in MODELS:
        suffix='li' if model=='l1' else model;allcoeff[model]={}
        expected=f'.model sky130_fd_pr__res_generic_{model} r tc1r = {{tc1r{model}}} tc2r = {{tc2r{model}}} rsh = {{r{model}}} dw = {{"-tol_{suffix}/2-{suffix}_dw/2"}} tnom = 30.0'
        require(common.splitlines().count(expected)==1,'Resistor primitive model changed.')
        for section in SECTIONS:
            text=(modelroot/linked['sections'][section]['include']).read_text()
            values=dict(rsh=literal(text,'r'+model),tol=literal(text,'tol_'+suffix),dw=literal(common,suffix+'_dw'),tc1=literal(common,'tc1r'+model),tc2=literal(common,'tc2r'+model))
            for name,value in values.items():require(math.isclose(value,spec['coefficients'][model][section][name],rel_tol=1e-10,abs_tol=1e-24),'Contract/source coefficient mismatch.')
            allcoeff[model][section]=values
    return allcoeff
def resistance(values,width=2):
    correction=1+values['tc1']*(-3)+values['tc2']*9
    return values['rsh']*(5e-6)/(width*1e-6+values['tol']+values['dw'])*correction
def matrix(values,tag):
    result=[[0.0]*4 for _ in range(4)]
    pairs=[(0,1,2)]
    if tag!='missing':pairs.append((0 if tag=='cross' else 2,3,3 if tag=='width' else 2))
    for a,b,w in pairs:
        conductance=1/resistance(values,w)
        result[a][a]+=conductance;result[b][b]+=conductance
        result[a][b]-=conductance;result[b][a]-=conductance
    return result
def currents(values,tag,voltage):return [sum(y*v for y,v in zip(row,voltage)) for row in matrix(values,tag)]
def raw(path,title,analysis):
    text=Path(path).read_text(encoding='ascii');require(len(re.findall(r'^Variables:',text,re.M))==len(re.findall(r'^Values:',text,re.M))==1,'Missing/extra native plot.')
    header,body=text.split('Values:\n');pre,variables=header.split('Variables:\n')
    def field(key):
        values=re.findall(r'^'+re.escape(key)+r':\s*(.*?)\s*$',pre,re.M);require(len(values)==1,'Missing/duplicate raw header.');return values[0]
    require(field('Title')==title and field('Plotname')==('AC Analysis' if analysis=='ac' else 'DC transfer characteristic'),'Raw execution/plot identity differs.')
    require(field('Flags')==('complex' if analysis=='ac' else 'real'),'Wrong raw value representation.')
    names=[]
    for i,row in enumerate(variables.splitlines()):
        fields=row.split();require((len(fields)==3 or i==0 and analysis=='ac' and len(fields)==4 and fields[-1]=='grid=3') and fields[0]==str(i),'Unordered raw variable.');names.append(fields[1].lower())
    require(len(names)==int(field('No. Variables')) and len(names)==len(set(names)),'Duplicate/missing native variables.')
    rows=[];lines=[x.split() for x in body.splitlines() if x.strip()]
    points=int(field('No. Points'));require(points==(8 if analysis=='ac' else 3) and len(lines)==points*len(names),'Wrong native sample coverage.')
    for i in range(points):
        chunk=lines[i*len(names):(i+1)*len(names)];require(len(chunk[0])==2 and chunk[0][0]==str(i) and all(len(row)==1 for row in chunk[1:]),'Native sample index/order differs.')
        values=[]
        for row in chunk:
            parts=row[-1].split(',');require(len(parts)==(2 if analysis=='ac' else 1),'Malformed raw number.')
            value=complex(*map(float,parts));require(math.isfinite(value.real) and (names[len(values)]=='frequency' or math.isfinite(value.imag)),'Nonfinite raw data.');values.append(value)
        rows.append(dict(zip(names,values)))
    return names,rows
def title(origin,nonce,case,analysis,basis):
    token=hashlib.sha256(json.dumps([origin,nonce,case,analysis,basis],separators=(',',':')).encode()).hexdigest()
    return '* metal-hierarchy-electrical '+token
def check_deck(text,spec,case,analysis,basis,networks,staged,origin,nonce,coeff):
    lines=[title(origin,nonce,case['name'],analysis,basis),staged,'.param mc_mm_switch=0 mc_pr_switch=0','.temp 27'];save=[]
    for tag in PATHS:
        lines += [f'.subckt whole_{tag} A1 B1 A2 B2']
        if tag=='numeric':
            value=resistance(coeff[case['model']][case['section']]);lines += [f'RREF1 A1 B1 {value:.17g}',f'RREF2 A2 B2 {value:.17g}']
        else:lines += [f'.include "{native_path(networks[tag]).as_posix()}"','Xwhole A1 B1 A2 B2 res_pair']
        lines += [f'.ends whole_{tag}']
        for i,port in enumerate(PORTS):
            amplitude=.001 if i==basis else 0
            if analysis=='dc' and i==basis:lines.append(f'E_{tag}_{port} {tag}_{port} 0 drive 0 1');source='e'
            else:lines.append(f'V_{tag}_{port} {tag}_{port} 0 DC {(amplitude if analysis=="dc" else 0):.17g} AC {amplitude:.17g}');source='v'
            save += [f'v({tag}_{port})',f'i({source}_{tag}_{port})']
        lines.append('X_'+tag+' '+' '.join(tag+'_'+port for port in PORTS)+' whole_'+tag)
    model=case['model'];suffix='li' if model=='l1' else model
    probes=dict(rsh='r'+model,tol='tol_'+suffix,dw=suffix+'_dw',tc1='tc1r'+model,tc2='tc2r'+model,mc_mm_switch='mc_mm_switch',mc_pr_switch='mc_pr_switch')
    for name,parameter in probes.items():lines.append(f'VPAR_{name} par_{name} 0 DC {{{parameter}}} AC {{{parameter}}}');save.append(f'v(par_{name})')
    lines += ['VDRIVE drive 0 0','.dc VDRIVE -0.001 0.001 0.001'] if analysis=='dc' else ['.ac dec 1 1k 10G']
    lines += ['.save '+' '.join(save),'.end',''];require(text=='\n'.join(lines),'Actual full-network wiring/section/stimulus/deck differs.')
def compare_saved(a,b):
    if isinstance(b,dict):
        require(isinstance(a,dict) and a.keys()==b.keys(),'Saved mapping differs.')
        for k,v in b.items():
            if k=='maximum_normalized_current_error':require(type(a[k]) in (int,float) and math.isfinite(a[k]) and math.isclose(a[k],v,rel_tol=1e-7,abs_tol=1e-10),'Saved normalized rounding summary differs.')
            else:compare_saved(a[k],v)
    elif isinstance(b,list):require(isinstance(a,list) and len(a)==len(b),'Saved coverage differs.');[compare_saved(x,y) for x,y in zip(a,b)]
    elif type(b) is float:require(type(a) in (int,float) and math.isfinite(a) and math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-14),'Saved number differs from raw data.')
    else:require(a==b,'Saved result differs.')
def receipt_maximum(spec,case,observed,actual_section=None):
    """Receipt arithmetic only; independent source/matrix gate is observations().

    The producer used frozen JSON floating literals. Source-unit parsing can
    reach a neighboring float. Reproduce only that reported summary's declared
    arithmetic here; never use this target for scientific current acceptance.
    """
    def literal_resistance(section,width):
        c=spec['coefficients'][case['model']][section];dt=spec['temperature_c']-30
        return c['rsh']*5e-6/(width*1e-6+c['tol']+c['dw'])*(1+c['tc1']*dt+c['tc2']*dt*dt)
    maximum=0.;section=actual_section or case['section'];r=literal_resistance(section,2);r3=literal_resistance(section,3);tol=spec['tolerances']
    for sample in observed['observations']:
        for tag,path in sample['paths'].items():
            v=[complex(*z) for z in path['voltages']];i=[complex(*z) for z in path['currents']]
            active_r=literal_resistance(case['section'],2) if tag=='numeric' else r
            first=(v[0]-v[1])/active_r
            if tag=='missing':target=(first,-first,0j,0j)
            else:
                second=(v[0 if tag=='cross' else 2]-v[3])/(r3 if tag=='width' else active_r)
                target=(first+second,-first,0j,-second) if tag=='cross' else (first,-first,second,-second)
            maximum=max(maximum,*(abs(z-t)/(tol['current_absolute']+tol['current_relative']*abs(t)) for z,t in zip(i,target)))
    return maximum
def observations(path,spec,case,analysis,basis,origin,nonce,coeff,actual_section=None):
    names,samples=raw(path,title(origin,nonce,case['name'],analysis,basis),analysis)
    scale='frequency' if analysis=='ac' else 'v(v-sweep)';expected_names={scale,*('v(par_'+key+')' for key in ('rsh','tol','dw','tc1','tc2','mc_mm_switch','mc_pr_switch'))}
    for tag in PATHS:
        for i,port in enumerate(PORTS):expected_names.update((f'v({tag}_{port})',f'i({"e" if analysis=="dc" and i==basis else "v"}_{tag}_{port})'))
    require(set(names)==expected_names,'Unexpected/missing raw channels.')
    actual=actual_section or case['section'];selected=coeff[case['model']][actual];intended=coeff[case['model']][case['section']]
    tolerance=spec['tolerances'];maximum=0.;detections=dict.fromkeys(FAULTS,False);record=[];zeros=kcl=0
    for index,sample in enumerate(samples):
        coordinate=sample[scale];x=10**(index+3) if analysis=='ac' else (index-1)*.001
        require(abs(coordinate-x)<=max(abs(x)*1e-10,1e-15),'Native sweep coordinate differs.')
        for key,value in {**selected,'mc_mm_switch':0,'mc_pr_switch':0}.items():
            require(abs(sample[f'v(par_{key})']-value)<=tolerance['coefficient_absolute']+tolerance['coefficient_relative']*abs(value),'Actual passive coefficient differs: '+key)
        amplitude=.001 if analysis=='ac' else x;paths={}
        for tag in PATHS:
            v=[sample[f'v({tag}_{p})'] for p in PORTS];i=[-sample[f'i({"e" if analysis=="dc" and j==basis else "v"}_{tag}_{p})'] for j,p in enumerate(PORTS)]
            require(all(abs(z-(amplitude if j==basis else 0))<=tolerance['voltage_absolute'] for j,z in enumerate(v)),'Actual clamped terminal voltage differs.')
            targets=currents(intended if tag=='numeric' else selected,tag,v)
            for z,target in zip(i,targets):
                error=abs(z-target)/(tolerance['current_absolute']+tolerance['current_relative']*abs(target));maximum=max(maximum,error)
                require(math.isfinite(error) and error<=1,'Terminal current/conductance matrix differs.');zeros += target==0
            require(abs(sum(i))<=4*tolerance['current_absolute']+tolerance['current_relative']*sum(map(abs,i)),'Whole-network KCL differs.');kcl+=1
            if tag in FAULTS:
                targets=currents(selected,'native',v);difference=max(abs(a-b) for a,b in zip(i,targets))/max(.001/resistance(selected),max(map(abs,targets)))
                detections[tag] |= difference>tolerance['fault_min_relative_difference']
            paths[tag]=dict(voltages=[[z.real,z.imag] for z in v],currents=[[z.real,z.imag] for z in i])
        record.append(dict(coordinate=[coordinate.real,coordinate.imag],paths=paths))
    return dict(samples=len(samples),maximum_normalized_current_error=maximum,detections=detections,zero_current_samples=zeros,kcl_samples=kcl,observations=record)
def fault_bytes(data,fault):
    lines=data.decode().splitlines(keepends=True);indices=[i for i,line in enumerate(lines) if re.match(r'^R\S+\s+(?:A2\s+B2|B2\s+A2)\s+',line)];require(len(indices)==1,'Wrong original occurrence.')
    i=indices[0];line=lines[i]
    if fault=='missing':del lines[i]
    else:
        m=re.search(r'\bA2\b' if fault=='cross' else r'(?i)(?<=w=)2(?=\s|$)',line);require(m is not None,'Missing control edit anchor.')
        lines[i]=line[:m.start()]+('A1' if fault=='cross' else '3')+line[m.end():]
    return ''.join(lines).encode()
def application(root,model,package,saved):
    folder=root/'applications'/model;p=load(folder/'schematic.icproj');cells={c['id']:c for c in p['cells']};require(len(cells)==2,'Wrong application hierarchy.')
    top=cells[p['top']];require(top['name']=='res_pair' and top['ports']==[p.upper() for p in PORTS] and len(top['devices'])==2,'Wrong application parent.')
    ids=[]
    for j,d in enumerate(top['devices'],1):
        require(d['kind']=='X' and d['name']==f'X{j}' and d['nets']==dict(A=f'A{j}',B=f'B{j}') and not d.get('array') and not d.get('parameters'),'Wrong application occurrence.');ids.append(d['cell'])
    require(len(set(ids))==1 and ids[0]!=p['top'],'Application must reuse one child.');leaf=cells[ids[0]]
    require(leaf['name']=='resistor_leaf' and leaf['ports']==['A','B'] and len(leaf['devices'])==1,'Wrong application leaf.')
    d=leaf['devices'][0];key='sky130_fd_pr/res_generic_'+('li' if model=='l1' else model)+'.sym';binding=package['technology']['simulation']['catalog'][key]
    require(saved==binding and binding['kind']=='PDK' and binding['prefix']=='R' and binding['model']=='sky130_fd_pr__res_generic_'+model and binding['pin_order']==['m','p'],'Wrong application catalog ABI.')
    require(d['kind']=='PDK' and d['name']=='RLEAF' and d['nets']==dict(m='A',p='B') and d['model_ref']==dict(pdk='sky130A',revision=package['revision'],device=key),'Wrong application model binding.')
    require(d['model_params']==dict(w=2,l=5,mult=1) and d['symbol']['pin_order']==['m','p'] and not d.get('array') and not d.get('parameters'),'Wrong application dimensions.')
    tech=p['pdk'];require(tech['package_lock']=={k:package[k] for k in ('id','revision','files')} and {k:v for k,v in tech.items() if k not in ('package_lock','package_root')}==package['technology'],'Wrong application package binding.')
    for c in cells.values():require(all(not c.get(k) for k in ('parameters','spice_parameters','spice_statements','shapes','layout_instances','wires','labels','junctions')),'Application has undeclared overrides.')
    require(all(not p.get(k) for k in ('global_nets','parameters','spice','xschem_exchange')),'Application has global overrides.')
    full='sky130_fd_pr__res_generic_'+model
    lines=lambda text:[x.strip() for x in text.splitlines() if x.strip() and not x.lstrip().startswith('*')]
    require(lines((folder/'application.spice').read_text())==['.subckt res_pair A1 B1 A2 B2',f'R_X1_RLEAF A1 B1 {full} l=5 m=1 w=2',f'R_X2_RLEAF A2 B2 {full} l=5 m=1 w=2','.ends res_pair'],'Actual flattened application export differs.')
    prefix=[];package_root=native_path(tech['package_root'])
    for item in package['technology']['simulation']['includes']:
        section=item.get('sections',{}).get('nominal',item.get('section'));path=(package_root/item['path']).as_posix()
        prefix.append(f'.lib "{path}" {section}' if section else f'.include "{path}"')
    require(lines((folder/'hierarchical.spice').read_text())==prefix+['.subckt resistor_leaf A B',f'R_RLEAF A B {full} l=5 m=1 w=2','.ends resistor_leaf','X1 A1 B1 resistor_leaf','X2 A2 B2 resistor_leaf','.end'],'Actual hierarchical application export differs.')
def audit(root,physical_root,reviewed_source=None):
    root=Path(root).resolve();report=load(root/'qualification.json');actual=inventory(root);actual.pop('manifest.json',None);manifest=load(root/'manifest.json');require(actual==manifest,'Evidence inventory differs.')
    require(report['schema']==1 and report['gate']=='sky130-metal-hierarchy-electrical-v1' and report['mode']=='source-integration' and report['status']=='PASS' and all(report.get(k) is False for k in ('qualified','installed','full_family','chunk_complete','release_ready','signoff')),'Failed/overclaimed evidence.')
    require(type(report['pilot']) is bool and report['source_integration_acceptance'] is (not report['pilot']),'Wrong selection acceptance scope.')
    require(report['guards']==dict(source=True,candidate=True,package=True,models=True,runtime=True,physical=True,networks=True),'Missing final input guard.')
    require(report['python']['dont_write_bytecode'] is True and report['python']['pycache_prefix'],'Missing bytecode isolation.')
    origin=report['execution_root'];nonce=report['nonce'];require(native_path(origin).is_absolute() and re.fullmatch('[0-9a-f]{32}',nonce),'Wrong original execution identity.')
    require(sha(root/'contract.json')==report['contract_sha256']==CONTRACT_SHA,'Unreviewed finite contract.');spec=load(root/'contract.json');require(report['scope']==spec['scope'],'Wrong scope.')
    require(sha(root/'source-manifest.json')==report['source_manifest_sha256']==SOURCE_SHA,'Unreviewed base snapshot.')
    base=load(root/'source-manifest.json')['files'];require(len(base)==6631,'Incomplete base snapshot.')
    sources=load(root/'source-files.json');require(sha(root/'source-files.json')==report['source_files_sha256'] and inventory(root/'source')==sources,'Captured source closure differs.')
    expected_sources={name for name in base if name.count('/')==1 and name.startswith(('icstudio/','scripts/')) and name.endswith('.py')}|set(spec['source_contracts'])
    require(set(sources)==expected_sources,'Captured source name coverage differs.')
    for name,digest in sources.items():require(base[name]==digest and (reviewed_source is None or sha(Path(reviewed_source)/name)==digest),'Source binding differs: '+name)
    candidates=load(root/'candidate-files.json');require(sha(root/'candidate-files.json')==report['candidate_files_sha256'] and inventory(root/'candidate')==candidates,'Candidate closure differs.')
    reader_name='scripts/audit_sky130_metal_hierarchy_electrical.py'
    for name,digest in candidates.items():
        if name==reader_name:require(digest in (EXECUTED_READER_SHA,sha(__file__)),'Unreviewed executed reader revision.')
        else:require(sha(CANDIDATE/name)==digest,'Reviewed candidate source differs: '+name)
    require({'scripts/audit_sky130_metal_hierarchy_electrical.py','scripts/qualify_sky130_metal_hierarchy_electrical.py','docs/qualification/sky130-metal-hierarchy-electrical-v1.json'}<=candidates.keys(),'Missing candidate implementation/reader/contract.')
    package=load(root/'package.json');require(sha(root/'package.json')==spec['simulation_package']['manifest_sha256']==sha(root/'contract-sources/package'),'Simulation package differs.')
    staged=verify_models(root,report,manifest);coeff=source_coefficients(root,spec)
    before=load(root/'runtime-before.json');require(before==load(root/'runtime-after.json') and sha(root/'runtime-before.json')==report['runtime_before_sha256'] and sha(root/'runtime-after.json')==report['runtime_after_sha256'],'Runtime changed.');runtime_profile(root,before,dict(root=origin))
    old=Path(physical_root);require(sha(old/'qualification.json')==PHYSICAL_SHA,'Different original physical evidence.');proof=physical.audit(old)
    require(load(root/'physical-readback.json')==proof and sha(root/'physical-readback.json')==report['physical_dependency']['readback_sha256'],'Historical readback differs.')
    require(report['physical_dependency']['archive_sha256']=='f160341c8a956a4ee2f6e0a60beaed9b9822fdf6202ce0b4ba7c66ffd7e65fe9' and proof['counts']['clean_layouts']==10 and proof['full_selected_models'],'Incomplete historical class.')
    for model in MODELS:application(root,model,package,report['applications'][model])
    bindings={}
    for model in MODELS:
        for rotation in (0,90):
            key=f'{model}-r{rotation}';folder=root/'networks'/key;native=(old/model/f'r{rotation}'/'physical/lvs-extraction/extracted.spice').read_bytes();physical.native_circuit(old/model/f'r{rotation}'/'physical/lvs-extraction/extracted.spice',model)
            expected={}
            for tag in ('app','reference','native',*FAULTS):
                p=root/'applications'/model/'application.spice' if tag=='app' else folder/(tag+'.spice')
                if tag=='native':require(p.read_bytes()==native,'Positive native bytes changed.')
                elif tag=='reference':require(p.read_bytes()==(old/model/f'r{rotation}'/'physical/schematic.spice').read_bytes(),'Positive reference bytes changed.')
                elif tag in FAULTS:require(p.read_bytes()==fault_bytes(native,tag),'Control changed beyond exactly one occurrence edit.')
                expected[tag]=dict(path=str(native_path(origin)/p.relative_to(root).as_posix()),sha256=sha(p))
            bindings[key]=expected
    require(report['network_bindings']==bindings,'Network binding differs.')
    full=[dict(name=f'{m}-r{r}-{s}',model=m,rotation=r,section=s) for m in MODELS for r in (0,90) for s in SECTIONS]
    selected=[c for c in full if not report['pilot'] or c['rotation']==0 and c['section']=='tt']
    require(report['full_declared_cases']==[c['name'] for c in full] and report['selected_cases']==[c['name'] for c in selected] and [c['name'] for c in report['cases']]==[c['name'] for c in selected],'Missing/duplicate/noncanonical selected cases.')
    maximum=0.;counts=dict(contexts=len(selected),native_runs=0,dc_samples=0,ac_samples=0,zero_current_samples=0,kcl_samples=0,detected_network_controls=0,wrong_section_controls=0,historical_clean_layouts=10,source_files=len(sources),candidate_files=len(candidates))
    for case,row in zip(selected,report['cases']):
        folder=root/case['name'];require(all(row[k]==v for k,v in case.items()) and row['status']=='PASS' and load(folder/'record.json')==row and not row.get('error'),'Case receipt differs.')
        require(set(row['runs'])=={f'{a}-e{i}' for a in ('dc','ac') for i in range(4)},'Missing basis/analysis coverage.')
        detected=dict.fromkeys(FAULTS,False);key=f'{case["model"]}-r{case["rotation"]}'
        for tag,saved in [*row['runs'].items(),('wrong-section',row['wrong_section'])]:
            wrong=tag=='wrong-section';analysis='ac' if wrong else tag.split('-')[0];basis=0 if wrong else int(tag[-1]);dest=folder/tag;require(saved['files']==inventory(dest),'Native run artifacts differ.')
            alternate='hh' if case['section']!='hh' else 'll';section=alternate if wrong else case['section']
            check_deck((dest/'input.cir').read_text(),spec,case,analysis,basis,{k:v['path'] for k,v in bindings[key].items()},staged[section],origin,nonce,coeff)
            invocation=load(dest/'invocation.json');command=[before['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(native_path(origin)/case['name']/tag/'result.raw'),str(native_path(origin)/case['name']/tag/'input.cir')]
            require(invocation==dict(command=command,cwd=str(native_path(origin)),environment=before['environment'],returncode=0),'Native invocation differs.')
            log=(dest/'console.log').read_text();require(log.strip() and not re.search(r'error|unknown parameter',log,re.I),'Native engine error.')
            values=observations(dest/'result.raw',spec,case,analysis,basis,origin,nonce,coeff,section)
            # Scientific values retain the independently source-derived maximum.
            receipt_values={**values,'maximum_normalized_current_error':receipt_maximum(spec,case,values,section)}
            compare_saved(saved['observed'],receipt_values)
            maximum=max(maximum,values['maximum_normalized_current_error']);counts['native_runs']+=1;counts[analysis+'_samples']+=values['samples'];counts['zero_current_samples']+=values['zero_current_samples'];counts['kcl_samples']+=values['kcl_samples']
            if wrong:
                require(saved['actual_section']==alternate and saved['requested_section']==case['section'] and saved['rejected'] is True,'Wrong-section control receipt differs.')
                try:observations(dest/'result.raw',spec,case,analysis,basis,origin,nonce,coeff)
                except ValueError as error:require(str(error)==saved['error'] and str(error).startswith('Actual passive coefficient differs:'),'Wrong-section rejection differs.')
                else:raise ValueError('Wrong section accepted.')
                counts['wrong_section_controls']+=1
            else:
                for fault in FAULTS:detected[fault] |= values['detections'][fault]
        require(all(detected.values()) and detected==row['detected'],'Real wrong network not detected.');counts['detected_network_controls']+=3
    return dict(schema=1,status='PASS',gate=report['gate'],original_execution_root=origin,nonce=nonce,qualification_sha256=sha(root/'qualification.json'),manifest_sha256=sha(root/'manifest.json'),full_declared_selection=not report['pilot'],source_integration_acceptance=not report['pilot'],qualified=False,full_family=False,installed=False,chunk_complete=False,release_ready=False,signoff=False,maximum_normalized_current_error=maximum,scientific_oracle='Independent source coefficients and incidence matrix; unchanged current/voltage/coefficient criteria.',producer_summary_arithmetic_verified=True,executed_reader_sha256=candidates[reader_name],reviewing_reader_sha256=sha(__file__),reader_revision='separate-contract-literal-receipt-v2',counts=counts,scope=spec['scope'])
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','root','physical'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--out',type=Path);a=p.parse_args();result=audit(a.root,a.physical,a.source);text=json.dumps(result,indent=2)+'\n'
    if a.out:require(not a.out.exists() and not a.out.resolve().is_relative_to(a.root.resolve()),'Use fresh external audit path.');a.out.write_text(text,encoding='utf-8')
    print(text,end='')
if __name__=='__main__':main()
