"""Independent selected terminal responses for every placeable MOS symbol.

These are integration test points, not complete operating ranges, ESD ratings,
RF accuracy or physical qualification. Model names, pins and instance equations
below are explicit source contracts; reference calls never use the emitter.
"""
import argparse, cmath, json, math, sys, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import clone, device, example, file_digest, save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice, run_deck
from icstudio.osdi import configure, preload
from icstudio.pdks import model_lines, stage_model_deck
from scripts.qualify_standard_mos import PROFILES, load_technology, write

SKY_CORE = (
    'nfet3_01v8', 'nfet3_01v8_lvt', 'nfet3_03v3_nvt', 'nfet3_05v0_nvt',
    'nfet3_g5v0d10v5', 'nfet3_g5v0d16v0', 'nfet_01v8', 'nfet_01v8_lvt',
    'nfet_01v8_lvt_nf', 'nfet_01v8_nf', 'nfet_03v3_nvt', 'nfet_03v3_nvt_nf',
    'nfet_05v0_nvt', 'nfet_05v0_nvt_nf', 'nfet_g5v0d10v5', 'nfet_g5v0d10v5_nf',
    'nfet_g5v0d16v0', 'nfet_g5v0d16v0_nf', 'pfet3_01v8', 'pfet3_01v8_hvt',
    'pfet3_01v8_lvt', 'pfet3_g5v0d10v5', 'pfet3_g5v0d16v0', 'pfet_01v8',
    'pfet_01v8_hvt', 'pfet_01v8_hvt_nf', 'pfet_01v8_lvt', 'pfet_01v8_lvt_nf',
    'pfet_01v8_nf', 'pfet_g5v0d10v5', 'pfet_g5v0d10v5_nf', 'pfet_g5v0d16v0',
    'pfet_g5v0d16v0_nf')
SKY_HV = ('nfet3_20v0', 'nfet_20v0', 'nfet_20v0_iso', 'nfet_20v0_nvt',
          'nfet_20v0_zvt', 'pfet3_20v0', 'pfet_20v0')
SKY_ESD = ('nfet_01v8_esd', 'nfet_g5v0d10v5_esd')
GF = ('nfet3_03v3', 'nfet3_05v0', 'nfet3_06v0', 'nfet_03v3', 'nfet_03v3_dss',
      'nfet_05v0', 'nfet_06v0', 'nfet_06v0_dss', 'nfet_06v0_nvt',
      'pfet3_03v3', 'pfet3_05v0', 'pfet3_06v0', 'pfet_03v3', 'pfet_03v3_dss',
      'pfet_05v0', 'pfet_06v0', 'pfet_06v0_dss')
IHP = ('sg13_hv_nmos', 'sg13_hv_pmos', 'sg13_hv_rf_nmos', 'sg13_hv_rf_pmos',
       'sg13_lv_nmos', 'sg13_lv_pmos', 'sg13_lv_rf_nmos', 'sg13_lv_rf_pmos')
GROUPS = {'sky-core': ('sky130A', SKY_CORE), 'sky-hv': ('sky130A', SKY_HV),
          'sky-esd': ('sky130A', SKY_ESD), 'gf-c': ('gf180mcuC', GF),
          'gf-d': ('gf180mcuD', GF), 'ihp-mos': ('ihp-sg13g2', IHP),
          'ihp-clamp': ('ihp-sg13g2', ('nmoscl_2', 'nmoscl_4'))}
REL, ABS = 1e-6, 1e-12
FREQUENCIES = [1e3 * 10**(i/5) for i in range(31)]


def probes(group):
    target, names = GROUPS[group]
    for index, name in enumerate(names):
        for shape in (0, 1):
            m = 1 if shape == 0 else 3
            w, l, nf = (4., 1., 1) if shape == 0 else (8., 2., 2)
            model = name.replace('fet3_', 'fet_').removesuffix('_nf')
            pins = ('d', 'g', 's', 'b')
            pm = name.startswith('pfet') or name.endswith('pmos')
            if target == 'sky130A':
                prefix = 'sky130_fd_pr/'
                # These public models contain discrete size bins, not a general
                # W/L rectangle. Keep each selected point inside an actual bin.
                if model == 'nfet_03v3_nvt': w, l, nf = (1 if shape == 0 else 4), .5, 1
                if model == 'nfet_05v0_nvt': w, l, nf = (1 if shape == 0 else 10), (.9 if shape == 0 else 2), 1
                if model == 'nfet_g5v0d16v0': w, l, nf = (5 if shape == 0 else 20), .7, 1
                if model == 'pfet_g5v0d16v0': w, l, nf = (5 if shape == 0 else 20), .66, 1
                if group == 'sky-hv':
                    w, l = {'nfet_20v0': (29.41, 2.95), 'nfet_20v0_iso': (30, 1.5),
                            'nfet_20v0_nvt': (30, 1.5), 'nfet_20v0_zvt': (30, 5),
                            'pfet_20v0': (30, .5)}[model]
                    nf = 1
                    if name.endswith('_iso'): pins += ('sub',)
                if group == 'sky-esd':
                    model = 'esd_' + name.removesuffix('_esd'); nf = 1
                    w, l = ((20.35, .165) if shape == 0 else (40.31, .165)) if name == 'nfet_01v8_esd' else ((21.5, .55) if shape == 0 else (30.25, 1))
                model = 'sky130_fd_pr__' + model
            elif target.startswith('gf180'):
                prefix = 'symbols/'
                if 'fet3_' in name: pins = ('d', 'g', 's', 'body')
                if name == 'nfet_06v0_nvt': l = 1.8 if shape == 0 else 2
            else:
                prefix = 'sg13g2_pr/'; model = name.replace('_rf_', '_')
                if group == 'ihp-clamp': pins = ('vdd', 'vss'); w = l = 0; nf = 1
            yield dict(tag=f'q{index}s{shape}', key=prefix+name+'.sym', name=name, model=model,
                       pins=pins, shape=shape, w=w, l=l, nf=nf, copies=m, pm=pm, target=target)


def manual(row):
    w, l, nf, m = (row[k] for k in ('w', 'l', 'nf', 'copies'))
    t, name = row['target'], row['name']
    if name.startswith('nmoscl'): return f'm={m}'
    if t == 'ihp-sg13g2':
        return f'w={w:g}u l={l:g}u ng={nf} m={m} mm_ok=1' + (' rfmode=1' if '_rf_' in name else '')
    if t == 'sky130A' and '20v0' in name: return f'w={w:g} l={l:g} m={m}'
    scale = 1 if t == 'sky130A' else 1e-6
    # SKY _nf symbols specify width per finger; ordinary views specify total W.
    total = w * nf if name.endswith('_nf') else w
    wd, ld, e = total*scale, l*scale, (.29 if t == 'sky130A' else .18)*scale
    values = dict(w=wd, l=ld, nf=nf, ad=math.floor((nf+1)/2)*wd/nf*e,
                  **{'as': math.floor((nf+2)/2)*wd/nf*e},
                  pd=2*math.floor((nf+1)/2)*(wd/nf+e), ps=2*math.floor((nf+2)/2)*(wd/nf+e),
                  nrd=e/wd, nrs=e/wd, sa=0, sb=0, sd=0, m=m)
    if t == 'sky130A': values['mult'] = m
    if name.endswith('_dss'):
        values.update(d_sab=(2.78 if name.startswith('pfet') else 3.78)*1e-6, s_sab=.28e-6)
    return ' '.join(f'{k}={v:.12g}' for k,v in values.items())


def voltages(row):
    if row['name'].startswith('nmoscl'): return {'vdd': 0, 'vss': 0}
    return dict(d=.6, g=0, s=1.2 if row['pm'] else 0,
                **{row['pins'][3]: 1.35 if row['pm'] else -.15},
                **({'sub': -.3} if len(row['pins']) == 5 else {}))


def fixture(tech, group, drive, osdi):
    p = example('empty'); p['pdk'] = clone(tech); c = p['cells'][0]; c['devices'] = []
    v = device('V', 'VG', 0, 0, value='.8', nets={'p': 'sweep', 'n': '0'}); v['source']['ac'] = '0'; c['devices'].append(v)
    for r in probes(group):
        d = create_device(tech, r['key'], 'D'+r['tag'])
        if r['name'].startswith('nmoscl'): d['model_params']['m'] = r['copies']
        else:
            d['model_params'].update(w=r['w']*(1 if r['target']=='sky130A' else 1e-6),
                                     l=r['l']*(1 if r['target']=='sky130A' else 1e-6))
            # Typed MOS sizes use params; generic five/hidden-pin views use model_params.
            if d['kind'] in ('NMOS', 'PMOS'): d['params'].update(w=f"{r['w']}u", l=f"{r['l']}u")
            d['model_params']['mult' if r['target']=='sky130A' else 'm'] = r['copies']
            if '20v0' not in r['name']: d['model_params']['ng' if r['target']=='ihp-sg13g2' else 'nf'] = r['nf']
        d['nets'] = {pin: r['tag']+pin for pin in r['pins']}
        for pin, value in voltages(r).items():
            v = device('V', 'V'+r['tag']+pin, 0, 0, value=str(value),
                       nets={'p': d['nets'][pin], 'n': 'sweep' if pin in ('g', 'vdd') else '0'})
            v['source']['ac'] = str(int(pin == drive)); c['devices'].append(v)
        c['devices'].append(d)
    # Separate explicitly labelled terminals for a valid schematic handoff.
    for index, d in enumerate(c['devices']): d.update(x=(index%10)*300,y=(index//10)*300)
    if GROUPS[group][0] == 'ihp-sg13g2': p['simulation_runtime'] = {'osdi': clone(osdi)}
    return p


def independent(tech, group, drive, corner, temp):
    lines = ['* Independent MOS variant terminal contracts', *model_lines(tech, corner), 'VG sweep 0 .8 AC 0']
    for r in probes(group):
        for pin, value in voltages(r).items():
            lines.append(f'V{r["tag"]}{pin} {r["tag"]}{pin} '+('sweep' if pin in ('g', 'vdd') else '0')+f' DC {value:g} AC {int(pin == drive)}')
        lines.append('X'+r['tag']+' '+' '.join(r['tag']+pin for pin in r['pins'])+' '+r['model']+' '+manual(r))
    return '\n'.join([*lines, f'.temp {temp}', '.dc VG 0 1.2 .03' if drive == 'dc' else '.ac dec 5 1k 1g', '.end', ''])


def currents(result, rows, drive):
    domain = [i*.03 for i in range(41)] if drive == 'dc' else FREQUENCIES
    x = result.get('x', [])
    if len(x) != len(domain) or any(not math.isfinite(a) or not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-14) for a,b in zip(x,domain)):
        raise ValueError('Invalid MOS probe domain.')
    values = {k.casefold():v for k,v in result.get('currents', {}).items()}
    phases = {k.casefold():v for k,v in result.get('current_phase', {}).items()}; out = {}
    for r in rows:
        for pin in r['pins']:
            key = 'v'+r['tag']+pin; v = values.get(key, [])
            if len(v) != len(domain) or any(not math.isfinite(a) for a in v): raise ValueError('Invalid MOS current: '+key)
            if drive != 'dc':
                p = phases.get(key, [])
                if len(p) != len(domain) or any(not math.isfinite(a) for a in p) or any(a < 0 for a in v): raise ValueError('Invalid MOS phase: '+key)
                v = [cmath.rect(a,math.radians(b)) for a,b in zip(v,p)]
            out[key] = v
    return out


def compare(actual, reference, rows, drive):
    a, b = currents(actual, rows, drive), currents(reference, rows, drive)
    if drive == 'dc':
        for r in rows:
            v = b['v'+r['tag']+r['pins'][0]]
            if max(v)-min(v) < 1e-10: raise ValueError('Unexercised reference DC current: '+r['name'])
    # Enforce signed/complex current conservation on the reference only: faults
    # can disconnect a probe while the simulator still returns valid numbers.
    for r in rows:
        for values in zip(*(b['v'+r['tag']+p] for p in r['pins'])):
            if abs(sum(values)) > 1e-11+1e-6*max(abs(v) for v in values): raise ValueError('Reference current conservation failed: '+r['name'])
    errors = {k:max(abs(u-v)/(ABS+REL*abs(v)) for u,v in zip(a[k],b[k])) for k in b}
    per_device = {r['tag']:max(errors['v'+r['tag']+p] for p in r['pins']) for r in rows}
    return dict(status='PASS' if max(errors.values()) <= 1 else 'MISMATCH', device_errors=per_device,
                vectors=len(errors), samples=len(reference['x']), maximum_normalized_error=max(errors.values()),
                relative_tolerance=REL, absolute_tolerance_a=ABS)


def case(tech, group, corner, temp, drive, out, engine, osdi):
    name=f'{group}-{corner}-{temp}-{drive}'; folder=out/name; folder.mkdir()
    record=dict(name=name, group=group, corner=corner, temperature_c=temp, drive=drive, status='RUNNING')
    rows=list(probes(group))
    try:
        p=fixture(tech,group,drive,osdi); save_project(p,folder/'input.icproj')
        settings=dict(type='dc' if drive=='dc' else 'ac', corner=corner, temperature=temp,
                      source='VG', dc_start='0', dc_stop='1.2', dc_step='.03', start='1k',end='1g',points=5)
        app,ref=folder/'application',folder/'independent';app.mkdir();ref.mkdir()
        a=run_ngspice(p,p['top'],settings,engine,app)
        text=preload(p,stage_model_deck(tech,independent(tech,group,drive,corner,temp),ref),ref)
        path=ref/'reference.cir';path.write_bytes(text.encode())
        b=run_deck(p,p['top'],dict(deck=str(path),analysis=settings),engine,ref)
        write(app/'comparison-result.json',a);write(ref/'comparison-result.json',b)
        record['comparison']=compare(a,b,rows,drive)
        record['raw_sha256']=dict(application=file_digest(app/'result.raw'),independent=file_digest(ref/'deck.raw'))
        if record['comparison']['status']!='PASS':raise ValueError('Independent MOS variant currents differ.')
        if group=='ihp-mos' and drive=='g':
            q=clone(p);rf_rows=[r for r in rows if '_rf_' in r['name']]
            for r in rf_rows:
                next(d for d in q['cells'][0]['devices'] if d['name']=='D'+r['tag'])['model_params']['rfmode']=0
            dest=folder/'disabled-rf-mode';dest.mkdir();save_project(q,dest/'input.icproj')
            changed=run_ngspice(q,q['top'],settings,engine,dest);write(dest/'comparison-result.json',changed)
            check=compare(changed,b,rows,drive)
            record['rf_mode_control']=dict(comparison=check,raw_sha256=file_digest(dest/'result.raw'))
            if not all(check['device_errors'][r['tag']]>1 for r in rf_rows):raise ValueError('RF-mode difference was not detected on every RF view.')
        if drive=='dc':
            record['faults']=[]
            for fault in ('wrong-multiplicity','wrong-terminal'):
                q=clone(p)
                for r in rows:
                    d=next(d for d in q['cells'][0]['devices'] if d['name']=='D'+r['tag'])
                    if fault=='wrong-multiplicity':d['model_params']['mult' if r['target']=='sky130A' else 'm']*=2
                    elif r['name'].startswith('nmoscl'):d['nets']['vdd'],d['nets']['vss']=d['nets']['vss'],d['nets']['vdd']
                    else:d['nets']['g']=d['nets']['s']
                dest=folder/fault;dest.mkdir();save_project(q,dest/'input.icproj')
                changed=run_ngspice(q,q['top'],settings,engine,dest);write(dest/'comparison-result.json',changed)
                check=compare(changed,b,rows,drive)
                record['faults'].append(dict(fault=fault,comparison=check,raw_sha256=file_digest(dest/'result.raw')))
                if not all(v>1 for v in check['device_errors'].values()):raise ValueError('Missed MOS fault: '+fault)
        record['status']='PASS'
    except Exception as error: record.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',record);return record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--ngspice',required=True);ap.add_argument('--osdi',type=Path,required=True)
    ap.add_argument('--groups',nargs='+',choices=GROUPS,default=list(GROUPS));ap.add_argument('--pilot',action='store_true')
    ap.add_argument('--drives',nargs='+',choices=('dc','d','g','s','b','body','sub','vdd','vss'))
    ap.add_argument('--correct-bindings',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,9),default=4)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    if a.correct_bindings:sources.append(ROOT/'scripts/prepare_mos_variant_bindings.py')
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',cases=[],processes={},
                scope='Selected independent DC and complex terminal integration for placeable MOS symbol variants. No full bias/geometry/temperature envelope, ESD rating, silicon, RF-accuracy or physical qualification.',
                probes={g:list(probes(g)) for g in a.groups},engine_sha256=file_digest(a.ngspice),osdi=osdi,source_files_sha256=file_digest(out/'source-files.json'))
    technologies={}
    for target in dict.fromkeys(GROUPS[g][0] for g in a.groups):
        tech,identity=load_technology(target)
        if a.correct_bindings and target != 'sky130A':
            from scripts.prepare_mos_variant_bindings import prepare
            dest=out/(target+'-corrected');identity.update(prepare(ROOT/'icstudio/assets/pdks'/target,dest))
            package=json.loads((dest/'package.json').read_bytes());tech=clone(package['technology'])
            tech.update(package_root=str(dest),package_lock={k:package[k] for k in ('id','revision','files')})
        technologies[target]=tech;report['processes'][target]=identity
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for group in a.groups:
            target=GROUPS[group][0]
            drives=['dc',*dict.fromkeys(p for r in probes(group) for p in r['pins'])]
            if a.drives:drives=[d for d in drives if d in a.drives]
            for corner in (('nominal',) if a.pilot else PROFILES[target]['corners']):
                for temp in ((27,) if a.pilot else (0,27,85)):
                    for drive in drives:jobs.append(pool.submit(case,technologies[target],group,corner,temp,drive,out,a.ngspice,osdi))
        for job in as_completed(jobs):
            r=job.result();report['cases'].append(r);write(out/'qualification.json',report)
            print(r['name'],r['status'],r.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['cases'] and report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
