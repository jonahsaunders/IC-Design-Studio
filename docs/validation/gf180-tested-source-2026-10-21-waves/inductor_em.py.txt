"""Reproducible EM exchange and imported differential impedance evidence.

No solver is run here. Physical material data must be supplied explicitly;
illustrative 3D display heights are never promoted into an EM stackup.
"""
import cmath
import io
import json
import math
import tempfile
import zipfile
from pathlib import Path

from .model import clone, digest, atomic_write
from .layout import kdb, polygon
from .em_technology import validate_stackup, readiness, mapping_for, solver_stackup, technology_identity

MAX_BYTES=8_000_000


def manifest(p,cid,did,scope='context'):
    if scope not in ('context','isolated'):raise ValueError('Choose isolated inductor or surrounding layout for EM.')
    from . import inductor
    from .layout_vias import technology
    from .design_ops import flatten_layout
    c=next(c for c in p['cells'] if c['id']==cid)
    r=next((r for r in c.get('parametric_devices',[]) if r['device_id']==did and r['spec'].get('kind')=='inductor'),None)
    if not r:raise ValueError('Create and save a generated inductor before EM characterization.')
    _,invalid=inductor._recognized(p)
    if any(v['object']==did and v['cell_id']==cid for v in invalid):
        raise ValueError('Regenerate the stale inductor before exporting EM geometry.')
    spec=inductor.current_spec(c,r);tech=technology(p)
    own=[s for s in c['shapes'] if s.get('pcell_id')==r['id']]
    pins=[{k:v[k] for k in ('pin','point','layer')} for v in c.get('layout_pins',[]) if v['device_id']==did]
    def physical(shape):
        return {k:clone(shape[k]) for k in ('kind','layer','points','holes','width','net') if k in shape}
    context=[physical(s) for s in flatten_layout(p,cid)]
    stack=tech.get('em_stackup')
    selected=context if scope=='context' else [physical(s) for s in own]
    missing=readiness(tech,stack,{s['layer'] for s in selected},{s['layer'] for s in own})
    mapping=mapping_for(tech,stack) if stack and not missing else {}
    solver_missing=list(missing)
    if not solver_missing:
        try:solver_stackup(stack,{name:physical for name,physical in mapping.items() if name in {s['layer'] for s in selected}})
        except ValueError as exc:solver_missing.append(str(exc))
    identity=dict(schema=2,scope=scope,project_id=p['id'],cell_id=cid,device_id=did,spec=spec,
                  geometry=[physical(s) for s in own],context_geometry=context,pins=pins,
                  layer_map=[{k:l[k] for k in ('name','gds','datatype')} for l in tech['layers']],
                  technology=technology_identity(tech),
                  process_lock=tech.get('package_lock'),stackup=stack,
                  port_definition='Differential voltage V(P)-V(N), current entering P and leaving N')
    return {**identity,'fingerprint':digest(identity),'stackup_complete':not missing,'missing':missing,'physical_layer_map':mapping,
            'solver_stackup_complete':not solver_missing,'solver_missing':solver_missing,
            'qualification':'External solver input/evidence only. Solver setup, meshing, convergence and process qualification remain the characterization source responsibility.'}


def export_bundle(p,cid,did,path,scope='context'):
    data=manifest(p,cid,did,scope);db=kdb();layout=db.Layout();layout.dbu=.001
    mapping={l['name']:layout.layer(l['gds'],l['datatype']) for l in data['layer_map']}
    winding=layout.create_cell('INDUCTOR');context=layout.create_cell('CONTEXT')
    for shape in data['geometry']:winding.shapes(mapping[shape['layer']]).insert(polygon(shape))
    for shape in data['context_geometry']:context.shapes(mapping[shape['layer']]).insert(polygon(shape))
    result_template=dict(schema=1,scope=scope,fingerprint=data['fingerprint'],source='REPLACE with solver, version, settings and convergence evidence',
                         port_definition=data['port_definition'],frequency_hz=[],z_real_ohm=[],z_imag_ohm=[])
    instructions=(
        'INDUCTOR is the isolated winding; CONTEXT is the full flattened cell including the winding.\n'
        'Choose ONE cell for simulation; do not superimpose both cells. Database unit: 1 nm.\n'
        'The declared simulation scope is '+scope+'. Results must describe that scope.\n'
        'When present, solver-geometry.gds (EM_MODEL) and stackup.xml are a matched pair for\n'
        'the gds2openEMS/gds2palace absolute-position stackup format. Use these together.\n'
        'solver-layers.json maps original layer/datatype pairs to unique solver layer numbers.\n'
        'Configure excitation port geometry from the manifest pin coordinates/layers, plus\n'
        'frequency sweep, mesh, boundaries and convergence. These files do not run a solver.\n'
        'Manifest pins identify P and N; use the documented differential voltage/current convention.\n'
        'A missing stackup is an incomplete exchange, not a runnable physical model. Supply explicit\n'
        'pdk.em_stackup in the application and re-export before importing results. Display heights are not used.\n'
        'Return differential impedance in results-template.json, retaining fingerprint and port_definition.\n'
        'Alternatively return Touchstone 1.x .s1p (P-to-N port) or .s2p (P and N to a common reference).\n'
        'For Touchstone, include same-name .json with fingerprint, source and port_definition from the template.\n'
        'Two-port conversion uses Zdiff=Z11+Z22-Z12-Z21 (current I into P, -I into N).\n'
        'Record solver/version, mesh convergence, boundaries, reference plane and frequency range in source.\n'
        'Imported L=Im(Z)/(2*pi*f); Q=Im(Z)/Re(Z) only in the inductive region.\n'
        'No built-in field solver or automatic process/RF qualification is claimed.\n')
    output=io.BytesIO()
    with tempfile.TemporaryDirectory() as folder:
        gds=Path(folder)/'geometry.gds';layout.write(str(gds))
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('geometry.gds',gds.read_bytes())
            archive.writestr('manifest.json',json.dumps(data,indent=2,allow_nan=False))
            archive.writestr('results-template.json',json.dumps(result_template,indent=2))
            archive.writestr('README.txt',instructions)
            issues=list(data['solver_missing'])
            if not issues:
                try:
                    selected=data['context_geometry'] if scope=='context' else data['geometry']
                    used={s['layer'] for s in selected}
                    mapped={name:physical for name,physical in data['physical_layer_map'].items() if name in used}
                    xml,numbers=solver_stackup(data['stackup'],mapped)
                    solver=db.Layout();solver.dbu=.001;cell=solver.create_cell('EM_MODEL')
                    solver_layers={name:solver.layer(numbers[physical],0) for name,physical in mapped.items()}
                    for shape in selected:
                        if shape['layer'] in solver_layers:cell.shapes(solver_layers[shape['layer']]).insert(polygon(shape))
                    solver_gds=Path(folder)/'solver.gds';solver.write(str(solver_gds))
                    table=[{**layer,'physical':mapped[layer['name']],'solver_gds':numbers[mapped[layer['name']]],'solver_datatype':0}
                           for layer in data['layer_map'] if layer['name'] in mapped]
                    archive.writestr('solver-geometry.gds',solver_gds.read_bytes())
                    archive.writestr('stackup.xml',xml)
                    archive.writestr('solver-layers.json',json.dumps(dict(layers=table,
                        excluded_layers=data['stackup'].get('excluded_layers',{})),indent=2))
                except ValueError as exc:issues.append(str(exc))
            if issues:archive.writestr('solver-setup-missing.txt','\n'.join(issues))
    atomic_write(path,output.getvalue())
    return data


def _read(path):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise ValueError('EM input is limited to 8 MB.')
    return path.read_text(encoding='utf-8-sig')


def touchstone(text,ports):
    """Strict Touchstone 1.x S/RI, S/MA or S/DB, with arbitrary line wraps."""
    unit='ghz';fmt='ma';reference=50.;tokens=[];options=False
    units={'hz':1.,'khz':1e3,'mhz':1e6,'ghz':1e9}
    for raw in text.splitlines():
        line=raw.split('!',1)[0].strip()
        if not line:continue
        if line.startswith('['):raise ValueError('Use Touchstone 1.x; version 2 keyword blocks are not supported.')
        if line.startswith('#'):
            if options or tokens:raise ValueError('Touchstone must have one option line before data.')
            words=line[1:].lower().split();options=True
            if len(words)!=5 or words[0] not in units or words[1]!='s' or words[2] not in ('ri','ma','db') or words[3]!='r':
                raise ValueError('Use # Hz S RI R 50 (or kHz/MHz/GHz, MA/DB and a positive reference).')
            unit,fmt,reference=words[0],words[2],float(words[4])
            if not math.isfinite(reference) or reference<=0:raise ValueError('Reference impedance must be finite and positive.')
        else:
            try:tokens.extend(float(x) for x in line.split())
            except ValueError as exc:raise ValueError('Touchstone data must be numeric.') from exc
    stride=1+2*ports*ports
    if not tokens or len(tokens)%stride or len(tokens)//stride>10000 or any(not math.isfinite(x) for x in tokens):
        raise ValueError('Provide complete finite Touchstone samples, at most 10,000.')
    frequency=[];real=[];imag=[]
    for i in range(0,len(tokens),stride):
        row=tokens[i:i+stride];values=[]
        for a,b in zip(row[1::2],row[2::2]):
            if fmt=='ri':value=complex(a,b)
            else:
                if fmt=='ma' and a<0:raise ValueError('Touchstone magnitudes must be nonnegative.')
                try:value=cmath.rect(10**(a/20) if fmt=='db' else a,math.radians(b))
                except OverflowError as exc:raise ValueError('Touchstone magnitude is too large.') from exc
            values.append(value)
        if ports==1:
            if abs(1-values[0])<1e-12:raise ValueError('Singular S-to-Z conversion at an open-circuit sample.')
            z=reference*(1+values[0])/(1-values[0])
        else:
            a,c,b,d=values # Touchstone column order: S11 S21 S12 S22.
            det=(1-a)*(1-d)-b*c
            if abs(det)<1e-12:raise ValueError('Singular two-port S-to-Z conversion.')
            z11=reference*((1+a)*(1-d)+b*c)/det
            z22=reference*((1+d)*(1-a)+b*c)/det
            z= z11+z22-2*reference*(b+c)/det
        frequency.append(row[0]*units[unit]);real.append(z.real);imag.append(z.imag)
    return dict(frequency_hz=frequency,z_real_ohm=real,z_imag_ohm=imag)


def load_results(path):
    path=Path(path);suffix=path.suffix.lower()
    if suffix=='.json':return json.loads(_read(path))
    if suffix not in ('.s1p','.s2p'):raise ValueError('Choose impedance JSON or Touchstone .s1p/.s2p.')
    metadata=json.loads(_read(path.with_suffix('.json')))
    return {**metadata,**touchstone(_read(path),1 if suffix=='.s1p' else 2)}


def validate_results(data,current):
    if not current['stackup_complete']:
        raise ValueError('Declare the missing EM stackup data and re-export before importing results: '+', '.join(current['missing']))
    if not isinstance(data,dict) or data.get('schema')!=1 or data.get('fingerprint')!=current['fingerprint']:
        raise ValueError('EM results belong to different geometry, context or stackup. Re-export and characterize the current design.')
    if data.get('port_definition')!=current['port_definition']:
        raise ValueError('EM port convention does not match the exported P/N definition.')
    if data.get('scope','context')!=current['scope']:
        raise ValueError('EM results use a different isolated/context simulation scope.')
    source=data.get('source','')
    if not isinstance(source,str) or not source.strip() or source.startswith('REPLACE') or len(source)>10000:
        raise ValueError('Name the actual solver/measurement source, settings and convergence evidence.')
    arrays=[data.get(k) for k in ('frequency_hz','z_real_ohm','z_imag_ohm')]
    if any(not isinstance(a,list) for a in arrays) or not 2<=len(arrays[0])<=10000 or len({len(a) for a in arrays})!=1:
        raise ValueError('Provide 2–10,000 matching frequency, real-Z and imaginary-Z samples.')
    if any(type(x) not in (int,float) or not math.isfinite(x) for a in arrays for x in a):
        raise ValueError('EM samples must be finite numeric values.')
    frequency,real,imag=arrays
    if frequency[0]<=0 or any(b<=a for a,b in zip(frequency,frequency[1:])):
        raise ValueError('EM frequencies must be positive and strictly increasing.')
    if any(r<0 for r in real):raise ValueError('Negative differential resistance is unsupported; check passivity and port conversion.')
    rows=[dict(frequency_hz=f,resistance_ohm=r,inductance_h=x/(2*math.pi*f),
               q=x/r if r>0 and x>0 else None) for f,r,x in zip(frequency,real,imag)]
    # Only claim an observed inductive-to-capacitive crossing within the data.
    srf=None;bracket=None
    for i in range(1,len(imag)):
        if imag[i-1]>0 and imag[i]<=0:
            bracket=[frequency[i-1],frequency[i]]
            srf=frequency[i-1]+(frequency[i]-frequency[i-1])*imag[i-1]/(imag[i-1]-imag[i]);break
    evidence={k:clone(data[k]) for k in ('schema','fingerprint','source','port_definition','frequency_hz','z_real_ohm','z_imag_ohm')}
    if 'scope' in data:evidence['scope']=data['scope']
    if 'solver_run' in data:
        run=data['solver_run']
        if not isinstance(run,dict) or run.get('backend')!='openEMS':
            raise ValueError('Unsupported structured solver evidence.')
        for key in ('run_hash','driver_sha256'):
            value=run.get(key)
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Solver evidence needs a valid '+key+'.')
        if len(json.dumps(run,allow_nan=False))>100000:
            raise ValueError('Structured solver evidence is limited to 100 KB.')
        evidence['solver_run']=clone(run)
    if any(not math.isfinite(row[key]) for row in rows for key in ('inductance_h','resistance_ohm','q') if row[key] is not None):
        raise ValueError('Derived EM metrics overflow; check sample units and magnitudes.')
    return dict(evidence=evidence,evidence_hash=digest(evidence),rows=rows,srf_hz=srf,srf_bracket_hz=bracket,
                qualification='Derived from supplied differential impedance. SRF is interpolated only when bracketed; no extrapolation or automatic solver qualification.')


def install_results(p,cid,did,data):
    if not isinstance(data,dict):raise ValueError('EM results must be a JSON object.')
    result=validate_results(data,manifest(p,cid,did,data.get('scope','context')))
    c=next(c for c in p['cells'] if c['id']==cid)
    r=next(r for r in c['parametric_devices'] if r['device_id']==did)
    r['em_characterization']=result
    return result


def result_status(p,cid,did):
    c=next(c for c in p['cells'] if c['id']==cid)
    r=next((r for r in c.get('parametric_devices',[]) if r['device_id']==did),{})
    result=r.get('em_characterization')
    if not result:return None,'No imported characterization.'
    try:
        checked=validate_results(result['evidence'],manifest(p,cid,did,result['evidence'].get('scope','context')))
        if checked!=result:raise ValueError('Stored characterization was modified; import the original evidence again.')
        return result,'Current characterization.'
    except (ValueError,KeyError,TypeError) as exc:return None,'Stale characterization: '+str(exc)
