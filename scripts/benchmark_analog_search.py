"""Compare measured search outcomes at an equal circuit-simulation budget."""
import argparse,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio import analog_optimizer as opt,analog_adaptive as adaptive
from icstudio.model import example,device,clone,validate,file_digest


def fixtures():
    p=example('empty');p['analysis']['type']='op'
    p['cells'][0]['devices']=[device('V','VS',value='1.8',nets=dict(p='rail',n='0')),device('R','R1',value='10k',nets=dict(p='rail',n='out')),device('R','R2',value='10k',nets=dict(p='out',n='0'))]
    p['cells'][0]['specifications']=[dict(name='Output window',expression='final(V("out"))',min='.8',max='1',unit='V')]
    axes=[dict(target=f'R{i}.value',lower='1k',upper='100k',count=31,scale='log') for i in (1,2)]
    yield 'Resistor divider',p,axes,dict(entry_id='op',expression='abs(final(I("VS")))',unit='A',goal='minimize')
    p=example('empty');p['analysis']['type']='op'
    p['cells'][0]['devices']=[device('NMOS','M1',nets=dict(d='d',g='g',s='0',b='0')),device('V','VG',value='.8',nets=dict(p='g',n='0')),device('V','VD',value='1.8',nets=dict(p='d',n='0'))]
    p['cells'][0]['specifications']=[dict(name='Gate window',expression='final(V("g"))',min='.6',max='.85',unit='V')]
    axes=[dict(target='M1.params.w',lower='.5u',upper='10u',count=31,scale='log'),dict(target='M1.params.l',lower='.2u',upper='2u',count=31,scale='log'),dict(target='VG.value',lower='.5',upper='1',count=31)]
    yield 'MOS bias and sizing',p,axes,dict(entry_id='op',expression='abs(final(I("VD")))',unit='A',goal='target',target='20u')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--executable');parser.add_argument('--budget',type=int,default=24);args=parser.parse_args()
    engine='ngspice' if args.executable else 'builtin';results=[]
    def prepare(settings,engine,project,cid):
        job=dict(settings=clone(settings),engine=engine,project=clone(project),cell=cid)
        if args.executable:job['executable']=str(Path(args.executable).resolve())
        return job
    for name,p,axes,objective in fixtures():
        validate(p);plan=opt.source_plan(dict(id='op',name='Bias',cell=p['top'],settings=p['analysis'],engine=engine))
        for strategy in ('adaptive','surrogate'):
            start=time.perf_counter();spec=dict(kind='analog_optimizer',strategy=strategy,axes=axes,objective=objective,budget=args.budget)
            manifest=opt.prepare(p,p['top'],plan,spec,prepare);rows=[]
            with tempfile.TemporaryDirectory() as directory:
                while True:
                    done={r['job']['case']['index'] for r in rows}
                    for job in manifest['jobs']:
                        index=job['case']['index']
                        if index in done:continue
                        if args.executable:
                            from icstudio.engines import run_ngspice
                            result=run_ngspice(job['project'],job['cell'],job['settings'],args.executable,Path(directory)/str(index))
                        else:
                            from icstudio.simulation import run
                            result=run(job['project'],job['cell'],job['settings'])
                        rows.append(dict(id=str(index),job=job,state='Complete',result=result))
                    report=opt.evaluate(manifest,rows)
                    if report['complete']:break
                    manifest,_=adaptive.advance(manifest,rows,prepare)
            best=report['best'];results.append(dict(circuit=name,strategy=strategy,simulations=len(rows),passing=sum(c['state']=='Passed' for c in report['candidates']),best_score=best['score'] if best else None,best_value=best['worst_value'] if best else None,objective=objective,elapsed_seconds=time.perf_counter()-start))
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(dict(engine=engine,engine_sha256=file_digest(args.executable) if args.executable else None,budget=args.budget,results=results,scope='Two deterministic reference circuits; these results do not establish a general speed or quality advantage.'),indent=2))
    print(args.out)


if __name__=='__main__':main()
