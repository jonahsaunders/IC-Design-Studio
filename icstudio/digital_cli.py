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
    example = commands.add_parser('example'); example.add_argument('--output', required=True)
    capture = commands.add_parser('import'); capture.add_argument('manifest'); capture.add_argument('--output', required=True)
    export = commands.add_parser('export'); export.add_argument('project'); export.add_argument('--output', required=True)
    run = commands.add_parser('run'); run.add_argument('project'); run.add_argument('--output', required=True)
    run.add_argument('--stage', choices=digital_flow.STAGES, default='simulate')
    run.add_argument('--simulator', choices=['icarus', 'verilator'], default='icarus')
    run.add_argument('--tool', action='append', default=[], metavar='NAME=EXECUTABLE')
    args = parser.parse_args(argv)
    try:
        if args.command in ('example', 'import'):
            project = digital.counter_project()
            if args.command == 'import':
                project['digital'] = digital.read_manifest(args.manifest)
                project['name'] = project['digital']['top']
            save_project(project, args.output)
            print('Saved '+args.output); return 0
        project = load_project(args.project)
        if args.command == 'export':
            print(digital_flow.export_flow(project['digital'], args.output)); return 0
        tools = dict(item.split('=', 1) for item in args.tool)
        job = digital_flow.prepare(project, args.stage, args.simulator, tools)
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
