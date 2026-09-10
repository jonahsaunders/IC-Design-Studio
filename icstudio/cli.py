from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .model import load_project,atomic_write,clone,validate,uid,save_project

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    from .interop_cli import COMMANDS as INTEROP_COMMANDS,main as interop
    if argv and argv[0] in INTEROP_COMMANDS:return interop(argv)
    from .feature_cli import COMMANDS,main as features
    if argv and argv[0] in COMMANDS:return features(argv)
    parser=argparse.ArgumentParser(prog='ICDesignStudio --cli',description='Offline reproducible circuit design runner')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('diagnostics');sub.add_parser('rpc')
    sim=sub.add_parser('simulate');sim.add_argument('project');sim.add_argument('--analysis',choices=['op','tran','dc','ac','noise']);sim.add_argument('--engine',choices=['builtin','ngspice'],default='builtin');sim.add_argument('--executable',default='ngspice');sim.add_argument('--cell');sim.add_argument('--output',required=True);sim.add_argument('--set',action='append',default=[])
    check=sub.add_parser('check');check.add_argument('project');check.add_argument('--kind',choices=['erc','drc','mapping','connectivity'],default='erc');check.add_argument('--output')
    export=sub.add_parser('export');export.add_argument('project');export.add_argument('--output',required=True)
    magic=sub.add_parser('magic')
    for name in ('executable','gds','technology','top','output'):magic.add_argument('--'+name,required=True)
    lvs=sub.add_parser('lvs')
    for name in ('executable','schematic','schematic-cell','extracted','layout-cell','setup','output'):lvs.add_argument('--'+name,required=True)
    plugin=sub.add_parser('plugin');plugin.add_argument('manifest');plugin.add_argument('project');plugin.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='diagnostics':
            from .engines import diagnostics
            print(json.dumps(diagnostics(),indent=2));return 0
        if args.command=='rpc':return rpc()
        if args.command=='simulate':
            from .simulation import run
            from .engines import run_ngspice
            p=load_project(args.project);settings=clone(p['analysis'])
            if args.analysis:settings['type']=args.analysis
            for setting in args.set:
                k,v=setting.split('=',1)
                if k not in settings:raise ValueError('Unknown analysis setting: '+k)
                settings[k]=int(v) if k=='points' else float(v) if k=='temperature' else v
            cid=args.cell or p['top']
            if not any(c['id']==cid for c in p['cells']):cid=next(c['id'] for c in p['cells'] if c['name']==cid)
            out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
            r=run(p,cid,settings) if args.engine=='builtin' else run_ngspice(p,cid,settings,args.executable,out.parent)
            atomic_write(out,json.dumps(r,allow_nan=False));print('Result written to '+str(out));return 0
        if args.command=='check':
            from .model import erc
            from .layout import drc,mapping_audit
            p=load_project(args.project);issues=erc(p) if args.kind=='erc' else drc(p,p['top']) if args.kind=='drc' else __import__('icstudio.physical',fromlist=['connectivity']).connectivity(p,p['top'])['issues'] if args.kind=='connectivity' else mapping_audit(p,p['top']);text=json.dumps({'revision':p['revision'],'qualification':'generic checks only','issues':issues},indent=2)
            if args.output:atomic_write(args.output,text)
            else:print(text)
            return 2 if any(i['severity']=='error' for i in issues) else 0
        if args.command=='export':
            from .interchange import export_handoff
            export_handoff(load_project(args.project),args.output);print('Handoff exported to '+args.output);return 0
        if args.command=='magic':
            from .engines import magic_convert
            print(magic_convert(args.executable,args.gds,args.technology,args.output,args.top));return 0
        if args.command=='lvs':
            from .engines import netgen_lvs
            print(netgen_lvs(args.executable,args.schematic,args.schematic_cell,args.extracted,args.layout_cell,args.setup,args.output));return 0
        if args.command=='plugin':
            from .sdk import run_plugin
            p=run_plugin(args.manifest,load_project(args.project));save_project(p,args.output);print('Validated plugin commands saved to '+args.output);return 0
    except Exception as e:print(json.dumps({'error':str(e)}),file=sys.stderr);return 1
    return 0

def rpc():
    # JSON-RPC 2.0 over stdin/stdout. No TCP listener and no implicit script execution.
    for line in sys.stdin:
        request={}
        try:
            if len(line)>50*1024*1024:raise ValueError('Request size limit exceeded.')
            request=json.loads(line)
            if request.get('jsonrpc')!='2.0':raise ValueError('jsonrpc must be 2.0')
            method=request['method'];params=request.get('params',{})
            if method=='capabilities':result={'api':'1.0','methods':['capabilities','validate','simulate','erc','connectivity','parasitics'],'schema':1,'limits':{'solver_unknowns':80,'transient_steps':20000}}
            elif method=='validate':result={'valid':bool(validate(params['project']))}
            elif method=='simulate':
                from .simulation import run
                p=validate(params['project']);result=run(p,params.get('cell',p['top']),params.get('settings',p['analysis']))
            elif method in ('connectivity','parasitics'):
                from .workflow_jobs import check_job
                p=validate(params['project']);result=check_job(p,params.get('cell',p['top']),method)
            elif method=='erc':
                from .model import erc
                result=erc(validate(params['project']))
            else:raise ValueError('Unsupported method: '+method)
            print(json.dumps({'jsonrpc':'2.0','id':request.get('id'),'result':result},allow_nan=False),flush=True)
        except Exception as e:print(json.dumps({'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32602,'message':str(e)}}),flush=True)
    return 0
