"""Selected M1-M4 application/native/analytical resistor integration.

Fresh source execution. The physical coupons and finite electrical points do
not establish continuous validity, calibrated accuracy or installed signoff.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.catalog import create_device
from icstudio.engines import parse_raw
from icstudio.interchange import spice
from icstudio.model import clone, device, example, save_project
from icstudio.pdks import model_lines, stage_model_deck
from scripts import installed_mim_inputs as identity
from scripts import qualify_sky130_metal_resistor_layouts as physical
from scripts import sky130_li_resume as physical_identity
from scripts.qualify_standard_mos_layout import technology

CONTRACT = 'docs/qualification/sky130-metal-resistors-linked-v1.json'
CONTRACT_SHA = '2c0ad7e2142ec684bebe843596b84a1e6809e3f5a52195660bba8509e190c612'
KINDS = ('application', 'native', 'analytic')
PREFIX = dict(application='a', native='n', analytic='c')
ANALYSES = ('dc', 'ac', 'tran', 'noise')
sha, write, require = identity.sha, identity.write, identity.require


def contract():
    path = ROOT / CONTRACT
    require(sha(path) == CONTRACT_SHA, 'Review a changed acceptance contract before execution.')
    spec = json.loads(path.read_bytes())
    for name, row in spec['sources'].items():
        require(sha(ROOT / name) == row['sha256'], 'Contract source changed: ' + name)
    return spec


def logical_rows(spec, pilot=False):
    experiment = spec['experiment']; selected = experiment['pilot'] if pilot else experiment
    indices = selected.get('geometry_indices', range(len(experiment['geometries_um'])))
    rows = []
    for model in selected['models']:
        for g in indices:
            w, l = experiment['geometries_um'][g]
            for rotation in experiment['rotations']:
                for multiplicity in experiment['multiplicities']:
                    tag = f'{model}_g{g}_r{rotation}_m{multiplicity}'
                    rows.append(dict(tag=tag, model=model, geometry_index=g, width_um=w, length_um=l,
                                     rotation=rotation, multiplicity=multiplicity,
                                     physical_case=f'{model}-w{w:g}-l{l:g}'))
    return rows


def selection(spec, pilot=False):
    selected = spec['experiment']['pilot'] if pilot else spec['experiment']
    rows = []
    for section in selected['sections']:
        for temp in selected['temperatures_c']:
            for analysis in ANALYSES:
                rows.append(dict(section=section, temperature_c=temp, analysis=analysis, control='positive'))
            for control in spec['experiment']['context_controls']:
                rows.append(dict(section=section, temperature_c=temp, analysis='dc', control=control))
    for row in rows:
        row['name'] = f'{row["section"]}-t{row["temperature_c"]}-{row["analysis"]}-{row["control"]}'
    return rows


def branches(spec, logical, analysis, control='positive'):
    if analysis == 'noise':
        logical = [r for r in logical if r['geometry_index'] == spec['experiment']['noise_geometry_index']
                   and r['rotation'] == spec['experiment']['noise_rotation']]
    out = [{**r, 'kind': kind, 'fault': None, 'branch': PREFIX[kind] + '_' + r['tag']}
           for r in logical for kind in KINDS]
    if analysis == 'dc' and control == 'positive':
        out += [{**r, 'kind': 'application', 'fault': fault, 'branch': f'f{i}_' + r['tag']}
                for r in logical if r['multiplicity'] == 1
                for i, fault in enumerate(spec['experiment']['faults'])]
    return out


def actual_parameters(row):
    model, w, l, m = (row[k] for k in ('model', 'width_um', 'length_um', 'multiplicity'))
    if row['fault'] == 'wrong-width': w *= 1.2
    elif row['fault'] == 'wrong-length': l *= 1.2
    elif row['fault'] == 'wrong-model': model = 'm3' if model in ('m1', 'm2') else 'm1'
    elif row['fault'] == 'wrong-multiplicity': m *= 2
    return model, w, l, m


def resistance(spec, row, section, temperature, *, altered=False):
    model, w, l, m = actual_parameters(row) if altered else tuple(row[k] for k in ('model','width_um','length_um','multiplicity'))
    parameters = spec['sections'][section]['coefficients']; fixed = spec['models'][model]
    scale = spec['analytical']['global_geometry_scale']
    width = w * scale + parameters['tol_' + model] + fixed['width_correction_m']
    delta = temperature - spec['analytical']['model_reference_temperature_c']
    require(width > 0, 'Nonpositive effective resistor width.')
    return parameters['r' + model] * l * scale / width * (1 + fixed['tc1']*delta + fixed['tc2']*delta*delta) / m


def pulse(spec, t):
    e = spec['experiment']; lo, hi, delay, edge, period, width = [e[k] for k in
        ('pulse_low_v','pulse_high_v','pulse_delay_s','pulse_edge_s','pulse_period_s','pulse_width_s')]
    if t <= delay: return lo
    phase = (t-delay) % period
    if phase < edge: return lo+(hi-lo)*phase/edge
    if phase < edge+width: return hi
    if phase < 2*edge+width: return hi-(hi-lo)*(phase-edge-width)/edge
    return lo


def transient(spec, r, times):
    e = spec['experiment']; gain = e['load_ohm']/(r+e['load_ohm'])
    tau = r*gain*e['load_farad']; lo, hi, delay, edge, period, width = [e[k] for k in
        ('pulse_low_v','pulse_high_v','pulse_delay_s','pulse_edge_s','pulse_period_s','pulse_width_s')]
    knots = [(0.0,lo),(delay,lo)]
    for n in range(int(e['transient_stop_s']/period)+2):
        t = delay+n*period
        knots.extend([(t+edge,hi),(t+edge+width,hi),(t+2*edge+width,lo),(t+period,lo)])
    knots.sort(); result=[]; index=0; start=knots[0][0]; initial=gain*lo
    for t in times:
        while index+1 < len(knots) and knots[index+1][0] < t:
            end,u1=knots[index+1]; u0=knots[index][1]; dt=end-start
            if dt:
                slope=(u1-u0)/dt
                initial=gain*(u1-slope*tau)+(initial-gain*u0+gain*slope*tau)*math.exp(-dt/tau)
            index+=1; start=end
        end,u1=knots[index+1]; u0=knots[index][1]; slope=(u1-u0)/(end-start)
        dt=t-start
        result.append(gain*(u0+slope*dt-slope*tau)+(initial-gain*u0+gain*slope*tau)*math.exp(-dt/tau))
    return result


def fixture(tech, rows, analysis):
    p=example('empty'); p['pdk']=clone(tech); c=p['cells'][0]; c['name']='metal_linked'
    v=device('V','VDRIVE',0,0,value='.0005',nets={'p':'input','n':'0'}); v['source']['ac']='1'
    if analysis=='tran': v['source'].update(type='pulse',low='.0001',high='.001',period='10n',delay='1n',duty='.5')
    c['devices']=[v]
    for row in rows:
        if row['kind']!='application': continue
        tag=row['branch']; model,w,l,m=actual_parameters(row)
        d=create_device(tech,f'sky130_fd_pr/res_generic_{model}.sym','D_'+tag)
        d['model_params'].update(w=w,l=l,mult=m)
        d['nets']={'m':'0' if row['fault']=='disconnected-terminal' else 'in_'+tag,'p':'out_'+tag}
        sense=device('V','VS_'+tag,0,0,value='0',nets={'p':'input','n':'in_'+tag})
        sense['source']['ac']='0'
        c['devices'] += [sense,d,
                         device('R','RL_'+tag,0,0,value='1',nets={'p':'out_'+tag,'n':'0'},model_mode='generic'),
                         device('C','CL_'+tag,0,0,value='1n',nets={'p':'out_'+tag,'n':'0'},model_mode='generic')]
    return p


def title(execution, name):
    token=hashlib.sha256(json.dumps(dict(execution=execution,case=name),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return '* icstudio-metal-linked-v1 '+token


def read_native(path, row):
    text=Path(path).read_text(encoding='utf-8')
    interface=re.findall(r'(?im)^\s*\.subckt\s+(\S+)\s+([^\n]+)',text)
    require(interface==[('coupon','R1 R2')], 'Unexpected native resistor interface.')
    devices=[line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(('*','.'))]
    require(len(devices)==1 and len(devices[0])==6,'Expected one original native resistor.')
    values=devices[0]; require(re.fullmatch('R\\S+',values[0],re.I) and set(values[1:3])=={'R1','R2'}
        and values[3]=='sky130_fd_pr__res_generic_'+row['model'],'Wrong native resistor model/terminals.')
    parameters=dict(value.split('=',1) for value in values[4:])
    require(set(parameters)=={'w','l'} and float(parameters['w'])==row['width_um'] and float(parameters['l'])==row['length_um'], 'Wrong native dimensions.')
    require([line.split()[0].lower() for line in text.splitlines() if line.lstrip().startswith('.')]==['.subckt','.ends'], 'Unreviewed extraction directive.')
    return dict(path=str(path),sha256=sha(path),model=values[3],terminals=values[1:3],width_um=float(parameters['w']),length_um=float(parameters['l']))


def deck(spec, case, rows, application, staged, native, execution):
    section=case['section']; temperature=case['temperature_c']
    if case['control']=='wrong-section':
        sections=spec['experiment']['sections']; section=sections[(sections.index(section)+1)%len(sections)]
    if case['control']=='wrong-temperature': temperature+=17
    accuracy='.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear'
    if case['analysis']=='tran': accuracy+=' chgtol=1e-24 trtol=1'
    lines=[title(execution,case['name']),staged[section],accuracy,f'.temp {temperature}']
    lines += [line for line in application.splitlines() if line.strip() and not line.lstrip().startswith(('*','.'))]
    used={}
    for row in rows:
        tag=row['branch']
        if row['kind']=='application': continue
        lines.append(f'VS_{tag} input in_{tag} DC 0 AC 0')
        if row['kind']=='native':
            key=row['physical_case']+'-r'+str(row['rotation']); source=native[key]
            read_native(source,row)
            wrapper=key.replace('-','_').replace('.','d')
            if wrapper not in used:
                lines += [f'.subckt native_{wrapper} a b',f'.include {Path(source).as_posix()}',
                          'X_COUPON a b coupon',f'.ends native_{wrapper}']
                used[wrapper]=True
            for n in range(row['multiplicity']): lines.append(f'XN_{tag}_{n} in_{tag} out_{tag} native_{wrapper}')
        else:
            # This branch uses the independent source-derived numeric value,
            # never another invocation of the same compact resistor model.
            value=resistance(spec,row,case['section'],case['temperature_c'])
            lines.append(f'RC_{tag} in_{tag} out_{tag} {value:.17g}')
        lines += [f'RL_{tag} out_{tag} 0 1',f'CL_{tag} out_{tag} 0 1n']
    coefficients=spec['sections'][section]['coefficients']
    lines += [f'VP_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}' for name in coefficients]
    analysis=case['analysis']; channels=['v(input)']
    channels += [v for row in rows for v in (f'v(in_{row["branch"]})',f'v(out_{row["branch"]})',f'i(vs_{row["branch"]})')]
    channels += [f'v(par_{name})' for name in coefficients]
    if analysis=='noise':
        lines += ['.control','set filetype=ascii']
        for index,row in enumerate(rows):
            tag=row['branch']; lines += [f'echo BEGIN_NOISE_{tag}',f'noise v(out_{tag}) VDRIVE dec 3 1k 10g',
                f'setplot noise{index*2+1}',f'let noise_{tag} = onoise_spectrum',
                f'write noise_{tag}.raw frequency noise_{tag}',f'echo END_NOISE_{tag}']
        lines += ['quit 0','.endc']
    else:
        lines += ['.save '+' '.join(channels),dict(dc='.dc VDRIVE -.001 .001 .0001',ac='.ac dec 3 1k 10g',tran='.tran 20p 21n')[analysis]]
    return '\n'.join([*lines,'.end','']),section,temperature


def read_raw(path, expected_title, plot, names):
    header=path.read_bytes().split(b'Variables:',1)[0].decode('ascii')
    for label,value in (('title',expected_title.lower()),('plotname',plot)):
        require([line.partition(':')[2].strip() for line in header.splitlines() if line.lower().startswith(label+':')]==[value], 'Raw context or analysis differs.')
    variables, rows, complex_data=parse_raw(path)
    require(len(variables)==len(set(variables)) and set(variables)==set(names),'Unexpected raw channels.')
    require(len(rows)>1 and all(len(row)==len(variables) for row in rows),'Incomplete native samples.')
    for row in rows:
        for name,value in zip(variables,row):
            require(math.isfinite(complex(value).real) and (name=='frequency' or math.isfinite(complex(value).imag)), 'Nonfinite native sample.')
    data={name:[row[index] for row in rows] for index,name in enumerate(variables)}
    scale=variables[0]; x=[float(complex(value).real) for value in data[scale]]
    require(all(a<b for a,b in zip(x,x[1:])), 'Native coordinates are not increasing.')
    return x,data,complex_data


def normalized(actual, expected, relative, absolute):
    require(len(actual)==len(expected) and bool(actual),'Comparison shape differs.')
    return max(abs(a-b)/(absolute+relative*abs(b)) for a,b in zip(actual,expected))


def observe(spec, case, rows, folder, execution):
    analysis=case['analysis']; expected_title=title(execution,case['name']); tol=spec['tolerances']; e=spec['experiment']
    result={}; coefficients={}; total=0
    if analysis=='noise':
        for row in rows:
            tag=row['branch']; path=folder/f'noise_{tag}.raw'
            x,data,complex_data=read_raw(path,expected_title,'Noise Spectral Density Curves',['frequency','noise_'+tag])
            require(not complex_data and len(x)==22 and all(math.isclose(f,1000*10**(i/3),rel_tol=1e-10) for i,f in enumerate(x)), 'Incomplete noise frequencies.')
            r=resistance(spec,row,case['section'],case['temperature_c']); parallel=r/(1+r)
            expected=[math.sqrt(4*spec['analytical']['boltzmann_j_per_k']*(case['temperature_c']+273.15)*parallel/(1+(2*math.pi*f*parallel*1e-9)**2)) for f in x]
            actual=data['noise_'+tag]; require(all(value>0 for value in actual),'Nonpositive thermal noise.')
            error=normalized(actual,expected,tol['noise_relative'],tol['noise_absolute'])
            require(error<=1,'Analytical thermal noise mismatch: '+tag)
            result[tag]=dict(maximum_normalized_error=error,resistance_ohm=r,raw_sha256=sha(path),samples=len(x)); total+=len(x)
        return dict(branches=result,parameters={},samples=total)
    parameters=spec['sections'][case['section']]['coefficients']; scale={'dc':'v(v-sweep)','ac':'frequency','tran':'time'}[analysis]
    names=[scale,'v(input)',*[v for row in rows for v in (f'v(in_{row["branch"]})',f'v(out_{row["branch"]})',f'i(vs_{row["branch"]})')],*[f'v(par_{name})' for name in parameters]]
    x,data,complex_data=read_raw(folder/'result.raw',expected_title,dict(dc='DC transfer characteristic',ac='AC Analysis',tran='Transient Analysis')[analysis],names)
    require(complex_data==(analysis=='ac'),'Wrong raw number type.')
    if analysis=='dc': require(len(x)==21 and all(abs(t-(-.001+i*.0001))<1e-12 for i,t in enumerate(x)),'Incomplete DC sweep.')
    elif analysis=='ac': require(len(x)==22 and all(math.isclose(f,1000*10**(i/3),rel_tol=1e-10) for i,f in enumerate(x)),'Incomplete AC sweep.')
    else: require(x[0]==0 and math.isclose(x[-1],21e-9,rel_tol=1e-10),'Incomplete transient.')
    for name,value in parameters.items():
        actual=data['v(par_'+name+')']; coefficients[name]=float(complex(actual[0]).real)
        require(all(abs(v-value)<=tol['coefficient_absolute']+abs(value)*tol['coefficient_relative'] for v in actual),'Wrong effective passive coefficient: '+name)
    drive=x if analysis=='dc' else [1]*len(x) if analysis=='ac' else [pulse(spec,t) for t in x]
    require(normalized(data['v(input)'],drive,1e-9,1e-10)<=1,'Applied source differs.')
    for row in rows:
        tag=row['branch']; r=resistance(spec,row,case['section'],case['temperature_c'],altered=bool(row['fault']))
        output=data['v(out_'+tag+')']; current=data['i(vs_'+tag+')']; gain=1/(r+1)
        if row['fault']=='disconnected-terminal': expected=[0]*len(x); expected_current=[0]*len(x)
        else:
            expected=[v*gain for v in x] if analysis=='dc' else [gain/(1+2j*math.pi*f*r*gain*1e-9) for f in x] if analysis=='ac' else transient(spec,r,x)
            expected_current=[(a-b)/r for a,b in zip(data['v(in_'+tag+')'],output)]
        error=normalized(output,expected,tol[analysis+'_relative'],tol[analysis+'_absolute'])
        require(error<=1,'Analytical response mismatch: '+tag)
        require(normalized(data['v(in_'+tag+')'],drive,1e-9,1e-10)<=1,'Wrong sense-source input.')
        require(normalized(current,expected_current,tol['current_relative'],tol['current_absolute'])<=1,'Native resistor current mismatch.')
        if analysis in ('dc','ac'):
            load_current=[v*(1+(2j*math.pi*f*1e-9 if analysis=='ac' else 0)) for f,v in zip(x,output)]
            require(normalized(current,load_current,tol['current_relative'],tol['current_absolute'])<=1,'Loaded-node KCL mismatch.')
        detected=None
        if row['fault']:
            nominal=resistance(spec,row,case['section'],case['temperature_c']); target=[v/(1+nominal) for v in x]
            difference=max(abs(a-b) for a,b in zip(output,target))/max(abs(v) for v in target)
            require(difference>tol['fault_min_relative_difference'],'Electrical fault was not observable: '+tag)
            detected=difference
        result[tag]=dict(maximum_normalized_error=error,resistance_ohm=r,samples=len(x),fault_detected_relative=detected)
    return dict(branches=result,parameters=coefficients,samples=len(x)*len(rows),raw_sha256=sha(folder/'result.raw'))


def source_files():
    paths={ROOT/CONTRACT,Path(__file__),ROOT/'tests/test_sky130_metal_resistors_linked.py',
           ROOT/'scripts/audit_sky130_metal_resistors_linked.py',ROOT/'tests/test_sky130_metal_resistors_linked_audit.py',
           ROOT/'examples/sky130-qualification-lock.json'}
    paths.update(ROOT/name for name in contract()['sources'])
    paths.update((ROOT/'icstudio').rglob('*.py')); paths.update((ROOT/'scripts').glob('*.py'))
    return {path.relative_to(ROOT).as_posix():sha(path) for path in sorted(paths)}


def retain_files(mapping, output):
    for name,digest in mapping.items():
        destination=output/digest; destination.parent.mkdir(parents=True,exist_ok=True)
        if not destination.exists(): destination.write_bytes(Path(name).read_bytes())
        require(sha(destination)==digest,'Input changed during retention.')


def run(args):
    spec=contract(); require(args.workers in range(1,5),'Select one to four workers.')
    require(sys.platform=='linux','Reviewed native physical runtime requires Linux.')
    out=identity.gui.unlinked(args.out).resolve(); require(not out.exists() and not any(c.isspace() for c in str(out)),'Use a fresh native output path without whitespace.')
    out.mkdir(parents=True); started=time.monotonic(); execution=dict(root=str(out),nonce=uuid.uuid4().hex)
    report=dict(schema=1,gate=spec['id'],status='RUNNING',mode='source-integration',qualified=False,installed_acceptance=False,
                full_family=False,chunk_complete=False,release_ready=False,signoff=False,pilot=args.pilot,execution=execution,cases=[],physical=[],scope=__doc__)
    write(out/'qualification.json',report)
    try:
        (out/'contract.json').write_bytes((ROOT/CONTRACT).read_bytes())
        for name,row in spec['engine_sources'].items():
            path=args.engine_source/name; require(sha(path)==row['sha256'],'Wrong primitive reference source: '+name)
            target=out/'engine-reference'/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(path.read_bytes())
        package_root=ROOT/spec['package']['path']; package=json.loads((package_root/'package.json').read_bytes())
        require(sha(package_root/'package.json')==spec['package']['manifest_sha256'],'Simulation package changed.')
        tech=clone(package['technology']); tech.update(package_root=str(package_root),package_lock={k:package[k] for k in ('id','revision','files')})
        package_files={'package.json':sha(package_root/'package.json'),**package['files']}
        for name,digest in package_files.items():
            path=identity.gui.unlinked(package_root/name); require(sha(path)==digest,'Simulation package asset changed.')
            dest=out/'original-package'/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(path.read_bytes())
        write(out/'package-files.json',package_files)
        staged={s:stage_model_deck(tech,'\n'.join(model_lines(tech,s)),out) for s in spec['experiment']['sections']}
        write(out/'selected-model-lines.json',staged); staged_files=identity.inventory(out/'pdk-models'); write(out/'staged-model-files.json',staged_files)
        logical=logical_rows(spec,args.pilot); tools={key:str(getattr(args,key).resolve(strict=True)) for key in ('magic','netgen')}
        phys,physid=technology('sky130A',args.sky130)
        physical_files=physical_identity.tree(args.sky130)
        write(out/'physical-package-files.json',physical_files)
        for name,item in physical_files.items():
            if name.startswith('$'): continue
            if not isinstance(item,dict) or 'sha256' not in item: continue
            path=args.sky130/name
            if path.is_file():
                dest=out/'original-physical-package'/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(path.read_bytes())
        before_physical=physical_identity.runtime(tools); write(out/'physical-runtime-before.json',before_physical)
        sources=source_files(); write(out/'source-files.json',sources)
        for name,digest in sources.items():
            dest=out/'source'/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes((ROOT/name).read_bytes()); require(sha(dest)==digest,'Source changed during capture.')
        engine=identity.checked_path(args.ngspice); require(sha(engine)==spec['runtime']['ngspice_sha256'],'Unreviewed electrical engine.')
        env=identity.native_environment(dict(mode='source-pilot'),engine,out); before=identity.runtime(dict(mode='source-pilot'),engine,env)
        write(out/'runtime-before.json',before); runtime_files={**before['files'],**{v['resolved']:v['sha256'] for v in before['elf_dependencies'].values()}}
        retain_files(runtime_files,out/'runtime-assets'); write(out/'runtime-assets.json',runtime_files)
        report.update(contract_sha256=CONTRACT_SHA,source_files_sha256=sha(out/'source-files.json'),source_root=str(ROOT),simulation_package=spec['package'],
                      physical_package=physid,logical_rows=logical,selected_cases=[c['name'] for c in selection(spec,args.pilot)],
                      runtime_before_sha256=sha(out/'runtime-before.json'),physical_runtime_before_sha256=sha(out/'physical-runtime-before.json'))
        physical_out=out/'physical'; physical_out.mkdir(); native={}
        coupons={(r['model'],r['width_um'],r['length_um']) for r in logical}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(physical.case,phys,m,w,l,physical_out,tools) for m,w,l in sorted(coupons)]):
                value=future.result(); report['physical'].append(value); write(out/'qualification.json',report)
                require(value['status']=='PASS','Fresh physical coupon failed: '+value['name'])
                for angle in (0,90): native[value['name']+'-r'+str(angle)]=physical_out/value['name']/f'physical-{angle}/lvs-extraction/extracted.spice'
        write(out/'native-inputs.json',{key:dict(path=str(path),sha256=sha(path)) for key,path in native.items()})
        def execute(case):
            folder=out/case['name']; folder.mkdir(); rows=branches(spec,logical,case['analysis'],case['control'])
            project=fixture(tech,rows,case['analysis']); save_project(project,folder/'input.icproj')
            application=spice(project,project['top'],hierarchical=False); (folder/'application.spice').write_text(application,encoding='utf-8',newline='\n')
            text,section,temp=deck(spec,case,rows,application,staged,native,execution); (folder/'input.cir').write_text(text,encoding='utf-8',newline='\n')
            command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b']
            if case['analysis']!='noise': command += ['-r',str(folder/'result.raw')]
            command += [str(folder/'input.cir')]
            value={**case,'status':'RUNNING','branches':rows,'actual_section':section,'actual_temperature_c':temp,
                   'command':command,'cwd':str(out if case['analysis']!='noise' else folder),'environment':env}
            # Models are staged relative to the immutable aggregate. The noise
            # control output paths are explicit, so it uses that same cwd.
            if case['analysis']=='noise':
                text=re.sub(r'(?m)^write (noise_\S+\.raw)',lambda m:'write '+(folder/m[1]).as_posix(),text)
                (folder/'input.cir').write_text(text,encoding='utf-8',newline='\n'); value['cwd']=str(out)
            try:
                proc=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=180)
                log=proc.stdout+proc.stderr; (folder/'console.log').write_text(log,encoding='utf-8')
                require(proc.returncode==0 and 'error' not in log.lower() and 'unknown parameter' not in log.lower(),'Native simulator failed; inspect its log.')
                if case['control']=='positive': value['observation']=observe(spec,case,rows,folder,execution)
                else:
                    try: observe(spec,case,rows,folder,execution)
                    except ValueError as exc: value['detected']=str(exc)
                    else: raise ValueError('Wrong section/temperature escaped the intended-context check.')
                    # Preserve and independently inspect the actual response too;
                    # numeric analytic branches intentionally retain intended R.
                value.update(status='PASS',returncode=proc.returncode,deck_sha256=sha(folder/'input.cir'),log_sha256=sha(folder/'console.log'))
                if case['analysis']!='noise': value['raw_sha256']=sha(folder/'result.raw')
            except Exception: value.update(status='FAIL',error=traceback.format_exc())
            write(folder/'record.json',value); return value
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(execute,c) for c in selection(spec,args.pilot)]):
                value=future.result(); report['cases'].append(value); write(out/'qualification.json',report); print(value['name'],value['status'],flush=True)
        require(len(report['cases'])==len(selection(spec,args.pilot)) and all(c['status']=='PASS' for c in report['cases']),'Electrical acceptance failed.')
        after=identity.runtime(dict(mode='source-pilot'),engine,env); write(out/'runtime-after.json',after)
        after_physical=physical_identity.runtime(tools); write(out/'physical-runtime-after.json',after_physical)
        require(before==after and before_physical==after_physical,'Native runtime changed.')
        require(all(sha(ROOT/n)==d for n,d in sources.items()),'Reviewed source changed.')
        require(all(sha(package_root/n)==d for n,d in package_files.items()),'Simulation assets changed.')
        require(staged_files==identity.inventory(out/'pdk-models'),'Staged models changed.')
        require(physical_files==physical_identity.tree(args.sky130),'Physical package changed.')
        report.update(status='PASS',runtime_after_sha256=sha(out/'runtime-after.json'),physical_runtime_after_sha256=sha(out/'physical-runtime-after.json'),
                      guards=dict(source=True,simulation_package=True,staged_models=True,physical_package=True,runtime=True))
    except Exception: report.update(status='FAIL',error=traceback.format_exc())
    report['cases'].sort(key=lambda c:c['name']); report['physical'].sort(key=lambda c:c['name']); report['seconds']=time.monotonic()-started
    write(out/'qualification.json',report); write(out/'manifest.json',identity.inventory(out,('manifest.json',)))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sky130','magic','netgen','ngspice','engine-source','out'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--pilot',action='store_true'); parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    with physical_identity.controlled_environment(): report=run(args)
    print(json.dumps(dict(status=report['status'],seconds=report['seconds']),indent=2))
    if report['status']!='PASS': raise SystemExit(1)


if __name__=='__main__': main()
