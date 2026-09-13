"""Captured digital jobs using Studio's external-process protocol."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from . import digital
from .engines import execute
from .model import atomic_write, clone, design_digest, digest, file_digest, now, validate

STAGES = ('simulate', 'lint', 'synth')


def tool_names(stage, simulator):
    if stage == 'synth': return ('yosys',)
    if stage == 'lint' or simulator == 'verilator': return ('verilator',)
    return ('iverilog', 'vvp')


def environment(job):
    from .build_info import WORKFLOW_SOURCE_HASH
    sources = {}
    if not getattr(sys, 'frozen', False):
        for name in ('digital.py', 'digital_flow.py', 'digital_waveform.py', 'engines.py'):
            sources[name] = file_digest(Path(__file__).with_name(name))
    return {'workflow_hash': WORKFLOW_SOURCE_HASH, 'engine': 'digital', 'sources': sources,
            'executables': {name: file_digest(path) for name, path in job['settings']['tools'].items()}}


def prepare(project, stage='simulate', simulator='icarus', tools=None):
    project = clone(validate(project))
    if stage not in STAGES or simulator not in ('icarus', 'verilator'):
        raise ValueError('Choose a supported digital stage and simulator.')
    config = project.get('digital')
    digital.check_dependencies(config)
    if stage == 'simulate' and (not config.get('testbench') or not any(f['role'] == 'testbench' for f in config['files'])):
        raise ValueError('Set a testbench top and mark its source as Testbench.')
    resolved = {}
    for name in tool_names(stage, simulator):
        value = (tools or {}).get(name) or shutil.which(name)
        path = Path(shutil.which(str(value)) or str(value)).resolve() if value else None
        if path is None or not path.is_file():
            raise ValueError(name+' is not installed. Set its executable in Digital flow → Tools.')
        resolved[name] = str(path)
    job = {'project': project, 'cell': project['top'], 'engine': 'digital',
           'settings': {'type': 'digital', 'stage': stage, 'simulator': simulator, 'tools': resolved}}
    job['environment'] = environment(job)
    return job


def stage_sources(config, root):
    digital.check_dependencies(config)
    root = Path(root)
    for item in config['files']:
        target = root / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, item['text'])


def include_dirs(config):
    # Both supported simulators search these explicit paths. Include each
    # source's directory to match the dependency closure checked on import.
    return list(dict.fromkeys(config.get('include_dirs', ['.']) +
                             [str(Path(f['path']).parent) for f in config['files']]))


def compiler_args(config, simulation=False):
    args = ['-I'+path for path in include_dirs(config)]
    args += ['-D'+name+('='+value if value else '') for name, value in config.get('defines', {}).items()]
    args += ['./'+f['path'] for f in config['files']
             if f['role'] == 'rtl' or simulation and f['role'] == 'testbench']
    return args


def yosys_script(config):
    quote = lambda s: '"'+s.replace('\\', '\\\\').replace('"', '\\"')+'"'
    flags = ['-I'+quote(path) for path in include_dirs(config)]
    flags += ['-D'+quote(name+('='+value if value else '')) for name, value in config.get('defines', {}).items()]
    files = [quote('./'+f['path']) for f in config['files'] if f['role'] == 'rtl']
    return '\n'.join([
        'read_verilog -sv '+' '.join(flags+files),
        'hierarchy -check -top '+config['top'],
        'synth -top '+config['top'], 'check -assert',
        'write_verilog -noattr ../netlist.v', 'write_json ../netlist.json',
        'tee -o ../statistics.json stat -json', ''])


def artifact(root, path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('The digital tool did not produce '+path.name+'. Inspect its log.')
    return {'path': path.relative_to(root).as_posix(), 'sha256': file_digest(path), 'bytes': path.stat().st_size}


def validate_result(result, directory):
    data = result.get('digital_result')
    if (result.get('result_type') != 'digital' or not isinstance(data, dict)
            or data.get('stage') not in STAGES or not isinstance(data.get('artifacts'), dict)
            or not isinstance(data.get('summary'), str)):
        raise ValueError('Invalid digital result structure.')
    required = {'log'} | {'simulate': {'vcd','waveform'}, 'synth': {'netlist','hierarchy','statistics'}, 'lint': set()}[data['stage']]
    if not required.issubset(data['artifacts']) or data['stage'] != result.get('settings',{}).get('stage'):
        raise ValueError('Digital result is missing the required artifacts or has a mismatched stage.')
    root = Path(directory).resolve()
    for record in data['artifacts'].values():
        if not isinstance(record, dict): raise ValueError('Invalid digital artifact record.')
        relative = digital.relative_path(record.get('path'))
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path) != record.get('sha256'):
            raise ValueError('A captured digital artifact is missing or changed: '+relative)


def run(job, directory, progress=lambda *_: None):
    config = job['project']['digital']; settings = job['settings']; stage = settings['stage']
    if stage not in STAGES:
        raise ValueError('Unsupported digital stage.')
    if environment(job) != job.get('environment'):
        raise ValueError('The digital toolchain changed since this job was prepared. Start a new run.')
    root = Path(directory).resolve()
    if stage == 'simulate' and settings['simulator'] == 'verilator' and (
            any(c.isspace() for c in str(root)) or any(' ' in f['path'] for f in config['files'])):
        raise ValueError('Verilator simulation builds require run and source paths without spaces. '
                         'Choose Icarus, or use the CLI with an output path without spaces.')
    root.mkdir(parents=True, exist_ok=True)
    source = root / 'sources'; source.mkdir(exist_ok=False)
    temporary = root / 'tmp'; temporary.mkdir()
    process_env = {**os.environ, **{key: str(temporary) for key in ('TMPDIR', 'TMP', 'TEMP')}}
    stage_sources(config, source)
    atomic_write(root/'inputs.json', json.dumps(digital.input_manifest(config), indent=2))
    commands = []; versions = {}; artifacts = {}; log = root/'engine.log'
    def command(args, fraction, message, cwd=source):
        commands.append({'argv': [str(a) for a in args], 'cwd': str(Path(cwd).relative_to(root))})
        atomic_write(root/'commands.json', json.dumps(commands, indent=2))
        progress(fraction, message)
        with log.open('a', encoding='utf-8') as output:
            def line(text):
                output.write(text+'\n'); output.flush()
                progress(fraction, text[:1000])
            return execute(args, cwd, timeout=config.get('timeout', 60), on_line=line, env=process_env)
    for name, path in settings['tools'].items():
        versions[name] = command([path, '--version' if name == 'verilator' else '-V'], .02, 'Checking '+name).strip()
    tools = settings['tools']
    if stage == 'synth':
        script = root/'synth.ys'; atomic_write(script, yosys_script(config))
        command([tools['yosys'], '-s', str(script)], .3, 'Synthesizing '+config['top'])
        for key, name in [('netlist', 'netlist.v'), ('hierarchy', 'netlist.json'), ('statistics', 'statistics.json')]:
            artifacts[key] = artifact(root, root/name)
        stats = json.loads((root/'statistics.json').read_text())
        modules = stats.get('modules', {})
        cells = sum(m.get('num_cells', 0) for m in modules.values())
        summary = f'Synthesis complete · {cells} generic cells · no technology mapping or timing qualification'
    elif stage == 'lint':
        command([tools['verilator'], '--lint-only', '--top-module', config['top'], '-Wall'] + compiler_args(config), .3, 'Linting '+config['top'])
        summary = 'Lint completed without fatal diagnostics'
    else:
        if settings['simulator'] == 'icarus':
            program = root/'simulation.vvp'
            command([tools['iverilog'], '-g2012', '-s', config['testbench'], '-o', str(program)] + compiler_args(config, True), .2, 'Compiling testbench')
            command([tools['vvp'], '-n', str(program)], .6, 'Running testbench')
        else:
            objdir = root/'obj_dir'
            command([tools['verilator'], '--binary', '--timing', '--trace', '--assert',
                     '--top-module', config['testbench'], '--Mdir', '../obj_dir', '-o', 'simulation'] + compiler_args(config, True), .2, 'Building testbench')
            command([str(objdir/'simulation')], .6, 'Running testbench')
        wave = source / config.get('waveform', 'wave.vcd')
        artifacts['vcd'] = artifact(root, wave)
        from .digital_waveform import read_vcd
        waveform = read_vcd(wave)
        atomic_write(root/'waveform.json', json.dumps(waveform, separators=(',', ':')))
        artifacts['waveform'] = artifact(root, root/'waveform.json')
        summary = f"Simulation complete · {len(waveform['signals'])} signals · {waveform['event_count']} transitions"
        stats = {'signals': len(waveform['signals']), 'events': waveform['event_count'], 'timescale': waveform['timescale']}
    artifacts['log'] = artifact(root, log)
    project = job['project']
    result = {'schema': 1, 'result_type': 'digital', 'created': now(), 'engine': 'digital',
              'project_id': project['id'], 'cell_id': job['cell'], 'revision': project['revision'],
              'design_hash': design_digest(project), 'settings': clone(settings),
              'digital_result': {'stage': stage, 'source_hash': digital.source_hash(config),
                                 'summary': summary, 'versions': versions, 'environment': job['environment'],
                                 'artifacts': artifacts, 'statistics': stats if stage != 'lint' else {}}}
    validate_result(result, root)
    progress(1, summary)
    return result


def export_flow(config, directory):
    """Export runnable Yosys/EQY inputs and a SKY130 ORFS starting config.

    This is an explicit handoff; it does not claim equivalence or physical
    qualification. ORFS performs its own technology-mapped synthesis.
    """
    digital.check_dependencies(config)
    root = Path(directory).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError('Choose an empty folder for the digital flow bundle.')
    if any(c.isspace() for c in str(root)) or any(' ' in f['path'] for f in config['files']):
        raise ValueError('The initial ORFS Makefile handoff requires folder and source paths without spaces.')
    constraints = [f for f in config['files'] if f['role'] == 'constraint']
    if len(constraints) != 1:
        raise ValueError('Mark exactly one SDC file as Constraint before exporting the physical flow.')
    if '$' in config['top'] or any('$' in k or ' ' in v or '$' in v for k,v in config.get('defines', {}).items()):
        raise ValueError('Use simple identifiers and unspaced definitions for the initial ORFS handoff.')
    stage_sources(config, root/'sources')
    atomic_write(root/'synth.ys', yosys_script(config))
    gold = yosys_script(config).split('hierarchy -check')[0]
    eqy = ('[gold]\n'+gold+'prep -top '+config['top']+'\n\n[gate]\n'
           'read_verilog ../netlist.v\nprep -top '+config['top']+'\n\n'
           '[strategy simple]\nuse sat\ndepth 20\n')
    atomic_write(root/'equivalence.eqy', eqy)
    lines = ['# Generated starting configuration; qualify with a pinned ORFS/platform revision.',
             'ICSTUDIO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))',
             'export DESIGN_NAME = '+config['top'], 'export PLATFORM = sky130hd',
             'export VERILOG_FILES = '+' '.join('$(ICSTUDIO_ROOT)/sources/'+f['path'] for f in config['files'] if f['role'] == 'rtl'),
             'export VERILOG_INCLUDE_DIRS = '+' '.join('$(ICSTUDIO_ROOT)/sources/'+d for d in include_dirs(config)),
             'export VERILOG_DEFINES = '+' '.join(k+('='+v if v else '') for k,v in config.get('defines', {}).items()),
             'export SDC_FILE = $(ICSTUDIO_ROOT)/sources/'+constraints[0]['path'],
             'export CORE_UTILIZATION = 30', 'export CORE_ASPECT_RATIO = 1', 'export CORE_MARGIN = 2', '']
    atomic_write(root/'config.mk', '\n'.join(lines))
    atomic_write(root/'manifest.json', json.dumps({'version': 1, 'source_hash': digital.source_hash(config),
                 'inputs': digital.input_manifest(config), 'physical_status': 'not_run'}, indent=2))
    atomic_write(root/'README.txt', '''Digital flow handoff

From the sources directory:
  yosys -s ../synth.ys
  eqy -f ../equivalence.eqy

The EQY check compares RTL with the generic netlist produced above. It does
not check the separate technology-mapped ORFS netlist. Inspect EQY's status;
unproved/timeout is not a pass. The SAT strategy has a depth budget of 20.

With a separately installed, pinned OpenROAD Flow Scripts checkout/platform:
  make -C /path/to/OpenROAD-flow-scripts/flow DESIGN_CONFIG=/absolute/path/to/config.mk

Review SDC, floorplan and platform settings for your design before running.
The supplied SKY130 configuration is a starting point. No physical run,
DRC/LVS, timing closure, or fabrication qualification is claimed by export.
For memory initialization, configure ORFS's captured working inputs explicitly.
See docs/DIGITAL_FLOW.md in IC Design Studio for supported scope and next steps.
''')
    return root
