"""Headless entry point for the same digital jobs used by the desktop."""
import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    from . import digital, digital_flow, job_store, worker
    from .model import atomic_write, load_project, save_project
    parser = argparse.ArgumentParser(prog='ICDesignStudio --cli digital')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('setup',help='Install and verify the included digital runtime')
    commands.add_parser('status',help='Report included runtime readiness as JSON')
    example = commands.add_parser('example'); example.add_argument('--output', required=True)
    example.add_argument('--design',choices=['counter','uart','apb'],default='counter')
    capture = commands.add_parser('import'); capture.add_argument('manifest'); capture.add_argument('--output', required=True)
    export = commands.add_parser('export'); export.add_argument('project'); export.add_argument('--output', required=True)
    run = commands.add_parser('run'); run.add_argument('project'); run.add_argument('--output', required=True)
    run.add_argument('--stage', choices=digital_flow.STAGES, default='simulate')
    run.add_argument('--simulator', choices=['icarus', 'verilator'], default='icarus')
    run.add_argument('--tool', action='append', default=[], metavar='NAME=EXECUTABLE')
    run.add_argument('--toolchain', choices=['auto','included','custom'], default='auto',
                     help='Use included tools or an external toolchain (auto preserves --tool/PATH behavior)')
    run.add_argument('--cell',help='Native cell ID (defaults to the bound digital cell)')
    run.add_argument('--platform',help='Version-1 platform JSON manifest')
    run.add_argument('--orfs',help='OpenROAD Flow Scripts checkout; captured for physical jobs')
    run.add_argument('--orfs-platform',choices=['sky130hd','nangate45'],help='Import this platform from --orfs')
    run.add_argument('--upstream',help='Completed mapped or physical run directory')
    run.add_argument('--timeout',type=int,help='Per-command time limit in seconds')
    args = parser.parse_args(argv)
    try:
        from . import digital_runtime
        if args.command=='setup': return digital_runtime.main()
        if args.command=='status':
            info=digital_runtime.status(); print(json.dumps(info,indent=2)); return 0 if info['state']=='ready' else 1
        if args.command in ('example', 'import'):
            project = digital.counter_project()
            if args.command=='example' and args.design=='uart':
                from .digital_examples import uart_project
                project=uart_project()
            if args.command=='example' and args.design=='apb':
                from .digital_apb_example import apb_project
                project=apb_project()
            if args.command == 'import':
                project['digital'] = digital.read_manifest(args.manifest)
                project['name'] = project['digital']['top']
            digital_runtime.defaults(project)
            save_project(project, args.output)
            print('Saved '+args.output); return 0
        project = load_project(args.project)
        if args.command == 'export':
            print(digital_flow.export_flow(project['digital'], args.output)); return 0
        from .digital_design import config as cell_config,set_config
        cid=args.cell or project.get('digital_cell',project['top']);config=cell_config(project,cid)
        if not config:raise ValueError('The selected cell has no RTL sources.')
        if args.platform and args.orfs_platform:raise ValueError('Choose one platform import method.')
        if args.platform:
            from .digital_platform import read_manifest
            config['platform']=read_manifest(args.platform)
        if args.orfs_platform:
            if not args.orfs:raise ValueError('--orfs-platform requires --orfs.')
            from .digital_platform import from_orfs
            config['platform']=from_orfs(args.orfs,args.orfs_platform)
        if args.timeout is not None:config['timeout']=args.timeout
        set_config(project,cid,config)
        tools = dict(item.split('=', 1) for item in args.tool)
        if args.toolchain == 'included' and (any(tools.values()) or args.orfs):
            raise ValueError('Use --toolchain custom with --tool or --orfs overrides.')
        if args.toolchain != 'custom' and not any(tools.values()): digital_runtime.defaults(project,cid)
        job = digital_flow.prepare(project, args.stage, args.simulator, tools, cid, args.upstream, args.orfs, toolchain=args.toolchain)
        root = Path(args.output).resolve()
        if root.exists() and any(root.iterdir()):
            raise ValueError('Choose an empty run directory.')
        root.mkdir(parents=True, exist_ok=True)
        atomic_write(root/'input.json', json.dumps(job))
        job_store.state(root, 'running')
        code = worker.main(root/'input.json', root/'result.json')
        job_store.state(root, 'complete' if code == 0 else 'failed', exit_code=code)
        if code == 0:
            job_store.read_result(root/'result.json', project['id'])
        return code
    except (ValueError, KeyError, OSError) as exc:
        print(str(exc), file=sys.stderr); return 1
