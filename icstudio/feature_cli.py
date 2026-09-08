"""Additional reproducible workflows for automation and remote shell execution."""
import argparse,json,sys
from pathlib import Path
from .model import load_project,save_project,atomic_write
COMMANDS={'mirror-layout','inverter-layout','analog','characterize','verify','testbench','ring-layout','silicon','sky130-layout','magic-import','sky130-reference','study','extract','parasitics','post-layout','verilog','project-folder','pdk','route'}

def main(argv):
    parser=argparse.ArgumentParser(prog='ICDesignStudio --cli');sub=parser.add_subparsers(dest='command',required=True)
    for cmd in ('silicon','sky130-layout'):
        a=sub.add_parser(cmd);a.add_argument('project');a.add_argument('--cell',required=True);a.add_argument('--output',required=True)
        for engine in ('magic','netgen','ngspice'):a.add_argument('--'+engine,default=engine)
    for command in ('verify','testbench'):
        a=sub.add_parser(command);a.add_argument('project');a.add_argument('--testbench',required=True);a.add_argument('--output',required=True)
        for engine in ('magic','netgen','ngspice'):a.add_argument('--'+engine,default=engine)
    for command in ('mirror-layout','inverter-layout'):
        a=sub.add_parser(command);a.add_argument('project');a.add_argument('--cell',required=True);a.add_argument('--output',required=True);a.add_argument('--replace',action='store_true')
    a=sub.add_parser('ring-layout');a.add_argument('project');a.add_argument('--cell',required=True);a.add_argument('--output',required=True);a.add_argument('--replace',action='store_true')
    a=sub.add_parser('analog');a.add_argument('project',help='Blank or existing project with the PDK to use');a.add_argument('--kind',choices=['current_mirror','differential_pair'],required=True);a.add_argument('--output',required=True)
    a=sub.add_parser('characterize');a.add_argument('project');a.add_argument('--testbench',required=True);a.add_argument('--spec',help='Optional study JSON; defaults to the saved bench study');a.add_argument('--ngspice',default='ngspice');a.add_argument('--output',required=True)
    a.add_argument('--compare-layout',action='store_true');a.add_argument('--magic',default='magic');a.add_argument('--netgen',default='netgen')
    study=sub.add_parser('study');study.add_argument('project');study.add_argument('--spec',required=True);study.add_argument('--engine',choices=['builtin','ngspice'],default='builtin');study.add_argument('--executable',default='ngspice');study.add_argument('--output',required=True)
    extract=sub.add_parser('extract')
    for key in ('executable','gds','technology','top','output'):extract.add_argument('--'+key,required=True)
    extract.add_argument('--profile',choices=['lvs','rc'],default='rc')
    for cmd in ('parasitics','post-layout','verilog','project-folder'):
        p=sub.add_parser(cmd);p.add_argument('project');p.add_argument('--output',required=True)
    p=sub.add_parser('pdk');p.add_argument('action',choices=['install','register','list','activate','verify']);p.add_argument('--registry',required=True);p.add_argument('--manifest');p.add_argument('--folder');p.add_argument('--key');p.add_argument('--project');p.add_argument('--output')
    route=sub.add_parser('route');route.add_argument('project');route.add_argument('--spec',required=True);route.add_argument('--output',required=True)
    sky=sub.add_parser('sky130-reference');sky.add_argument('--pdk-root',required=True);sky.add_argument('--output',required=True)
    for name in ('ngspice','magic','netgen'):sky.add_argument('--'+name,default=name)
    magic=sub.add_parser('magic-import')
    for key in ('executable','source','technology','output'):magic.add_argument('--'+key,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='magic-import':
            from .engines import magic_import
            print(magic_import(args.executable,args.source,args.technology,args.output));return 0
        if args.command=='sky130-reference':
            from .sky130_flow import run
            report=run(args.pdk_root,args.output,args.ngspice,args.magic,args.netgen);print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1
        if args.command=='extract':
            from .engines import magic_extract
            print(json.dumps(magic_extract(args.executable,args.gds,args.technology,args.top,args.output,args.profile),indent=2));return 0
        if args.command=='pdk':
            from .pdks import PDKRegistry
            r=PDKRegistry(args.registry)
            if args.action=='list':print(json.dumps(r.entries(),indent=2))
            elif args.action=='register':print(r.register_local(args.folder))
            elif args.action=='install':print(r.install(args.manifest))
            elif args.action=='verify':print(json.dumps(r.verify(args.key),indent=2))
            else:
                p=load_project(args.project)
                from .catalog import link_technology
                link_technology(p,r.technology(args.key));save_project(p,args.output)
            return 0
        p=load_project(args.project);cid=p['top'];out=Path(args.output)
        if args.command=='analog':
            from .analog import reference
            p,_,_=reference(p['pdk'],args.kind);save_project(p,out);return 0
        if args.command=='characterize':
            from .testbenches import get
            from .characterization import run,csv_text
            t=get(p,args.testbench);spec=json.loads(Path(args.spec).read_text()) if args.spec else t.get('characterization')
            if spec is None:raise ValueError('Supply --spec or save a characterization study on the bench.')
            if args.compare_layout:spec={**spec,'compare_layout':True}
            result=run(p,t['id'],spec,args.ngspice,out,lambda f,m:print(m,flush=True),tools={e:getattr(args,e) for e in ('magic','netgen','ngspice')});atomic_write(out/'measurements.csv',csv_text(result));print(json.dumps(result['summary']));return 0 if result['status']=='passed' else 1
        if args.command in ('verify','testbench'):
            from .testbenches import get,simulate
            t=get(p,args.testbench)
            if args.command=='verify':
                from .hierarchical_flow import run
                result=run(p,t['id'],out,{e:getattr(args,e) for e in ('magic','netgen','ngspice')},lambda f,m:print(m,flush=True));print(json.dumps(result,indent=2));return 0 if result['status']=='passed' else 1
            if out.exists() and any(out.iterdir()):raise ValueError('Choose an empty testbench output directory.')
            result=simulate(p,t,args.ngspice,out);print(json.dumps(result['measurements'],indent=2));return 0 if result['measurements']['status']=='passed' else 1
        if args.command in ('mirror-layout','inverter-layout'):
            from .analog_layout import generate_mirror
            from .process_adapters import generate_inverter
            cid=next(c['id'] for c in p['cells'] if args.cell in (c['id'],c['name']));(generate_mirror if args.command=='mirror-layout' else generate_inverter)(p,cid,args.replace);p['revision']+=1;save_project(p,out);return 0
        if args.command=='ring-layout':
            from .ring_oscillator import generate
            cid=next(c['id'] for c in p['cells'] if args.cell in (c['id'],c['name']));generate(p,cid,args.replace);p['revision']+=1;save_project(p,out);return 0
        if args.command in ('silicon','sky130-layout'):
            cid=next(c['id'] for c in p['cells'] if args.cell in (c['id'],c['name']))
            if args.command=='sky130-layout':
                from .sky130_layout import generate_inverter
                generate_inverter(p,cid);p['revision']+=1;save_project(p,out);return 0
            from .silicon_flow import run
            result=run(p,cid,out,{e:getattr(args,e) for e in ('magic','netgen','ngspice')},lambda f,m:print(m,flush=True));print(json.dumps(result,indent=2));return 0 if result['status']=='passed' else 1
        if args.command=='study':
            from .studies import run_study
            spec=json.loads(Path(args.spec).read_text());work=out.parent/(out.stem+'-cases');result=run_study(p,cid,p['analysis'],spec,args.engine,args.executable,work)
        elif args.command=='parasitics':
            from .physical import capacitance_estimate
            result=capacitance_estimate(p,cid)
        elif args.command=='post-layout':
            from .workflow_jobs import post_layout_job
            result=post_layout_job(p,{'cell':cid,'engine':'builtin','settings':{'analysis':p['analysis']}},out.parent,lambda *_:None)
        elif args.command=='verilog':
            from .design_ops import verilog
            atomic_write(out,verilog(p));return 0
        elif args.command=='project-folder':
            from .project_store import save_directory
            print(save_directory(p,out));return 0
        elif args.command=='route':
            from .physical import route
            spec=json.loads(Path(args.spec).read_text());shape=route(p,cid,**spec);next(c for c in p['cells'] if c['id']==cid)['shapes'].append(shape);p['revision']+=1;save_project(p,out);return 0
        atomic_write(out,json.dumps(result,indent=2,allow_nan=False));print('Written '+str(out));return 0
    except Exception as e:print(json.dumps({'error':str(e)}),file=sys.stderr);return 1
