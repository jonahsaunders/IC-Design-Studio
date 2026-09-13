"""Portable, embedded RTL inputs. No Qt or external engine dependencies.

The first digital format deliberately uses literal include/readmem paths and
an ordered file list. Imported files become project-owned snapshots: editing
their original folder does not change a saved project or queued job.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

from .model import clone, digest, example, validate

MAX_FILES = 128
MAX_SOURCE_BYTES = 16 * 1024 * 1024
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*\Z')
ROLES = ('rtl', 'testbench', 'include', 'data', 'constraint')


def relative_path(value, directory=False):
    if directory and value == '.':
        return value
    if (not isinstance(value, str) or not value or len(value) > 240
            or not re.fullmatch(r'[A-Za-z0-9_./ -]+', value)
            or value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/'))):
        raise ValueError('Use a relative digital file path without .., backslashes or special characters.')
    return value


def validate_config(config):
    if not isinstance(config, dict) or config.get('version') != 1:
        raise ValueError('Unsupported digital project format; expected version 1.')
    for key in ('top', 'testbench'):
        value = config.get(key, '')
        if not isinstance(value, str) or (value and not IDENT.fullmatch(value)):
            raise ValueError('Digital '+key+' must be a Verilog module identifier.')
    if not config.get('top'):
        raise ValueError('Choose a digital top module.')
    files = config.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError(f'A digital project needs 1–{MAX_FILES} embedded files.')
    seen = set(); total = 0
    for item in files:
        if not isinstance(item, dict):
            raise ValueError('Invalid digital file record.')
        path = relative_path(item.get('path'))
        if path.casefold() in seen or item.get('role') not in ROLES:
            raise ValueError('Digital paths must be unique and every file needs a supported role.')
        seen.add(path.casefold())
        text = item.get('text')
        if not isinstance(text, str) or '\0' in text:
            raise ValueError('Digital files must contain UTF-8 text without NUL bytes.')
        total += len(text.encode('utf-8'))
    if total > MAX_SOURCE_BYTES:
        raise ValueError('Embedded digital sources exceed the 16 MiB limit.')
    paths = {f['path'].casefold() for f in files}
    for path in paths:
        if any(str(parent) in paths for parent in PurePosixPath(path).parents):
            raise ValueError('A digital path is both a file and a directory: '+path)
    if not any(f['role'] == 'rtl' for f in files):
        raise ValueError('Mark at least one file as RTL.')
    includes = config.get('include_dirs', ['.'])
    if not isinstance(includes, list) or len(includes) > MAX_FILES:
        raise ValueError('Use a bounded list of digital include directories.')
    for path in includes:
        relative_path(path, directory=True)
    defines = config.get('defines', {})
    if not isinstance(defines, dict) or len(defines) > 100:
        raise ValueError('Use at most 100 preprocessor definitions.')
    for key, value in defines.items():
        if not isinstance(key, str) or not IDENT.fullmatch(key) or not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_' .+-]*", value) or len(value) > 200:
            raise ValueError('Use simple literal preprocessor definitions.')
    wave = relative_path(config.get('waveform', 'wave.vcd')).casefold()
    if any(wave == path or wave.startswith(path+'/') or path.startswith(wave+'/') for path in paths):
        raise ValueError('The waveform output must not overwrite an input file.')
    timeout = config.get('timeout', 60)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError('Digital timeout must be 1–3,600 seconds.')
    return config


def validate_project(project):
    if 'digital' in project:
        validate_config(project['digital'])


def source_hash(config):
    return digest(validate_config(config))


def input_manifest(config):
    return {f['path']: hashlib.sha256(f['text'].encode('utf-8')).hexdigest()
            for f in validate_config(config)['files']}


def check_dependencies(config):
    """Conservative dependency closure for the supported portable RTL subset."""
    validate_config(config)
    paths = {f['path'] for f in config['files']}
    for item in config['files']:
        if item['role'] not in ('rtl', 'testbench', 'include'):
            continue
        # Keep strings intact while removing comments, so // inside a quoted
        # string is not interpreted as a comment.
        text = re.sub(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*',
                      lambda m: m[0] if m[0].startswith('"') else ' ', item['text'], flags=re.S)
        for match in re.finditer(r'`include\s+([^\n]+)', text):
            literal = re.match(r'"([^"\n]+)"', match[1])
            if not literal:
                raise ValueError(item['path']+': use literal `include paths for captured digital runs.')
            name = relative_path(literal[1])
            candidates = [str(PurePosixPath(item['path']).parent / name)]
            candidates += [str(PurePosixPath(d) / name) for d in config.get('include_dirs', ['.'])]
            if not any(p in paths for p in candidates):
                raise ValueError(item['path']+': embed the missing include '+name+'.')
        for match in re.finditer(r'\$readmem[hb]\s*\(\s*([^,]+)', text):
            literal = re.fullmatch(r'"([^"\n]+)"\s*', match[1])
            if not literal:
                raise ValueError(item['path']+': use literal $readmem file paths for captured runs.')
            if relative_path(literal[1]) not in paths:
                raise ValueError(item['path']+': embed the memory initialization file '+literal[1]+'.')


def read_manifest(path):
    """Import an explicit disk manifest; capture sources under its directory."""
    import json
    path = Path(path).resolve()
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('Digital manifest exceeds 16 MiB.')
    config = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict) or not isinstance(config.get('files'), list) or len(config['files']) > MAX_FILES:
        raise ValueError('Choose a digital JSON manifest with an ordered files list.')
    total = 0
    for item in config['files']:
        if not isinstance(item, dict):
            raise ValueError('Invalid digital file record in manifest.')
        name = relative_path(item.get('path'))
        source = (path.parent / name).resolve()
        if not source.is_relative_to(path.parent) or not source.is_file():
            raise ValueError('Digital source is missing or outside the manifest directory: '+name)
        total += source.stat().st_size
        if total > MAX_SOURCE_BYTES:
            raise ValueError('Digital sources exceed the 16 MiB capture limit.')
        item['text'] = source.read_text(encoding='utf-8')
    validate_config(config); check_dependencies(config)
    return config


def counter_project():
    project = example('empty'); project['name'] = 'Digital counter'
    project['cells'][0]['name'] = 'counter'
    project['digital'] = {
        'version': 1, 'top': 'counter', 'testbench': 'counter_tb',
        'include_dirs': ['.'], 'defines': {}, 'waveform': 'wave.vcd', 'timeout': 60,
        'files': [
            {'path': 'counter.sv', 'role': 'rtl', 'text': '''`timescale 1ns/1ps
module counter(input wire clk, input wire reset, output reg [3:0] count);
  always @(posedge clk)
    if (reset) count <= 0;
    else count <= count + 1'b1;
endmodule
'''},
            {'path': 'counter_tb.sv', 'role': 'testbench', 'text': '''`timescale 1ns/1ps
module counter_tb;
  reg clk = 0;
  reg reset = 1;
  wire [3:0] count;
  integer expected;
  counter dut(.clk(clk), .reset(reset), .count(count));
  always #5 clk = ~clk;
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0, counter_tb);
    @(negedge clk);
    if (count !== 0) $fatal(1, "Reset failed");
    reset = 0;
    for (expected = 1; expected <= 20; expected = expected + 1) begin
      @(negedge clk);
      if (count !== expected[3:0]) $fatal(1, "Counter mismatch");
    end
    $display("Counter checks passed: reset, increment and wraparound");
    $finish;
  end
  initial begin #1000; $fatal(1, "Testbench timed out"); end
endmodule
'''},
            {'path': 'constraints.sdc', 'role': 'constraint', 'text': '''create_clock -name core_clk -period 10 [get_ports clk]
set_input_delay 1 -clock core_clk [get_ports reset]
set_output_delay 1 -clock core_clk [get_ports count*]
'''}]
    }
    return validate(project)
