"""First-install acceptance uses real engines and retains every result."""
import json
from pathlib import Path

from . import digital_flow, digital_runtime
from .digital_qualification import counter, faulty_mapping, require_clean_route
from .model import atomic_write


def qualify(runtime, directory, progress=lambda message: None):
    root = Path(directory); root.mkdir(parents=True)
    platforms=digital_runtime.platforms(runtime)
    project=counter(next(iter(platforms.values())))
    records=[];qualified=[]
    def run(name, stage, p=project, upstream=None, simulator='icarus', expected=None):
        progress('Installation check: '+name)
        job = digital_flow.prepare(p,stage,simulator,runtime=runtime,upstream=upstream)
        folder = root/name; folder.mkdir(parents=True)
        atomic_write(digital_runtime.state_root()/'active-check.json',json.dumps({'directory':str(folder)}))
        atomic_write(folder/'input.json',json.dumps(job))
        result = digital_flow.run(job,folder,lambda fraction,message:progress(name+': '+message))
        atomic_write(folder/'result.json',json.dumps(result))
        data = result['digital_result']
        if ((expected is not None and data.get('verdict') not in expected)
                or expected is None and data.get('verdict') in ('FAIL','ERROR','UNKNOWN','INCOMPLETE')):
            raise ValueError(name+' did not pass. See '+str(folder))
        records.append({'name':name,'summary':data['summary'],'verdict':data.get('verdict')})
        return folder, result
    try:
        run('icarus','simulate')
        from .digital_examples import uart_project
        uart=uart_project(); uart['digital']['timeout']=300
        run('verilator-coverage','regression',uart,expected=('PASS',))
        for name,platform in platforms.items():
            p=counter(platform);prefix=name+'/'
            mapped,_=run(prefix+'mapped','mapped',p)
            run(prefix+'equivalence','equivalence',p,upstream=mapped,expected=('PASS',))
            fault=faulty_mapping(mapped,root/(prefix+'faulty-mapped'))
            run(prefix+'fault-detected','equivalence',p,upstream=fault,expected=('FAIL',))
            run(prefix+'timing','timing',p,upstream=mapped,expected=('PASS','FAIL'))
            floorplan,_=run(prefix+'floorplan','floorplan',p,upstream=mapped)
            finish,result=run(prefix+'gds','finish',p,upstream=floorplan)
            if not result['digital_result']['physical']['resumed']:raise ValueError('The managed physical checkpoint did not resume.')
            if not {'gds','spef'}.issubset(result['digital_result']['artifacts']):raise ValueError('The physical installation check produced no GDS/SPEF.')
            require_clean_route(finish)
            run(prefix+'extracted-timing','timing',p,upstream=finish,expected=('PASS',))
            run(prefix+'physical-equivalence','equivalence',p,upstream=finish,expected=('PASS',))
            qualified.append(name)
        report={'status':'PASS','runtime':runtime,'platforms':qualified,'checks':records,
                'scope':'Installation counters, selected library corners and one extracted RC condition; not foundry or full-chip signoff'}
        atomic_write(root/'report.json',json.dumps(report,indent=2))
        return report
    except Exception as exc:
        atomic_write(root/'report.json',json.dumps({'status':'FAIL','runtime':runtime,'platforms':qualified,'checks':records,'error':str(exc)},indent=2))
        raise
