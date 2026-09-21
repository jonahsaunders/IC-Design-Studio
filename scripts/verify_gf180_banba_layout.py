"""Check the segmented layout schematic with the real bundled GF180 models.

These are pre-extraction simulations. Geometry and terminal connectivity are
checked separately by create_gf180_banba_layout.py.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.model import load_project, clone, file_digest
from icstudio.engines import run_ngspice
from scripts.verify_gf180_banba_pass2 import transient_metrics, cell


def verify(executable, output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('Choose an empty simulation output folder.')
    path=ROOT/'examples/gf180-banba/layout/banba-layout.icproj'
    project=load_project(path)
    baseline=load_project(ROOT/'examples/gf180-banba/pass2/banba.icproj')
    report=dict(schema=1,project_sha256=file_digest(path),engine_sha256=file_digest(executable),
        pdk_revision=project['pdk']['revision'],comparison={},pvt=[],
        qualification='Segmented schematic simulation; no extracted interconnect resistance/capacitance.',
        limits=dict(vref=[.57,.63],supply_current=70e-6,startup_peak=.75,tail_ripple=.0006),
        limitations=['Fixed 5 pF bench load; no mismatch, trimming, noise or return-ratio verification.',
                    'Combined bundled process corners, not an independent device-family matrix.'])

    def run(p,cid,settings,name):
        folder=output/name;folder.mkdir(parents=True)
        r=run_ngspice(p,cid,settings,str(Path(executable).resolve()),folder)
        (folder/'result.json').write_text(json.dumps(r))
        return r

    for label,p in [('pass2',baseline),('segmented_layout',project)]:
        op=run(p,p['top'],p['analysis'],label+'/op')
        setup=p['simulation_setups'][1]
        tr=run(p,setup['cell'],setup['settings'],label+'/startup')
        temps=[]
        for t in [-40,-20,0,27,50,75,100,125]:
            r=run(p,p['top'],{**p['analysis'],'temperature':t},label+f'/temp-{t}')
            temps.append(dict(temperature=t,vref=r['traces']['vref'][-1]))
        volts=[r['vref'] for r in temps]
        report['comparison'][label]=dict(vref=op['traces']['vref'][-1],
            supply_current=-op['operating_currents']['VDD'],startup=transient_metrics(tr),
            temperatures=temps,temperature_span=max(volts)-min(volts),
            box_tc_ppm=(max(volts)-min(volts))/(sum(volts)/len(volts)*165)*1e6)
        print(label,json.dumps(report['comparison'][label]),flush=True)
    for corner in ['nominal','ff','ss','fs','sf']:
        for t in [-40,125]:
            for vdd in [2.7,3.6]:
                p=clone(project);p['parameters']['vdd']=str(vdd)
                settings={**p['analysis'],'corner':corner,'temperature':t}
                prefix=f'pvt/{corner}-{t}-{vdd}'
                op=run(p,p['top'],settings,prefix+'/op')
                row=dict(corner=corner,temperature=t,supply=vdd,vref=op['traces']['vref'][-1],
                    supply_current=-op['operating_currents']['VDD'],ramps=[])
                for ramp,stop,step,bench in [('100n','500u','100n','tb_startup'),
                                            ('10u','500u','100n','tb_medium_startup'),
                                            ('1m','2m','500n','tb_slow_startup')]:
                    s={**settings,'type':'tran','stop':stop,'step':step,
                        'diagnostic':dict(kind='startup',source='VDD',output='VREF',initial_node='VREF',
                            initial_voltage='0',ramp=ramp,supply=str(vdd),stop=stop,
                            minimum='.57',maximum='.63',tail_fraction='.2')}
                    r=run(p,cell(p,bench)['id'],s,prefix+'/ramp-'+ramp)
                    m=transient_metrics(r,tolerance=.03);limit=.00125 if ramp=='1m' else .00025
                    m['passed']=(.57<=m['final_vref']<=.63 and m['peak_vref']<=.75 and
                        m['settling_seconds'] is not None and m['settling_seconds']<=limit and m['tail_peak_to_peak']<.0006)
                    row['ramps'].append(dict(ramp=ramp,settling_limit_seconds=limit,**m))
                row['passed']=.57<=row['vref']<=.63 and row['supply_current']<=70e-6 and all(r['passed'] for r in row['ramps'])
                report['pvt'].append(row)
                print(prefix,'PASS' if row['passed'] else 'FAIL',flush=True)
                (output/'simulation.json').write_text(json.dumps(report,indent=2)+'\n')
    report['passed']=all(r['passed'] for r in report['pvt'])
    (output/'simulation.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['passed']:raise ValueError('Segmented circuit failed; inspect simulation.json.')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngspice',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();verify(a.ngspice,a.out)
