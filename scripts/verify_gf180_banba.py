"""Exercise the native Banba schematic through Studio's ngspice/optimizer APIs.

python scripts/verify_gf180_banba.py --ngspice /path/to/ngspice --out /new/results
The temperature search deliberately does not claim startup qualification.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.model import load_project, clone, erc, file_digest, design_digest
from icstudio.engines import run_ngspice
from icstudio import analog_optimizer as opt, specifications


def verify(executable, output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('Choose an empty output directory.')
    executable=str(Path(executable).resolve())
    project_path=ROOT/'examples/gf180-banba/banba.icproj'
    p=load_project(project_path)
    cid=next(c['id'] for c in p['cells'] if c['name']=='banba_core')
    issues=erc(p)
    if issues:raise ValueError(issues)
    config=json.loads((project_path.parent/'optimizer.json').read_text())

    def run(project, cell, settings, name):
        folder=output/name;folder.mkdir()
        result=run_ngspice(project,cell,settings,executable,folder)
        specifications.attach(dict(project=project,cell=cell,settings=settings),result)
        (folder/'result.json').write_text(json.dumps(result,indent=2))
        return result

    initial=clone(p);opt.set_target(initial,cid,'RPTAT.model_params.l','10u')
    baseline=run(initial,p['top'],p['analysis'],'baseline-op')
    selected=run(p,p['top'],p['analysis'],'selected-op')
    setup=p['simulation_setups'][1]
    startup=run(p,setup['cell'],setup['settings'],'selected-startup')

    def prepare(settings,engine,project,cell):
        return dict(settings=clone(settings),engine=engine,project=clone(project),cell=cell,executable=executable)

    manifest=opt.prepare(initial,cid,p['test_plans'][0],config['spec'],prepare)
    rows=[]
    for job in manifest['jobs']:
        i=job['case']['index']
        try:
            result=run(job['project'],job['cell'],job['settings'],f'case-{i:02d}')
            specifications.attach(job,result)
            rows.append(dict(id=str(i),job=job,state='Complete',result=result))
        except Exception as exc:
            rows.append(dict(id=str(i),job=job,state='Failed',log=str(exc)))
    report=opt.evaluate(manifest,rows)
    summary=dict(schema=1,project_sha256=file_digest(project_path),design_hash=design_digest(p),
        engine='ngspice',engine_sha256=file_digest(executable),pdk_revision=p['pdk']['revision'],
        erc_issues=issues,baseline=dict(vref=baseline['traces']['vref'][-1],supply_current=-baseline['operating_currents']['VDD']),
        selected=dict(vref=selected['traces']['vref'][-1],supply_current=-selected['operating_currents']['VDD'],
                      va=selected['traces']['xdut/va'][-1],vb=selected['traces']['xdut/vb'][-1]),
        startup=dict(final_vref=startup['traces']['vref'][-1],peak_vref=max(startup['traces']['vref']),
                     specifications=startup.get('specifications',[])),
        optimizer=dict(complete=report['complete'],simulations=report['total'],best=report['best'],candidates=report['candidates']),
        limitations=['Only nominal process corner and three temperatures checked.',
                     'Startup overshoot fails; no loop-gain, mismatch, load or extracted-layout qualification.'])
    (output/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    (output/'optimizer-manifest.json').write_text(json.dumps(manifest))
    if not report['complete'] or not report['best']:raise ValueError('The optimizer did not finish with an eligible candidate.')
    print(json.dumps({k:summary[k] for k in ('baseline','selected','startup')},indent=2))
    print('Completed',report['total'],'optimizer simulations; candidate',report['best']['candidate'])
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();verify(args.ngspice,args.out)
