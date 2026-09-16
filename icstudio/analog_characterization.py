"""Isolated, model-specific gm/Id tables with checked provenance and interpolation.

All dimensions are SI. VGS/VDS are polarity-normalized forward biases; VSB is
positive reverse body bias for either polarity. Width means total drawn width,
with exactly one finger and one parallel device in the supported PDK adapter.
"""
import itertools
import json
import math
import re
from pathlib import Path
from .model import clone, scalar, flatten, device, uid, validate, digest, design_digest, file_digest, now, atomic_write, example
from .catalog import binding_for, parameter_values
from . import analog_optimizer as opt

DIMENSIONS = ('length', 'vgs', 'vds', 'vsb', 'temperature')
VERSION = 2
RAW_METRICS = ('id','gm','gds','cgg','cgs','cgd','cgb','headroom')
METRICS = RAW_METRICS + ('gmid','current_density','intrinsic_gain','gm_cgg','ft_estimate')


def contract(project, root, name):
    d = next((d for d in flatten(project, root) if d['name'].casefold() == name.casefold()), None)
    if not d or d['kind'] not in ('NMOS', 'PMOS') or d.get('native_spice'):
        raise ValueError('Characterization supports generic MOS and the linked standard SKY130 1.8 V catalog MOS. Native/imported model adapters are not yet qualified.')
    binding = binding_for(project['pdk'], d)
    out = dict(version=VERSION, polarity=1 if d['kind'] == 'NMOS' else -1, width=scalar(d['params']['w']),
               convention='total drawn W in metres; nf=1, m=1; polarity-normalized VGS/VDS and reverse VSB',
               model='teaching square-law', internal=None, device=d)
    if binding:
        model = binding['model']; expected = 'sky130_fd_pr__' + ('nfet' if d['kind'] == 'NMOS' else 'pfet') + '_01v8'
        if model != expected or binding.get('prefix') != 'X' or binding.get('pin_order') != ['d','g','s','b']:
            raise ValueError('This process model has no qualified width/current adapter. Use the circuit gm/Id explorer for raw gm/Id.')
        if binding.get('parameter_scale') != {'w': 1e6, 'l': 1e6}:
            raise ValueError('The SKY130 adapter requires micrometre W/L model parameters.')
        values = parameter_values(binding, d)
        if any(values.get(k, 1) != 1 for k in ('nf', 'm', 'mult')):
            raise ValueError('Characterize a single finger and a single device (nf=m=mult=1).')
        if binding.get('emit_parameters', {'w':'w','l':'l'}).get('w') != 'w' or binding.get('emit_parameters', {'w':'w','l':'l'}).get('l') != 'l':
            raise ValueError('The model W/L emission does not match the adapter.')
        rel = 'libs.ref/sky130_fd_pr/spice/' + model + '.pm3.spice'
        lock = project['pdk'].get('package_lock', {}); root_path = Path(project['pdk'].get('package_root', '')).resolve(); path = root_path / rel
        if not lock.get('files', {}).get(rel) or not path.is_file() or file_digest(path) != lock['files'][rel]:
            raise ValueError('The locked SKY130 model definition is missing or changed. Repair the PDK package first.')
        text = path.read_text(encoding='utf-8'); internal = 'm' + model
        if not re.search(r'^' + re.escape(internal) + r'\s+d\s+g\s+s\s+b\s+' + re.escape(model) + r'__model\s+l\s*=\s*\{l\}\s+w\s*=\s*\{w\}\s+nf\s*=\s*\{nf\}', text, re.M | re.I):
            raise ValueError('The pinned model internal device differs from this adapter.')
        out.update(model=model, internal=internal, binding=clone(binding), model_definition_sha256=lock['files'][rel])
    return out


def grid(spec, process):
    out = {}
    for key in DIMENSIONS:
        values = [scalar(v) for v in spec[key]]
        if not values or len(values) > 100 or len(set(values)) != len(values): raise ValueError('Use 1–100 distinct samples for ' + key + '.')
        if any(v <= 0 for v in values) and key in ('length', 'vds'): raise ValueError('Length and forward VDS must be positive.')
        if key in ('vgs', 'vsb') and min(values) < 0: raise ValueError('Use nonnegative forward VGS and reverse VSB.')
        if key == 'temperature' and min(values) <= -273.15: raise ValueError('Invalid temperature.')
        out[key] = sorted(values)
    out['corner'] = list(dict.fromkeys(spec.get('corner', ['nominal'])))
    if process and any(c not in ('nominal','tt','ff','ss','sf','fs','ll','hh','hl','lh') for c in out['corner']): raise ValueError('Use deterministic process corners for reusable tables. Monte Carlo characterization requires a recorded random-seed workflow.')
    if not out['corner'] or any(not isinstance(c, str) for c in out['corner']): raise ValueError('Select at least one model corner.')
    count = math.prod(map(len, out.values()))
    if count > 500: raise ValueError(f'This characterization needs {count} simulations. Limit the library grid to 500 per experiment.')
    if not process and (out['vsb'] != [0.] or out['temperature'] != [27.] or out['corner'] != ['nominal']):
        raise ValueError('The teaching MOS model supports only VSB=0, 27 °C and nominal. Use a process model for body/temperature/corner characterization.')
    return out


def prepare(project, root, name, spec, prepare_job):
    from .run_environment import stamp
    adapter = contract(project, root, name); process = bool(adapter.get('binding')); samples = grid(spec, process)
    engine = spec.get('engine', 'ngspice' if process else 'builtin')
    if project.get('spice', {}).get('version') == 1 and engine != 'ngspice': raise ValueError('Native projects require ngspice for characterization.')
    if engine not in ('builtin', 'ngspice') or process and engine != 'ngspice': raise ValueError('Process characterization requires ngspice.')
    # Start a new simulation document so unrelated sources, programs and model
    # scopes cannot influence an isolated PDK measurement. The installed locked
    # library supplies the model; native DUT overrides are verified in circuit search.
    q = example('empty'); q.update(id=project['id'], revision=project['revision'], pdk=clone(project['pdk']), name='Isolated device characterization')
    d = clone(adapter['device']); d.update(id=uid(), name='MCHAR', x=420, y=250, nets=dict(d='d',g='g',s='0',b='b'))
    for key in ('layout_binding','terminal_ids','net_ids'):d.pop(key, None)
    if d.get('model_ref'):d['model_ref'].pop('instance_prefix', None)
    fixture = dict(id=uid(), name='gmid_characterization_' + uid()[:8], ports=[], shapes=[], devices=[d,
        device('V', 'VGS', 120, 180, nets=dict(p='g', n='0')),
        device('V', 'VDS', 640, 180, nets=dict(p='d', n='0')),
        device('V', 'VBS', 120, 420, nets=dict(p='b', n='0'))])
    q['cells'] = [fixture]; q['top'] = fixture['id']
    if process: q['gmid_fixture'] = dict(cell=fixture['id'], device=d['id'])
    base = design_digest(project); group = uid(); jobs = []; polarity = adapter['polarity']
    for index, values in enumerate(itertools.product(*(samples[k] for k in (*DIMENSIONS, 'corner'))), 1):
        condition = dict(zip((*DIMENSIONS, 'corner'), values)); p = clone(q); c = p['cells'][-1]
        c['devices'][0]['params']['l'] = str(condition['length'])
        for source, key, sign in (('VGS','vgs',1), ('VDS','vds',1), ('VBS','vsb',-1)):
            next(d for d in c['devices'] if d['name'] == source)['value'] = str(sign * polarity * condition[key])
        validate(p); settings = {**clone(p['analysis']), 'type':'op', 'temperature':condition['temperature'], 'corner':condition['corner']}
        job = prepare_job(settings, engine, p, fixture['id']); job['environment'] = stamp(job)
        job['case'] = dict(kind='analog_gmid', group=group, index=index, candidate=index, entry_id='characterize', test_name='Isolated MOS',
                           changes={k:condition[k] for k in DIMENSIONS}, labels=condition, base_design_hash=base)
        job['case']['fingerprint'] = digest({k:v for k,v in job.items() if k != 'case'}); jobs.append(job)
    # The original device identity/net names do not define a reusable model table.
    signature_device = {k:v for k,v in d.items() if k in ('kind','params','model_ref','model_params','model_mode')}
    technology = {k:v for k,v in q['pdk'].items() if k in ('package_lock','simulation')}
    identity = dict(version=VERSION, device=signature_device, technology=technology, spice=project.get('spice', {}),
                    adapter={k:v for k,v in adapter.items() if k not in ('device','binding')}, samples=samples, environment=jobs[0]['environment'])
    key = digest(identity)
    return dict(schema=1,id=group,created=now(),name='Library · '+name,project_id=project['id'],base_design_hash=base,cell_id=root,
                spec=dict(kind='analog_gmid', axes=[dict(target='vgs', lower=min(samples['vgs']), upper=max(samples['vgs']), count=len(samples['vgs']))],
                          gmid=dict(entry_id='characterize', device='MCHAR')), jobs=jobs,
                library=dict(key=key, identity=identity, width=adapter['width'], samples=samples, source_device=name))


def collect(manifest, rows):
    report = opt.evaluate(manifest, rows); lib = manifest['library']; points = []
    for candidate, job in zip(report['candidates'], manifest['jobs']):
        point = dict(condition=clone(job['case']['labels']), status=candidate['state'], error='; '.join(candidate['failures']),
                     run_ids=candidate['runs'], fingerprint=job['case']['fingerprint'])
        if candidate['state'] == 'Passed' and candidate['points']:
            captured = candidate['points'][0]
            point.update(values={k:captured[k] for k in (*METRICS,'vgs','vds','source') if k in captured})
            point['values']['current_density'] = abs(captured['id']) / lib['width']
        points.append(point)
    return dict(schema=VERSION,key=lib['key'],identity=lib['identity'],samples=lib['samples'],width=lib['width'],
                complete=report['complete'],points=points,created=manifest['created'])


def save_cache(table, directory):
    if not table['complete']: raise ValueError('Finish characterization before saving a reusable library table.')
    payload = clone(table); payload['checksum'] = digest(table)
    path = Path(directory) / 'gmid-library' / (table['key'] + '.json'); atomic_write(path, json.dumps(payload, allow_nan=False, indent=2))
    return path


def load_cache(key, directory):
    if not re.fullmatch('[a-f0-9]{64}', key): raise ValueError('Invalid characterization identity.')
    path = Path(directory) / 'gmid-library' / (key + '.json')
    if not path.exists(): return None
    table = json.loads(path.read_text(encoding='utf-8')); checksum = table.pop('checksum', None)
    if digest(table) != checksum or table.get('key') != key or digest(table['identity']) != key or not table.get('complete'):
        raise ValueError('The cached characterization is incomplete or changed. Run a new characterization.')
    return table


def interpolate(table, query):
    """Multilinear interpolation inside complete measured cells; never extrapolate."""
    if not table['complete']: raise ValueError('Wait for all characterization conditions to finish.')
    if query['corner'] not in table['samples']['corner']: raise ValueError('That corner was not characterized.')
    brackets = []
    for key in DIMENSIONS:
        x = scalar(query[key]); values = table['samples'][key]
        if x < values[0] or x > values[-1]: raise ValueError('Query is outside characterized ' + key + '. Extrapolation is disabled.')
        if x in values: brackets.append([(x, 1.)]); continue
        hi = next(v for v in values if v > x); lo = max(v for v in values if v < x)
        brackets.append([(lo,(hi-x)/(hi-lo)),(hi,(x-lo)/(hi-lo))])
    by = {tuple(p['condition'][k] for k in (*DIMENSIONS,'corner')):p for p in table['points']}; out = {}; sources = []; available=None
    for corner in itertools.product(*brackets):
        coordinates = [p[0] for p in corner]; weight = math.prod(p[1] for p in corner)
        point = by.get(tuple(coordinates + [query['corner']]))
        if not point or point['status'] != 'Passed' or not point.get('values'): raise ValueError('A required neighboring sample is unavailable. Interpolation across missing data is disabled.')
        keys={k for k in (*RAW_METRICS,'gmid','current_density') if point['values'].get(k) is not None}
        available=keys if available is None else available & keys
        for key in keys:
            value = scalar(point['values'][key]); out[key] = out.get(key,0.) + weight * value
        sources.extend(point['run_ids'])
    out={k:v for k,v in out.items() if k in available}
    out.update(opt.device_metrics(out))
    out.update(run_ids=list(dict.fromkeys(sources)), interpolated=any(len(b)>1 for b in brackets)); return out


def size(table, query, desired_gmid, desired_current):
    """Invert a VGS slice, exposing ambiguous/non-monotonic crossings as choices."""
    target, current = scalar(desired_gmid), scalar(desired_current)
    if min(target, current) <= 0: raise ValueError('Enter positive gm/Id and drain current targets.')
    samples = []
    for vgs in table['samples']['vgs']:
        try: point = interpolate(table, {**query,'vgs':vgs})
        except ValueError: point = None
        samples.append((vgs,point))
    estimates = []; used = set()
    for (a, p), (b, q) in zip(samples, samples[1:]):
        if p is None or q is None: continue
        if min(p['gmid'],q['gmid']) <= target <= max(p['gmid'],q['gmid']):
            if p['gmid'] == q['gmid']: raise ValueError('gm/Id is flat on this bias slice; choose a measured VGS explicitly.')
            vgs = a + (b-a)*(target-p['gmid'])/(q['gmid']-p['gmid'])
            if round(vgs,14) in used: continue
            used.add(round(vgs,14)); point = interpolate(table,{**query,'vgs':vgs})
            estimates.append(dict(width=current/point['current_density'], vgs=vgs, length=scalar(query['length']),
                                  desired_current=current, desired_gmid=target, condition={**query,'vgs':vgs},
                                  metrics={k:point[k] for k in METRICS if k in point}, run_ids=point['run_ids']))
    if not estimates: raise ValueError('The requested gm/Id has no complete bracketing samples. Extend the VGS sweep; no extrapolation was used.')
    return estimates


def prepare_verification(manifest, estimate, prepare_job):
    """Measure the proposed W/L at its proposed bias in a new ngspice job."""
    project=clone(manifest['jobs'][0]['project']);cid=project['top']
    mos=next(d for c in project['cells'] if c['id']==cid for d in c['devices'] if d['name']=='MCHAR')
    mos['params'].update(w=str(scalar(estimate['width'])),l=str(scalar(estimate['length'])))
    condition=estimate['condition']
    spec={k:[condition[k]] for k in (*DIMENSIONS,'corner')};spec['engine']='ngspice'
    result=prepare(project,cid,'MCHAR',spec,prepare_job)
    result['name']='SPICE sizing verification';result['sizing_verification']=dict(source=manifest['id'],estimate=clone(estimate),relative_tolerance=.05)
    return result


def verification_result(manifest, rows):
    table=collect(manifest,rows);point=table['points'][0];spec=manifest['sizing_verification'];estimate=spec['estimate']
    result=dict(state=point['status'],run_ids=point['run_ids'],error=point['error'])
    if point['status']=='Passed':
        job=manifest['jobs'][0];saved=next((r.get('result',{}) for r in rows if r['id'] in point['run_ids']),{})
        if not saved.get('engine','').startswith('ngspice') or saved.get('engine_hash')!=job.get('environment',{}).get('executable_sha256'):
            return dict(state='Failed',run_ids=point['run_ids'],error='Sizing verification requires results from the recorded ngspice executable.')
        values=point['values'];current=abs(values['id']);gmid=values['gmid']
        errors=dict(current=current/estimate['desired_current']-1,gmid=gmid/estimate['desired_gmid']-1)
        result.update(state='Verified' if all(abs(v)<=spec['relative_tolerance'] for v in errors.values()) else 'Outside tolerance',values=values,relative_errors=errors)
    return result
