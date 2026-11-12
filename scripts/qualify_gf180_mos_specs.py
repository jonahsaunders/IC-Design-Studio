"""Compare GF180 standard MOS currents with pinned public specifications.

Execution validity, application/reference equivalence and published-bound
compliance are separate results. Differences never become passes by fitting
tolerances or rounding limits. Maximum-gm threshold extraction is diagnostic:
the public source names the method but does not specify its complete equation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv
import io
import json
import math
from pathlib import Path
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.catalog import create_device
from icstudio.engines import parse_raw,run_deck
from icstudio.interchange import spice
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import independent_device,load_technology,write

SOURCES=ROOT/'docs/qualification/gf180-mos-spec-sources-v1'
REVISION='de3240d7529a6970437ac3344820aaae7839f215'
HASHES={
 'LICENSE':'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
 'docs/analog/model_parameters/LV/LV_2_4.rst':'7f564e6e5673f495823eb3ecc5d1403b0a1f8be2a1d19e844e51186753e48c29',
 'docs/analog/model_parameters/LV/LV_2_5.rst':'4c6580655db93edcbda59bec3285b14960d82a1ef8d380119361b79bf89e824b',
 'docs/analog/spice/elec_specs/elec_specs_1.rst':'89d19dd6c1289da1fb956bb2e2fe9993641119ff1f9c1ed7400625bf1e04319f',
 'docs/analog/spice/elec_specs/tables_clear/1_Low_Voltage_Devices.csv':'7d63fbb662dc4fbc74897d985b5820b685e3d3f3b48f31c98a7eef0a925049cf',
 'docs/analog/model_parameters/LV/tables_clear/18_Corner.csv':'62c59793b0e40feb918981eafd28488c0b479fb858083ef03c8b86d952e8c8b7',
 'docs/analog/model_parameters/LV/tables_clear/19_mos_3p3.csv':'c3f0cca345c65babe328554f543a2eb9a79e4612e318320ea5019c0bbdcb2724',
}
TARGETS=('gf180mcuC','gf180mcuD');CORNERS=('nominal','ss','ff','sf','fs')
PINS=('d','g','s','b');COARSE=.005;FINE=.0025;REL=1e-6;ABS=1e-13
# Numerical comparison only: 100 fA equals 0.01 pA/um for this 10 um device.
# This bounds residuals observed with both default and tightened solver settings;
# it is never added to the published specification limits.
SOLVER='.options reltol=1e-9 abstol=1e-18 vntol=1e-12'


def source_contract(root=SOURCES):
    lock=json.loads((root/'sources.json').read_bytes())
    if set(lock)!=set(HASHES):raise ValueError('Changed public specification source inventory.')
    for name,h in HASHES.items():
        row=lock[name]
        if row['revision']!=REVISION or row['sha256']!=h or file_digest(root/name)!=h:
            raise ValueError('Changed public specification source: '+name)
    rows=list(csv.reader(io.StringIO((root/'docs/analog/spice/elec_specs/tables_clear/1_Low_Voltage_Devices.csv').read_text(encoding='utf-8'))))
    limits={pol:{} for pol in ('n','p')}
    for row in rows:
        if len(row)!=8 or row[2] not in ('NCH (NE2)','PCH (PE2)'):continue
        name='idsat_uA_um' if row[1].startswith('Idsat') else 'ioff_pA_um' if row[1].startswith('Ioff') else 'vth_v' if row[1]=='VT0' else None
        if name is None:continue
        pol='n' if row[2].startswith('NCH') else 'p'
        if name in limits[pol] or row[3]!='W/L = 10/0.28 (THIN GATE)':raise ValueError('Ambiguous electrical specification row.')
        lo,typ,hi=(None if s.strip()=='--' else float(s) for s in row[4:7])
        limits[pol][name]=dict(minimum=lo,typical=typ,maximum=hi,units=row[7],source_parameter=row[1])
    if any(set(v)!={'idsat_uA_um','ioff_pA_um','vth_v'} for v in limits.values()):raise ValueError('Incomplete electrical specification table.')
    return dict(sources=lock,limits=limits,width_um=10,length_um=.28,temperature_c=25,saturation_v=3.3,off_drain_v=3.63,linear_drain_v=.05,
        threshold_scope='Conventional max-gm tangent intercept minus signed VDS/2 is reported alongside the uncorrected intercept. The public source gives max-gm and VDS=0.05 V but not the complete equation; threshold is diagnostic, not an accepted specification gate.')


def rows():
    for pol,sign in (('n',1),('p',-1)):
        for mode,drain in (('lin',.05),('sat',3.3),('off',3.63)):
            yield dict(tag=pol+mode,polarity=pol,sign=sign,mode=mode,drain_v=sign*drain)


def fixture(tech):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c.update(name='mos_public_specs',devices=[])
    c['devices'].append(device('V','VSWEEP',value='0',nets={'p':'sweep','n':'0'}));drivers=[]
    for row in rows():
        tag=row['tag'];d=create_device(tech,'symbols/'+('nfet_03v3' if row['polarity']=='n' else 'pfet_03v3')+'.sym','M'+tag)
        d['params'].update(w='10u',l='.28u');d['nets']={pin:tag+pin for pin in PINS}
        for pin in PINS:
            value=row['drain_v'] if pin=='d' else 0;negative=tag+'drive' if pin=='g' and row['mode']!='off' else '0'
            c['devices'].append(device('V','V'+tag+pin,value=str(value),nets={'p':d['nets'][pin],'n':negative}))
        if row['mode']!='off':drivers.append(f'E{tag} {tag}drive 0 sweep 0 {row["sign"]}')
        c['devices'].append(d)
    return p,drivers


def settings(corner,step):
    return dict(type='dc',source='VSWEEP',dc_start='0',dc_stop='3.3',dc_step=str(step),corner=corner,temperature=25)


def independent(tech,target,corner,step):
    lines=['* Public specification probe; separately written instances and behavioral biases',*model_lines(tech,corner),'VSWEEP sweep 0 0']
    for row in rows():
        tag=row['tag']
        for pin in PINS:
            value=f'{row["sign"]}*v(sweep)' if pin=='g' and row['mode']!='off' else str(row['drain_v'] if pin=='d' else 0)
            lines.extend((f'B{tag}{pin} {tag}{pin}bias 0 V={{{value}}}',f'V{tag}{pin} {tag}{pin} {tag}{pin}bias 0'))
        fields=independent_device(target,row['polarity'],dict(w=10,l=.28,fingers=1,copies=1)).split();fields[0]='XREF'+tag;fields[1:5]=[tag+pin for pin in PINS];lines.append(' '.join(fields))
    return '\n'.join([*lines,SOLVER,'.temp 25',f'.dc VSWEEP 0 3.3 {step:.12g}', '.end',''])


def raw(path,step):
    names,values,complex_data=parse_raw(path);count=round(3.3/step)+1
    if complex_data or len(values)!=count or len({n.lower() for n in names})!=len(names):raise ValueError('Incomplete or duplicate DC specification data.')
    data={n.lower():[row[i] for row in values] for i,n in enumerate(names)};x=[row[0] for row in values]
    if any(not math.isfinite(v) or abs(v-i*step)>1e-9 for i,v in enumerate(x)):raise ValueError('Changed specification sweep coordinates.')
    currents={};conservation={}
    for row in rows():
        tag=row['tag']
        for pin in PINS:
            voltage=data.get('v('+tag+pin+')',[]);current=data.get('i(v'+tag+pin+')',[])
            if len(voltage)!=count or len(current)!=count or not all(math.isfinite(v) for v in voltage+current):raise ValueError('Missing/nonfinite specification terminal: '+tag+pin)
            expected=[row['sign']*v for v in x] if pin=='g' and row['mode']!='off' else [row['drain_v'] if pin=='d' else 0]*count
            if any(abs(a-b)>1e-9 for a,b in zip(voltage,expected)):raise ValueError('Incorrect actual terminal bias: '+tag+pin)
            currents[tag+pin]=[-v for v in current]
        samples=list(zip(*(currents[tag+pin] for pin in PINS)))
        conservation[tag]=max(abs(sum(sample)) for sample in samples)
        for sample in samples:
            if abs(sum(sample))>ABS+1e-7*max(abs(v) for v in sample):raise ValueError('Terminal current conservation failed: '+tag)
    return dict(x=x,currents=currents,raw_sha256=file_digest(path),maximum_current_conservation_residual_a=conservation)


def compare(actual,reference):
    if actual['x']!=reference['x'] or set(actual['currents'])!=set(reference['currents']):raise ValueError('Different comparison coordinates or terminals.')
    required={row['tag']+pin for row in rows() for pin in PINS}
    for result in (actual,reference):
        if len(result['x'])<9 or set(result['currents'])!=required or not all(math.isfinite(v) for v in result['x']):raise ValueError('Incomplete specification comparison.')
        if any(len(values)!=len(result['x']) or not all(math.isfinite(v) for v in values) for values in result['currents'].values()):raise ValueError('Incomplete/nonfinite specification currents.')
    errors={row['tag']:max(abs(a-b)/(ABS+REL*abs(b)) for pin in PINS for a,b in zip(actual['currents'][row['tag']+pin],reference['currents'][row['tag']+pin])) for row in rows()}
    return dict(status='PASS' if max(errors.values())<=1 else 'MISMATCH',device_errors=errors,relative_tolerance=REL,absolute_tolerance_a=ABS)


def threshold(gate_magnitude,current_a,polarity,drain_magnitude=.05):
    sign=1 if polarity=='n' else -1;x=list(gate_magnitude);y=[sign*v for v in current_a]
    if polarity not in ('n','p') or len(x)<9 or len(x)!=len(y) or not all(math.isfinite(v) for v in x+y) or any(b<=a for a,b in zip(x,x[1:])):
        raise ValueError('Invalid threshold sweep.')
    slopes=[(y[i+1]-y[i-1])/(x[i+1]-x[i-1]) for i in range(1,len(x)-1)];index=max(range(len(slopes)),key=slopes.__getitem__)+1;gm=slopes[index-1]
    if gm<=0 or index in (1,len(x)-2):raise ValueError('Threshold transconductance peak is absent or clipped.')
    intercept=sign*(x[index]-y[index]/gm)
    return dict(maximum_gm_a_v=gm,peak_gate_v=sign*x[index],tangent_intercept_v=intercept,linear_threshold_v=intercept-sign*drain_magnitude/2,used_for_acceptance=False)


def bound(value,definition):
    if not math.isfinite(value):raise ValueError('Nonfinite specification measurement.')
    lo,hi=definition['minimum'],definition['maximum'];passed=(lo is None or value>=lo) and (hi is None or value<=hi)
    return dict(status='PASS' if passed else 'OUTSIDE_PUBLISHED_BOUND',value=value,minimum=lo,maximum=hi,typical=definition['typical'],difference_from_typical=value-definition['typical'],units=definition['units'])


def measurements(data,contract):
    result={}
    for pol,sign in (('n',1),('p',-1)):
        sat=data['currents'][pol+'satd'][-1]*1e6/contract['width_um'];off=data['currents'][pol+'offd'][0]*1e12/contract['width_um']
        if sign*sat<=0 or sign*off<0:raise ValueError('Incorrect drain-current polarity.')
        result[pol]=dict(idsat=bound(sat,contract['limits'][pol]['idsat_uA_um']),ioff=bound(off,contract['limits'][pol]['ioff_pA_um']),threshold=threshold(data['x'],data['currents'][pol+'lind'],pol))
    return result


def altered(project,fault):
    p=clone(project)
    for d in p['cells'][0]['devices']:
        if not d.get('model_ref'):continue
        if fault=='wrong-multiplicity':d['model_params']['m']=2
        elif fault=='wrong-width':d['params']['w']='5u'
        elif fault=='gate-drain-swap':d['nets']['d'],d['nets']['g']=d['nets']['g'],d['nets']['d']
        else:raise ValueError('Unknown specification fault.')
    return p


def case(target,corner,out,engine,contract):
    folder=Path(out)/(target+'-'+corner);folder.mkdir();row=dict(target=target,corner=corner,execution_status='RUNNING',specification_status='NOT_RUN',faults=[])
    try:
        tech,identity=load_technology(target);row['package']=identity;p,drivers=fixture(tech);save_project(p,folder/'input.icproj')
        def execute(label,text,step,selected_corner=None):
            dest=folder/label;dest.mkdir();path=dest/'input.cir';path.write_bytes(stage_model_deck(tech,text,dest).encode())
            result=run_deck(p,p['top'],dict(deck=str(path),analysis=settings(selected_corner or corner,step)),engine,dest);write(dest/'result.json',result);return raw(dest/'deck.raw',step)
        def exported(q,selected,step):
            text=spice(q,q['top'],settings(selected,step),hierarchical=False);return text.rsplit('.end',1)[0]+'\n'+'\n'.join(drivers)+'\n'+SOLVER+'\n.end\n'
        metrics={};responses={}
        for name,step in (('coarse',COARSE),('fine',FINE)):
            expected=execute(name+'-independent',independent(tech,target,corner,step),step)
            actual=execute(name+'-application',exported(p,corner,step),step);comparison=compare(actual,expected)
            if comparison['status']!='PASS':raise ValueError('Application differs from the independent specification circuit.')
            responses[name]=(actual,expected);metrics[name]=measurements(actual,contract);row[name]=dict(comparison=comparison,measurements=metrics[name],raw_sha256={'application':actual['raw_sha256'],'independent':expected['raw_sha256']},maximum_current_conservation_residual_a={k:v['maximum_current_conservation_residual_a'] for k,v in (('application',actual),('independent',expected))})
        row['threshold_grid_change_v']={pol:abs(metrics['fine'][pol]['threshold']['linear_threshold_v']-metrics['coarse'][pol]['threshold']['linear_threshold_v']) for pol in ('n','p')}
        # Numerical convergence is an analysis check, never added to a published bound.
        if max(row['threshold_grid_change_v'].values())>1e-4:raise ValueError('Threshold grid has not converged to 0.1 mV.')
        expected=responses['coarse'][1]
        for fault in ('wrong-multiplicity','wrong-width','gate-drain-swap','wrong-corner'):
            changed=altered(p,fault) if fault!='wrong-corner' else p;selected=('ss' if corner=='nominal' else 'nominal') if fault=='wrong-corner' else corner
            result=compare(execute(fault,exported(changed,selected,COARSE),COARSE,selected),expected)
            if not all(v>1 for v in result['device_errors'].values()):raise ValueError('Not every deliberate fault was detected: '+fault)
            row['faults'].append(dict(fault=fault,detected=True,comparison=result))
        row['execution_status']='PASS';row['specification_status']='MISMATCH' if any(v[k]['status']!='PASS' for v in metrics['fine'].values() for k in ('idsat','ioff')) else 'PASS'
    except Exception as error:row.update(execution_status='FAIL',error=str(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',type=Path,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);engine=a.ngspice.resolve(strict=True)
    contract=source_contract();files=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in files};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',execution_status='RUNNING',specification_status='NOT_RUN',pilot=a.pilot,contract=contract,cases=[],engine=dict(path=str(engine),sha256=file_digest(engine)),source_files_sha256=file_digest(out/'source-files.json'),scope=__doc__)
    selected=[(target,corner) for target in TARGETS for corner in (('nominal',) if a.pilot else CORNERS)]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,t,c,out,str(engine),contract) for t,c in selected]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'record.json',report);print(row['target'],row['corner'],row['execution_status'],row['specification_status'],row.get('error',''),flush=True)
    report['source_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    complete=report['source_unchanged'] and sorted((row['target'],row['corner']) for row in report['cases'])==sorted(selected) and all(row['execution_status']=='PASS' for row in report['cases'])
    report['execution_status']='PASS' if complete else 'FAIL';report['specification_status']=('MISMATCH' if any(row['specification_status']=='MISMATCH' for row in report['cases']) else 'PASS') if complete else 'NOT_ACCEPTED'
    report['status']=report['specification_status'] if complete else 'FAIL';report['cases'].sort(key=lambda row:(row['target'],row['corner']));write(out/'record.json',report)
    return 1 if not complete else 2 if report['specification_status']=='MISMATCH' else 0


if __name__=='__main__':raise SystemExit(main())
