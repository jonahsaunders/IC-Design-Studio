"""Qualify the UART and hierarchical APB FIFO on every declared digital profile."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio import digital_flow, digital_platform, job_store
from icstudio.digital_examples import uart_project
from icstudio.digital_apb_example import apb_project
from icstudio.digital_qualification import faulty_mapping, require_clean_route
from icstudio.model import atomic_write, file_digest, save_project

DESIGNS={'uart':uart_project,'apb':apb_project}


def workload(name, platform):
    project=DESIGNS[name]()
    project['digital']=digital_platform.bind(project['digital'],platform)
    project['digital']['timeout']=600
    project['digital']['physical']={'die_area':[0,0,400,400],'core_area':[20,20,380,380],
                                    'place_density':0.6,'threads':2}
    if name=='uart' and platform['name'] in ('gf180','gf180d'):
        # Preserve the original RTL and 10 ns / 1 ns I/O SDC. Map against the
        # captured slow library with an 8 ns combinational budget, then verify
        # every library corner with the profile's worst-case RC extraction.
        project['digital']['platform']['corner']='slow'
        project['digital']['synthesis']={'mapping':'speed','delay_ns':8,
            'driving_cell':'gf180mcu_fd_sc_mcu9t5v0__buf_4','load_pf':0}
    return project


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orfs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    platforms=parser.add_mutually_exclusive_group()
    platforms.add_argument('--platform',action='append',choices=digital_platform.BUNDLED_PLATFORMS)
    platforms.add_argument('--manifest',type=Path,help='Qualify one separately locked digital platform manifest.')
    parser.add_argument('--design',action='append',choices=DESIGNS)
    parser.add_argument('--tool',action='append',default=[],metavar='NAME=EXECUTABLE')
    args=parser.parse_args(argv);output=args.output.resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Choose an empty qualification output folder.')
    output.mkdir(parents=True,exist_ok=True)
    names=('iverilog','vvp','verilator','verilator_coverage','yosys','sta','eqy','sby','bitwuzla','yosys-abc','openroad','make','klayout')
    tools={name:os.environ.get('ICSTUDIO_TEST_'+name.upper()) or shutil.which(name) for name in names}
    tools.update(dict(value.split('=',1) for value in args.tool));tools={name:path for name,path in tools.items() if path}
    report={'schema':1,'status':'running','scope':'UART and APB FIFO implementation; not full-chip or foundry signoff',
            'qualifier_sha256':file_digest(Path(__file__)),
            'source_files':{p.name:file_digest(p) for p in sorted((ROOT/'icstudio').glob('digital*.py'))},'workloads':[]}
    def retain():atomic_write(output/'report.json',json.dumps(report,indent=2))
    platforms=[digital_platform.read_manifest(args.manifest)] if args.manifest else [
        digital_platform.from_orfs(args.orfs,name) for name in args.platform or digital_platform.BUNDLED_PLATFORMS]
    for platform in platforms:
        platform_name=platform['name']
        for name in args.design or DESIGNS:
            entry={'platform':platform_name,'design':name,'status':'running','cases':[]};report['workloads'].append(entry)
            root=output/platform_name/name;root.mkdir(parents=True);retain()
            try:
                project=workload(name,platform);config=project['digital'];save_project(project,root/'design.icproj')
                entry['technology']={k:v for k,v in config['platform'].items() if k!='root'}
                entry['conditions']={'physical':config['physical'],'timing_corners':config['timing_corners'],
                    'mapping_corner':config['platform']['corner'],'synthesis':config.get('synthesis',{}),
                    'constraints':[f for f in config['files'] if f['role']=='constraint']};retain()
                from icstudio.digital_rc import selected as extraction_corners
                entry['conditions']['rc_corners']=extraction_corners(config)
                def run(stage,label,upstream=None,expected=None):
                    folder=root/label;folder.mkdir()
                    job=digital_flow.prepare(project,stage,tools=tools,toolchain='custom',upstream=upstream,orfs=args.orfs)
                    atomic_write(folder/'input.json',json.dumps(job));job_store.state(folder,'running')
                    result=digital_flow.run(job,folder);atomic_write(folder/'result.json',json.dumps(result))
                    job_store.state(folder,'complete');job_store.read_result(folder/'result.json',project['id'])
                    data=result['digital_result'];entry['cases'].append({'name':label,'stage':stage,
                        'verdict':data.get('verdict'),'summary':data['summary'],'versions':data['versions'],
                        'result_sha256':file_digest(folder/'result.json')});retain()
                    print(platform_name,name,label,data['summary'],flush=True)
                    if expected and data.get('verdict') not in expected:
                        raise ValueError(label+': expected '+repr(expected)+', got '+str(data.get('verdict')))
                    return folder,data
                run('regression','behavior',expected=('PASS',))
                mapped,_=run('mapped','mapped')
                run('equivalence','equivalent',mapped,('PASS',))
                fault=faulty_mapping(mapped,root/'faulty-mapped',output='busy' if name=='uart' else None)
                _,bad=run('equivalence','fault-detected',fault,('FAIL',))
                if not bad['equivalence']['counterexamples']:raise ValueError('The fault did not retain a proof counterexample.')
                run('timing','pre-layout-timing',mapped,('PASS','FAIL'))
                finished,_=run('finish','finished',mapped)
                entry['router_checks']=require_clean_route(finished);retain()
                _,timed=run('timing','extracted-timing',finished,('PASS',))
                expected=[(lib,rc) for lib in config['timing_corners'] for rc in (extraction_corners(config) or [None])]
                if [(c['corner'],c.get('rc_corner')) for c in timed['timing']['corners']]!=expected:
                    raise ValueError('Extracted timing did not cover every selected library/interconnect pair.')
                run('equivalence','physical-equivalent',finished,('PASS',))
                entry['status']='passed'
            except Exception as exc:
                entry.update(status='failed',error=str(exc));print(platform_name,name,'FAILED',str(exc)[-1600:],flush=True)
            retain()
    report['status']='passed' if all(x['status']=='passed' for x in report['workloads']) else 'failed';retain()
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
