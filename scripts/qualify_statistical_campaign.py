#!/usr/bin/env python3
"""Real ngspice throughput, numerical yield and abrupt-worker recovery evidence.

The fixture is an ideal resistor divider with user-declared correlated tolerances,
not a foundry statistical model. Default: 128 trials × 9 PVT conditions = 1,152
actual ngspice simulations. --snapshot freezes the Python source used throughout
the qualification so concurrent development cannot change a running experiment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def source_files(root):
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((root/'icstudio').glob('*.py'))}


def freeze(args):
    destination=args.output/'source';destination.mkdir(parents=True)
    before=source_files(ROOT);(destination/'icstudio').mkdir();(destination/'scripts').mkdir()
    for name in before:shutil.copy2(ROOT/'icstudio'/name,destination/'icstudio'/name)
    shutil.copy2(ROOT/'main.py',destination/'main.py');shutil.copy2(__file__,destination/'scripts'/Path(__file__).name)
    if source_files(ROOT)!=before or source_files(destination)!=before:raise ValueError('Source changed during snapshot capture; retry once edits settle.')
    command=[sys.executable,str(destination/'scripts'/Path(__file__).name),'--output',str(args.output),'--executable',str(args.executable),
             '--trials',str(args.trials),'--workers',str(args.workers),'--fault-after',str(args.fault_after),'--deadline',str(args.deadline)]
    return subprocess.call(command)


def memory_tree(root_pid,extra_pids=()):
    """Linux measured resident bytes; return unavailable on other platforms."""
    if not Path('/proc').is_dir():return None,[]
    processes={}
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            values={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in path.read_text().splitlines() if ':' in line}
            processes[int(path.parent.name)]=(int(values['PPid']),int(values.get('VmRSS','0 kB').split()[0])*1024)
        except (OSError,ValueError,KeyError):continue
    selected={root_pid,*extra_pids};changed=True
    while changed:
        before=len(selected);selected.update(pid for pid,(parent,_) in processes.items() if parent in selected);changed=len(selected)!=before
    return sum(processes.get(pid,(0,0))[1] for pid in selected),list(selected)


def fixture(trials):
    from icstudio.model import example,device,clone,validate
    from icstudio.test_plans import sources
    p=example('empty');cell=p['cells'][0];p['name']='Statistical campaign qualification divider'
    cell['devices']=[device('V','VDD',value='1.8',nets={'p':'vdd','n':'0'}),
                     device('R','R1',value='10k',nets={'p':'vdd','n':'out'}),device('R','R2',value='10k',nets={'p':'out','n':'0'})]
    cell['specifications']=[dict(name='Divider ratio',expression='final(V("out")) / final(V("vdd"))',min='.48',max='.52',unit='')]
    p['analysis']['type']='op'
    p['simulation_setups']=[dict(name='Divider operating point',cell=p['top'],engine='ngspice',settings=clone(p['analysis']))]
    plan=dict(id='statistical-throughput',name='Correlated divider PVT',entries=sources(p),corners=['nominal'],temperatures=[-40,27,125],voltages=[1.62,1.8,1.98],
              statistics=dict(kind='correlated',cell=p['top'],count=trials,seed=20260920,
                variations=[dict(target='R1.value',relative_sigma=.06,distribution='normal',group='resistors',rho=.7),
                            dict(target='R2.value',relative_sigma=.06,distribution='normal',group='resistors',rho=.4)]))
    plan['entries'][0]['supply']='VDD.value';p['test_plans']=[plan]
    return validate(p),plan


def qualify(args):
    from icstudio.model import clone,file_digest,atomic_write,save_project
    from icstudio.verification_campaigns import create,Campaign,source_identity
    p,plan=fixture(args.trials)
    args.output.mkdir(parents=True,exist_ok=True)
    save_project(p,args.output/'divider.icproj')
    def prepare(settings,engine,project,cell):return dict(settings=clone(settings),engine=engine,project=clone(project),cell=cell,executable=str(args.executable))
    start=time.monotonic();campaign=create(args.output/'campaign',p,plan,prepare);capture_seconds=time.monotonic()-start
    version=subprocess.run([str(args.executable),'--version'],capture_output=True,text=True,timeout=15)
    proof=dict(schema=1,qualification_status='running',hostname=socket.gethostname(),source=source_identity(),
               executable=str(args.executable),executable_sha256=file_digest(args.executable),engine_version=(version.stdout+version.stderr).strip(),
               trials=args.trials,cases=campaign.manifest['case_count'],workers=args.workers,capture_seconds=capture_seconds,
               scope='Ideal resistor-divider numerical and scheduler qualification using user-declared tolerances. No process or silicon yield qualification.',
               two_host={'status':'not_run','reason':'This workload uses one physical host; see CAMPAIGN_WORKER_ACCEPTANCE.md.'})
    def publish():atomic_write(args.output/'qualification.json',json.dumps(proof,indent=2,allow_nan=False))
    publish();tracked=[];peak=0;peak_available=False;run_start=time.monotonic();deadline=run_start+args.deadline
    command=[sys.executable,str(ROOT/'main.py'),'--campaign','run',str(campaign.path),'--workers',str(args.workers),'--lease-seconds','5','--trust-project']
    log1=open(args.output/'before-crash.log','wb');first=subprocess.Popen(command,stdout=log1,stderr=subprocess.STDOUT)
    victim=None
    try:
        while time.monotonic()<deadline:
            memory,tracked=memory_tree(first.pid,tracked)
            if memory is not None:peak_available=True;peak=max(peak,memory)
            counts=campaign.counts()
            if counts.get('Complete',0)>=args.fault_after and counts.get('Running',0):
                with campaign.connect() as db:victim=dict(db.execute("SELECT * FROM cases WHERE state='Running' ORDER BY case_index LIMIT 1").fetchone())
                break
            if first.poll() is not None:raise ValueError('Initial worker ended before the requested crash point: '+json.dumps(counts))
            time.sleep(.1)
        if victim is None:raise TimeoutError('No running case reached the crash-injection point.')
        original=campaign.job(victim['case_index']);first.kill();first.wait(timeout=10);log1.close()
        proof['fault']=dict(kind='abrupt coordinator termination',exit_code=first.returncode,case=victim['case_index'],
                           prior_token=victim['token'],input_sha256=victim['input_hash'],counts_after_crash=campaign.counts(),
                           unresolved_after_crash=campaign.statistics()['joint']['unresolved'])
        publish();restart_start=time.monotonic()
        with open(args.output/'after-restart.log','wb') as log:
            second=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            try:
                while second.poll() is None:
                    if time.monotonic()>deadline:raise TimeoutError('Campaign exceeded the qualification deadline.')
                    memory,tracked=memory_tree(second.pid,tracked)
                    if memory is not None:peak_available=True;peak=max(peak,memory)
                    time.sleep(.1)
            finally:
                if second.poll() is None:second.terminate();second.wait(timeout=10)
        elapsed=time.monotonic()-run_start;counts=campaign.counts()
        if counts.get('Complete')!=proof['cases'] or counts.get('Failed'):raise ValueError('Not every simulator case completed: '+json.dumps(counts))
        if original!=campaign.job(victim['case_index']):raise ValueError('Recovery changed the sampled input or seed.')
        if campaign.finish(victim['case_index'],victim['token'],'Complete'):raise ValueError('A stale worker token was allowed to publish.')
        errors=[];expected_passed=set();expected_failed=set();maximum_error=0.;checked=0
        for offset in range(0,proof['cases'],100):
            for row in campaign.page(offset):
                saved=campaign.row(row['case_index']);job=saved['job'];devices={d['name']:d for d in job['project']['cells'][0]['devices']}
                r1=float(devices['R1']['value']);r2=float(devices['R2']['value']);ratio=r2/(r1+r2)
                actual=saved['result']['specifications'][0];error=abs(actual['value']-ratio);maximum_error=max(maximum_error,error)
                expected=.48<=ratio<=.52
                if error>1e-6 or actual['status']!=('PASS' if expected else 'FAIL'):errors.append({'case':row['case_index'],'expected':ratio,'actual':actual})
                (expected_passed if expected else expected_failed).add(job['case']['labels']['trial']);checked+=1
        statistical=campaign.statistics()
        if statistical['joint']['passed']!=len(expected_passed-expected_failed) or statistical['joint']['failed']!=len(expected_failed):raise ValueError('Joint yield does not match analytical trial classifications.')
        if errors:raise ValueError('Numerical or requirement classification errors: '+json.dumps(errors[:5]))
        with campaign.connect() as db:
            attempts=db.execute('SELECT SUM(attempts) FROM cases').fetchone()[0]
            retried=db.execute('SELECT COUNT(*) FROM cases WHERE attempts>1').fetchone()[0]
        proof.update(qualification_status='passed',completed_cases=checked,execution_seconds=elapsed,throughput_cases_per_second=checked/elapsed,
                     peak_worker_tree_resident_bytes=peak if peak_available else None,memory_measurement='Sampled /proc resident bytes, coordinator plus descendants; shared pages may be counted more than once.' if peak_available else 'Unavailable on this platform.',
                     maximum_divider_ratio_absolute_error=maximum_error,attempts=attempts,retried_cases=retried,
                     statistics=statistical,artifact_bytes=sum(path.stat().st_size for path in campaign.path.rglob('*') if path.is_file()))
        proof['fault'].update(recovery_seconds=time.monotonic()-restart_start,immutable_input_preserved=True,stale_publication_rejected=True)
        publish();print(json.dumps({key:proof[key] for key in ('qualification_status','cases','execution_seconds','throughput_cases_per_second','peak_worker_tree_resident_bytes','retried_cases')}));return 0
    except Exception as exc:
        proof.update(qualification_status='failed',error=str(exc));publish();raise
    finally:
        if first.poll() is None:first.terminate();first.wait(timeout=10)
        log1.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--trials',type=int,default=128);parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--fault-after',type=int,default=12);parser.add_argument('--deadline',type=float,default=1800)
    parser.add_argument('--snapshot',action='store_true');args=parser.parse_args()
    args.output=args.output.resolve();args.executable=args.executable.resolve()
    if not 2<=args.trials<=1111 or not 1<=args.workers<=16 or not 1<=args.fault_after<args.trials*9:parser.error('Use 2–1,111 trials, 1–16 workers and a crash point before the last case.')
    try:return freeze(args) if args.snapshot else qualify(args)
    except Exception as exc:print(json.dumps({'error':str(exc)}),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
