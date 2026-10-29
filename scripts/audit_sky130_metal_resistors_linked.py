"""Independent readback for the selected SKY130 M1--M4 linked experiment.

Native layout/model integration and sampled compact-model equations are distinct
from foundry validity, silicon accuracy, statistical or installed qualification.
"""
import cmath
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import posixpath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.audit_sky130_mim_mismatch_aliases import load, inventory, relative, require, sha

MODELS = ('m1', 'm2', 'm3', 'm4')
SECTIONS = ('tt', 'll', 'hh', 'hl', 'lh')
KINDS = ('application', 'native', 'analytic')
HISTORICAL_CONTRACT='docs/qualification/sky130-metal-resistors-linked-v1.json'
HISTORICAL_CONTRACT_SHA='2c0ad7e2142ec684bebe843596b84a1e6809e3f5a52195660bba8509e190c612'
from scripts import sky130_contract_versions as versions
CURRENT_CONTRACT=versions.selected('metal')
CONTRACT,CONTRACT_SHA=CURRENT_CONTRACT['path'],CURRENT_CONTRACT['sha256']


def read_raw(path, title, plot, *, complex_values=False):
    """Read one exact ASCII plot; never use the producer's parser or summaries."""
    text = Path(path).read_bytes().decode('ascii').replace('\r\n', '\n')
    require(text.count('\nVariables:\n') == text.count('\nValues:\n') == 1, 'Missing or duplicate raw plot.')
    header, tail = text.split('\nVariables:\n'); table, body = tail.split('\nValues:\n')
    def field(name):
        found = re.findall('^' + re.escape(name) + r':\s*(.*)$', header, re.M)
        require(len(found) == 1, 'Missing or duplicate raw field: '+name)
        return found[0].strip()
    require(field('Title') == title.lower(), 'Raw execution/context title differs.')
    require(field('Plotname') == plot and field('Flags') == ('complex' if complex_values else 'real'), 'Raw analysis/value kind differs.')
    nvars, npoints = int(field('No. Variables')), int(field('No. Points'))
    require(1 <= nvars <= 4096 and 1 <= npoints <= 1000000, 'Unbounded raw dimensions.')
    names, types = [], []
    entries = [line.split() for line in table.splitlines() if line.strip()]
    require(len(entries) == nvars, 'Truncated raw variable table.')
    for index, entry in enumerate(entries):
        require(len(entry) == 3 or (index == 0 and len(entry) == 4 and entry[3] == 'grid=3'), 'Unexpected raw variable fields.')
        require(entry[0] == str(index) and entry[1] not in names, 'Duplicate/out-of-order raw channel.')
        names.append(entry[1]); types.append(entry[2])
    rows = [line.split() for line in body.splitlines() if line.strip()]
    require(len(rows) == nvars*npoints, 'Incomplete/extra native samples.')
    values = {name: [] for name in names}
    for index, row in enumerate(rows):
        channel, sample = index % nvars, index // nvars
        require(len(row) == (2 if channel == 0 else 1) and (channel != 0 or row[0] == str(sample)), 'Raw sample index differs.')
        if complex_values:
            parts = row[-1].split(','); require(len(parts) == 2, 'Malformed complex sample.')
            value = complex(*map(float, parts))
            require(math.isfinite(value.real) and (channel == 0 and names[0] == 'frequency' or math.isfinite(value.imag)), 'Nonfinite physical sample.')
        else:
            value = float(row[-1]); require(math.isfinite(value), 'Nonfinite native sample.')
        values[names[channel]].append(value)
    return dict(names=names, types=types, points=npoints, values=values)


def model_resistance(width, length, multiplier, temperature, parameters, *, scale=1):
    """Literal primitive-R dimensions; explicit scale only, no inferred units."""
    require(all(math.isfinite(v) for v in (width,length,multiplier,temperature,scale)) and
            min(width,length,multiplier,scale)>0 and temperature>-273.15, 'Invalid resistor context.')
    dw = -(parameters['tol'] + parameters['dw']) / 2
    denominator = width*scale - 2*dw
    require(denominator > 0, 'Invalid primitive resistor geometry.')
    delta = temperature - parameters['tnom']
    factor = 1 + parameters['tc1']*delta + parameters['tc2']*delta*delta
    result = parameters['rsh']*length*scale/denominator*factor/multiplier
    require(math.isfinite(result) and result>0, 'Nonpositive source-defined resistance.')
    return result


def transfer(resistance, load, capacitance, frequency):
    return 1 / (1 + resistance/load + 2j*math.pi*frequency*resistance*capacitance)


def noise_density(resistance, load, capacitance, frequency, temperature, boltzmann):
    parallel = 1/(1/resistance + 1/load)
    return math.sqrt(4*boltzmann*(temperature+273.15)*parallel/(1+(2*math.pi*frequency*parallel*capacitance)**2))


def pulse_value(time, pulse):
    if time < pulse['delay']: return pulse['low']
    phase = (time-pulse['delay']) % pulse['period']
    low, high, rise, width, fall = [pulse[k] for k in ('low','high','rise','width','fall')]
    if phase < rise: return low+(high-low)*phase/rise
    if phase < rise+width: return high
    if phase < rise+width+fall: return high+(low-high)*(phase-rise-width)/fall
    return low


def transient_response(times, resistance, load, capacitance, pulse):
    """Exact piecewise-linear input solution, independent of SPICE integration."""
    require(times and times[0]>=0 and all(a<b for a,b in zip(times,times[1:])), 'Invalid transient coordinate order.')
    require(min(resistance,load,capacitance,pulse['period'],pulse['rise'],pulse['fall'])>0 and
            pulse['delay']>=0 and pulse['width']>=0 and pulse['rise']+pulse['width']+pulse['fall']<=pulse['period'], 'Invalid pulse network.')
    count = max(0, math.ceil((times[-1]-pulse['delay'])/pulse['period'])+1)
    require(count <= 10000, 'Unbounded transient duration.')
    breaks = {0.0}
    for cycle in range(count):
        base = pulse['delay']+cycle*pulse['period']
        breaks.update(base+x for x in (0,pulse['rise'],pulse['rise']+pulse['width'],pulse['rise']+pulse['width']+pulse['fall']))
    knots = sorted(set(times) | {v for v in breaks if 0<=v<=times[-1]})
    tau = capacitance/(1/resistance+1/load); gain = load/(load+resistance)
    previous, state = 0.0, gain*pulse_value(0,pulse)
    result = {0.0:state}
    for t in knots:
        if t == 0: continue
        dt=t-previous; u0=pulse_value(previous,pulse); u1=pulse_value(t,pulse)
        one_minus_exp=-math.expm1(-dt/tau)
        state=state*(1-one_minus_exp)+gain*(u0*one_minus_exp+(u1-u0)/dt*(dt-tau*one_minus_exp))
        result[t]=state; previous=t
    return [result[t] for t in times]


def normalized_error(actual, expected, *, relative_tolerance, absolute_tolerance):
    require(len(actual)==len(expected) and actual and relative_tolerance>=0 and absolute_tolerance>0, 'Comparison coverage differs.')
    values = []
    for left,right in zip(actual,expected):
        require(all(math.isfinite(v) for v in (complex(left).real,complex(left).imag,complex(right).real,complex(right).imag)), 'Nonfinite comparison.')
        values.append(abs(left-right)/(absolute_tolerance+relative_tolerance*abs(right)))
    return max(values)


def native_resistor(path, model, width, length):
    """Accept the real unmodified two-terminal extraction, not a reconstructed R."""
    require(model in MODELS, 'Unknown metal resistor model.')
    text=Path(path).read_text(encoding='utf-8')
    lines=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(lines)==3 and lines[0].split()==['.subckt','coupon','R1','R2'] and
            lines[2].split() in (['.ends'],['.ends','coupon']), 'Native interface/directives differ.')
    row=lines[1].split()
    require(len(row)==6 and re.fullmatch(r'R\S+',row[0],re.I) and set(row[1:3])=={'R1','R2'} and
            row[3]=='sky130_fd_pr__res_generic_'+model, 'Native model or connectivity differs.')
    parameters={}
    for token in row[4:]:
        pair=token.split('=');require(len(pair)==2 and pair[0] not in parameters,'Duplicate/malformed native parameter.')
        parameters[pair[0]]=float(pair[1])
    require(parameters==dict(w=width,l=length), 'Native width/length differs.')
    return dict(model=row[3],terminals=row[1:3],width_um=width,length_um=length,sha256=sha(path))


def physical_geometry(path, model, width, length, rotation):
    from scripts.audit_sky130_li_case import stream
    import klayout.db as db
    require(model in MODELS and rotation in (0,90), 'Unknown physical case.')
    masks,labels=stream(path); gds=68+MODELS.index(model)
    require(set(masks)=={(gds,20),(gds,13)}, 'Unexpected metal resistor masks.')
    conductor,marker=masks[(gds,20)],masks[(gds,13)]
    box=marker.bbox()
    require(marker.count()==1 and marker.area()==box.area() and box.center()==db.Point(0,0), 'Nonrectangular or displaced resistor marker.')
    expected=(round(width*1000),round(length*1000))
    if rotation:expected=expected[::-1]
    require((box.width(),box.height())==expected, 'Mask-derived width/length/orientation differs.')
    require(conductor.count()==1 and conductor.area()==conductor.bbox().area() and
            (marker-conductor).is_empty(), 'Interrupted or nonrectangular native conductor.')
    ends=(conductor-marker).merged()
    require(ends.count()==2, 'Native resistor must have two distinct terminal landings.')
    require(len(labels)==2 and {row[1] for row in labels}=={'R1','R2'} and
            all(row[0]==(gds,5) for row in labels), 'Native terminal names/purposes differ.')
    islands=list(ends.each())
    assigned=[]
    for _,name,x,y in labels:
        located=[i for i,poly in enumerate(islands) if poly.inside(db.Point(x,y))]
        require(len(located)==1, 'Terminal lies outside its conductor landing.')
        assigned.append(located[0])
        # Generator R1 is the lower landing; a90-degree rotation moves it right.
        require((y<box.bottom if name=='R1' else y>box.top) if rotation==0 else
                (x>box.right if name=='R1' else x<box.left), 'Terminal orientation differs.')
    require(len(set(assigned))==2, 'Native terminals share a conductor island.')
    return masks,labels


def selection(spec, pilot):
    require(type(pilot) is bool, 'Selection mode must be explicit.')
    e=spec['experiment']; chosen=e['pilot'] if pilot else e
    logical=[]; contexts=[]
    for model in chosen['models']:
        for g in chosen.get('geometry_indices',range(len(e['geometries_um']))):
            w,l=e['geometries_um'][g]
            for rotation in (0,90):
                for m in (1,3):
                    logical.append(dict(tag=f'{model}_g{g}_r{rotation}_m{m}',model=model,geometry_index=g,
                        width_um=w,length_um=l,rotation=rotation,multiplicity=m,physical_case=f'{model}-w{w:g}-l{l:g}'))
    for section in chosen['sections']:
        for temperature in chosen['temperatures_c']:
            for analysis,control in [(a,'positive') for a in ('dc','ac','tran','noise')]+[('dc',c) for c in ('wrong-section','wrong-temperature')]:
                contexts.append(dict(section=section,temperature_c=temperature,analysis=analysis,control=control,
                                     name=f'{section}-t{temperature}-{analysis}-{control}'))
    return logical,contexts


def branches(logical, case):
    selected=[r for r in logical if case['analysis']!='noise' or (r['geometry_index']==1 and r['rotation']==0)]
    result=[{**r,'kind':kind,'fault':None,'branch':prefix+'_'+r['tag']}
            for r in selected for kind,prefix in zip(KINDS,('a','n','c'))]
    if case['analysis']=='dc' and case['control']=='positive':
        result += [{**r,'kind':'application','fault':fault,'branch':f'f{i}_'+r['tag']}
                   for r in selected if r['multiplicity']==1 for i,fault in enumerate(
                   ('wrong-width','wrong-length','wrong-model','wrong-multiplicity','disconnected-terminal'))]
    return result


def actual(row):
    model,w,l,m=[row[k] for k in ('model','width_um','length_um','multiplicity')]
    if row['fault']=='wrong-width':w*=1.2
    elif row['fault']=='wrong-length':l*=1.2
    elif row['fault']=='wrong-model':model='m3' if model in ('m1','m2') else 'm1'
    elif row['fault']=='wrong-multiplicity':m*=2
    return model,w,l,m


def resistance(spec,row,section,temperature,altered=True):
    model,w,l,m=actual(row) if altered else [row[k] for k in ('model','width_um','length_um','multiplicity')]
    fixed=spec['models'][model]; coefficients=spec['sections'][section]['coefficients']
    return model_resistance(w,l,m,temperature,dict(rsh=coefficients['r'+model],tol=coefficients['tol_'+model],
        dw=fixed['width_correction_m'],tc1=fixed['tc1'],tc2=fixed['tc2'],tnom=30),scale=1e-6)


def context_title(execution, name):
    require(set(execution)=={'root','nonce'} and PurePosixPath(execution['root']).is_absolute() and
            re.fullmatch('[0-9a-f]{32}',execution['nonce']), 'Invalid native execution identity.')
    return '* icstudio-metal-linked-v1 '+hashlib.sha256(json.dumps(dict(execution=execution,case=name),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def same_lines(actual_text, expected):
    """Literal circuits with numeric spelling tolerance, never extra directives."""
    found=[line.split() for line in actual_text.splitlines() if line.strip()]
    wanted=[line.split() for line in expected if line.strip()]
    require(len(found)==len(wanted),'Extra or missing circuit statements.')
    for left,right in zip(found,wanted):
        require(len(left)==len(right),'Circuit statement arity differs.')
        for a,b in zip(left,right):
            if a==b:continue
            try:
                ka,va=a.split('=',1) if '=' in a else ('',a)
                kb,vb=b.split('=',1) if '=' in b else ('',b)
                av,bv=float(va),float(vb)
            except ValueError: raise ValueError('Circuit model, terminal, context or directive differs: '+a+' != '+b)
            require(ka==kb and math.isfinite(av) and math.isfinite(bv) and math.isclose(av,bv,rel_tol=1e-14,abs_tol=0),
                    'Circuit numeric parameter differs.')


def application_lines(rows, analysis):
    lines=['VDRIVE input 0 '+('PULSE(0.0001 0.001 1e-09 1e-13 1e-13 5e-09 1e-08)' if analysis=='tran' else 'DC 0.0005')+' AC 1']
    for row in rows:
        if row['kind']!='application':continue
        tag=row['branch']; model,w,l,m=actual(row); p='0' if row['fault']=='disconnected-terminal' else 'in_'+tag
        lines += [f'VS_{tag} input in_{tag} DC 0 AC 0',
                  f'R_D_{tag} {p} out_{tag} sky130_fd_pr__res_generic_{model} l={l:g} m={m:g} w={w:g}',
                  f'RL_{tag} out_{tag} 0 1',f'CL_{tag} out_{tag} 0 1e-09']
    return lines


def check_project(path, rows, package):
    project=load(path); require(len(project['cells'])==1,'Unexpected application hierarchy.')
    cell=project['cells'][0]; require(project['top']==cell['id'] and cell['name']=='metal_linked','Application top differs.')
    devices=cell['devices']; named={d['name']:d for d in devices}
    expected={'VDRIVE'}|{prefix+r['branch'] for r in rows if r['kind']=='application' for prefix in ('VS_','D_','RL_','CL_')}
    require(len(devices)==len(named) and set(named)==expected,'Application device coverage differs.')
    require(project['pdk']['package_lock']=={k:package[k] for k in ('id','revision','files')},'Application model lock differs.')
    for row in rows:
        if row['kind']!='application':continue
        tag=row['branch']; model,w,l,m=actual(row); d=named['D_'+tag]
        require(d['kind']=='PDK' and d['model_ref']==dict(pdk='sky130A',revision=package['revision'],device=f'sky130_fd_pr/res_generic_{model}.sym')
                and d['model_params']==dict(w=w,l=l,mult=m) and d['symbol']['pin_order']==['m','p'] and
                d['nets']=={'m':'0' if row['fault']=='disconnected-terminal' else 'in_'+tag,'p':'out_'+tag},
                'Application model, parameters or terminal mapping differs.')


def check_deck(root, case, rows, selected, native, execution):
    folder=root/case['name']; section=case['section']; temp=case['temperature_c'];spec=load(root/'contract.json')
    if case['control']=='wrong-section':section=SECTIONS[(SECTIONS.index(section)+1)%len(SECTIONS)]
    if case['control']=='wrong-temperature':temp+=17
    app=(folder/'application.spice').read_text(encoding='utf-8')
    active=[line for line in app.splitlines() if line.strip() and not line.lstrip().startswith(('*','.'))]
    expected_app=application_lines(rows,case['analysis']); same_lines('\n'.join(active),expected_app)
    options='.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear'
    if case['analysis']=='tran':options+=' chgtol=1e-24 trtol=1'
    lines=[context_title(execution,case['name']),*selected[section].splitlines(),options,f'.temp {temp}',*expected_app]
    used=set()
    for row in rows:
        tag=row['branch']
        if row['kind']=='application':continue
        lines.append(f'VS_{tag} input in_{tag} DC 0 AC 0')
        if row['kind']=='native':
            key=row['physical_case']+'-r'+str(row['rotation']); wrapper=key.replace('-','_').replace('.','d')
            if wrapper not in used:
                lines += [f'.subckt native_{wrapper} a b','.include '+native[key]['path'],'X_COUPON a b coupon',f'.ends native_{wrapper}'];used.add(wrapper)
            lines += [f'XN_{tag}_{n} in_{tag} out_{tag} native_{wrapper}' for n in range(row['multiplicity'])]
        else:lines.append(f'RC_{tag} in_{tag} out_{tag} {resistance(spec,row,case["section"],case["temperature_c"]):.17g}')
        lines += [f'RL_{tag} out_{tag} 0 1',f'CL_{tag} out_{tag} 0 1n']
    parameters=spec['sections'][section]['coefficients']
    lines += [f'VP_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}' for name in parameters]
    if case['analysis']=='noise':
        lines += ['.control','set filetype=ascii']
        for i,row in enumerate(rows):
            tag=row['branch']; lines += [f'echo BEGIN_NOISE_{tag}',f'noise v(out_{tag}) VDRIVE dec 3 1k 10g',f'setplot noise{i*2+1}',
                f'let noise_{tag} = onoise_spectrum','write '+str(PurePosixPath(execution['root'])/case['name']/f'noise_{tag}.raw')+f' frequency noise_{tag}',f'echo END_NOISE_{tag}']
        lines += ['quit 0','.endc']
    else:
        names=['v(input)',*[v for row in rows for v in (f'v(in_{row["branch"]})',f'v(out_{row["branch"]})',f'i(vs_{row["branch"]})')],*[f'v(par_{n})' for n in parameters]]
        lines += ['.save '+' '.join(names),{'dc':'.dc VDRIVE -.001 .001 .0001','ac':'.ac dec 3 1k 10g','tran':'.tran 20p 21n'}[case['analysis']]]
    lines += ['.end']; same_lines((folder/'input.cir').read_text(),lines)
    return section,temp


def check_observation(root,spec,case,rows,execution):
    folder=root/case['name']; analysis=case['analysis']; tol=spec['tolerances']; e=spec['experiment']
    actual_section=SECTIONS[(SECTIONS.index(case['section'])+1)%5] if case['control']=='wrong-section' else case['section']
    actual_temp=case['temperature_c']+(17 if case['control']=='wrong-temperature' else 0)
    title=context_title(execution,case['name']); result={}; total=0
    def error(a,b,kind):return normalized_error(a,b,relative_tolerance=tol[kind+'_relative'],absolute_tolerance=tol[kind+'_absolute'])
    def check(a,b,kind,message):
        value=error(a,b,kind);require(value<=1,message);return value
    if analysis=='noise':
        for row in rows:
            tag=row['branch']; path=folder/f'noise_{tag}.raw'; raw=read_raw(path,title,'Noise Spectral Density Curves')
            require(raw['names']==['frequency','noise_'+tag],'Noise output branch differs.')
            frequencies=raw['values']['frequency']; frequency_grid(frequencies)
            r=resistance(spec,row,case['section'],case['temperature_c'])
            expected=[noise_density(r,1,1e-9,f,case['temperature_c'],spec['analytical']['boltzmann_j_per_k']) for f in frequencies]
            measured=raw['values']['noise_'+tag];require(all(v>0 for v in measured),'Nonpositive thermal noise.')
            result[tag]=dict(maximum_normalized_error=check(measured,expected,'noise','Thermal noise differs.'),resistance_ohm=r,raw_sha256=sha(path),samples=len(frequencies));total+=len(frequencies)
        return dict(branches=result,parameters={},samples=total),0
    raw=read_raw(folder/'result.raw',title,{'dc':'DC transfer characteristic','ac':'AC Analysis','tran':'Transient Analysis'}[analysis],complex_values=analysis=='ac')
    scale={'dc':'v(v-sweep)','ac':'frequency','tran':'time'}[analysis]; data=raw['values']; parameters=spec['sections'][actual_section]['coefficients']
    expected_names={scale,'v(input)',*[v for row in rows for v in (f'v(in_{row["branch"]})',f'v(out_{row["branch"]})',f'i(vs_{row["branch"]})')],*[f'v(par_{n})' for n in parameters]}
    require(set(raw['names'])==expected_names and raw['names'][0]==scale,'Native channel coverage differs.')
    x=[complex(v).real for v in data[scale]];require(all(a<b for a,b in zip(x,x[1:])),'Nonmonotonic raw scale.')
    if analysis=='dc':require(len(x)==21 and all(abs(v-(-.001+i*.0001))<1e-12 for i,v in enumerate(x)),'DC coverage differs.')
    elif analysis=='ac':frequency_grid(x)
    else:
        require(x[0]==0 and math.isclose(x[-1],21e-9,rel_tol=1e-10) and len(x)>1000 and max(b-a for a,b in zip(x,x[1:]))<=2.001e-11,'Transient coverage differs.')
    coeff={}
    for name,value in parameters.items():
        check(data['v(par_'+name+')'],[value]*len(x),'coefficient','Actual model section/switch differs.');coeff[name]=float(complex(data['v(par_'+name+')'][0]).real)
    pulse=dict(low=e['pulse_low_v'],high=e['pulse_high_v'],delay=e['pulse_delay_s'],rise=e['pulse_edge_s'],fall=e['pulse_edge_s'],width=e['pulse_width_s'],period=e['pulse_period_s'])
    drive=x if analysis=='dc' else [1]*len(x) if analysis=='ac' else [pulse_value(t,pulse) for t in x]
    check(data['v(input)'],drive,'dc','Actual drive differs.')
    rejected=0
    for row in rows:
        tag=row['branch']; section,temp=(case['section'],case['temperature_c']) if row['kind']=='analytic' else (actual_section,actual_temp)
        r=resistance(spec,row,section,temp); output=data['v(out_'+tag+')']; current=data['i(vs_'+tag+')']; vin=data['v(in_'+tag+')']
        check(vin,drive,'dc','Branch sense source input differs.')
        if row['fault']=='disconnected-terminal':expected=[0]*len(x);expected_current=[0]*len(x)
        else:
            expected=[v*transfer(r,1,1e-9,0).real for v in x] if analysis=='dc' else [transfer(r,1,1e-9,f) for f in x] if analysis=='ac' else transient_response(x,r,1,1e-9,pulse)
            expected_current=[(a-b)/r for a,b in zip(vin,output)]
        measured_error=check(output,expected,analysis,'Analytical response differs: '+tag)
        check(current,expected_current,'current','Actual branch current differs.')
        if analysis in ('dc','ac'):check(current,[v*(1+(2j*math.pi*f*1e-9 if analysis=='ac' else 0)) for f,v in zip(x,output)],'current','Loaded node KCL differs.')
        difference=None
        if row['fault'] or case['control']!='positive' and row['kind']!='analytic':
            nominal=resistance(spec,row,case['section'],case['temperature_c'],False); target=[v/(1+nominal) for v in x]
            difference=max(abs(a-b) for a,b in zip(output,target))/max(abs(v) for v in target)
            require(difference>tol['fault_min_relative_difference'],'Intended fault/context change is not observable.');rejected+=1
        result[tag]=dict(maximum_normalized_error=measured_error,resistance_ohm=r,samples=len(x),fault_detected_relative=difference if row['fault'] else None)
    return dict(branches=result,parameters=coeff,samples=len(x)*len(rows),raw_sha256=sha(folder/'result.raw')),rejected


def frequency_grid(values):
    require(len(values)==22 and all(math.isclose(f,1000*10**(i/3),rel_tol=1e-10) for i,f in enumerate(values)),'Frequency coverage differs.')


def compare_summary(saved,observed):
    """Bind saved numeric summaries without requiring identical operation order."""
    require(type(saved)==type(observed),'Saved observation type differs.')
    if isinstance(observed,dict):
        require(set(saved)==set(observed),'Saved observation fields differ.')
        for name in observed:compare_summary(saved[name],observed[name])
    elif isinstance(observed,(int,float)):
        require(math.isfinite(saved) and math.isclose(saved,observed,rel_tol=1e-7,abs_tol=1e-7 if abs(observed)<1 else 1e-12),'Saved observation differs from independent raw readback.')
    else:require(saved==observed,'Saved observation differs.')


def model_closure(root,spec,manifest):
    package_root=root/'original-package';require(sha(package_root/'package.json')==spec['package']['manifest_sha256'],'Simulation manifest differs.')
    package=load(package_root/'package.json');require(package['revision']==spec['package']['revision'],'Simulation revision differs.')
    files={'package.json':spec['package']['manifest_sha256'],**package['files']}
    require(load(root/'package-files.json')==files and inventory(package_root)==files,'Original simulation package closure differs.')
    mapping=load(root/'pdk-model-files.json');require(mapping and len(set(mapping.values()))==len(mapping),'Duplicate staged mapping.')
    reverse={v:k for k,v in mapping.items()};require(set(mapping)=={n for n in manifest if n.startswith('pdk-models/')},'Staged file set differs.')
    require(load(root/'staged-model-files.json')=={n[len('pdk-models/'):]:manifest[n] for n in mapping},'Staged model inventory differs.')
    pattern=re.compile(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)([^\n]*)')
    for staged,original in mapping.items():
        require(original in package['files'],'Unbound model dependency.')
        require(staged=='pdk-models/'+hashlib.sha256((original+'\0'+package['files'][original]).encode()).hexdigest()[:24]+'.spice','Staged model name differs.')
        def rewrite(match):
            if match[1].lower()=='.lib' and not match[3].strip():return match[0]
            dependency=posixpath.normpath(posixpath.join(posixpath.dirname(original),match[2].strip('"\'')))
            require(dependency in reverse,'Missing model dependency.');return match[1]+' '+reverse[dependency]+match[3]
        expected=pattern.sub(rewrite,(package_root/relative(original)).read_bytes().decode('utf-8')).encode()
        require((root/relative(staged)).read_bytes()==expected,'Model changed beyond path relocation.')
    selected={}
    for section in SECTIONS:
        selected[section]='\n'.join('.lib '+reverse[i['path']]+' '+i['sections'][section] if 'sections' in i else '.include '+reverse[i['path']]
                                   for i in package['technology']['simulation']['includes'])
    require(load(root/'selected-model-lines.json')==selected,'Actual section selection differs.')
    return package,selected


def physical_context(root,report):
    package_root=root/'original-physical-package'; expected='531c0a4263b839b693d171ad223d01f1484130113f0fcb9010bf99b4c2da9417'
    require(sha(package_root/'package.json')==expected,'Physical package manifest differs.')
    package=load(package_root/'package.json');files=load(root/'physical-package-files.json')
    pdk=PurePosixPath(files['package.json']['resolved']).parent
    require(pdk.is_absolute() and report['physical_package']['manifest_sha256']==expected and
            report['physical_package']['revision']==package['revision']=='9a491f0ebd51a0aa','Physical adapter identity differs.')
    captured={n:v['sha256'] for n,v in files.items() if 'sha256' in v}
    require(inventory(package_root)==captured,'Physical package inventory differs.')
    for name,digest in package['files'].items():require(captured.get(name)==digest,'Unbound physical asset.')
    before,after=[load(root/('physical-runtime-'+v+'.json')) for v in ('before','after')]
    require(before==after and all(sha(root/f'physical-runtime-{v}.json')==report[f'physical_runtime_{v}_sha256'] for v in ('before','after')),'Physical runtime changed or receipt differs.')
    require(before['profile']=='linux-x86_64-headless-icstudio-v1' and before['bytecode_cache_prefix']=='/__icstudio_li_development_no_bytecode__','Unreviewed physical runtime profile.')
    fixed={'/opt/icstudio/bin/magic':'359bd5dbfccf21114b2f18e2ffa008debf159bd0d1ab78e01738d2af9500b223',
           '/opt/icstudio/bin/netgen':'209cc0bab75420d13094a99de13e94af05d735e744e06d817fac022ac74401d3',
           '/opt/icstudio/physical/installed/bin/magic':'4b74020f201fd8b09b4984614249f3602dd1f4b2a3731e087dfe88eeacc887c5'}
    for path,digest in fixed.items():require(before['files'][path]['sha256']==digest,'Unreviewed physical launcher.')
    trees={'/opt/icstudio/physical/installed':'12a0cae4b96c59dddbd3e8d4470973871fab052ef047fb0e98c3040c8f52eb8f',
           '/usr/share/tcltk':'18d3ef2d1f0c3c3d253a05c4bf0c7c189de54f8384ef926dd18178cc1b34bc9e',
           '/usr/lib/tcltk':'1ca2ada63b252a96da6f6a98c63301aed76e48dcba7c2b343314d00d1f77b1d5'}
    for path,digest in trees.items():require(hashlib.sha256((json.dumps(before['trees'][path],sort_keys=True,indent=2)+'\n').encode()).hexdigest()==digest,'Unreviewed native/Tcl dependency tree.')
    require(before['native_launcher_environment']==dict(LD_LIBRARY_PATH='/opt/icstudio/lib',TCL_LIBRARY='/usr/share/tcltk/tcl8.6',CAD_ROOT='/opt/icstudio/physical/installed/lib'),'Native launcher environment differs.')
    assets={str(pdk/n):d for n,d in package['files'].items() if n.startswith(('libs.tech/magic/','libs.tech/netgen/'))}
    tools={n:dict(path='/opt/icstudio/bin/'+n,sha256=fixed['/opt/icstudio/bin/'+n]) for n in ('magic','netgen')}
    return dict(pdk=pdk,assets=assets,tools=tools)


def physical_fault_geometry(target,model,fault):
    import klayout.db as db
    masks,labels=target;pair=(68+MODELS.index(model),20);marker=(pair[0],13)
    result={k:v.dup() for k,v in masks.items()};body=masks[marker].bbox();ports={n:(x,y) for _,n,x,y in labels};a,b=ports['R1'],ports['R2']
    if fault=='terminal-open':
        mid=(a[1]+body.bottom)//2;result[pair]-=db.Region(db.Box(body.left-100,mid-5,body.right+100,mid+5))
    elif fault=='terminal-short':
        x=body.right+1000
        for box in (db.Box(min(a[0],x)-200,a[1]-200,max(a[0],x)+200,a[1]+200),
                    db.Box(x-200,min(a[1],b[1])-200,x+200,max(a[1],b[1])+200),
                    db.Box(min(b[0],x)-200,b[1]-200,max(b[0],x)+200,b[1]+200)):result[pair].insert(box)
    return {k:v.merged() for k,v in result.items()},labels


def check_physical_project(path,target):
    import klayout.db as db
    from scripts.audit_sky130_li_case import equal_masks
    value=load(path);require(len(value['cells'])==1,'Unexpected physical hierarchy.')
    cell=value['cells'][0];require(value['top']==cell['id'] and cell['name']=='coupon' and cell['ports']==['R1','R2'],'Physical project interface differs.')
    layers={r['name']:(r['gds'],r['datatype']) for r in value['pdk']['layers']};masks={}
    for shape in cell['shapes']:
        require(shape['kind'] in ('rect','polygon'),'Unexpected shape type.')
        poly=db.Polygon(db.Box(*shape['points'][0],*shape['points'][1])) if shape['kind']=='rect' else db.Polygon([db.Point(*p) for p in shape['points']])
        for hole in shape.get('holes',[]):poly.insert_hole([db.Point(*p) for p in hole])
        masks.setdefault(layers[shape['layer']],db.Region()).insert(poly)
    equal_masks({k:v.merged() for k,v in masks.items()},target[0])
    if 'layout_ports' in cell:
        labels=sorted(((layers[r['layer']][0],5),r['name'],*r['point']) for r in cell['layout_ports'])
    else:labels=sorted((layers[r['layer']],r['text'],r['x'],r['y']) for r in cell.get('layout_texts',[]))
    require(labels==target[1],'Physical project terminals differ.')


def check_physical_native(folder,target,origin,context,model,w,l,fault=None):
    from scripts import audit_sky130_li_case as independent
    report=load(folder/'report.json');stages=report['stages'];require([r['name'] for r in stages]==list(independent.STAGES),'Incomplete native stages.')
    require(report['status']==('failed' if fault else 'passed') and report['drc_engine']=='magic' and
            report['lvs_extractor']=='magic' and report['magic_drc_style']=='drc(full)','Native status/engine differs.')
    require(stages[0]['status']=='passed' and stages[0]['evidence']['assets']==context['assets'] and stages[0]['evidence']['tools']==context['tools'],'Native preflight identity differs.')
    for name in ('original.gds','layout.gds'):independent.check_stream(folder/name,target)
    for name in ('input.icproj','original.gds.icstudio.json'):check_physical_project(folder/name,target)
    reference_model='sky130_fd_pr__res_generic_'+('l1' if fault=='reference-model' else model)
    for name in ('schematic.spice','schematic-lvs.spice'):
        independent.spice(folder/name,width=w*1.2 if fault=='reference-width' else w,length=l*1.2 if fault=='reference-length' else l,model=reference_model,reference=True)
    require(report['reference']==dict(top='coupon',ports=['R1','R2'],sha256=sha(folder/'schematic.spice')),'Reference receipt differs.')
    independent.spice(folder/'lvs-extraction/extracted.spice',width=w,length=l,model='sky130_fd_pr__res_generic_'+model,fault=fault)
    independent.check_native_scripts(folder,origin,context['pdk'])
    log=independent.magic_log(folder/'drc/console.log');independent.magic_log(folder/'lvs-extraction/console.log')
    counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)
    require(len(counts)==1 and re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)==['drc(full)'],'Missing complete native DRC.')
    count=int(counts[0]);require(report['drc_count']==count and (count>0 if fault=='terminal-open' else count==0),'Actual DRC outcome differs.')
    findings=(folder/'drc/findings.tsv').read_text().splitlines();require(bool(findings)==bool(count),'DRC findings absent/inconsistent.')
    for line in findings:
        rule,coords=line.split('\t');numbers=list(map(float,coords.split(',')))
        require(rule and len(numbers)==4 and all(map(math.isfinite,numbers)),'Invalid DRC finding.')
    if fault=='terminal-short':
        require([r['status'] for r in stages]==['passed','passed','passed','failed','not_run','not_run'],'Short must fail extracted port contract.')
    else:
        require([r['status'] for r in stages]==(['passed']*6 if not fault else ['passed','passed','failed' if fault=='terminal-open' else 'passed','passed','failed','passed']),'Native stage outcomes differ.')
        console=(folder/'lvs/console.log').read_text();independent.check_netgen_inputs(console,origin,context['pdk']);text=(folder/'lvs/lvs.log').read_text()
        require(not re.search('invalid command|could not open|cannot open|Error in',text,re.I),'Infrastructure error is not a detected fault.')
        if not fault:require('Final result: Circuits match uniquely.' in text and 'Cell pin lists are equivalent.' in text and not re.search('property errors|port errors|do not match|disconnected node|no matching pin',text,re.I),'No strict actual LVS match.')
        elif fault in ('reference-width','reference-length'):require('Property errors were found.' in text and re.search('^ '+('w' if fault=='reference-width' else 'l')+' circuit1:',text,re.M),'Missing native parameter mismatch.')
        elif fault=='reference-model':require('Netlists do not match.' in text and reference_model in text and 'sky130_fd_pr__res_generic_'+model in text,'Missing native model mismatch.')
        else:require('disconnected node: R1' in text and 'Top level cell failed pin matching.' in text,'Missing native open-terminal mismatch.')
    for row in stages:
        evidence=row.get('evidence',{})
        if row['name']=='integrity' and row['status']=='passed':
            require(evidence.get('verified') is True and evidence['assets']==context['assets'] and evidence['tools']==context['tools'],'Incomplete native integrity.')
            for name,digest in evidence['files'].items():require(sha(folder/relative(name))==digest,'Native member integrity differs.')
        if row['name']=='lvs_extraction' and row['status']=='passed':
            require(evidence['deck']=='lvs-extraction/extracted.spice' and evidence['sha256']==sha(folder/evidence['deck']) and evidence['settings']==independent.EXTRACTION_SETTINGS,'Extraction identity/settings differ.')
    return count


def physical_inputs(root,report,logical):
    from scripts import audit_sky130_li_case as independent
    context=physical_context(root,report);origin=PurePosixPath(report['execution']['root'])/'physical'
    expected={(r['physical_case'],r['model'],r['width_um'],r['length_um']) for r in logical}
    rows={r['name']:r for r in report['physical']};require(len(rows)==len(report['physical'])==len(expected) and set(rows)=={r[0] for r in expected},'Physical case coverage differs.')
    native={};fault_count=0
    for name,model,w,l in sorted(expected):
        folder=root/'physical'/name;row=rows[name];require(load(folder/'record.json')==row and row['status']=='PASS','Physical case receipt differs.')
        script=independent.generator_script(context['pdk']).replace('res_generic_l1','res_generic_'+model).replace('dict create w 2 l 5',f'dict create w {w:g} l {l:g}')
        require((folder/'generator/generate.tcl').read_text()==script and (folder/'generator/empty.magicrc').read_bytes()==b'','Generator parameters/source differ.')
        log=(folder/'generator/console.log').read_text();require(log.count('GENERATOR_COMPLETE')==1 and 'GENERATOR_FAILED' not in log and not re.search(r'\d+ problems occurred',log),'Generator did not complete.')
        layouts={r['rotation']:r for r in row['layouts']};require(len(row['layouts'])==2 and set(layouts)=={0,90},'Physical orientation coverage differs.')
        baseline=None
        for angle in (0,90):
            target=physical_geometry(folder/f'baseline-{angle}.gds',model,w,l,angle)
            if angle==0:
                baseline=target;independent.check_stream(folder/'generator/coupon.gds',target,labels=False);check_physical_project(folder/'saved.icproj',target)
            for member in (f'layout-{angle}.oas',f'external-{angle}.oas',f'reimported-{angle}.gds'):independent.check_stream(folder/member,target)
            dest=folder/f'physical-{angle}';count=check_physical_native(dest,target,origin/name/dest.name,context,model,w,l)
            extracted=native_resistor(dest/'lvs-extraction/extracted.spice',model,w,l)
            require(layouts[angle]['extracted']==extracted and layouts[angle]['drc_count']==count and layouts[angle]['report_sha256']==sha(dest/'report.json'),'Saved physical summary differs.')
            key=name+'-r'+str(angle);native[key]=dict(path=str(origin/name/dest.name/'lvs-extraction/extracted.spice'),sha256=extracted['sha256'])
        faults={r['name']:r for r in row['faults']};require(len(row['faults'])==5 and set(faults)==set(independent.FAULTS),'Physical negative-control coverage differs.')
        for fault,value in faults.items():
            dest=folder/fault;check_physical_native(dest,physical_fault_geometry(baseline,model,fault),origin/name/fault,context,model,w,l,fault)
            require(value['detected'] is True and value['status']=='failed' and value['report_sha256']==sha(dest/'report.json'),'Physical fault summary differs.');fault_count+=1
    require(load(root/'native-inputs.json')==native,'Native electrical input binding differs.')
    return native,dict(coupons=len(expected),layouts=len(native),faults=fault_count)


def audit(root,reviewed_source=None):
    from scripts.audit_sky130_mim_mismatch_aliases import runtime
    root=Path(root);actual_manifest=inventory(root);actual_manifest.pop('manifest.json');require(load(root/'manifest.json')==actual_manifest,'Complete evidence inventory differs.')
    report=load(root/'qualification.json');spec=load(root/'contract.json')
    review=versions.selected('metal',report['contract_sha256'],sha(root/'original-package/package.json'))
    require(sha(root/'contract.json')==review['sha256'] and spec['package']['manifest_sha256']==review['package_sha256'],'Acceptance contract/package pair differs.')
    require(report['schema']==1 and report['gate']==review['id'] and report['status']=='PASS' and report['mode']=='source-integration' and
            all(report[n] is False for n in ('qualified','installed_acceptance','full_family','chunk_complete','release_ready','signoff')),'Invalid completion or scope claim.')
    require(report['guards']==dict(source=True,simulation_package=True,staged_models=True,physical_package=True,runtime=True),'Missing final input guards.')
    source=load(root/'source-files.json');require(sha(root/'source-files.json')==report['source_files_sha256'] and inventory(root/'source')==source,'Source closure differs.')
    required={review['path'],'scripts/qualify_sky130_metal_resistors_linked.py','scripts/audit_sky130_metal_resistors_linked.py',
              'tests/test_sky130_metal_resistors_linked.py','tests/test_sky130_metal_resistors_linked_audit.py','examples/sky130-qualification-lock.json',*spec['sources']}
    if review['sha256']==CURRENT_CONTRACT['sha256']:required.add('scripts/sky130_contract_versions.py')
    require(required<=set(source),'Required source snapshot member missing.')
    for name,row in spec['sources'].items():require(source[name]==row['sha256'],'Primary source binding differs.')
    require(source[review['path']]==review['sha256'],'Captured source contract differs.')
    if reviewed_source is not None:
        for name,digest in source.items():require(sha(Path(reviewed_source)/relative(name))==digest,'Captured source differs from independently reviewed source.')
    for name,row in spec['engine_sources'].items():require(sha(root/'engine-reference'/relative(name))==row['sha256'],'Primitive source/reference differs.')
    package,selected=model_closure(root,spec,actual_manifest);engine=runtime(root,report)
    require(engine['platform']=='linux' and engine['sha256']==spec['runtime']['ngspice_sha256'],'Unreviewed electrical runtime.')
    logical,cases=selection(spec,report['pilot']);require(report['logical_rows']==logical and report['selected_cases']==[c['name'] for c in cases],'Selection differs.')
    native,physical=physical_inputs(root,report,logical);rows={r['name']:r for r in report['cases']}
    require(len(rows)==len(report['cases'])==len(cases) and set(rows)=={r['name'] for r in cases},'Electrical context coverage differs.')
    samples=0;faults=0;analyses={name:0 for name in ('dc','ac','tran','noise')};maximum={name:0.0 for name in analyses}
    for case in cases:
        row=rows[case['name']];folder=root/case['name'];require(load(folder/'record.json')==row and all(row[k]==v for k,v in case.items()),'Case/context receipt differs.')
        branch_rows=branches(logical,case);require(row['branches']==branch_rows and row['status']=='PASS' and row['returncode']==0,'Branch coverage or native completion differs.')
        check_project(folder/'input.icproj',branch_rows,package)
        section,temp=check_deck(root,case,branch_rows,selected,native,report['execution'])
        require(row['actual_section']==section and row['actual_temperature_c']==temp,'Actual operating context differs.')
        command=[engine['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b'];origin=PurePosixPath(report['execution']['root'])
        if case['analysis']!='noise':command+=['-r',str(origin/case['name']/'result.raw')]
        command+=[str(origin/case['name']/'input.cir')]
        require(row['command']==command and row['cwd']==str(origin) and row['environment']==engine['environment'],'Actual invocation/environment differs.')
        require(row['deck_sha256']==sha(folder/'input.cir') and row['log_sha256']==sha(folder/'console.log'),'Native input/log receipt differs.')
        log=(folder/'console.log').read_text();require('error' not in log.lower() and 'unknown parameter' not in log.lower(),'Native error concealed by summary.')
        observed,rejected=check_observation(root,spec,case,branch_rows,report['execution']);faults+=rejected;samples+=observed['samples'];analyses[case['analysis']]+=1
        if case['analysis']!='noise':require(row['raw_sha256']==observed['raw_sha256'],'Raw receipt differs.')
        if case['control']=='positive':compare_summary(row['observation'],observed)
        else:require(isinstance(row.get('detected'),str) and row['detected'] and rejected==2*len(logical),'Wrong-context control incomplete.')
        maximum[case['analysis']]=max(maximum[case['analysis']],max(v['maximum_normalized_error'] for v in observed['branches'].values()))
    return dict(status='PASS',scope='selected source integration; no installed, envelope, statistical, silicon or signoff qualification',
                source_binding='all captured files compared to reviewed source' if reviewed_source is not None else 'self-contained retained source closure only',
                qualification_sha256=sha(root/'qualification.json'),manifest_sha256=sha(root/'manifest.json'),source_files_sha256=sha(root/'source-files.json'),
                contexts=len(cases),logical_variants=len(logical),analyses=analyses,branch_samples=samples,detected_branch_controls=faults,
                physical=physical,maximum_normalized_errors=maximum)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);parser.add_argument('--reviewed-source',type=Path)
    args=parser.parse_args();print(json.dumps(audit(args.root,args.reviewed_source),indent=2,sort_keys=True))


if __name__=='__main__':main()
