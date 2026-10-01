"""A revision-scoped CMOS course using real catalog models and verification jobs.

There is deliberately no fallback from process models to the teaching solver,
or from missing physical decks to generic geometry checks.
"""
import json
import math
from pathlib import Path

from .model import clone, digest, design_digest, file_digest, scalar, uid

PROCESSES = {
    'sky130': dict(supply=1.8, length='0.15u', n='sky130_fd_pr__nfet_01v8', p='sky130_fd_pr__pfet_01v8'),
    'gf180mcu': dict(supply=3.3, length='0.28u', n='nfet_03v3', p='pfet_03v3'),
    'ihp': dict(supply=1.2, length='0.13u', n='sg13_lv_nmos', p='sg13_lv_pmos'),
}


def profile(technology):
    """Key progress by content, never by installation directory or display name."""
    from .project_templates import model_choices
    tech = clone(technology); lock = tech.get('package_lock', {})
    key = lock.get('id', '')
    if key in ('gf180mcuC','gf180mcuD'):
        from .gf180_layout import prepare as physical_layers
        try: physical_layers(tech)
        except (ValueError,OSError): pass
    if key=='ihp-sg13g2':
        from .ihp_layout import prepare as physical_layers
        try: physical_layers(tech)
        except (ValueError,OSError): pass
    if key=='sky130A':
        from .sky130_layout import configure_connectivity
        try: configure_connectivity(tech)
        except (ValueError,OSError,KeyError): pass
    family = next((f for f in PROCESSES if key.lower().startswith(f)), None)
    spec = PROCESSES.get(family)
    models = {}
    if spec:
        for kind, field in [('NMOS', 'n'), ('PMOS', 'p')]:
            matches = [k for k, b in model_choices(tech, kind)
                       if b.get('model') == spec[field] or b.get('model', '').endswith('__'+spec[field])]
            canonical = [k for k in matches if Path(k).stem==spec[field].split('__')[-1]]
            if len(canonical)==1:models[kind]=canonical[0]
            elif len(matches)==1:models[kind]=matches[0]
    identity = {k: v for k, v in tech.items() if k not in ('package_root', 'package_lock')}
    token = digest(dict(id=key, revision=lock.get('revision'), files=lock.get('files'), technology=identity))[:20]
    return dict(token=token, technology=tech, name=key+' · '+lock.get('revision', 'unregistered'),
                models=models, spec=spec, ready=bool(lock and spec and len(models)==2),
                reason='' if spec and len(models)==2 else 'This revision needs supported four-terminal core NMOS/PMOS model bindings. See PDK setup.')


def inventory(registry, current=None):
    """Discover every registered revision and the offline simulation packages."""
    from .bundled_pdks import packages
    out = {}; errors = []
    def add(manifest, root):
        tech = clone(manifest['technology'])
        tech.update(package_root=str(Path(root).resolve()), package_lock=dict(id=manifest['id'], revision=manifest['revision'],
                    manifest_hash=digest(manifest), files=manifest['files']))
        item = profile(tech); out[item['token']] = item
    for manifest in registry.entries():
        if manifest.get('error'):
            errors.append(manifest['id']+': '+manifest['error']); continue
        try:add(manifest, manifest.get('source_root', registry.root/(manifest['id']+'@'+manifest['revision'])))
        except (ValueError,KeyError,TypeError) as exc:errors.append(str(manifest.get('id','PDK'))+': '+str(exc))
    try:
        for entry in packages():
            root = Path(entry['path']); add(json.loads((root/'package.json').read_text(encoding='utf-8')), root)
    except (ValueError, OSError) as exc: errors.append(str(exc))
    if current and current.get('package_lock'):
        item = profile(current); out[item['token']] = item
    if not any(p['technology']['package_lock']['id']=='ihp-sg13g2' for p in out.values()):
        out['ihp-setup'] = dict(token='ihp-setup', name='IHP SG13G2 · setup required', ready=False,
            reason='Register IHP SG13G2, then configure compiled OSDI models in Tools → Simulation runtime. Reload PDKs here.', technology=None)
    return list(out.values()), errors


def expand(data, material, profiles):
    from .getting_started import resource_root
    from .student_hub import validate_curriculum
    source = json.loads((resource_root()/'examples/student-hub/inverter-course.json').read_text(encoding='utf-8'))
    data = clone(data); material = clone(material)
    data['paths'].append(dict(id='inverter', title='CMOS inverter · PDK to LVS',
                             subtitle='One circuit, from device physics to verified layout. Choose a process revision.'))
    for item in profiles:
        previous = None
        for unit in source['lessons']:
            lesson = clone(unit['lesson']); stage = lesson.pop('id')
            lesson.update(id='i-'+item['token']+'-'+stage, path='inverter', starter='pdk-inverter',
                          workspace='inverter-'+item['token'], requires=[previous] if previous else [],
                          inverter_profile=item['token'], inverter_stage=stage, doc='STUDENT_INVERTER.md')
            data['lessons'].append(lesson); material['lessons'][lesson['id']] = clone(unit['teaching'])
            previous = lesson['id']
    validate_curriculum(data)
    return data, material


def create(item):
    from .pdks import model_lines
    from .project_templates import create as template
    if not item['ready']: raise ValueError(item['reason'])
    tech = clone(item['technology']); model_lines(tech)  # Verify every locked asset before opening the lesson.
    spec = item['spec']
    p, cid, bench = template(tech, 'inverter', spec['supply'], item['models']['NMOS'], item['models']['PMOS'])
    for d in next(c for c in p['cells'] if c['id']==cid)['devices']:
        d['params'].update(w='1u' if d['kind']=='NMOS' else '2u', l=spec['length'], nf='1', m='1')
    p['student_inverter'] = dict(version=1, profile=item['token'], cell=cid, bench=bench, supply=spec['supply'])
    p['analysis'].update(stop='62n', step='20p', corner='nominal')
    p['name'] = 'Student inverter · '+item['name']
    return p


def context(p, lesson=None):
    record = p.get('student_inverter', {})
    if record.get('version') != 1: raise ValueError('Start the PDK inverter course from Student Hub.')
    if lesson and record.get('profile') != lesson.get('inverter_profile'):
        raise ValueError('This inverter belongs to another PDK course. Resume the selected revision from Student Hub.')
    if record.get('profile') != profile(p['pdk'])['token']:
        raise ValueError('The PDK binding changed. Start a separate course for the new revision.')
    c = next((c for c in p['cells'] if c['id']==record.get('cell')), None)
    if not c: raise ValueError('Restore the inverter cell.')
    return record, c


def readiness(item):
    if not item['ready']: return item['reason']
    from .process_adapters import capabilities
    cap = capabilities(item['technology'])
    return ('Simulation: real process models'+(' with compiled models in the included physical runtime' if item['technology'].get('simulation', {}).get('requires_osdi') else '')+
            '. Layout: '+('native inverter generator' if 'inverter' in cap['native_layout'] else 'import matching process geometry')+
            '. DRC/LVS: '+('locked process decks available; physical tools required.' if cap['external_verification'] else
            'matching physical decks are missing. Simulation packages alone cannot complete these checkpoints.')+
            ' Progress is separate for this exact revision. GF180 C and D are distinct variants.')


def prepare(p, lesson, tools=None):
    from .run_environment import stamp
    record, cell = context(p, lesson); stage = lesson['inverter_stage']; tools = tools or {}
    job = dict(project=clone(p), cell=p['top'], engine='ngspice', settings=clone(p['analysis']))
    if stage in ('drc', 'lvs', 'handoff'):
        from .layout_verification import reference
        from .testbenches import native_subcircuit
        from .physical_backend import prepare as physical
        if not cell.get('shapes') and not cell.get('layout_instances'):
            raise ValueError('Build or import the inverter layout before process verification.')
        job.update(cell=cell['id'], engine='physical', settings=dict(type='silicon', verification_mode='drc_lvs',
            reference=reference(native_subcircuit(p,cell['id']),cell['name']),
            physical_toolchain='auto', tools={k:tools.get(k,'') for k in ('magic','netgen','ngspice')}))
        physical(job)
    else:
        from .osdi import verified
        from .spice_program import find_ngspice
        if p['pdk'].get('simulation',{}).get('requires_osdi') and not p.get('simulation_runtime',{}).get('osdi'):
            from .physical_backend import prepare_simulation
            prepare_simulation(job)
        else:
            verified(p)
            executable = find_ngspice(tools.get('ngspice') or '')
            if not executable or not Path(executable).is_file():
                raise ValueError('Choose a native ngspice executable in Engine setup. Process lessons require ngspice.')
            job['executable'] = str(Path(executable).resolve())
        if stage == 'dc':
            job['settings'].update(type='dc', source='VIN', dc_start='0', dc_stop=str(record['supply']), dc_step=str(record['supply']/200))
        else: job['settings'].update(type='tran', stop='62n', step='20p')
    job['student_lesson'] = lesson['id']; job['environment'] = stamp(job)
    return job


def build_layout(p):
    from .process_adapters import generate_inverter
    _, cell = context(p)
    generate_inverter(p, cell['id'])  # Never silently replace student geometry.


def fault(p, kind):
    record, cell = context(p)
    if record.get('fault'): raise ValueError('Repair the current lesson fault first.')
    if not cell.get('inverter_layout'): raise ValueError('Build the native inverter layout before adding a practice fault.')
    if kind == 'drc':
        from .process_adapters import adapter
        layer = adapter(p['pdk']).layers(p['pdk'])['m1']
        shape = dict(id=uid(), kind='rect', layer=layer, points=[[40000,40000],[40050,40100]], net='', device_id='')
        cell['shapes'].append(shape); record['fault'] = dict(kind=kind, shape=shape)
    elif kind == 'lvs':
        device = next(d for d in cell['devices'] if d['kind']=='NMOS')
        old = device['params']['w']; value = f'{scalar(old)*1.3:.12g}'
        record['fault'] = dict(kind=kind, device=device['id'], old=old, value=value)
        device['params']['w'] = value
    else: raise ValueError('Unknown practice fault.')


def repair(p):
    record, cell = context(p); problem = record.get('fault')
    if not problem: raise ValueError('There is no injected lesson fault. Use the editor to repair your own changes.')
    if problem['kind']=='drc':
        shapes = [s for s in cell['shapes'] if s['id']==problem['shape']['id']]
        if shapes and shapes != [problem['shape']]: raise ValueError('The practice shape was edited. Repair it manually or undo those edits first.')
        cell['shapes'] = [s for s in cell['shapes'] if s['id']!=problem['shape']['id']]
    else:
        device = next(d for d in cell['devices'] if d['id']==problem['device'])
        if device['params']['w'] != problem['value']: raise ValueError('The practice device was edited. Undo that edit before restoring its original width.')
        device['params']['w'] = problem['old']
    del record['fault']


def measurements(p, result, kind):
    """Measure captured samples; reject absent, incomplete, nonfinite or wrong runs."""
    record, _ = context(p); vdd = record['supply']; xs = result.get('x', [])
    traces = result.get('traces', {}); vin = traces.get('in', []); out = traces.get('out', [])
    if result.get('settings', {}).get('type') != kind or not result.get('engine', '').startswith('ngspice'):
        raise ValueError('Run this lesson with real process models in ngspice.')
    if len(xs)<3 or len(xs)!=len(vin) or len(xs)!=len(out) or any(not math.isfinite(v) for a in (xs,vin,out) for v in a):
        raise ValueError('The run needs finite input and output waveforms.')
    if any(b<=a for a,b in zip(xs,xs[1:])): raise ValueError('The measurement axis must increase strictly.')
    if kind=='dc':
        if abs(vin[0])>vdd*.001 or abs(vin[-1]-vdd)>vdd*.001:
            raise ValueError('Sweep VIN over the complete 0 to VDD range.')
        if out[0]<.9*vdd or out[-1]>.1*vdd or any(b-a>.02*vdd for a,b in zip(out,out[1:])):
            raise ValueError('The transfer curve must invert: high output at zero input, low output at VDD, and no large upward steps.')
        crossings = [(a,b) for a,b in zip(range(len(xs)-1),range(1,len(xs))) if (out[a]-vin[a])*(out[b]-vin[b])<=0]
        if not crossings: raise ValueError('No switching threshold was found.')
        a,b = crossings[0]; fa=out[a]-vin[a]; fb=out[b]-vin[b]
        vm = vin[a] if fa==fb else vin[a]+(vin[b]-vin[a])*fa/(fa-fb)
        if not .2*vdd<vm<.8*vdd: raise ValueError('The switching threshold is outside the teaching target of 20–80% of VDD.')
        return dict(VOH=out[0], VOL=out[-1], switching_threshold=vm, supply=vdd)
    from .student_hub import at
    for time, expected in [(8e-9,False),(18e-9,True),(28e-9,False),(38e-9,True),(48e-9,False),(58e-9,True)]:
        vi,vo = at(result,'in',time),at(result,'out',time)
        if not ((vi<.1*vdd and vo>.9*vdd) if expected else (vi>.9*vdd and vo<.1*vdd)):
            raise ValueError('Switching check failed at '+str(time)+' s. Restore the 20 ns input period and inspect the output/load.')
    def edges(values, rising):
        level=vdd/2; found=[]
        for i in range(1,len(xs)):
            a,b=values[i-1],values[i]
            if (a<level<=b) if rising else (a>level>=b):
                found.append(xs[i-1]+(xs[i]-xs[i-1])*(level-a)/(b-a))
        return found
    delays = {}
    for name,rising in [('tPHL',True),('tPLH',False)]:
        ins=edges(vin,rising); outs=edges(out,not rising)
        values=[next((y-x for y in outs if 0<=y-x<10e-9),None) for x in ins if 1e-9<x<50e-9]
        if len(values)<2 or any(v is None for v in values): raise ValueError('Missing output transitions needed to measure propagation delay.')
        delays[name]=sum(values)/len(values)
    return dict(**delays, supply=vdd, checked_cycles=3)


def check(p, lesson, rule, rows):
    from .student_hub import current_result
    record, cell = context(p, lesson); test = rule['check']
    from .pdks import model_lines
    model_lines(p['pdk'])
    if test in ('binding','schematic'):
        expected = profile(p['pdk'])['models']
        if len(cell['devices'])!=2:raise ValueError('Keep exactly the core NMOS and PMOS in the inverter cell.')
        for kind,rail in [('NMOS','VGND'),('PMOS','VPWR')]:
            matches=[d for d in cell['devices'] if d['kind']==kind]
            if len(matches)!=1 or matches[0]['nets'] != dict(d='Y',g='A',s=rail,b=rail):
                raise ValueError('Connect one NMOS and one PMOS: common gate A, drain Y, source/body to their own supply rail.')
            d=matches[0]
            from .catalog import binding_for
            if (binding_for(p['pdk'],d) or {}).get('model') != p['pdk']['simulation']['catalog'][expected[kind]]['model']:
                raise ValueError('Use this process core model, not a generic MOS.')
        bench=next(c for c in p['cells'] if c['id']==p['top'])
        expected_nets={'VDD':dict(p='vdd',n='0'),'VIN':dict(p='in',n='0'),'CL':dict(p='out',n='0'),
                       'XDUT':dict(A='in',Y='out',VPWR='vdd',VGND='0')}
        for name,nets in expected_nets.items():
            found=[d for d in bench['devices'] if d['name']==name]
            if len(found)!=1 or found[0]['nets']!=nets:raise ValueError('Restore the testbench connections for '+name+'.')
            if name=='VDD' and not math.isclose(scalar(found[0]['value']),record['supply']):
                raise ValueError('Use this course nominal supply. Explore supply sweeps separately in saved testbenches.')
            if name=='XDUT' and found[0].get('cell')!=cell['id']:raise ValueError('Connect the actual inverter child cell to the testbench.')
        return dict(pdk_revision=p['pdk']['package_lock']['revision'], models=expected)
    if test=='layout':
        from .physical_cells import ports
        if not cell.get('shapes') and not cell.get('layout_instances'): raise ValueError('Build or import real process geometry first.')
        if {v['name'] for v in ports(p,cell['id'])} != set(cell['ports']): raise ValueError('Assign all four physical ports: A, Y, VPWR and VGND.')
        return dict(layout_cell=cell['name'], note='Geometry and interface only. DRC and LVS are separate checkpoints.')
    candidates=[r for r in rows if r['job'].get('student_lesson')==lesson['id']]
    result,evidence=current_result(p,candidates)
    if test in ('dc','tran'):
        check(p,lesson,dict(check='schematic'),[])
        evidence['inverter_measurements']=measurements(p,result,test); return evidence
    report=result.get('silicon_report',{})
    if report.get('mode')!='drc_lvs' or report.get('design_hash')!=design_digest(p):
        raise ValueError('Run process DRC/LVS for this exact design.')
    stages={s['name']:s for s in report.get('stages',[])}
    integrity=stages.get('integrity',{})
    if integrity.get('status')!='passed' or not integrity.get('evidence',{}).get('verified'):
        raise ValueError('Physical evidence integrity was not verified. Resolve the failed or blocked stages first.')
    root=Path(result['evidence_directory'])
    for name,sha in integrity['evidence']['files'].items():
        if not (root/name).is_file() or file_digest(root/name)!=sha:
            raise ValueError('Physical run evidence is missing or changed. Run the lesson again.')
    names=('drc','lvs') if test=='handoff' else (test.split('-')[0],)
    want='failed' if test.endswith('-failure') else 'passed'
    if any(stages.get(n,{}).get('status')!=want for n in names):
        detail='; '.join(s.get('error','') for s in report.get('stages',[]) if s.get('status')!='passed')
        raise ValueError('Expected '+', '.join(names)+' '+want+'. A missing tool, deck or extraction is not a demonstrated rule violation. '+detail)
    if want=='failed':
        if names[0]=='drc' and not report.get('drc_count',0)>0:
            raise ValueError('The DRC engine did not report an actual rule violation.')
        if names[0]=='lvs':
            log=root/'lvs/lvs.log'
            text=log.read_text(encoding='utf-8',errors='replace') if log.is_file() else ''
            if not any(v in text.lower() for v in ('property errors','netlists do not match','circuits do not match','disconnected node:','(no matching pin)')):
                raise ValueError('The LVS engine did not report a completed circuit comparison with a mismatch.')
    evidence['physical_checks']={n:stages[n] for n in names}; evidence['pdk']=p['pdk']['package_lock']['id']
    return evidence
