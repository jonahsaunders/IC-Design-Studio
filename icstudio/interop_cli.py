"""CLI entry points for external-tool execution and reviewed interchange."""
import argparse,json
from pathlib import Path
from .model import load_project,save_project,atomic_write

COMMANDS={'xschem-netlist','magic-workspace','magic-workspace-export','layout-review','tool-technology','pdk-template','klayout-lvs-report'}


def main(argv):
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('xschem-netlist');a.add_argument('--source',required=True);a.add_argument('--output',required=True)
    a.add_argument('--executable',default='xschem');a.add_argument('--library',action='append',default=[]);a.add_argument('--rcfile');a.add_argument('--mode',choices=['simulation','lvs'],default='simulation')
    a=sub.add_parser('magic-workspace');a.add_argument('project');a.add_argument('--cell',required=True);a.add_argument('--output',required=True)
    a.add_argument('--executable',default='magic');a.add_argument('--technology');a.add_argument('--profile',choices=['lvs','capacitance','rc'],default='lvs')
    a=sub.add_parser('magic-workspace-export');a.add_argument('workspace');a.add_argument('--output',required=True);a.add_argument('--executable',default='magic')
    a=sub.add_parser('layout-review');a.add_argument('project');a.add_argument('layout');a.add_argument('--output',required=True);a.add_argument('--choices');a.add_argument('--apply',action='store_true')
    a=sub.add_parser('tool-technology');a.add_argument('project');a.add_argument('--output',required=True)
    a=sub.add_parser('pdk-template');a.add_argument('project');a.add_argument('--kind',choices=['inverter','ring','current_mirror','differential_pair','amplifier'],required=True);a.add_argument('--supply',required=True);a.add_argument('--nmos');a.add_argument('--pmos');a.add_argument('--output',required=True)
    a=sub.add_parser('klayout-lvs-report');a.add_argument('database');a.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='xschem-netlist':
            from .external_tools import xschem_netlist
            result=xschem_netlist(args.source,args.output,args.executable,args.library,args.rcfile,args.mode)
        elif args.command=='magic-workspace':
            from .external_tools import magic_workspace
            p=load_project(args.project);cid=next(c['id'] for c in p['cells'] if args.cell in (c['id'],c['name']))
            result=magic_workspace(p,cid,args.output,args.executable,args.technology,args.profile)
        elif args.command=='magic-workspace-export':
            from .external_tools import magic_workspace_export
            result=magic_workspace_export(args.workspace,args.output,args.executable)
        elif args.command=='layout-review':
            from .layout_exchange import review,apply
            p=load_project(args.project);choices=json.loads(Path(args.choices).read_text()) if args.choices else {}
            result=review(p,args.layout,choices)
            if args.apply:apply(p,result);p['revision']+=1;save_project(p,args.output)
            else:atomic_write(args.output,json.dumps(result,indent=2))
        elif args.command=='tool-technology':
            from .interchange import export_technology
            export_technology(load_project(args.project),args.output);result={'status':'complete'}
        elif args.command=='pdk-template':
            from .project_templates import create
            p,_,_=create(load_project(args.project)['pdk'],args.kind,args.supply,args.nmos,args.pmos);save_project(p,args.output);result={'status':'complete'}
        else:
            from .klayout_lvs import read_database
            result=read_database(args.database);atomic_write(args.output,json.dumps(result,indent=2))
        print(json.dumps({k:v for k,v in result.items() if k not in ('candidate','inputs','files')},indent=2));return 0
    except Exception as exc:print(json.dumps({'error':str(exc)}));return 1
