import json,sys,traceback
from pathlib import Path
from .model import load_project,atomic_write

def main(input_path,output_path):
    try:
        job=json.loads(Path(input_path).read_text(encoding='utf-8'))
        from .run_environment import verify
        verify(job)
        from .model import validate
        p=validate(job['project'])
        def progress(fraction,message): print(json.dumps({'progress':fraction,'message':message}),flush=True)
        kind=job['settings'].get('type')
        if kind in ('layout_route','layout_compare'):
            from .layout_jobs import run
            result=run(p,job['cell'],job['settings'],Path(output_path).parent,progress)
        elif kind=='klayout_drc':
            from .klayout_verification import run
            result=run(p,job['cell'],job['settings'],Path(output_path).parent,progress)
        elif kind=='program':
            from .native_spice import run
            result=run(p,job['cell'],job['settings'],job['executable'],Path(output_path).parent,progress)
        elif kind=='xschem':
            from .xschem_runtime import run
            result=run(p,job['cell'],job['settings'],job['executable'],Path(output_path).parent,progress)
        elif kind=='rc_compare':
            from .distributed_rc import compare_job
            result=compare_job(p,job,Path(output_path).parent,progress)
        elif kind=='silicon':
            from .silicon_flow import job as silicon_job
            result=silicon_job(p,job['cell'],job['settings'],Path(output_path).parent,progress)
        elif kind=='testbench':
            from .testbenches import get,simulate
            result=simulate(p,get(p,job['settings']['testbench']),job['settings']['executable'],Path(output_path).parent,progress=progress)
        elif kind=='characterization':
            from .characterization import run
            result=run(p,job['settings']['testbench'],job['settings']['study'],job['executable'],Path(output_path).parent/'characterization',progress,tools=job['settings'].get('tools'))
        elif kind=='study':
            from .studies import run_study
            result=run_study(p,job['cell'],job['settings']['analysis'],job['settings']['study'],job.get('engine','builtin'),job.get('executable',''),Path(output_path).parent,progress)
        elif kind=='deck':
            from .engines import run_deck
            result=run_deck(p,job['cell'],job['settings'],job['executable'],Path(output_path).parent,progress)
        elif kind in ('connectivity','drc','parasitics'):
            from .workflow_jobs import check_job
            result=check_job(p,job['cell'],kind,progress)
        elif kind=='post_layout':
            from .workflow_jobs import post_layout_job
            result=post_layout_job(p,job,Path(output_path).parent,progress)
        elif job.get('engine','builtin')=='builtin':
            from .simulation import run
            result=run(p,job['cell'],job['settings'],progress)
        else:
            from .engines import run_ngspice
            result=run_ngspice(p,job['cell'],job['settings'],job['executable'],Path(output_path).parent,progress)
        from .specifications import attach
        attach(job,result)
        atomic_write(output_path,json.dumps(result,allow_nan=False)); print(json.dumps({'complete':True}),flush=True);return 0
    except Exception as e:
        print(json.dumps({'error':str(e)}),flush=True);traceback.print_exc(file=sys.stderr);return 1
