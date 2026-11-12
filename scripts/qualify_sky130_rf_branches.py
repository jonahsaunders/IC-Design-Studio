"""Compare public RF diode branches with independent small-signal equations.

Two models, three process corners, five geometries and three temperatures.
Zero-bias AC is repeated after OP and DC; intentional perimeter, area and
resistance faults must fail. This does not qualify full bias, noise, physical
extraction or measured-silicon accuracy.
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
from icstudio.model import file_digest
from icstudio.engines import parse_raw
from icstudio.diode_runtime import verify, THERMAL_VOLTAGE
from icstudio.spice_program import runtime_environment
from scripts.prepare_sky130_rf_qualification import public_sources, derivative, COMMON, corner_sources

# Numeric facts from the four retained public models. Resistances combine each
# junction's conductance and capacitance in series, independently of ngspice.
COEFFICIENTS = {
    'ps2nw': dict(ra1=760000, ra2=2000, rp=3750, aj=.98286, pj=.98954,
                 cj=9.155e-17, cjp=5.822e-16, js=4.21e-18, jsw=4.94e-18, xti=5.2, cta=.00165),
    'pw2dn': dict(ra1=49400, ra2=130, rp=7920, aj=.982, pj=.96304,
                 cj=3.8945e-16, cjp=3.743e-16, js=1.4693e-17, jsw=7.41e-18, xti=3, cta=.0016157),
}
GEOMETRIES = ((4, 8), (8, 12), (100, 40), (4, 10), (16, 20))
TEMPERATURES = (-40, 27, 125)
FAULTS = ('none', 'missing-perimeter', 'wrong-area', 'wrong-series-resistance')


def expected(model, area, perimeter, aj, pj, temperature, frequency):
    c = COEFFICIENTS[model]
    half_difference = math.sqrt(perimeter**2/16 - area)
    width = perimeter/4 + half_difference; length = area/width
    ra = (c['ra1']/area + c['ra2']/(length/width + width/length))*(2*c['aj'] - aj)
    rp = c['rp']/perimeter*(2*c['pj'] - pj)
    thermal = THERMAL_VOLTAGE*(temperature + 273.15)/300.15
    ratio = (temperature + 273.15)/303.15
    # TREF=30 sets IV temperature; NS defaults to 1. TLEVC=1 capacitance uses
    # 27 C. Public ngspice-46 diotemp.c lines 85-118 specify these conventions.
    ga = area*c['js']*ratio**(c['xti']/1.0791)*math.exp((ratio-1)*1.17/(1.0791*thermal))/(1.0791*thermal)
    gp = perimeter*c['jsw']*ratio**c['xti']*math.exp((ratio-1)*1.17/thermal)/(1.0791*thermal)
    ca = area*c['cj']*aj*(1+c['cta']*(temperature-27))
    cp = perimeter*c['cjp']*pj*(1+.0008*(temperature-27))
    ya = ga + 2j*math.pi*frequency*ca; yp = gp + 2j*math.pi*frequency*cp
    return -(ya/(1+ra*ya) + yp/(1+rp*yp))


def inspect(path, model, area, perimeter, aj, pj, temperature):
    variables, rows, complex_data = parse_raw(path)
    if not complex_data or len(rows) != 71 or variables[0] != 'frequency':
        raise ValueError('Incomplete RF frequency sweep.')
    current = variables.index('i(vdrive)'); voltage = variables.index('v(d)'); errors = []
    for i, row in enumerate(rows):
        f = 1e3*10**(i/10)
        if (not math.isclose(row[0].real, f, rel_tol=1e-9) or row[0].imag != 0 or
                any(not math.isfinite(abs(v)) for v in row) or abs(row[voltage]-1) > 1e-12):
            raise ValueError('Changed RF stimulus, domain or nonfinite result.')
        value = expected(model, area, perimeter, aj, pj, temperature, f)
        errors.append(abs(row[current]-value)/(1e-18+1e-6*abs(value)))
    return dict(maximum_normalized_error=max(errors), accepted=max(errors) <= 1,
                samples=len(rows), raw_sha256=file_digest(path))


def qualify(executable, output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    executable = str(Path(executable).resolve())
    runtime = verify(executable, output/'runtime')
    if runtime['status'] != 'PASS' or runtime['behavior']['mode'] != 'unscaled-explicit-area':
        raise ValueError('RF qualification requires verified unscaled AREA/PJ history.')
    lock, sources = public_sources(); corner_source, corners = corner_sources()
    report = dict(schema=1, status='RUNNING', qualified=False, chunk_complete=False,
                  scope=__doc__, source=lock, runner_sha256=file_digest(__file__),
                  engine_sha256=file_digest(executable), corner_source=corner_source, corners={}, cases=[])
    for corner in ('tt', 'ss', 'ff'):
        parameters = '\n'.join(line for line in corners[corner]['text'].splitlines()
                               if not line.startswith('*') and any('diode_'+m+'__' in line for m in COEFFICIENTS))
        values = {name: float(value) for name, value in re.findall(r'(sky130\w+)\s*=\s*([\d.eE+-]+)', parameters)}
        report['corners'][corner] = dict(sha256=corners[corner]['sha256'], parameters=values)
        for model in COEFFICIENTS:
            aj = values[COMMON+'diode_'+model+'__ajunction_mult']; pj = values[COMMON+'diode_'+model+'__pjunction_mult']
            for temperature in TEMPERATURES:
                for area, perimeter in GEOMETRIES:
                    for fault in FAULTS:
                        name = f'{corner}-{model}-{temperature}-{area}-{perimeter}-{fault}'
                        root = output/name; root.mkdir()
                        original = sources[COMMON+'rf_diode_'+model+'.model.spice']
                        wrapper = derivative(model, original).decode()
                        if fault == 'missing-perimeter': wrapper = original.decode()
                        elif fault == 'wrong-area': wrapper = wrapper.replace('area = {area}', 'area = {2*area}')
                        elif fault == 'wrong-series-resistance': wrapper = wrapper.replace('rp1_diode/perim', '2*rp1_diode/perim')
                        models = sources[COMMON+'diode_'+model+'_noresistor.model.spice'] + b'\n' + wrapper.encode()
                        (root/'models.spice').write_bytes(models)
                        text = '\n'.join(['* Public RF branch qualification', '.param', parameters, '.include models.spice',
                                          '.option scale=1u gmin=1e-30', f'.temp {temperature}', 'Vdrive d 0 0 ac 1',
                                          f'X1 d 0 {COMMON}rf_diode_{model} area={area} perim={perimeter}',
                                          '.control', 'set filetype=ascii', 'set numdgt=16', 'op', 'write op.raw all',
                                          'ac dec 10 1k 10g', 'write ac1.raw all', 'dc Vdrive -.1 .2 .05', 'write dc.raw all',
                                          'ac dec 10 1k 10g', 'write ac2.raw all', 'quit', '.endc', '.end', ''])
                        (root/'input.cir').write_bytes(text.encode())
                        run = subprocess.run([executable, '-n', '-D', 'ngbehavior=hsa', '-b', 'input.cir'], cwd=root,
                                             capture_output=True, timeout=60,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                             env={**(runtime_environment(executable) or os.environ), 'OMP_THREAD_LIMIT': '1'})
                        (root/'engine.log').write_bytes(run.stdout+run.stderr)
                        if run.returncode: raise ValueError('RF simulator failed in ' + name)
                        checks = {a: inspect(root/(a+'.raw'), model, area, perimeter, aj, pj, temperature) for a in ('ac1', 'ac2')}
                        row = dict(name=name, model=model, temperature_c=temperature, corner=corner, area_um2=area,
                                   perimeter_um=perimeter, fault=fault, checks=checks,
                                   status='PASS' if all(c['accepted'] == (fault == 'none') for c in checks.values()) else 'FAIL')
                        report['cases'].append(row)
                        (root/'review.json').write_bytes((json.dumps(row, indent=2)+'\n').encode())
                print(corner, model, temperature, 'complete', flush=True)
    report['status'] = 'PASS' if all(c['status']=='PASS' for c in report['cases']) else 'FAIL'
    (output/'report.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = qualify(args.ngspice, args.output)
    print(result['status'], len(result['cases']), 'cases')
    raise SystemExit(result['status'] != 'PASS')
