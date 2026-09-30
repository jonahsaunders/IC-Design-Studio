"""Bounded, clocked RTL/SPICE coupling with causal full-history replay.

SPICE integrates the complete analog history before each digital sampling edge.
Icarus replays the captured input prefix; prior outputs must agree exactly.
This trades speed for portable, inspectable state preservation without a shared
library/VPI dependency. It is not an asynchronous Verilog-AMS solver.
"""
import json
import math
import re
import shutil
import time
from pathlib import Path

from .model import atomic_write, clone, design_digest, digest, file_digest, now, scalar

IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
NODE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
TICK = 1e-12


def validate_project(project):
    c = project.get('mixed_signal')
    if c is None:
        return
    if not isinstance(c, dict) or c.get('version') != 1:
        raise ValueError('Unsupported mixed-signal configuration.')
    cells = {cell['id']: cell for cell in project['cells']}
    if c.get('analog_cell') not in cells or c.get('digital_cell') not in cells:
        raise ValueError('Mixed-signal analog and digital cells must exist.')
    if c['analog_cell'] == c['digital_cell'] or project.get('spice', {}).get('version') != 1:
        raise ValueError('Choose separate native analog and RTL cells.')
    from .digital_design import config
    from .digital import validate_config, check_dependencies
    rtl = config(project, c['digital_cell']); validate_config(rtl); check_dependencies(rtl)
    if any(f['path'].split('/')[0].casefold().startswith('bridge') for f in rtl['files']):
        raise ValueError('The bridge file prefix is reserved for mixed-signal runs.')
    period = scalar(c.get('period', 0)); rise = scalar(c.get('rise', 0))
    step = scalar(c.get('max_step', 0)); cycles = c.get('cycles')
    ticks = round(period / TICK)
    if not 1000 <= ticks <= 10**9 or not math.isclose(period, ticks*TICK, rel_tol=0, abs_tol=TICK*.001):
        raise ValueError('Clock period must be 1 ns–1 ms in whole picoseconds.')
    if not 2*TICK <= rise < period/4 or not 0 < step <= period/10:
        raise ValueError('Use a finite rise below a quarter period and a maximum step below a tenth period.')
    if type(cycles) is not int or not 2 <= cycles <= 256:
        raise ValueError('Clocked replay supports 2–256 edges per run.')
    if type(c.get('timeout', 180)) is not int or not 1 <= c.get('timeout', 180) <= 3600:
        raise ValueError('Mixed-signal timeout must be 1–3,600 seconds.')
    ports = {c.get('clock')}; nodes = set()
    if not isinstance(c.get('clock'), str) or not IDENT.fullmatch(c['clock']):
        raise ValueError('Choose a scalar RTL clock port.')
    for direction in ('inputs', 'outputs'):
        rows = c.get(direction)
        if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
            raise ValueError('Use 1–32 mixed-signal ports in each direction.')
        for row in rows:
            port = row.get('port'); width = row.get('width', 1)
            if not isinstance(port, str) or not IDENT.fullmatch(port) or port in ports:
                raise ValueError('Bridge port names must be distinct RTL identifiers.')
            ports.add(port)
            if type(width) is not int or not 1 <= width <= 32:
                raise ValueError('Bridge port width must be 1–32 bits.')
            if direction == 'inputs':
                if 'node' in row:
                    if width != 1 or not NODE.fullmatch(row['node']) or scalar(row['low']) >= scalar(row['high']):
                        raise ValueError('Analog inputs need a scalar node and increasing logic thresholds.')
                else:
                    values = row.get('values')
                    if not isinstance(values, list) or len(values) != cycles or any(type(v) is not int or not 0 <= v < 2**width for v in values):
                        raise ValueError('Provide one in-range stimulus value per clock edge.')
            elif 'nodes' in row:
                if len(row['nodes']) != width or scalar(row['low']) >= scalar(row['high']):
                    raise ValueError('Digital outputs need one node per bit and increasing voltage levels.')
                if type(row.get('initial')) is not int or not 0 <= row['initial'] < 2**width:
                    raise ValueError('Declare an in-range initial value for every analog driver.')
                for node in row['nodes']:
                    if not isinstance(node, str) or not NODE.fullmatch(node) or node.casefold() in nodes:
                        raise ValueError('Analog bridge drivers must have distinct simple node names.')
                    nodes.add(node.casefold())
    outputs = {r['port']: r for r in c['outputs']}
    for row in c['inputs']:
        gate = row.get('sample_when')
        if gate and (gate.get('port') not in outputs or outputs[gate['port']].get('width', 1) != 1 or gate.get('value') not in (0, 1)):
            raise ValueError('Sampling enable must reference a scalar RTL output.')
    stimuli = c.get('stimuli', {})
    if not isinstance(stimuli, dict) or len(stimuli) > 32:
        raise ValueError('Use at most 32 analog stimulus nodes.')
    for node, points in stimuli.items():
        if not NODE.fullmatch(node) or node.casefold() in nodes:
            raise ValueError('Analog stimulus and bridge nodes must be distinct.')
        nodes.add(node.casefold()); validate_points(points, cycles*period)
    probes = c.get('probes', [])
    if not isinstance(probes, list) or not 1 <= len(probes) <= 64 or any(not isinstance(n, str) or not NODE.fullmatch(n) for n in probes):
        raise ValueError('Choose 1–64 simple analog probe nodes.')
    verification = c.get('verification')
    if verification is not None and (verification.get('kind') != 'sar4' or not 0 < scalar(verification.get('reference', 0)) <= 100):
        raise ValueError('Choose the four-bit SAR check and a positive reference voltage.')


def validate_points(points, stop):
    if not isinstance(points, list) or not 1 <= len(points) <= 1024:
        raise ValueError('Analog stimuli need 1–1,024 time/voltage pairs.')
    previous = -1
    for pair in points:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('Each stimulus point needs time and voltage.')
        t, v = map(scalar, pair)
        if not previous < t <= stop:
            raise ValueError('Stimulus times must increase within the run duration.')
        previous = t
    if scalar(points[0][0]) != 0:
        raise ValueError('Analog stimuli must start at time zero.')


def environment(job):
    from .build_info import WORKFLOW_SOURCE_HASH
    return dict(engine='mixed_signal', workflow_hash=WORKFLOW_SOURCE_HASH,
                executables={k: file_digest(v) for k, v in job['settings']['tools'].items()},
                sources={p: file_digest(Path(__file__).with_name(p)) for p in
                         ('mixed_signal.py', 'sar_example.py', 'engines.py', 'native_spice.py', 'native_analysis.py',
                          'digital.py', 'digital_design.py', 'digital_flow.py', 'model.py', 'run_environment.py')})


def prepare(project, tools=None):
    from .model import validate
    from .spice_program import find_ngspice
    p = clone(project); validate(p)
    if 'mixed_signal' not in p:
        raise ValueError('Open a project with a saved mixed-signal configuration.')
    resolved = {}
    for name in ('ngspice', 'iverilog', 'vvp'):
        candidate = (tools or {}).get(name) or (find_ngspice() if name == 'ngspice' else shutil.which(name))
        path = Path(shutil.which(str(candidate)) or str(candidate)).resolve() if candidate else None
        if path is None or not path.is_file():
            raise ValueError('Mixed-signal simulation requires a local '+name+' executable. Select it in Mixed-signal setup.')
        resolved[name] = str(path)
    job = dict(project=p, cell=p['mixed_signal']['analog_cell'], engine='mixed_signal',
               settings=dict(type='mixed_signal', tools=resolved))
    job['environment'] = environment(job)
    return job


def bridge_testbench(c, top):
    inputs, outputs = c['inputs'], c['outputs']
    declarations = [f'reg {c["clock"]} = 0;']
    for direction, rows in (('reg', inputs), ('wire', outputs)):
        declarations += [f'{direction} [{r.get("width", 1)-1}:0] {r["port"]};' for r in rows]
    ports = [c['clock']] + [r['port'] for r in inputs+outputs]
    width = sum(r.get('width', 1) for r in inputs); period = round(scalar(c['period'])/TICK)
    bindings = ','.join(f'.{p}({p})' for p in ports)
    lhs = ','.join(r['port'] for r in inputs)
    fmt = ' '.join('%b' for _ in outputs); values = ','.join(r['port'] for r in outputs)
    return f'''`timescale 1ps/1ps
module bridge_tb;
{chr(10).join(declarations)}
{top} dut({bindings});
integer fd, count, n, ok;
reg [{width-1}:0] packed_inputs;
initial begin
  $dumpfile("bridge.vcd"); $dumpvars(0, bridge_tb);
  if (!$value$plusargs("edges=%d", count)) $fatal(1,"Missing edge count");
  fd = $fopen("bridge_inputs.txt","r");
  if (!fd) $fatal(1,"Missing bridge inputs");
  for (n=0; n<count; n=n+1) begin
    ok = $fscanf(fd,"%h",packed_inputs);
    if (ok != 1) $fatal(1,"Incomplete bridge inputs");
    {{{lhs}}} = packed_inputs;
    #1 {c['clock']} = 1;
    #1 $display("ICMS %0d {fmt}",n,{values});
    #{period//2-2} {c['clock']} = 0;
    #{period-period//2};
  end
  $fclose(fd); $finish;
end
endmodule
'''


def decode_outputs(log, c, count):
    rows = []
    for line in log.splitlines():
        if not line.startswith('ICMS '):
            continue
        parts = line.split()
        if len(parts) != 2+len(c['outputs']) or parts[1] != str(len(rows)):
            raise ValueError('Malformed or out-of-order digital bridge output.')
        row = {}
        for spec, value in zip(c['outputs'], parts[2:]):
            if len(value) != spec.get('width', 1) or not re.fullmatch('[01]+', value):
                raise ValueError('Unknown or high-impedance digital output: '+spec['port'])
            row[spec['port']] = int(value, 2)
        rows.append(row)
    if len(rows) != count:
        raise ValueError('Digital simulation ended before every bridge edge was produced.')
    return rows


def logic_input(value, spec):
    if not math.isfinite(value):
        raise ValueError('Non-finite analog bridge sample.')
    if value <= scalar(spec['low']): return 0
    if value >= scalar(spec['high']): return 1
    raise ValueError('Ambiguous analog level at '+spec['port']+': '+str(value)+' V; refine timing or thresholds.')


def driver_points(c, outputs):
    period = scalar(c['period']); rise = scalar(c['rise']); histories = {}
    for spec in c['outputs']:
        for bit, node in enumerate(spec.get('nodes', [])):
            voltage = lambda value: scalar(spec['high'] if value & (1 << bit) else spec['low'])
            last = voltage(spec['initial']); points = [[0., last]]
            for k, row in enumerate(outputs):
                value = voltage(row[spec['port']])
                if value != last:
                    edge = k*period+2*TICK
                    points.extend([[edge, last], [edge+rise, value]]); last = value
            histories[node] = points
    return histories


def run(job, directory, progress=lambda *_: None):
    from .engines import execute, parse_raw
    from .digital_design import config
    from .digital_flow import stage_sources, compiler_args
    from .native_spice import netlist
    from .native_analysis import circuit_text
    from .run_environment import verify
    from .spice_program import runtime_environment
    verify(job); p = clone(job['project']); validate_project(p); c = p['mixed_signal']
    root = Path(directory).resolve(); root.mkdir(parents=True, exist_ok=True)
    work = root/'bridge'; work.mkdir(exist_ok=True)
    rtl = config(p, c['digital_cell']); stage_sources(rtl, work)
    atomic_write(work/'bridge_tb.sv', bridge_testbench(c, rtl['top']))
    tools = job['settings']['tools']; commands = []; deadline = time.monotonic()+c.get('timeout', 180)
    def command(args, cwd, name, env=None):
        remaining = deadline-time.monotonic()
        if remaining <= 0: raise TimeoutError('Mixed-signal run exceeded its total time budget.')
        commands.append([str(v) for v in args])
        atomic_write(root/'commands.json', json.dumps(commands, indent=2))
        try: log = execute(args, cwd, timeout=remaining, env=env)
        except Exception as exc:
            atomic_write(cwd/name, str(exc)); raise
        atomic_write(cwd/name, log); return log
    args = [tools['iverilog'], '-g2012', '-Wportbind', '-s', 'bridge_tb', '-o', 'bridge.vvp']+compiler_args(rtl)
    args += ['bridge_tb.sv']
    compile_log = command(args, work, 'compile.log')
    if re.search(r'expects \d+ bits|dangling input port', compile_log, re.I):
        raise ValueError('RTL port widths or connections do not match the bridge. Inspect bridge/compile.log.')
    analog = clone(p); analog['top'] = c['analog_cell']
    # Native netlisting captures embedded model assets in this same directory.
    body = circuit_text(netlist(analog, root))
    if re.search(r'(?im)^\s*v_icms_', body):
        raise ValueError('The V_ICMS_ source prefix is reserved for bridge drivers.')
    probes = list(dict.fromkeys(c['probes']+[r['node'] for r in c['inputs'] if 'node' in r]))
    outputs, inputs, samples = [], [], []; period = scalar(c['period'])
    def analog_run(stop, name):
        folder = root/name; folder.mkdir(exist_ok=True)
        # Model references are relative to root, so execute every deck there.
        histories = {**clone(c.get('stimuli', {})), **driver_points(c, outputs)}
        lines = [body]
        for i, (node, points) in enumerate(histories.items()):
            points = [[scalar(t), scalar(v)] for t, v in points]
            # Future stimulus points remain: PWL interpolation before an edge
            # must not depend on how long this particular prefix is simulated.
            values = ' '.join(f'{t:.15g} {v:.15g}' for t, v in points)
            lines.append(f'V_ICMS_{i} {node} 0 PWL({values})')
        step = min(scalar(c['max_step']), stop/20)
        lines += ['.options reltol=1e-6 abstol=1e-12 vntol=1e-8',
                  '.save '+' '.join('v('+n+')' for n in probes),
                  f'.tran {step:.15g} {stop:.15g} 0 {step:.15g}', '.end']
        deck = folder/'input.cir'; raw = folder/'result.raw'
        atomic_write(deck, '\n'.join(lines)+'\n')
        if raw.exists(): raw.unlink()
        command([tools['ngspice'], '-n', '-b', '-D', 'filetype=ascii', '-r', raw, deck], root,
                name.replace('/', '_')+'.log', runtime_environment(tools['ngspice']))
        names, rows, complex_data = parse_raw(raw)
        if complex_data or not rows or abs(rows[-1][0]-stop) > max(TICK*.01, stop*1e-8):
            raise ValueError('Analog transient did not reach the sampling edge.')
        if any(not math.isfinite(v) for row in rows for v in row):
            raise ValueError('Analog transient returned non-finite values.')
        traces = {n: [row[names.index('v('+n.lower()+')')] for row in rows] for n in probes}
        return [row[0] for row in rows], traces
    for k in range(c['cycles']):
        measured = analog_run(k*period+TICK, f'edge-{k:03d}')[1] if k else {}
        row = {}; enabled = {}
        for spec in c['inputs']:
            if 'node' not in spec: value = spec['values'][k]
            else:
                gate = spec.get('sample_when')
                active = not gate or bool(outputs and outputs[-1][gate['port']] == gate['value'])
                enabled[spec['port']] = active
                if active and not measured: raise ValueError('Analog sampling at time zero needs a disabled sampling enable.')
                value = logic_input(measured[spec['node']][-1], spec) if active else 0
            row[spec['port']] = value
        inputs.append(row)
        packed = []
        for values in inputs:
            value = 0
            for spec in c['inputs']: value = (value << spec.get('width', 1)) | values[spec['port']]
            packed.append(f'{value:x}')
        atomic_write(work/'bridge_inputs.txt', '\n'.join(packed)+'\n')
        log = command([tools['vvp'], 'bridge.vvp', '+edges='+str(k+1)], work, f'edge-{k:03d}.log')
        replayed = decode_outputs(log, c, k+1)
        if replayed[:-1] != outputs:
            raise ValueError('Digital prefix changed during replay; use deterministic clocked RTL.')
        outputs = replayed
        samples.append(dict(edge=k, time=k*period+TICK, inputs=row, outputs=outputs[-1],
                            sampled=enabled, analog={n: v[-1] for n, v in measured.items()}))
        atomic_write(root/'bridge-samples.json', json.dumps(samples, indent=2))
        progress((k+1)/(c['cycles']+1), f'Mixed-signal edge {k+1}/{c["cycles"]}')
    x, traces = analog_run(c['cycles']*period, 'final')
    atomic_write(root/'waveforms.json', json.dumps(dict(x=x, traces=traces), allow_nan=False))
    result = dict(schema=1, created=now(), engine='ngspice + Icarus · clocked replay',
                  project_id=p['id'], revision=p['revision'], cell_id=job['cell'],
                  design_hash=design_digest(p), pdk_hash=digest(p['pdk']), rule_hash=digest(p['pdk']['layers']),
                  settings=clone(job['settings']), x=x, x_label='Time (s)', y_label='Voltage (V)', traces=traces,
                  mixed_signal=dict(version=1, config_hash=digest(c), samples=samples,
                                    environment=job['environment'], artifacts={}),
                  warnings=['Educational clock-boundary coupling; asynchronous crossings, metastability, transistor noise and physical signoff are outside this run.'], log='Completed every analog/digital sampling edge.')
    if c.get('verification', {}).get('kind') == 'sar4':
        from .sar_example import conversion_report
        stimulus = c.get('stimuli', {}).get('vin', [])
        expected = None
        if len(stimulus) == 1:
            expected = max(0, min(15, math.floor(16*scalar(stimulus[0][1])/scalar(c['verification']['reference']))))
        result['mixed_signal']['verification'] = conversion_report(result, expected)
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name not in ('input.json', 'result.json', 'status.json', 'run.json', 'output.log'):
            result['mixed_signal']['artifacts'][path.relative_to(root).as_posix()] = file_digest(path)
    progress(1, 'Mixed-signal conversion completed'); return result


def validate_result(result, job, directory):
    c = job['project']['mixed_signal']; data = result.get('mixed_signal', {})
    if (result.get('settings') != job['settings'] or data.get('config_hash') != digest(c)
            or data.get('environment') != job.get('environment') or len(data.get('samples', [])) != c['cycles']):
        raise ValueError('Mixed-signal result does not match captured inputs.')
    root = Path(directory).resolve()
    files = data.get('artifacts', {})
    if not {'bridge/bridge.vcd', 'bridge-samples.json', 'final/result.raw', 'waveforms.json'} <= files.keys():
        raise ValueError('Mixed-signal result is missing required evidence.')
    for name, expected in files.items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path) != expected:
            raise ValueError('Mixed-signal artifact changed or is missing: '+name)
    if (json.loads((root/'bridge-samples.json').read_text()) != data['samples'] or
            json.loads((root/'waveforms.json').read_text()) != dict(x=result.get('x'), traces=result.get('traces'))):
        raise ValueError('Mixed-signal result differs from its captured waveforms or samples.')
