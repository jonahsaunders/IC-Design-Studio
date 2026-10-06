"""Real standard-cell mapping, timing, proof and optional RTL-to-GDS qualification."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio import digital_flow, digital_platform, job_store
from icstudio.digital_qualification import counter, faulty_mapping, require_clean_route
from icstudio.model import atomic_write, file_digest, save_project


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orfs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--platform',action='append',choices=['sky130hd','gf180','ihp-sg13g2'])
    parser.add_argument('--tool',action='append',default=[],metavar='NAME=EXECUTABLE')
    parser.add_argument('--physical',action='store_true',help='Require final GDS, extraction and post-route timing')
    args=parser.parse_args()
    output=args.output.resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Choose an empty qualification output folder.')
    output.mkdir(parents=True,exist_ok=True)
    tools={name:os.environ.get('ICSTUDIO_TEST_'+name.upper()) or shutil.which(name)
           for name in ('yosys','sta','eqy','sby','bitwuzla','yosys-abc','openroad','make','klayout')}
    tools.update(dict(value.split('=',1) for value in args.tool))
    if tools.get('yosys'):
        for name in ('eqy','sby','bitwuzla','yosys-abc'):
            sibling=Path(tools['yosys']).with_name(name)
            if not tools.get(name) and sibling.is_file():tools[name]=str(sibling)
    tools={key:value for key,value in tools.items() if value}
    report={'schema':1,'status':'running','scope':'Declared standard-cell counter flow; not foundry or full-chip signoff',
            'qualifier_sha256':file_digest(Path(__file__)),
            'source_files':{p.name:file_digest(p) for p in sorted((ROOT/'icstudio').glob('digital*.py'))},'platforms':[]}

    def retain():atomic_write(output/'report.json',json.dumps(report,indent=2))

    for name in args.platform or ['sky130hd','gf180','ihp-sg13g2']:
        entry={'name':name,'status':'running','cases':[]};report['platforms'].append(entry);retain()
        root=output/name;root.mkdir()
        try:
            p=counter(digital_platform.from_orfs(args.orfs,name));config=p['digital']
            save_project(p,root/'counter.icproj')
            entry['platform']={k:v for k,v in config['platform'].items() if k!='root'}
            entry['conditions']={'clock_period_ns':50,'load_pf':0.01,'physical':config['physical']};retain()

            def run(stage,label,project=p,upstream=None,expected=None):
                folder=root/label;folder.mkdir()
                job=digital_flow.prepare(project,stage,tools=tools,toolchain='custom',upstream=upstream,orfs=args.orfs)
                atomic_write(folder/'input.json',json.dumps(job))
                result=digital_flow.run(job,folder)
                atomic_write(folder/'result.json',json.dumps(result));job_store.state(folder,'complete')
                job_store.read_result(folder/'result.json',project['id'])
                data=result['digital_result']
                case={'name':label,'stage':stage,'verdict':data.get('verdict'),'result_sha256':file_digest(folder/'result.json'),
                      'versions':data['versions'],'summary':data['summary']}
                entry['cases'].append(case);retain()
                if expected and data.get('verdict')!=expected:raise ValueError(label+': expected '+expected+', got '+str(data.get('verdict')))
                print(name,label,data['summary'],flush=True)
                return folder,data

            mapped,mapped_data=run('mapped','mapped')
            # Pre-layout hold violations are retained, then repaired by physical
            # implementation under the same constraints. Only extracted closure
            # can qualify a physical run; missing timing evidence never qualifies.
            _,prelayout=run('timing','timing',upstream=mapped)
            if prelayout.get('verdict') not in ('PASS','FAIL'):
                raise ValueError('Pre-layout timing evidence is incomplete.')
            run('equivalence','equivalent',upstream=mapped,expected='PASS')
            fault=faulty_mapping(mapped,root/'faulty-mapped')
            run('equivalence','fault-detected',upstream=fault,expected='FAIL')
            if args.physical:
                finished,_=run('finish','finished',upstream=mapped)
                entry['physical_checks']=require_clean_route(finished);retain()
                run('timing','extracted-timing',upstream=finished,expected='PASS')
                run('equivalence','physical-equivalent',upstream=finished,expected='PASS')
            elif prelayout.get('verdict')!='PASS':
                raise ValueError('Pre-layout timing is not closed; physical repair and extracted timing are required.')
            entry['status']='passed'
        except Exception as exc:
            entry.update(status='failed',error=str(exc));print(name,'FAILED',str(exc)[-1000:],flush=True)
        retain()
    report['status']='passed' if all(p['status']=='passed' for p in report['platforms']) else 'failed';retain()
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
