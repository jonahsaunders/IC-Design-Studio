"""Sample public SKY130 core-MOS voltage boundaries through exported bindings.

Uses all 33 symbol views, 11 models, five corners and three selected temperatures.
The independent reference writes literal model instances and behavioral bias
sources; application decks use the product exporter and linear bias sources.
This does not establish SOA, reliability, continuous ranges or silicon accuracy.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.catalog import create_device
from icstudio.engines import parse_raw, run_deck
from icstudio.interchange import spice
from icstudio.model import clone, device, example, file_digest, save_project
from icstudio.pdks import model_lines, stage_model_deck
from scripts.qualify_mos_variants import manual, probes as variant_probes
from scripts.qualify_standard_mos import load_technology, write

SOURCES = ROOT/'docs/qualification/sky130-mos-bias-sources-v1'
AXES = ('gate', 'drain', 'body', 'off-drain')
CORNERS = ('nominal', 'ss', 'ff', 'sf', 'fs')
TEMPERATURES = (0, 27, 85)  # Selected integration points, not published limits.
PINS = ('d', 'g', 's', 'b')
STEPS = 40
REL, ABS = 1e-6, 1e-12
# Signed VDS/VGS/VBS relative to source. 16 V drain limits apply at VGS=0 only.
# The document also conditions these extended-drain limits on separate SOA.
LIMITS = {
    'nfet_01v8': ((0, 1.95), (0, 1.95), (-1.95, .3), (15, 17)),
    'nfet_01v8_lvt': ((0, 1.95), (0, 1.95), (-1.95, .3), (54, 56)),
    'nfet_03v3_nvt': ((0, 3.3), (0, 3.3), (-3.3, 0), (274, 276)),
    'nfet_05v0_nvt': ((0, 5.5), (0, 5.5), (-5.5, .3), (315, 317)),
    'nfet_g5v0d10v5': ((0, 11), (0, 5.5), (-5.5, 0), (357, 359)),
    'nfet_g5v0d16v0': ((0, 11), (0, 5.5), (-2, 0), (477, 480)),
    'pfet_01v8': ((-1.95, 0), (-1.95, 0), (-.1, 1.95), (98, 100)),
    'pfet_01v8_lvt': ((-1.95, 0), (-1.95, 0), (-.1, 1.95), (142, 144)),
    'pfet_01v8_hvt': ((-1.95, 0), (-1.95, 0), (-.1, 1.95), (186, 188)),
    'pfet_g5v0d10v5': ((-11, 0), (-5.5, 0), (0, 5.5), (394, 396)),
    'pfet_g5v0d16v0': ((-10, 0), (-5.5, 0), (0, 2), (439, 442)),
}


def sources():
    expected = {'device-details.rst': '506021827f52b26673daf8b580f8d79d408724af3138a65695bde86e5c1c6e49',
                'LICENSE': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'}
    lock = json.loads((SOURCES/'source-lock.json').read_bytes())
    if set(lock) != set(expected): raise ValueError('Changed voltage source inventory.')
    for name, sha in expected.items():
        if file_digest(SOURCES/name) != sha or lock[name]['sha256'] != sha or lock[name]['revision'] != '7198cf647113f56041e02abf3eb623692820c5e1':
            raise ValueError('Changed public voltage source: '+name)
    return lock


def rows(axis):
    if axis not in AXES: raise ValueError('Unknown voltage axis.')
    for original in variant_probes('sky-core'):
        model = original['model'].removeprefix('sky130_fd_pr__')
        drain, gate, body, lines = LIMITS[model]
        sign = -1 if original['pm'] else 1
        vmax = lambda pair: max(pair, key=abs)
        if axis == 'off-drain' and not model.endswith('g5v0d16v0'): continue
        for context in (0, 1):
            row = dict(original, tag=original['tag']+'c'+str(context), context=context)
            bias = dict(d=vmax(drain), g=vmax(gate), s=0., b=0.)
            if axis == 'gate':
                bias.update(d=vmax(drain)*(.05, 1)[context], b=vmax(body)*context)
                driven, span = 'g', gate
            elif axis == 'drain':
                bias.update(g=vmax(gate)*(.5, 1)[context], b=vmax(body)*context)
                driven, span = 'd', drain
            elif axis == 'body':
                bias.update(d=vmax(drain)*(.05, .5)[context], g=vmax(gate)*(.75, 1)[context])
                driven, span = 'b', body
            else:
                bias.update(g=0., b=vmax(body)*context)
                driven, span = 'd', tuple(sorted((0, sign*16.)))
            row.update(bias=bias, driven=driven, span=span, documentation_lines=lines)
            yield row


def fixture(tech, axis):
    p = example('empty'); p['pdk'] = clone(tech); c = p['cells'][0]; c['devices'] = []
    c['name'] = 'sky130_bias_boundaries'
    c['devices'].append(device('V', 'VSWEEP', value='0', nets={'p':'sweep', 'n':'0'}))
    drivers = []
    for row in rows(axis):
        tag = row['tag']; d = create_device(tech, row['key'], 'D'+tag)
        d['model_params'].update(w=row['w'], l=row['l'], nf=row['nf'], mult=row['copies'])
        if d['kind'] in ('NMOS', 'PMOS'): d['params'].update(w=f"{row['w']}u", l=f"{row['l']}u")
        d['nets'] = {pin: tag+pin for pin in PINS}
        for pin in PINS:
            value, negative = row['bias'][pin], '0'
            if pin == row['driven']:
                low, high = row['span']; value, negative = low, tag+'drive'
                drivers.append(f'E{tag} {negative} 0 sweep 0 {high-low:.12g}')
            c['devices'].append(device('V', 'V'+tag+pin, value=str(value), nets={'p':d['nets'][pin], 'n':negative}))
        c['devices'].append(d)
    for index, d in enumerate(c['devices']): d.update(x=(index%16)*300, y=(index//16)*300)
    return p, drivers


def independent(tech, axis, corner, temperature):
    lines = ['* Independent public-voltage reference', *model_lines(tech, corner), 'VSWEEP sweep 0 0']
    for row in rows(axis):
        tag = row['tag']
        for pin in PINS:
            value = f"{row['bias'][pin]:.12g}"
            if pin == row['driven']:
                low, high = row['span']; value = f'{low:.12g}+({high-low:.12g})*v(sweep)'
            lines += [f'B{tag}{pin} {tag}{pin}bias 0 V={{{value}}}', f'V{tag}{pin} {tag}{pin} {tag}{pin}bias 0']
        lines.append('X'+tag+' '+' '.join(tag+pin for pin in PINS)+' '+row['model']+' '+manual(row))
    return '\n'.join([*lines, f'.temp {temperature}', f'.dc VSWEEP 0 1 {1/STEPS:.12g}', '.end', ''])


def raw(path):
    names, values, complex_data = parse_raw(path)
    if complex_data: raise ValueError('Expected DC voltage-boundary output.')
    return dict(x=[row[0] for row in values],
                currents={name[2:-1].lower(): [row[i] for row in values] for i,name in enumerate(names) if name.lower().startswith('i(')},
                traces={name[2:-1].lower(): [row[i] for row in values] for i,name in enumerate(names) if name.lower().startswith('v(')})


def compare(actual, reference, axis, *, fault=False):
    grid = [i/STEPS for i in range(STEPS+1)]; errors = {}
    for result in (actual, reference):
        if len(result['x']) != len(grid) or any(not math.isfinite(a) or abs(a-b)>1e-9 for a,b in zip(result['x'],grid)):
            raise ValueError('Missing or changed voltage sweep coordinates.')
        for row in rows(axis):
            for pin in PINS:
                for collection, key in (('currents','v'+row['tag']+pin), ('traces',row['tag']+pin)):
                    values = result[collection].get(key, [])
                    if len(values)!=len(grid) or not all(math.isfinite(v) for v in values): raise ValueError('Missing/nonfinite terminal data: '+key)
            # Check actual electrical terminals, not just the requested source.
            # Fault circuits intentionally alter those terminals.
            if result is reference or not fault:
                for pin in PINS:
                    expected = [row['span'][0]+(row['span'][1]-row['span'][0])*g for g in grid] if pin==row['driven'] else [row['bias'][pin]]*len(grid)
                    if any(abs(a-b)>1e-9 for a,b in zip(result['traces'][row['tag']+pin],expected)):
                        raise ValueError('Terminal does not reach the declared voltage: '+row['tag']+pin)
    for row in rows(axis):
        currents = [reference['currents']['v'+row['tag']+pin] for pin in PINS]
        if axis!='off-drain' and max(max(v)-min(v) for v in currents)<1e-10:
            raise ValueError('Unexercised reference: '+row['tag'])
        for point in zip(*currents):
            if abs(sum(point))>ABS+REL*max(abs(v) for v in point): raise ValueError('Reference current conservation failed.')
        errors[row['tag']] = max(abs(a-b)/(ABS+REL*abs(b)) for pin in PINS
            for a,b in zip(actual['currents']['v'+row['tag']+pin],reference['currents']['v'+row['tag']+pin]))
    return dict(status='PASS' if max(errors.values())<=1 else 'MISMATCH', device_errors=errors,
                devices=len(errors), terminal_vectors=4*len(errors), samples=STEPS+1,
                relative_tolerance=REL, absolute_tolerance_a=ABS)


def case(tech, axis, corner, temperature, out, engine):
    name=f'{axis}-{corner}-{temperature}'; folder=out/name; folder.mkdir()
    record=dict(name=name, axis=axis, corner=corner, temperature_c=temperature, status='RUNNING', faults=[])
    try:
        project, drivers=fixture(tech, axis); save_project(project,folder/'input.icproj')
        settings=dict(type='dc', source='VSWEEP', dc_start='0', dc_stop='1', dc_step=str(1/STEPS), corner=corner, temperature=temperature)
        def execute(label, text):
            dest=folder/label; dest.mkdir(); path=dest/'input.cir'
            path.write_bytes(stage_model_deck(tech,text,dest).encode())
            result=run_deck(project,project['top'],dict(deck=str(path),analysis=settings),engine,dest)
            write(dest/'result.json',result)
            return raw(dest/'deck.raw')
        def exported(p):
            text=spice(p,p['top'],settings,hierarchical=False)
            return text.rsplit('.end',1)[0]+'\n'+'\n'.join(drivers)+'\n.end\n'
        expected=execute('independent',independent(tech,axis,corner,temperature))
        actual=execute('application',exported(project))
        record['comparison']=compare(actual,expected,axis)
        if record['comparison']['status']!='PASS': raise ValueError('Exported device boundary response differs from reference.')
        for fault in ('wrong-multiplicity','gate-drain-swap'):
            q=clone(project)
            for d in q['cells'][0]['devices']:
                if not d.get('model_ref'): continue
                if fault=='wrong-multiplicity': d['model_params']['mult']*=2
                else: d['nets']['g'],d['nets']['d']=d['nets']['d'],d['nets']['g']
            check=compare(execute(fault,exported(q)),expected,axis,fault=True)
            if not all(v>1 for v in check['device_errors'].values()): raise ValueError('Not every faulty device was detected: '+fault)
            record['faults'].append(dict(fault=fault,status='detected',comparison=check))
        record['raw_sha256']={p.parent.name:file_digest(p) for p in folder.glob('*/deck.raw')}
        record['status']='PASS'
    except Exception as error:
        record.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',record)
    return record


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True); ap.add_argument('--ngspice',type=Path,required=True)
    ap.add_argument('--pilot',action='store_true'); ap.add_argument('--workers',type=int,choices=range(1,5),default=2)
    ap.add_argument('--axes',nargs='+',choices=AXES,default=list(AXES))
    a=ap.parse_args(); a.ngspice=a.ngspice.resolve(strict=True); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    identities=sources(); tech,identity=load_technology('sky130A')
    files=[Path(__file__),ROOT/'scripts/qualify_mos_variants.py',ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}; write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',pilot=a.pilot,
                scope='Source-backed voltage-boundary samples of 33 SKY130 core MOS symbol views / 11 models through exported application bindings. Separate SOA, reliability, continuous ranges, silicon accuracy, full geometry/temperature limits and physical qualification remain open.',
                sources=identities,limits=LIMITS,process=identity,engine_sha256=file_digest(a.ngspice),
                source_files_sha256=file_digest(out/'source-files.json'), probes={axis:list(rows(axis)) for axis in a.axes},cases=[])
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,axis,corner,temp,out,str(a.ngspice)) for axis in a.axes
              for corner in (('nominal',) if a.pilot else CORNERS) for temp in ((27,) if a.pilot else TEMPERATURES)]
        report['expected_cases']=len(jobs)
        for job in as_completed(jobs):
            row=job.result(); report['cases'].append(row); write(out/'qualification.json',report)
            print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda row:row['name']); write(out/'qualification.json',report)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__': raise SystemExit(main())
