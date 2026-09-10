"""Real-ngspice analog characterization and independent electrical expectations."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,validate,atomic_write,save_project,file_digest
from icstudio.analog import reference
from icstudio.characterization import run,read_case,csv_text
from icstudio.testbenches import simulate,spice_testbench
from icstudio.engines import run_deck


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pdks',required=True);parser.add_argument('--ngspice',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    out=Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Use a new evidence directory.')
    out.mkdir(parents=True);reports=[]
    def record(name,passed,**extra):
        reports.append({'name':name,'passed':bool(passed),**extra});atomic_write(out/'regression.json',json.dumps(reports,indent=2));print(name,passed,flush=True)
        if not passed:raise AssertionError(name)
    for family in ('sky130A','gf180mcuC'):
        root=Path(args.pdks).resolve()/family;manifest=json.loads((root/'package.json').read_text());tech=manifest['technology'];tech.update(package_root=str(root),package_lock={k:manifest[k] for k in ('id','revision','files')})
        for rel,sha in manifest['files'].items():assert file_digest(root/rel)==sha,rel
        for kind in ('current_mirror','differential_pair'):
            p,cid,key=reference(tech,kind);base=out/(family+'-'+kind);base.mkdir();save_project(p,base/'design.icproj')
            for t in p['testbenches']:
                result=run(p,t['id'],t['characterization'],args.ngspice,base/t['name']);atomic_write(base/(t['name']+'.csv'),csv_text(result))
                record(family+'-'+t['name'],result['status']=='passed',summary=result['summary'],report=str((base/t['name']/'report.json').relative_to(out)))
                if kind=='current_mirror' and t['analysis']['type']=='op':
                    currents=[r['measurements'][0]['value'] for r in result['characterization_rows']]
                    record(family+'-mirror-compliance',all(40e-6<i<60e-6 for i in currents) and currents==sorted(currents),amperes=currents,expectation='Saturated 1:1 mirror near 50 uA; finite output conductance gives rising current.')
                if kind=='differential_pair' and t['analysis']['type']=='op':
                    vals=[r['measurements'][0]['value'] for r in result['characterization_rows']]
                    record(family+'-pair-polarity',vals[0]>0 and abs(vals[1])<1e-6 and vals[2]<0,volts=vals,expectation='Matched devices balance at zero input; increasing INP lowers OUTP.')
                    for i in range(3):
                        wave=read_case(result,i);v=wave['traces'];total=(v['vdd'][-1]-v['outp'][-1])/1e4+(v['vdd'][-1]-v['outn'][-1])/1e4
                        assert abs(total-100e-6)<1e-7,(family,total)
                    record(family+'-pair-kcl',True,expectation='Two 10 kohm load currents sum to the ideal 100 uA tail current, tolerance 0.1 uA.')
            # Exact exported fixture must produce the same independently invoked result.
            t=p['testbenches'][0];work=base/'exported-spice';work.mkdir();atomic_write(work/'bench.cir',spice_testbench(p,t));raw=run_deck(p,t['bench_cell'],{'type':'deck','deck':str(work/'bench.cir')},args.ngspice,work)
            original=simulate(p,t,args.ngspice,base/'single');common=t['probes'];error=max(abs(raw['traces'][n.lower()][-1]-original['traces'][n.lower()][-1]) for n in common)
            record(family+'-'+kind+'-spice-export',error<1e-10,maximum_voltage_error=error)
            bad=clone(p);bt=bad['testbenches'][0]
            if kind=='current_mirror':bt['measurements'][0].update(min='0',max='1u')
            else:bt['measurements'][1].update(min='0',max='.01')
            result=run(bad,bt['id'],bt['characterization'],args.ngspice,base/'reject-limit')
            record(family+'-'+kind+'-reject-limit',result['status']=='failed' and result['summary']['failed']==3)
            if kind=='current_mirror':
                # Reversing only the sense source terminals must reverse current sign.
                bad=clone(p);fixture=next(c for c in bad['cells'] if c['id']==t['bench_cell']);source=next(d for d in fixture['devices'] if d['name']=='VSENSE');source['nets']={k:source['nets'][v] for k,v in [('p','n'),('n','p')]}
                from icstudio.wiring import migrate
                for k in ('wires','labels','junctions'):fixture.pop(k,None)
                source.pop('net_labels',None);migrate(fixture,bad);validate(bad)
                r=simulate(bad,bad['testbenches'][0],args.ngspice,base/'reverse-sense')
                record(family+'-reverse-sense',r['measurements']['status']=='failed' and r['measurements']['measurements'][0]['value']<0)
    print('PASS:',len(reports),'real-engine checks')
    return 0


if __name__=='__main__':raise SystemExit(main())
