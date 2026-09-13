"""First-install acceptance uses real engines and retains every result."""
import json
from pathlib import Path

from . import digital, digital_flow, digital_runtime
from .model import atomic_write, clone


def qualify(runtime, directory, progress=lambda message: None):
    root = Path(directory); root.mkdir(parents=True)
    project = digital.counter_project(); digital_runtime.defaults(project,runtime=runtime)
    project['digital']['timeout']=300
    records=[]
    def run(name, stage, p=project, upstream=None, simulator='icarus'):
        progress('Installation check: '+name)
        job = digital_flow.prepare(p,stage,simulator,runtime=runtime,upstream=upstream)
        folder = root/name; folder.mkdir()
        atomic_write(digital_runtime.state_root()/'active-check.json',json.dumps({'directory':str(folder)}))
        atomic_write(folder/'input.json',json.dumps(job))
        result = digital_flow.run(job,folder,lambda fraction,message:progress(name+': '+message))
        atomic_write(folder/'result.json',json.dumps(result))
        data = result['digital_result']
        if data.get('verdict') in ('FAIL','ERROR','UNKNOWN','INCOMPLETE'):
            raise ValueError(name+' did not pass. See '+str(folder))
        records.append({'name':name,'summary':data['summary']})
        return folder, result
    try:
        run('icarus','simulate')
        from .digital_examples import uart_project
        uart=uart_project(); uart['digital']['timeout']=300
        run('verilator-coverage','regression',uart)
        mapped,_=run('mapped','mapped')
        _,proof=run('equivalence','equivalence',upstream=mapped)
        if proof['digital_result']['equivalence']['status']!='PASS': raise ValueError('The installation equivalence proof did not pass.')
        run('timing','timing',upstream=mapped)
        finish,result=run('gds','finish',upstream=mapped)
        if not {'gds','spef'}.issubset(result['digital_result']['artifacts']): raise ValueError('The physical installation check produced no GDS/SPEF.')
        run('extracted-timing','timing',upstream=finish)
        atomic_write(root/'report.json',json.dumps({'status':'PASS','runtime':runtime,'checks':records},indent=2))
    except Exception as exc:
        atomic_write(root/'report.json',json.dumps({'status':'FAIL','runtime':runtime,'checks':records,'error':str(exc)},indent=2))
        raise
