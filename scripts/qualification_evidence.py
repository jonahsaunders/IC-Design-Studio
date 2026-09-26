"""Shared, fail-closed evidence for executed compatibility qualifications."""
from __future__ import annotations

from collections import Counter
from importlib import import_module
import json
import platform
from pathlib import Path
import re
import shutil
import subprocess
import time

from icstudio.engines import execute, netgen_lvs, require_lvs_match, tcl_word
from icstudio.model import atomic_write, file_digest

ROOT = Path(__file__).resolve().parents[1]


class Blocked(RuntimeError):
    """A prerequisite is unavailable; no verification result can be claimed."""


def require_tool(value, name):
    candidate = shutil.which(str(value or name)) or value
    if not candidate or not Path(candidate).is_file():
        raise Blocked('Missing executable: ' + name)
    return str(Path(candidate).resolve())


def command(arguments, directory, name='engine', timeout=900, env=None):
    """Preserve the command and diagnostic on success, timeout and nonzero exit."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    arguments = list(map(str, arguments))
    atomic_write(directory / (name + '.command.json'), json.dumps(arguments, indent=2))
    try:
        log = execute(arguments, directory, timeout=timeout, env=env)
    except Exception as exc:
        atomic_write(directory / (name + '.log'), str(exc))
        raise
    atomic_write(directory / (name + '.log'), log)
    return log


class Report:
    def __init__(self, output, suite):
        self.output = Path(output).resolve()
        if self.output.exists() and any(self.output.iterdir()):
            raise ValueError('Choose a new, empty qualification output directory.')
        self.output.mkdir(parents=True, exist_ok=True)
        commit = subprocess.check_output(
            ['git', '-c', 'safe.directory=' + str(ROOT), 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(
            ['git', '-c', 'safe.directory=' + str(ROOT), 'status', '--porcelain'], cwd=ROOT, text=True).strip())
        self.data = dict(schema=1, suite=suite, commit=commit, dirty=dirty,
                         platform=platform.platform(), status='running', cases=[], tools={},
                         source_hashes={p.relative_to(ROOT).as_posix(): file_digest(p)
                                        for base in ('icstudio', 'scripts', 'tests') for p in (ROOT / base).rglob('*.py')},
                         python=platform.python_version(),
                         dependencies={name:import_module(name).__version__ for name in ('klayout','PySide6')},
                         lock_hashes={name:file_digest(ROOT/name) for name in (
                             'examples/physical-engine-lock.json','examples/sky130-reference-assets.json',
                             'examples/open-projects/overvoltage-lock.json',
                             'examples/open-projects/sky130-resistor-extraction.json')},
                         signoff=False)
        self.publish()

    def publish(self):
        atomic_write(self.output / 'qualification.json', json.dumps(self.data, indent=2, allow_nan=False) + '\n')

    def case(self, name, action, required=True):
        row = dict(name=name, required=required, status='running')
        self.data['cases'].append(row)
        self.publish()
        start = time.monotonic()
        try:
            details = action()
            row.update(status='passed', details=details)
        except Blocked as exc:
            row.update(status='blocked', reason=str(exc))
        except Exception as exc:
            row.update(status='failed', reason=str(exc), exception=type(exc).__name__)
        row['elapsed_seconds'] = round(time.monotonic() - start, 3)
        self.publish()
        print(name + ': ' + row['status'], flush=True)
        return row

    def blocked(self, name, reason, required=False):
        def action():
            raise Blocked(reason)
        return self.case(name, action, required)

    def tool(self, name, executable, version_args):
        executable = require_tool(executable, name)
        log = command([executable, *version_args], self.output / 'tools', name, 30)
        self.data['tools'][name] = dict(path=executable, sha256=file_digest(executable), version=log.strip())
        self.publish()
        return executable

    def finish(self):
        required = [c for c in self.data['cases'] if c['required']]
        statuses = [c['status'] for c in required]
        self.data['status'] = ('failed' if 'failed' in statuses else
                               'blocked' if not statuses or any(s != 'passed' for s in statuses) else 'passed')
        self.data['complete_scope'] = bool(self.data['cases']) and all(
            c['status'] == 'passed' for c in self.data['cases'])
        self.data['counts'] = dict(Counter(c['status'] for c in self.data['cases']))
        self.publish()
        lines = ['# Compatibility qualification', '',
                 f"Commit: `{self.data['commit']}`; working changes: {self.data['dirty']}", '',
                 f"Required checks: **{self.data['status']}**. Complete requested scope: **{self.data['complete_scope']}**.", '',
                 '| Check | Result | Required |', '|---|---|---|']
        for case in self.data['cases']:
            lines.append(f"| {case['name']} | {case['status']} | {case['required']} |")
        for case in self.data['cases']:
            if case.get('reason'):
                lines += ['', '**' + case['name'] + '**: ' + case['reason']]
        atomic_write(self.output / 'compatibility.md', '\n'.join(lines) + '\n')
        # Do not hash a manifest into itself. Raw evidence remains independently auditable.
        files = {p.relative_to(self.output).as_posix(): file_digest(p)
                 for p in self.output.rglob('*') if p.is_file() and p.name != 'manifest.json'}
        atomic_write(self.output / 'manifest.json', json.dumps(files, indent=2) + '\n')
        return 0 if self.data['status'] == 'passed' else 1


def parse_magic_drc(log, findings):
    counts = re.findall(r'^QUAL_DRC_COUNT (\d+)\s*$', log, re.M)
    styles = re.findall(r'^QUAL_DRC_STYLE (.+)$', log, re.M)
    if counts == [] or len(counts) != 1 or styles != ['drc(full)'] or 'QUAL_MAGIC_COMPLETE' not in log:
        raise ValueError('Incomplete Magic full-DRC report.')
    if re.search(r'QUAL_MAGIC_ERROR|invalid command name|contained errors|Malformed line|Illegal keyword', log, re.I):
        raise ValueError('Magic reported an engine/technology error.')
    if not Path(findings).is_file():
        raise ValueError('Missing DRC findings report.')
    rows = []
    for line in Path(findings).read_text().splitlines():
        fields = line.split('\t')
        if len(fields) != 2 or not fields[0] or len(fields[1].split(',')) != 4:
            raise ValueError('Malformed DRC finding.')
        box = [float(v) for v in fields[1].split(',')]
        import math
        if not all(math.isfinite(v) for v in box):
            raise ValueError('Nonfinite DRC coordinates.')
        rows.append(dict(rule=fields[0], box=box))
    count = int(counts[0])
    if bool(count) != bool(rows):
        raise ValueError('DRC count and findings disagree.')
    return dict(status='passed' if count == 0 else 'failed', count=count,
                rules=dict(Counter(row['rule'] for row in rows)), findings=rows)


def stream_pin_contract(source, top, pin_layers, label_layers):
    """Read pin intent only from the stream's PDK layer purposes, never a schematic.

    Magic 8.3.600 promotes an ordinary label to a port when a label rectangle
    precedes its text in a rewritten stream. Only explicitly non-pin labels
    may be demoted. Missing, renamed and additional *pin-layer* labels remain
    untouched and must be detected by strict LVS.
    """
    import klayout.db as db
    layout=db.Layout();layout.read(str(source));cell=layout.cell(top)
    if cell is None:raise ValueError('Missing stream top for pin contract.')
    names={'pins':set(),'labels':set()}
    for key,pairs in [('pins',pin_layers),('labels',label_layers)]:
        for pair in pairs:
            index=layout.find_layer(*pair)
            if index is not None:
                names[key].update(s.text.string for s in cell.shapes(index).each() if s.is_text())
    if names['pins'] & names['labels']:
        raise ValueError('Ambiguous pin and non-pin label purpose: '+repr(names['pins'] & names['labels']))
    return {key:sorted(values) for key,values in names.items()}


def magic_verify(source, top, technology, output, executable, ports=(), *, extract=True, input_style=None,
                 pin_layers=(), label_layers=()):
    """Fresh full DRC and flat device extraction; never synthesize missing pins."""
    from icstudio.external_tools import extraction_commands
    source, technology, output = Path(source).resolve(), Path(technology).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if source.suffix == '.mag':
        native = output / 'native'
        shutil.copytree(source.parent, native)
        read = 'path search ' + tcl_word('+' + str(native)) + '\n'
    else:
        read = ''
        if input_style:
            read += 'cif istyle ' + tcl_word(input_style) + '\nputs "QUAL_INPUT_STYLE [cif list istyle]"\n'
        read += 'gds read ' + tcl_word(source) + '\n'
    body = 'drc off\n' + read + 'load ' + tcl_word(top) + '\nselect top cell\n'
    pin_contract=None
    if source.suffix != '.mag' and pin_layers:
        pin_contract=stream_pin_contract(source,top,pin_layers,label_layers)
        atomic_write(output/'stream-pin-contract.json',json.dumps(pin_contract,indent=2)+'\n')
        for name in pin_contract['labels']:
            word=tcl_word(name)
            body+='if {[port '+word+' exists]} {port '+word+' remove; puts '+tcl_word('QUAL_DEMOTED_NONPIN '+name)+'}\n'
    for index, port in enumerate(ports, 1):
        word = tcl_word(port)
        body += 'if {![port ' + word + ' exists]} {error ' + tcl_word('Missing layout port ' + port) + '}\n'
        body += 'port ' + word + ' index ' + str(index) + '\n'
    body += ('snap internal\nselect top cell\nbox values {*}[select bbox]\nbox grow c 10um\n'
             'drc style drc(full)\ndrc ignore none\ndrc euclidean on\ndrc check\ndrc catchup\n'
             'puts "QUAL_DRC_COUNT [drc list count total]"\nputs "QUAL_DRC_STYLE [drc list style]"\nputs "QUAL_MAGIC_SCALE [cif scale out]"\n'
             'set f [open findings.tsv w]\n'
             'foreach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]"}}\nclose $f\n'
             'feedback save feedback.txt\n')
    if extract:
        body += extraction_commands('lvs', {'hierarchy': False})[0] + 'ext2spice -o extracted.spice\n'
    script = 'if {[catch {\n' + body + '\nputs QUAL_MAGIC_COMPLETE\n} err]} {puts "QUAL_MAGIC_ERROR $err"}\nquit -noprompt\n'
    atomic_write(output / 'run.tcl', script)
    atomic_write(output / 'startup.tcl', 'tech load ' + tcl_word(technology) + '\n')
    log = command([executable, '-dnull', '-noconsole', '-rcfile', output / 'startup.tcl', output / 'run.tcl'], output)
    drc = parse_magic_drc(log, output / 'findings.tsv')
    scales = re.findall(r'^QUAL_MAGIC_SCALE ([0-9.eE+-]+)$', log, re.M)
    if len(scales) != 1 or not 0 < float(scales[0]) < 1000:
        raise ValueError('Missing or invalid Magic coordinate scale.')
    drc['coordinate_unit_um'] = float(scales[0])
    extracted = output / 'extracted.spice'
    if input_style and source.suffix != '.mag' and re.findall(r'^QUAL_INPUT_STYLE (.+)$', log, re.M) != [input_style]:
        raise ValueError('Magic did not select the exact requested stream input style.')
    if extract and (not extracted.is_file() or not re.search(r'(?im)^\.subckt\s+' + re.escape(top) + r'\s', extracted.read_text())):
        raise ValueError('Magic did not extract the requested top circuit.')
    feedback = (output / 'feedback.txt').read_text() if (output / 'feedback.txt').exists() else ''
    result = dict(input_sha256=file_digest(source), technology_sha256=file_digest(technology),
                  extracted_sha256=file_digest(extracted) if extract else None, input_style=input_style,
                  stream_pin_contract=pin_contract,
                  demoted_nonpin_labels=re.findall(r'^QUAL_DEMOTED_NONPIN (.+)$',log,re.M),
                  drc=drc, conversion_feedback=feedback,
                  diagnostics=[line for line in log.splitlines() if re.search(r'warning|error|mismatch|disagree', line, re.I)])
    atomic_write(output / 'physical.json', json.dumps(result, indent=2) + '\n')
    return result


def compare_lvs(executable, reference, extracted, top, setup, output, expect_match=True):
    log = netgen_lvs(executable, reference, top, extracted, top, setup, output)
    if not (Path(output) / 'lvs.log').is_file():
        raise ValueError('Missing LVS report.')
    try:
        require_lvs_match(log)
        matched = True
    except ValueError:
        if not re.search(r'Netlists do not match|Circuits do not match|Property errors|disconnected node:|\(no matching pin\)|failed pin matching', log, re.I):
            raise ValueError('LVS did not finish a recognizable comparison.')
        matched = False
    if matched != expect_match:
        raise ValueError('LVS unexpectedly ' + ('matched the defective layout.' if matched else 'rejected the layout.'))
    return dict(matched=matched, expected_match=expect_match, reference_sha256=file_digest(reference),
                extracted_sha256=file_digest(extracted), setup_sha256=file_digest(setup))
