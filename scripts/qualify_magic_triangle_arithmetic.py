"""Build test-command-only engine copies and exercise the real triangle routine."""
from pathlib import Path
import argparse,hashlib,json,math,re,shutil,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--baseline-build',type=Path,required=True)
ap.add_argument('--candidate-build',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--work',type=Path,required=True)
ap.add_argument('--jobs',type=int,default=2)
args=ap.parse_args()
if not 1<=args.jobs<=16:ap.error('--jobs must be between 1 and 16')
out=args.out.resolve();scratch=args.work.resolve()
if out.exists() or scratch.exists():ap.error('Output and work directories must both be new.')
out.mkdir(parents=True);scratch.mkdir(parents=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
helper=(ROOT/'scripts/native_magic_triangle_control.c').read_text()
(out/'control-command.c').write_text(helper)
report=dict(status='running',qualified=False,scope='Actual native triangle routine, both search branches, terminal resistance against independent delta/star formulas. Diagnostic copies add only a private test command; production arithmetic is unmodified in each copy.',script_sha256=sha(Path(__file__)),helper_sha256=sha(out/'control-command.c'),limits=dict(relative=3e-7,absolute_milliohm=1e-12,reason='Single-precision stored star arms; frozen before execution.'),variants={})
def retain():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
retain()
for variant,build in [('baseline',args.baseline_build.resolve()),('candidate',args.candidate_build.resolve())]:
    original=Path(build)/'magic';target=scratch/variant;target.mkdir();source=target/'source';shutil.copytree(original,source);prefix=target/'installed';folder=out/variant;folder.mkdir()
    p=source/'resis/ResRex.c';text=p.read_text();before=sha(p);text=text.replace('void\nCmdExtResis(win, cmd)',helper+'\nvoid\nCmdExtResis(win, cmd)')
    needle='    resisdata = ResInit();';assert text.count(needle)==1;text=text.replace(needle,'    if (cmd->tx_argc == 6 && !strcmp(cmd->tx_argv[1], "icstudio_triangle")) {icstudioTriangleControl(cmd);return;}\n\n'+needle);p.write_text(text)
    changed=[str(p.relative_to(source)) for p in source.rglob('*') if p.suffix in ('.c','.h') and p.is_file() and (original/p.relative_to(source)).is_file() and sha(p)!=sha(original/p.relative_to(source))];assert changed==['resis/ResRex.c'],changed
    row=dict(source_engine=str(build),source_lock_sha256=sha(build/'source-lock.json'),arithmetic_source_sha256=sha(source/'resis/ResMerge.c'),command_source_before_sha256=before,command_source_after_sha256=sha(p),changed_source_files=changed,build_steps=[],cases=[]);report['variants'][variant]=row;retain()
    for step,command in enumerate([['./configure','--prefix='+str(prefix)],['make','-j'+str(args.jobs)],['make','install']]):
        started=time.time()
        with (folder/f'build-{step}.log').open('w') as log:proc=subprocess.run(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        row['build_steps'].append(dict(command=command,exit_code=proc.returncode,seconds=time.time()-started));retain();assert proc.returncode==0
    row['installed_files']={str(p.relative_to(prefix)):sha(p) for p in prefix.rglob('*') if p.is_file() and not p.is_symlink()}
    values=[(.001,.002,.009),(1,7,29),(100,100,100),(.0001,100000,10000000),(100,10000000,10000000),(1000000,2000000,7000000)]
    for degree in (2,3,9,10,12):
        for i,vals in enumerate(values):
            case=folder/(str(degree)+'-'+str(i));case.mkdir();(case/'startup.tcl').write_text('drc off\n');script=case/'test.tcl';script.write_text('extresist icstudio_triangle '+str(degree)+' '+' '.join(map(str,vals))+'\nquit -noprompt\n')
            command=[str(prefix/'bin/magic'),'-dnull','-noconsole','-rcfile',str(case/'startup.tcl'),str(script)]
            proc=subprocess.run(command,cwd=case,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30);(case/'engine.log').write_text(proc.stdout)
            lines=[l.split('TRIANGLE_RESULT ',1)[1] for l in proc.stdout.splitlines() if l.startswith('TRIANGLE_RESULT ')];assert proc.returncode==0 and len(lines)==1 and 'TRIANGLE_ERROR' not in proc.stdout,proc.stdout
            result=json.loads(lines[0]);assert result['status']==result['triangle_status']==32 and result['star_degree']==3
            d=result['input_milliohm'];s=result['arms_milliohm'];expected=[d[0]*(d[1]+d[2])/sum(d),d[1]*(d[0]+d[2])/sum(d),d[2]*(d[0]+d[1])/sum(d)];actual=[s[0]+s[1],s[0]+s[2],s[1]+s[2]]
            result.update(expected_pair_milliohm=expected,actual_pair_milliohm=actual,maximum_pair_error_milliohm=max(abs(a-b) for a,b in zip(actual,expected)),passed=all(math.isclose(a,b,rel_tol=3e-7,abs_tol=1e-12) for a,b in zip(actual,expected)),log_sha256=sha(case/'engine.log'),command=command)
            row['cases'].append(result);retain()
    print(json.dumps(dict(variant=variant,cases=len(row['cases']),passed=sum(c['passed'] for c in row['cases']))),flush=True)
assert all(c['passed'] for c in report['variants']['candidate']['cases'])
assert all(any(not c['passed'] and c['degree']==degree for c in report['variants']['baseline']['cases']) for degree in (2,3,9,10,12))
report['status']='native-triangle-arithmetic-controls-passed';retain()
