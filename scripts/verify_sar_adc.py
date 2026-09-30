"""Real-engine SAR qualification: transfer, thresholds, hold, settling and faults."""
import argparse
import json
import math
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from icstudio.model import clone, file_digest, atomic_write
from icstudio.mixed_signal import prepare, run, validate_result
from icstudio.sar_example import sar_project, conversion_report
from icstudio.engines import execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    for name in ('ngspice', 'iverilog', 'vvp'): parser.add_argument('--'+name)
    args = parser.parse_args(); root = args.out.resolve()
    if root.exists() and any(root.iterdir()): parser.error('Use an empty evidence directory.')
    root.mkdir(parents=True, exist_ok=True)
    selected = {n:getattr(args,n) for n in ('ngspice','iverilog','vvp')}
    base = sar_project(); probe = prepare(base, selected); report = dict(status='RUNNING',
        host=dict(platform=platform.platform(), python=platform.python_version()),
        scope='Four-bit behavioral SAR; real ngspice analog integration and Icarus RTL. No transistor/PDK, noise, metastability, ENOB or physical qualification.',
        environment=probe['environment'], versions={}, cases=[], faults=[], checks=[])
    for name, path in probe['settings']['tools'].items():
        report['versions'][name] = execute([path, '--version' if name=='ngspice' else '-V'], root)
    def save(): atomic_write(root/'report.json', json.dumps(report, indent=2, allow_nan=False))
    save()
    def simulate(p, name):
        folder=root/name; folder.mkdir(); job=prepare(p, selected)
        atomic_write(folder/'input.json', json.dumps(job, allow_nan=False))
        result=run(job, folder); atomic_write(folder/'result.json', json.dumps(result, allow_nan=False))
        validate_result(result, job, folder); return result
    try:
        lsb=1.8/16; stimuli=[('center-'+str(i), (i+.5)*lsb) for i in range(16)]
        stimuli += [('boundary-'+str(i)+side, (i+offset)*lsb) for i in range(1,16) for side,offset in (('-below',-.05),('-above',.05))]
        stimuli += [('zero',0.), ('full-scale',1.8), ('below-range',-.05), ('above-range',1.85)]
        for name, voltage in stimuli:
            p=clone(base); p['mixed_signal']['stimuli']['vin']=[[0.,voltage]]
            p['cells'][0]['specifications']=[]
            expected=max(0,min(15,math.floor(voltage/lsb)))
            result=simulate(p,name); check=conversion_report(result,expected)
            report['cases'].append(dict(name=name,voltage=voltage,expected=expected,**check));save()
            if check['status']!='PASS': raise AssertionError(name+': wrong code or protocol')
            print(name+': PASS',flush=True)
        centers=[r['code'] for r in report['cases'][:16]]
        report['checks'].append(dict(name='Every code present and monotonic at bin centers',passed=centers==list(range(16))))
        for name in ('hold-input-step','step-convergence'):
            p=clone(base)
            if name=='hold-input-step': p['mixed_signal']['stimuli']['vin']=[[0,.93],[3.5e-6,.93],[3.501e-6,.2]]
            else: p['mixed_signal']['max_step']/=4
            result=simulate(p,name); check=conversion_report(result,8)
            report['checks'].append(dict(name=name,passed=check['status']=='PASS',**check));save()
            if check['status']!='PASS': raise AssertionError(name)
        for name in ('wrong-dac-weight','wrong-rtl-decision','insufficient-settling'):
            p=clone(base); expected=8
            if name=='wrong-dac-weight':next(d for d in p['cells'][0]['devices'] if d['name']=='Rbit3')['value']='20k'
            elif name=='wrong-rtl-decision':
                f=p['cells'][1]['digital']['files'][0];f['text']=f['text'].replace('if (!cmp)','if (cmp)')
            else:
                p['mixed_signal'].update(period=10e-9,max_step=1e-10,rise=1e-10)
                p['mixed_signal']['stimuli']['vin']=[[0,.3]]; expected=2
            try:
                result=simulate(p,name); check=conversion_report(result,expected)
                caught=check['status']=='FAIL'; detail=check
            except ValueError as exc:
                caught='Ambiguous analog' in str(exc);detail=str(exc)
                if not caught:raise
            report['faults'].append(dict(name=name,detected=caught,detail=detail));save()
            if not caught:raise AssertionError('Fault was not detected: '+name)
        report['status']='PASS'
    except Exception as exc:
        report['status']='FAIL';report['error']=str(exc);save();raise
    save();print(json.dumps(dict(status=report['status'],cases=len(report['cases']),faults=len(report['faults']))))


if __name__=='__main__':main()
