"""Reproduce edit/undo/redo/render/save/recovery on real and synthetic designs."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=3)
    args = parser.parse_args()
    from icstudio.automation_benchmark import benchmark
    from icstudio.design_automation import envelope
    from icstudio.model import example, device, load_project, validate
    from icstudio.layout import rect
    workloads = []
    real = load_project(ROOT / 'examples/amplifier-testbench.icproj')
    workloads.append(('saved amplifier testbench', real))
    synthetic = example('empty')
    cell = synthetic['cells'][0]
    cell['devices'] = [device('R', 'R' + str(i), x=(i % 25) * 250, y=(i // 25) * 200,
                              nets={'p': 'signal' + str(i), 'n': '0'}) for i in range(500)]
    cell['shapes'] = [rect('metal1', (i % 100) * 1000, (i // 100) * 1000, 400, 400) for i in range(10000)]
    workloads.append(('synthetic 500 devices and 10000 distinct shapes', validate(synthetic)))
    rows = []
    for name, project in workloads:
        cell = next(c for c in project['cells'] if c['devices'])
        target = cell['devices'][0]
        batch = envelope(project, [{'type': 'move_device', 'cell_id': cell['id'],
            'device_id': target['id'], 'x': target['x'] + 20}], 'Benchmark connected move')
        row = benchmark(project, batch, args.iterations, render=True)
        rows.append({'workload': name, **row})
        print(json.dumps({'workload': name, 'median_ms': {k: v['median'] for k, v in row['timings_ms'].items()}}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'workloads': rows, 'qualification':
        'Measured build-host lifecycle and CPU offscreen canvas rendering. Full Studio refresh, external engines and native display latency are excluded.'}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
