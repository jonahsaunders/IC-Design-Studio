"""Sampled nonlinear reverse-pulse qualification of the public RF candidates.

Grounded anode, cathode 1 -> 1.5 -> 1 V. Independent RK4 junction-charge
integration and native timestep refinement; no forward, avalanche, statistical,
silicon calibration, continuous operating envelope or default promotion claim.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.diode_runtime import verify, THERMAL_VOLTAGE
from icstudio.engines import parse_raw
from icstudio.model import file_digest
from icstudio.spice_program import runtime_environment
from scripts.qualify_sky130_rf_bias import branches, JUNCTIONS, COEFFICIENTS, COMMON, model_text, public_sources
from scripts.prepare_sky130_rf_qualification import corner_sources
from scripts.qualify_sky130_rf_branches import GEOMETRIES, TEMPERATURES

FAULTS = ('none', 'missing-perimeter', 'wrong-capacitance', 'wrong-series-resistance')
POINTS = 833
RELATIVE_TOLERANCE = 1e-4
ABSOLUTE_TOLERANCE = 1e-12


def waveform(time, tau):
    s = time/tau
    if s <= 2:return 1.
    if s < 4:return 1+(s-2)*.25
    if s <= 14:return 1.5
    if s < 16:return 1.5-(s-14)*.25
    return 1.


def oracle(model, area, perimeter, aj, pj, temperature, step_ratio):
    """Integrate C(u) du/dt = -(u + Vc)/R - I(u), with u = Va_internal - Vc.

    The public model's two junction states evolve independently. Event times
    are exact integration boundaries. No simulator outputs enter this solution.
    """
    if not 0 < step_ratio <= .05:raise ValueError('Unverified oracle integration step.')
    j = JUNCTIONS[model]
    vte = 1.0791*THERMAL_VOLTAGE*(temperature+273.15)/300.15
    parts = branches(model,area,perimeter,aj,pj,temperature,0)
    initial = branches(model,area,perimeter,aj,pj,temperature,-1)
    potentials = [j['pb']-j['tpb']*(temperature-27),j['php']-j['tphp']*(temperature-27)]
    grading = [j['m'],j['mp']]
    tau = max(b['resistance']*b['capacitance'] for b in initial)
    fastest = min(b['resistance']*b['capacitance'] for b in branches(model,area,perimeter,aj,pj,temperature,-1.5))
    samples = [i*tau/32 for i in range(POINTS)]
    def rate(time, voltages):
        vd = waveform(time,tau); answer = []
        for u,p,pot,m in zip(voltages,parts,potentials,grading):
            if not -1.500001 <= u <= -.999999:raise ValueError('Transient oracle left its reverse-bias domain.')
            sat = p['conductance']*vte
            current = sat*math.expm1(u/vte) if u >= -3*vte else -sat*(1+(3*vte/(u*math.e))**3)
            cap = p['capacitance']/(1-u/pot)**m
            answer.append((-(u+vd)/p['resistance']-current)/cap)
        return answer
    time = 0.; y = [b['voltage'] for b in initial]; values = []
    events = [2*tau,4*tau,14*tau,16*tau]
    for target in samples:
        while time < target:
            stop = min([target,*[e for e in events if e > time]])
            h = min(stop-time,fastest*step_ratio)
            a = rate(time,y)
            b = rate(time+h/2,[v+h*d/2 for v,d in zip(y,a)])
            c = rate(time+h/2,[v+h*d/2 for v,d in zip(y,b)])
            d = rate(time+h,[v+h*k for v,k in zip(y,c)])
            y = [v+h*(a0+2*b0+2*c0+d0)/6 for v,a0,b0,c0,d0 in zip(y,a,b,c,d)]
            time = min(stop,time+h)
        values.append(-sum((u+waveform(target,tau))/p['resistance'] for u,p in zip(y,parts)))
    return dict(time=samples,current=values,tau=tau,fastest=fastest)


def normalized(actual, expected):
    if len(actual) != len(expected) or not actual:raise ValueError('Incomplete transient comparison.')
    if any(not math.isfinite(x) for x in (*actual,*expected)):raise ValueError('Nonfinite transient comparison.')
    return max(abs(a-b)/(ABSOLUTE_TOLERANCE+RELATIVE_TOLERANCE*abs(b)) for a,b in zip(actual,expected))


def inspect(path, reference):
    names,rows,is_complex = parse_raw(path)
    if is_complex or names != ['time','v(d)','i(vdrive)'] or len(rows) != POINTS:
        raise ValueError('Incomplete RF transient output.')
    for row,time in zip(rows,reference['time']):
        if (len(row)!=3 or any(not math.isfinite(v) for v in row)
                or not math.isclose(row[0],time,rel_tol=1e-9,abs_tol=1e-24)
                or abs(row[1]-waveform(time,reference['tau'])) > 1e-9):
            raise ValueError('Changed transient time axis or voltage stimulus.')
    current = [r[2] for r in rows]
    error = normalized(current,reference['current'])
    return dict(accepted=error<=1,maximum_normalized_error=error,current=current,raw_sha256=file_digest(path))


def fault_model(model, sources, fault):
    if fault in ('none','missing-perimeter'):return model_text(model,sources,fault)
    text = model_text(model,sources,'none')
    if fault == 'wrong-capacitance':
        text,count = re.subn(r"(?im)^(\+\s*(?:cj|cjsw)\s*=\s*')",r'\g<1>2*',text)
        if count != 2:raise ValueError('Capacitance fault did not alter both branches.')
    elif fault == 'wrong-series-resistance':
        if text.count('rp1_diode/perim') != 1:raise ValueError('Ambiguous RF resistance fault.')
        text = text.replace('rp1_diode/perim','2*rp1_diode/perim')
    else:raise ValueError('Unknown transient fault.')
    return text


def deck(model, area, perimeter, temperature, parameters, reference, refinement):
    if refinement not in (160,320):raise ValueError('Unverified native timestep.')
    tau = reference['tau']
    pwl = ' '.join(f'{s*tau:.17g} {v}' for s,v in [(0,1),(2,1),(4,1.5),(14,1.5),(16,1),(26,1)])
    return '\n'.join(['* Nonlinear public RF reverse pulse','.include models.spice','.param',parameters,
        '.option scale=1u gmin=1e-30 reltol=1e-5 abstol=1e-14 vntol=1e-8 method=gear',f'.temp {temperature}',
        f'Vdrive d 0 PWL({pwl})',f'X1 0 d {COMMON}rf_diode_{model} area={area} perim={perimeter}',
        '.control','set filetype=ascii','set numdgt=16',
        f'tran {tau/32:.17g} {26*tau:.17g} 0 {reference["fastest"]/refinement:.17g}',
        'linearize v(d) i(vdrive)','write tran.raw time v(d) i(vdrive)','quit','.endc','.end',''])


def qualify(executable, output, pilot=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    executable=str(Path(executable).resolve());runtime=verify(executable,output/'runtime')
    if runtime['status']!='PASS' or runtime['behavior']['mode']!='unscaled-explicit-area':
        raise ValueError('Transient qualification requires verified RF runtime behavior.')
    lock,sources=public_sources();corner_source,corners=corner_sources()
    report=dict(schema=1,status='RUNNING',qualified=False,chunk_complete=False,pilot=pilot,scope=__doc__,source=lock,
                runner_sha256=file_digest(__file__),engine_sha256=file_digest(executable),corner_source=corner_source,corners={},cases=[],
                relative_tolerance=RELATIVE_TOLERANCE,absolute_current_tolerance_a=ABSOLUTE_TOLERANCE,
                native_refinements=[160,320],oracle_step_ratios=[.05,.025],oracle_maximum_normalized_difference=.01)
    def retain(): (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    for corner in (('tt',) if pilot else ('tt','ss','ff')):
        parameters='\n'.join(line for line in corners[corner]['text'].splitlines() if not line.startswith('*') and any('diode_'+m+'__' in line for m in COEFFICIENTS))
        values={k:float(v) for k,v in re.findall(r'(sky130\w+)\s*=\s*([\d.eE+-]+)',parameters)}
        report['corners'][corner]=dict(sha256=corners[corner]['sha256'],parameters=values)
        for model in COEFFICIENTS:
            aj=values[COMMON+'diode_'+model+'__ajunction_mult'];pj=values[COMMON+'diode_'+model+'__pjunction_mult']
            for temperature in ((27,) if pilot else TEMPERATURES):
                for area,perimeter in (GEOMETRIES[:1] if pilot else GEOMETRIES):
                    name=f'{corner}-{model}-{temperature}-{area}-{perimeter}';folder=output/name;folder.mkdir()
                    coarse=oracle(model,area,perimeter,aj,pj,temperature,.05)
                    reference=oracle(model,area,perimeter,aj,pj,temperature,.025)
                    convergence=normalized(coarse['current'],reference['current'])
                    (folder/'oracle.json').write_text(json.dumps(dict(coarse=coarse,fine=reference,convergence=convergence)))
                    if convergence>.01:raise ValueError('Independent transient solution did not converge.')
                    row=dict(name=name,model=model,temperature_c=temperature,corner=corner,area_um2=area,perimeter_um=perimeter,oracle_convergence=convergence,
                             oracle_sha256=file_digest(folder/'oracle.json'),runs=[])
                    nominal=[]
                    for fault in FAULTS:
                        for refinement in ((160,320) if fault=='none' else (320,)):
                            case=folder/f'{fault}-{refinement}';case.mkdir()
                            (case/'models.spice').write_text(fault_model(model,sources,fault),encoding='utf-8')
                            (case/'input.cir').write_text(deck(model,area,perimeter,temperature,parameters,reference,refinement),encoding='utf-8')
                            with (case/'engine.log').open('wb') as log:
                                run=subprocess.run([executable,'-n','-D','ngbehavior=hsa','-b','input.cir'],cwd=case,stdout=log,stderr=subprocess.STDOUT,timeout=60,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                                    env={**(runtime_environment(executable) or os.environ),'OMP_THREAD_LIMIT':'1'})
                            if run.returncode:raise ValueError('Native transient solver failed: '+str(case))
                            result=inspect(case/'tran.raw',reference);current=result.pop('current')
                            if fault=='none':nominal.append(current)
                            row['runs'].append(dict(fault=fault,refinement=refinement,**result,status='PASS' if result['accepted']==(fault=='none') else 'FAIL'))
                    row['native_convergence']=normalized(nominal[0],nominal[1])
                    row['status']='PASS' if all(r['status']=='PASS' for r in row['runs']) and row['native_convergence']<=1 else 'FAIL'
                    report['cases'].append(row);retain();print(name,row['status'],flush=True)
    report['status']='PASS' if all(c['status']=='PASS' for c in report['cases']) else 'FAIL';retain();return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ngspice',required=True);p.add_argument('--output',required=True,type=Path);p.add_argument('--pilot',action='store_true')
    a=p.parse_args();result=qualify(a.ngspice,a.output,a.pilot);print(result['status'],len(result['cases']),'conditions');raise SystemExit(result['status']!='PASS')
