"""Command-line inspection, atomic editing, and measured document lifecycles."""
import argparse
import json
import sys
from pathlib import Path

from .model import atomic_write, load_project, save_project
from .design_automation import capabilities, inspect, preview


def main(argv=None):
    parser = argparse.ArgumentParser(prog='ICDesignStudio --cli automation')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('capabilities')
    query = sub.add_parser('inspect')
    query.add_argument('project')
    query.add_argument('--root-cell')
    query.add_argument('--instance', action='append', default=[], help='Stable instance ID; repeat to descend')
    query.add_argument('--output')
    apply = sub.add_parser('apply')
    apply.add_argument('project')
    apply.add_argument('--batch', required=True, help='Versioned JSON batch including project/revision/hash guards')
    apply.add_argument('--output', help='Destination project; required unless --preview is set')
    apply.add_argument('--preview', action='store_true', help='Validate and report without saving a project')
    apply.add_argument('--report')
    bench = sub.add_parser('benchmark')
    bench.add_argument('project')
    bench.add_argument('--batch', required=True)
    bench.add_argument('--iterations', type=int, default=5)
    bench.add_argument('--render', action='store_true', help='Include offscreen schematic/layout canvas rendering')
    bench.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'capabilities':
            result = capabilities()
        elif args.action == 'inspect':
            result = inspect(load_project(args.project), args.instance, args.root_cell)
        else:
            project = load_project(args.project)
            file = Path(args.batch)
            if file.stat().st_size > 10 * 1024 * 1024:
                raise ValueError('Automation batch exceeds 10 MiB.')
            batch = json.loads(file.read_text(encoding='utf-8'))
            if args.action == 'apply':
                if not args.preview and not args.output:
                    raise ValueError('Applying a batch requires --output.')
                proposal = preview(project, batch)
                result = proposal['report']
                if not args.preview:
                    save_project(proposal['project'], args.output)
                if args.report:
                    atomic_write(args.report, json.dumps(result, indent=2, allow_nan=False) + '\n')
            else:
                from .automation_benchmark import benchmark
                result = benchmark(project, batch, args.iterations, render=args.render)
        text = json.dumps(result, indent=2, allow_nan=False) + '\n'
        if args.action in ('inspect', 'benchmark') and args.output:
            atomic_write(args.output, text)
        else:
            print(text, end='')
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
