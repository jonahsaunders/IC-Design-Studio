"""Qualify native capacitance arithmetic against independent exact-sum cases."""
from pathlib import Path
import argparse,hashlib,json,math,shutil,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description='Exercise native capacitance reading and distribution in isolated test-command builds.')
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
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
helper=(ROOT/'scripts/native_magic_capacitance_control.c').read_text();(out/'control-command.c').write_text(helper)
report=dict(status='running',qualified=False,scope='Native ResReadCapacitor, ResisData transfer and ResDistributeCapacitance under four permutations of identical exactly representable positive terms, both parser modes and three scales. Isolated builds add only a test command.',script_sha256=sha(__file__),helper_sha256=sha(out/'control-command.c'),limits=dict(accumulator_relative=1e-12,node_relative=8e-8,reason='Double accumulator accuracy and final float rounding; frozen before execution.'),variants={})
def retain():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
retain()
for variant,build in [('baseline',args.baseline_build.resolve()),('candidate',args.candidate_build.resolve())]:
    target=scratch/variant;target.mkdir();source=target/'source';shutil.copytree(build/'magic',source);prefix=target/'installed';folder=out/variant;folder.mkdir()
    p=source/'resis/ResRex.c';text=p.read_text();before=sha(p)
    needle='void\nCmdExtResis(win, cmd)';assert text.count(needle)==1;text=text.replace(needle,helper+'\n'+needle)
    needle='    resisdata = ResInit();';assert text.count(needle)==1;text=text.replace(needle,'    if (cmd->tx_argc == 5 && !strcmp(cmd->tx_argv[1], "icstudio_cap")) {icstudioCapControl(cmd);return;}\n\n'+needle);p.write_text(text)
    changed=[str(p.relative_to(source)) for p in source.rglob('*') if p.suffix in ('.c','.h') and p.is_file() and (build/'magic'/p.relative_to(source)).is_file() and sha(p)!=sha(build/'magic'/p.relative_to(source))];assert changed==['resis/ResRex.c'],changed
    row=dict(engine_lock_sha256=sha(build/'source-lock.json'),command_before_sha256=before,command_after_sha256=sha(p),changed_source_files=changed,steps=[],cases=[]);report['variants'][variant]=row;retain()
    for index,command in enumerate([['./configure','--prefix='+str(prefix)],['make','-j'+str(args.jobs)],['make','install']]):
        start=time.time()
        with (folder/f'build-{index}.log').open('w') as log:result=subprocess.run(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        row['steps'].append(dict(command=command,exit_code=result.returncode,seconds=time.time()-start));retain();assert result.returncode==0
    for exponent in (-20,0,20):
        for mode in (0,1):
            for order in range(4):
                case=folder/f'{exponent}-{mode}-{order}';case.mkdir();(case/'startup.tcl').write_text('drc off\n');(case/'test.tcl').write_text(f'extresist icstudio_cap {order} {exponent} {mode}\nquit -noprompt\n')
                command=[str(prefix/'bin/magic'),'-dnull','-noconsole','-rcfile',str(case/'startup.tcl'),str(case/'test.tcl')]
                result=subprocess.run(command,cwd=case,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30);(case/'engine.log').write_text(result.stdout)
                lines=[line.split('CAP_RESULT ',1)[1] for line in result.stdout.splitlines() if line.startswith('CAP_RESULT ')]
                assert result.returncode==0 and len(lines)==1 and 'CAP_ERROR' not in result.stdout,result.stdout
                actual=json.loads(lines[0]);scale=math.ldexp(1.,exponent);expected_total=math.fsum([scale]+[math.ldexp(scale,-26)]*4096);expected_area=math.fsum([math.ldexp(scale,24)]+[scale]*4096)
                expected_large=expected_total*math.ldexp(scale,24)/expected_area;expected_small=expected_total*scale/expected_area
                accumulator_ok=all(math.isclose(actual[k],expected_total,rel_tol=1e-12,abs_tol=0) for k in ('accumulated_a','accumulated_b','transferred_total'))
                distribution_ok=math.isclose(actual['large_node'],expected_large,rel_tol=8e-8,abs_tol=0) and all(math.isclose(actual[k],expected_small,rel_tol=8e-8,abs_tol=0) for k in ('small_min','small_max'))
                actual.update(expected_total=expected_total,expected_large=expected_large,expected_small=expected_small,accumulator_passed=accumulator_ok,distribution_passed=distribution_ok,passed=accumulator_ok and distribution_ok,command=command,log_sha256=sha(case/'engine.log'));row['cases'].append(actual);retain()
    print(json.dumps(dict(variant=variant,cases=len(row['cases']),passed=sum(c['passed'] for c in row['cases']))),flush=True)
assert all(c['passed'] for c in report['variants']['candidate']['cases'])
assert any(not c['accumulator_passed'] for c in report['variants']['baseline']['cases'])
assert any(not c['distribution_passed'] for c in report['variants']['baseline']['cases'])
for exponent in (-20,0,20):
    for mode in (0,1):
        group=[c for c in report['variants']['candidate']['cases'] if c['exponent']==exponent and c['mode']==mode]
        assert len({tuple(c[k] for k in ('accumulated_a','large_node','small_min','small_max')) for c in group})==1
report['status']='native-cap-arithmetic-controls-passed';retain()
