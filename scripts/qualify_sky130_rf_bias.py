"""Independent reverse-bias DC, AC and noise checks for public RF candidates.

Sampled 0 to 5 V reverse bias, three temperatures/corners and five rectangular
geometries. This verifies the public equations and application model derivative;
it does not establish measured-silicon accuracy or a safe operating envelope.
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
from icstudio.diode_runtime import THERMAL_VOLTAGE, verify
from icstudio.engines import parse_raw
from icstudio.model import file_digest
from icstudio.spice_program import runtime_environment
from scripts.prepare_sky130_rf_qualification import COMMON, public_sources, derivative, corner_sources
from scripts.qualify_sky130_rf_branches import COEFFICIENTS, GEOMETRIES, TEMPERATURES

JUNCTIONS = {
    'ps2nw': dict(pb=.5348, php=.5348, m=.4509, mp=.2433, tpb=.0022563, tphp=.00165),
    'pw2dn': dict(pb=.58758, php=.5348, m=.33982, mp=.23357, tpb=.0025003, tphp=.001675),
}
BIASES = (0, -.05, -.1, -.5, -1, -5, 0)  # Return to zero without resetting the circuit.
FAULTS = ('none', 'missing-perimeter', 'wrong-barrier', 'wrong-leakage')
FREQUENCIES = tuple(10*10**(i/10) for i in range(91))
CHARGE = 1.6021766208e-19
BOLTZMANN = 1.38064852e-23  # Constants used by the retained public engine equations.


def branches(model, area, perimeter, aj, pj, temperature, bias):
    """Solve each series resistor/junction independently by monotone bisection.

    Reverse IV uses the public simulator's cubic continuation below -3*N*Vt.
    TREF=30 controls IV; TLEVC=1 uses 27 C for barrier/capacitance correction.
    The public zero IKR disables reverse knee limiting; no avalanche is tested.
    """
    values = (area, perimeter, aj, pj, temperature, bias)
    if (not all(math.isfinite(v) for v in values) or min(area, perimeter, aj, pj) <= 0
            or perimeter**2 < 16*area or not -40 <= temperature <= 125 or not -5 <= bias <= 0):
        raise ValueError('Outside the explicit RF reverse-bias test domain.')
    c = {**COEFFICIENTS[model], **JUNCTIONS[model]}
    kelvin = temperature + 273.15; delta = temperature - 27; ratio = kelvin/303.15
    thermal = THERMAL_VOLTAGE*kelvin/300.15; vte = 1.0791*thermal
    width = perimeter/4 + math.sqrt(perimeter**2/16 - area); length = area/width
    resistance = ((c['ra1']/area+c['ra2']/(length/width+width/length))*(2*c['aj']-aj),
                  c['rp']/perimeter*(2*c['pj']-pj))
    saturation = (area*c['js']*ratio**(c['xti']/1.0791)*math.exp((ratio-1)*1.17/vte),
                  perimeter*c['jsw']*ratio**c['xti']*math.exp((ratio-1)*1.17/thermal))
    capacitance = (area*c['cj']*aj*(1+c['cta']*delta), perimeter*c['cjp']*pj*(1+.0008*delta))
    potential = (c['pb']-c['tpb']*delta, c['php']-c['tphp']*delta)
    result = []
    for sat, res, cap, pot, grading in zip(saturation, resistance, capacitance, potential, (c['m'], c['mp'])):
        if min(res, cap, pot) <= 0:raise ValueError('Nonphysical RF branch parameters.')
        def iv(voltage):
            if voltage >= -3*vte:
                return sat*math.expm1(voltage/vte), sat*math.exp(voltage/vte)/vte
            correction = (3*vte/(voltage*math.e))**3
            return -sat*(1+correction), sat*3*correction/voltage
        low, high = bias, 0
        for _ in range(100):
            mid = (low+high)/2; current, _ = iv(mid)
            if mid+res*current > bias:high = mid
            else:low = mid
        voltage = (low+high)/2; current, conductance = iv(voltage)
        result.append(dict(current=current, conductance=conductance, resistance=res,
                           capacitance=cap/(1-voltage/pot)**grading, voltage=voltage,
                           temperature_k=kelvin))
    return result


def expected(parts, frequency):
    admittance = 0j; noise_power = 0
    for branch in parts:
        r = branch['resistance']; y = branch['conductance']+2j*math.pi*frequency*branch['capacitance']
        transfer = 1+r*y
        admittance += y/transfer
        # Junction shot noise and resistor Johnson noise propagate separately
        # through the series branch. The 1-ohm ideal current-to-voltage sensor
        # makes the recorded voltage spectrum numerically equal to A/sqrt(Hz).
        noise_power += (2*CHARGE*abs(branch['current']) +
                        4*BOLTZMANN*branch['temperature_k']*r*abs(y)**2)/abs(transfer)**2
    return dict(dc=sum(b['current'] for b in parts), ac=-admittance, noise=math.sqrt(noise_power))


def read(path, complex_data, count, required):
    variables, rows, actual_complex = parse_raw(path)
    if (actual_complex != complex_data or len(rows) != count or len(set(variables)) != len(variables)
            or not set(required) <= set(variables)):
        raise ValueError('Incomplete RF analysis: '+str(path))
    if any(len(row) != len(variables) or any(not math.isfinite(abs(v)) for v in row) for row in rows):
        raise ValueError('Malformed or nonfinite RF analysis: '+str(path))
    return [dict(zip(variables, row)) for row in rows]


def inspect(folder, model, area, perimeter, aj, pj, temperature):
    checks = []; hashes = {}
    for index, bias in enumerate(BIASES):
        paths = {kind:folder/f'{kind}{index}.raw' for kind in ('op', 'ac', 'noise')}
        hashes.update({p.name:file_digest(p) for p in paths.values()})
        op = read(paths['op'], False, 1, ('v(d)', 'i(vdrive)'))[0]
        ac = read(paths['ac'], True, len(FREQUENCIES), ('frequency', 'v(d)', 'i(vdrive)'))
        noise = read(paths['noise'], False, len(FREQUENCIES), ('frequency', 'onoise_spectrum'))
        if abs(op['v(d)']+bias) > 1e-12:raise ValueError('Changed RF DC stimulus.')
        parts = branches(model, area, perimeter, aj, pj, temperature, bias)
        dc = expected(parts, 0)['dc']
        errors = dict(dc=abs(op['i(vdrive)']-dc)/(1e-18+1e-6*abs(dc)), ac=0, noise=0)
        for frequency, a, n in zip(FREQUENCIES, ac, noise):
            if (abs(a['frequency'].imag) > 0 or not math.isclose(a['frequency'].real, frequency, rel_tol=1e-9)
                    or not math.isclose(n['frequency'], frequency, rel_tol=1e-9) or abs(a['v(d)']-1) > 1e-12
                    or n['onoise_spectrum'] < 0):
                raise ValueError('Changed RF frequency domain or stimulus.')
            values = expected(parts, frequency)
            errors['ac'] = max(errors['ac'], abs(a['i(vdrive)']-values['ac'])/(1e-18+1e-6*abs(values['ac'])))
            errors['noise'] = max(errors['noise'], abs(n['onoise_spectrum']-values['noise'])/(1e-24+1e-6*values['noise']))
        checks.append(dict(bias_v=bias, maximum_normalized_error=errors, accepted=all(v <= 1 for v in errors.values())))
    return dict(accepted=all(c['accepted'] for c in checks), checks=checks, raw_sha256=hashes)


def model_text(model, sources, fault):
    primitive = sources[COMMON+'diode_'+model+'_noresistor.model.spice'].decode()
    original = sources[COMMON+'rf_diode_'+model+'.model.spice']
    wrapper = derivative(model, original).decode()
    if fault == 'missing-perimeter':wrapper = original.decode()
    elif fault in ('wrong-barrier', 'wrong-leakage'):
        keys = 'pb|php' if fault == 'wrong-barrier' else 'js|jsw'
        primitive, count = re.subn(r'(?im)^(\+\s*(?:'+keys+r')\s*=\s*)([0-9.eE+-]+)',
                                  lambda m:m[1]+format(float(m[2])*2,'.17g'), primitive)
        if count != 2:raise ValueError('Fault did not change both requested parameters.')
    elif fault != 'none':raise ValueError('Unknown RF model fault.')
    return primitive+'\n'+wrapper


def deck(model, area, perimeter, parameters, temperature):
    text = ['* RF reverse-bias DC, AC and noise', '.include models.spice', '.param', parameters,
            '.option scale=1u gmin=1e-30 reltol=1e-9 abstol=1e-24 vntol=1e-12', f'.temp {temperature}',
            'Vdrive d 0 0 ac 1', 'Hnoise nout 0 Vdrive 1',
            f'X1 0 d {COMMON}rf_diode_{model} area={area} perim={perimeter}',
            '.control', 'set filetype=ascii', 'set numdgt=16']
    for index, bias in enumerate(BIASES):
        text += [f'alter Vdrive {-bias}', 'op', f'write op{index}.raw all',
                 'ac dec 10 10 10g', f'write ac{index}.raw all',
                 'noise v(nout) Vdrive dec 10 10 10g', f'setplot noise{2*index+1}', f'write noise{index}.raw all']
    return '\n'.join([*text, 'quit', '.endc', '.end', ''])


def qualify(executable, output, pilot=False):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    executable = str(Path(executable).resolve()); runtime = verify(executable, output/'runtime')
    if runtime['status'] != 'PASS' or runtime['behavior']['mode'] != 'unscaled-explicit-area':
        raise ValueError('RF qualification requires verified unscaled AREA/PJ history.')
    lock, sources = public_sources(); corner_source, corners = corner_sources()
    report = dict(schema=1, status='RUNNING', qualified=False, chunk_complete=False, pilot=pilot,
                  scope=__doc__, source=lock, runner_sha256=file_digest(__file__), engine_sha256=file_digest(executable),
                  relative_tolerance=1e-6, absolute_current_tolerance_a=1e-18,
                  absolute_noise_tolerance_a_sqrt_hz=1e-24, biases_v=BIASES, frequencies_hz=FREQUENCIES,
                  grounding='Anode grounded; cathode driven. Avoids cancellation of tiny resistor currents at a large anode common-mode voltage.',
                  corner_source=corner_source, corners={}, cases=[])
    for corner in (('tt',) if pilot else ('tt', 'ss', 'ff')):
        parameters = '\n'.join(line for line in corners[corner]['text'].splitlines()
                               if not line.startswith('*') and any('diode_'+m+'__' in line for m in COEFFICIENTS))
        values = {name:float(value) for name,value in re.findall(r'(sky130\w+)\s*=\s*([\d.eE+-]+)',parameters)}
        report['corners'][corner] = dict(sha256=corners[corner]['sha256'], parameters=values)
        for model in COEFFICIENTS:
            aj = values[COMMON+'diode_'+model+'__ajunction_mult']; pj = values[COMMON+'diode_'+model+'__pjunction_mult']
            for temperature in ((27,) if pilot else TEMPERATURES):
                for area, perimeter in (GEOMETRIES[:1] if pilot else GEOMETRIES):
                    for fault in FAULTS:
                        name = f'{corner}-{model}-{temperature}-{area}-{perimeter}-{fault}'
                        folder = output/name; folder.mkdir()
                        (folder/'models.spice').write_text(model_text(model,sources,fault),encoding='utf-8')
                        (folder/'input.cir').write_text(deck(model,area,perimeter,parameters,temperature),encoding='utf-8')
                        run = subprocess.run([executable,'-n','-D','ngbehavior=hsa','-b','input.cir'],cwd=folder,
                                             capture_output=True,timeout=60,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                                             env={**(runtime_environment(executable) or os.environ),'OMP_THREAD_LIMIT':'1'})
                        (folder/'engine.log').write_bytes(run.stdout+run.stderr)
                        if run.returncode:raise ValueError('RF simulator failed in '+name)
                        result = inspect(folder,model,area,perimeter,aj,pj,temperature)
                        row = dict(name=name,model=model,temperature_c=temperature,corner=corner,area_um2=area,
                                   perimeter_um=perimeter,fault=fault,**result,
                                   status='PASS' if result['accepted']==(fault=='none') else 'FAIL')
                        report['cases'].append(row)
                        (folder/'review.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
                print(corner,model,temperature,'complete',flush=True)
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    report['status'] = 'PASS' if all(c['status']=='PASS' for c in report['cases']) else 'FAIL'
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice',required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pilot',action='store_true')
    args=parser.parse_args();result=qualify(args.ngspice,args.output,args.pilot)
    print(result['status'],len(result['cases']),'cases');raise SystemExit(result['status']!='PASS')
