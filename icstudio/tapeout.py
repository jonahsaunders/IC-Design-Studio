"""Reproducible Tiny Tapeout source handoffs for the Studio UART fixture."""

import hashlib
import io
import json
import re
import zipfile
import zlib
from pathlib import Path

from . import digital, digital_design
from .model import atomic_write

PROFILE_NAME = 'Tiny Tapeout SKY 26e'
DEFAULT_TOP = 'tt_um_icstudio_uart'
DEFAULT_DESCRIPTION = 'An eight-bit UART transmitter with a send strobe and busy output.'
SUPPORT = '9d13ff3e3e6202090740110438c6a10c1d62ca0f'
ACTION = '395eedb3eeec3c2f4961c3b04ff2cf87f5525636'
LIBRELANE = '3.0.14'
HARDENING_PDK = '8afc8346a57fe1ab7934ba5a6056ea8b43078e71'
PRECHECK_PDK = '0536d02d875c8f67dd7cca3902ac457e62f20005'
CLOCK_NS = 10
MANIFEST = 'studio/manifest.json'

_PROFILE = {
    'shuttle': PROFILE_NAME, 'pdk': 'sky130A', 'library': 'sky130_fd_sc_hd',
    'tiles': '1x1', 'clock_period_ns': CLOCK_NS, 'io_delay_ns': 1,
    'support_commit': SUPPORT, 'gds_action_commit': ACTION, 'librelane_version': LIBRELANE,
    'hardening_pdk_commit': HARDENING_PDK, 'precheck_pdk_commit': PRECHECK_PDK,
}
_SDC = (
    'create_clock -name core_clk -period 10 [get_ports clk]',
    'set_input_delay 1 -clock core_clk [get_ports {reset send data*}]',
    'set_output_delay 1 -clock core_clk [get_ports {tx busy}]',
)
_PORTS = {
    'ui': [f'data[{bit}]' for bit in range(8)],
    'uo': ['tx', 'busy'] + [''] * 6,
    'uio': ['send'] + [''] * 7,
}
_SOURCE_NAME = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*\.(?:v|sv)')
_TOP_NAME = re.compile(r'tt_um_[a-z0-9_]{1,44}')
_MEMBER_NAME = re.compile(r'(?:[a-zA-Z0-9_.-]+/)*[a-zA-Z0-9_.-]+')
_WINDOWS_DEVICE = re.compile(r'(?:aux|con|nul|prn|com[1-9]|lpt[1-9])(?:\..*)?', re.IGNORECASE)
_MAX_PACKAGE_BYTES = digital.MAX_SOURCE_BYTES + 128 * 1024
_REQUIRED_MEMBERS = {
    MANIFEST, 'info.yaml', 'src/tt_wrapper.v', 'src/config.json', '.github/workflows/gds.yaml',
    'test/Makefile', 'test/tb.v', 'docs/info.md', 'studio/constraints.sdc',
}


def uart_inputs(project, cell_id=None):
    """Limit export to the explicit UART contract this profile can translate."""
    cell_id = cell_id or project.get('digital_cell', project['top'])
    try:
        config = digital_design.config(project, cell_id)
    except StopIteration as exc:
        raise ValueError('Choose a digital cell in this project.') from exc
    if not config or config['top'] != 'uart_tx':
        raise ValueError('Open the UART regression example or choose its uart_tx RTL cell.')
    digital.validate_config(config)
    if config.get('platform', {}).get('name', 'sky130hd') != 'sky130hd':
        raise ValueError('Select the SKY130 HD platform for the UART cell.')
    rtl = [entry for entry in config['files'] if entry['role'] == 'rtl']
    if config.get('defines') or any(entry['role'] in ('include', 'data') for entry in config['files']):
        raise ValueError('This UART handoff requires self-contained RTL without includes, data files, or external defines.')
    for entry in rtl:
        name = entry['path']
        if not _SOURCE_NAME.fullmatch(name) or _WINDOWS_DEVICE.fullmatch(name) or name.casefold() == 'tt_wrapper.v':
            raise ValueError('Use flat Verilog or SystemVerilog filenames with letters, numbers, dots, hyphens, or underscores.')
    # Dependency checking applies to the transmitted RTL. Studio's own
    # testbenches keep their original run setup and are outside this export.
    digital.check_dependencies({**config, 'files': rtl})
    constraints = [entry['text'] for entry in config['files'] if entry['role'] == 'constraint']
    if len(constraints) == 1:
        commands = tuple(' '.join(line.split()) for line in constraints[0].splitlines() if line.strip())
        if commands == _SDC:
            return cell_id, config, rtl, constraints[0]
    raise ValueError('Restore the UART example’s 10 ns clock and 1 ns input/output delays before exporting.')


def _json(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _metadata(title, author, description, top):
    fields = tuple(value.strip() for value in (title, author, description, top))
    for name, value, limit in zip(('title', 'author', 'description'), fields, (80, 80, 160)):
        if not value or len(value) > limit or any(ord(char) < 32 for char in value):
            raise ValueError(f'Enter a {name} of 1–{limit} characters on one line.')
    if not _TOP_NAME.fullmatch(fields[3]):
        raise ValueError('Use a top module starting with tt_um_ followed by 1–44 lowercase letters, numbers, or underscores.')
    return fields


def prepare(project, *, title, author, description=DEFAULT_DESCRIPTION, top=DEFAULT_TOP, cell_id=None):
    """Build a deterministic ZIP from the current project snapshot."""
    title, author, description, top = _metadata(title, author, description, top)
    cell_id, config, rtl, sdc = uart_inputs(project, cell_id)
    sources = ['tt_wrapper.v', *(entry['path'] for entry in rtl)]
    info = {'yaml_version': 6, 'project': {
        'title': title, 'author': author, 'description': description,
        'language': 'SystemVerilog' if any(name.endswith('.sv') for name in sources) else 'Verilog',
        'clock_hz': 1_000_000_000 // CLOCK_NS, 'tiles': '1x1',
        'top_module': top, 'source_files': sources,
    }, 'pinout': {f'{kind}[{bit}]': name for kind, bus in _PORTS.items() for bit, name in enumerate(bus)}}
    files = {f"src/{entry['path']}": entry['text'].encode('utf-8') for entry in rtl}
    files.update({
        'info.yaml': _json(info),  # JSON strings preserve arbitrary metadata in YAML.
        'src/tt_wrapper.v': _WRAPPER.replace('@TOP@', top).encode('ascii'),
        'src/config.json': _json({
            'CLOCK_PERIOD': CLOCK_NS, 'CLOCK_PORT': 'clk', 'IO_DELAY_CONSTRAINT': 10,
            'PL_TARGET_DENSITY_PCT': 60, 'RUN_LINTER': True, 'LINTER_INCLUDE_PDK_MODELS': True,
            'RUN_KLAYOUT_DRC': False, 'RUN_KLAYOUT_XOR': False,
            'DESIGN_REPAIR_BUFFER_OUTPUT_PORTS': False, 'FP_SIZING': 'absolute',
            'TOP_MARGIN_MULT': 1, 'BOTTOM_MARGIN_MULT': 1, 'LEFT_MARGIN_MULT': 6,
            'RIGHT_MARGIN_MULT': 6, 'GRT_ALLOW_CONGESTION': True, 'FP_IO_HLENGTH': 2,
            'FP_IO_VLENGTH': 2, 'FP_PDN_VPITCH': 38.87, 'RUN_CTS': True,
            'FP_PDN_MULTILAYER': False, 'MAGIC_DEF_LABELS': False, 'MAGIC_WRITE_LEF_PINONLY': True,
            'PL_RESIZER_HOLD_SLACK_MARGIN': 0.1, 'GRT_RESIZER_HOLD_SLACK_MARGIN': 0.05,
        }),
        '.github/workflows/gds.yaml': _WORKFLOW.encode('ascii'),
        '.gitignore': _IGNORE.encode('ascii'),
        'test/tb.v': _TESTBENCH.replace('@TOP@', top).encode('ascii'),
        'test/Makefile': _MAKEFILE.replace('@RTL@', ' '.join(f'../src/{name}' for name in sources)).encode('ascii'),
        'test/requirements.txt': b'# This simulation uses Icarus Verilog and make.\n',
        'docs/info.md': _DESIGN_NOTES.encode('ascii'),
        'README.md': _README.encode('ascii'),
        'studio/constraints.sdc': sdc.encode('utf-8'),
    })
    files[MANIFEST] = _json({
        'schema': 1,
        'kind': 'tiny-tapeout-source',
        'profile': _PROFILE,
        'project': {'id': project['id'], 'cell': cell_id, 'rtl_config_sha256': digital.source_hash(config)},
        'status': {'hardening': 'not_run', 'gate_level_test': 'not_run', 'stream_precheck': 'not_run',
                   'shuttle_acceptance': 'not_run'},
        'sha256': {name: _sha(data) for name, data in files.items()},
    })
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return output.getvalue()


def write_package(path, package):
    path = Path(path)
    if path.suffix.lower() != '.zip':
        raise ValueError('Choose a destination ending in .zip.')
    atomic_write(path, package)
    return path


def verify_package(path):
    """Check the Studio source archive for missing files and accidental changes."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if (len(names) != len(entries) or len(names) > digital.MAX_FILES + 12 or not _REQUIRED_MEMBERS <= names
                    or sum(entry.file_size for entry in entries) > _MAX_PACKAGE_BYTES):
                raise ValueError('The source ZIP has an invalid file inventory.')
            for name in names:
                if not _MEMBER_NAME.fullmatch(name) or any(part in ('.', '..') for part in name.split('/')):
                    raise ValueError(f'The source ZIP has an invalid path {name!r}.')
            manifest = json.loads(archive.read(MANIFEST))
            if (not isinstance(manifest, dict) or manifest.get('schema') != 1
                    or manifest.get('kind') != 'tiny-tapeout-source' or manifest.get('profile') != _PROFILE
                    or not isinstance(manifest.get('sha256'), dict)):
                raise ValueError('Choose a Studio Tiny Tapeout SKY 26e source ZIP.')
            digests = manifest['sha256']
            if set(digests) != names - {MANIFEST}:
                raise ValueError('The source ZIP files do not match the manifest.')
            for name, expected in digests.items():
                if _sha(archive.read(name)) != expected:
                    raise ValueError(f'The source ZIP checksum differs for {name}.')
            return manifest
    except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, UnicodeError) as exc:
        raise ValueError('The source ZIP cannot be read. Export a fresh package.') from exc


_WRAPPER = """`default_nettype none
module @TOP@(
    input wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input wire ena,
    input wire clk,
    input wire rst_n
);
    assign uio_out = 8'b0;
    assign uio_oe = 8'b0;
    assign uo_out[7:2] = 6'b0;
    uart_tx uart(
        .clk(clk), .reset(!rst_n || !ena), .send(uio_in[0]), .data(ui_in),
        .tx(uo_out[0]), .busy(uo_out[1])
    );
    wire unused = &{uio_in[7:1], 1'b0};
endmodule
`default_nettype wire
"""

_TESTBENCH = """`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg ena = 1;
    reg rst_n = 0;
    reg [7:0] ui_in = 0;
    reg [7:0] uio_in = 0;
    wire [7:0] uo_out, uio_out, uio_oe;
    @TOP@ dut(
        `ifdef GL_TEST
        .VPWR(1'b1), .VGND(1'b0),
        `endif
        .clk(clk), .ena(ena), .rst_n(rst_n), .ui_in(ui_in), .uio_in(uio_in),
        .uo_out(uo_out), .uio_out(uio_out), .uio_oe(uio_oe)
    );
    always #5 clk = ~clk;

    task expect_idle;
        if ({uo_out, uio_out, uio_oe} !== 24'h010000)
            $fatal(1, "Expected idle UART and undriven bidirectional pins");
    endtask

    task send_frame(input [7:0] value);
        reg [9:0] expected;
        integer bit_index, cycle;
        begin
            expected = {1'b1, value, 1'b0};
            @(negedge clk);
            ui_in = value;
            uio_in = 8'hff;
            @(negedge clk);
            uio_in = 8'hfe;
            for (bit_index = 0; bit_index < 10; bit_index = bit_index + 1)
                for (cycle = 0; cycle < 4; cycle = cycle + 1) begin
                    if (uo_out !== {6'b0, 1'b1, expected[bit_index]}
                        || {uio_out, uio_oe} !== 16'b0)
                        $fatal(1, "UART byte %02x bit %0d cycle %0d did not match", value, bit_index, cycle);
                    @(negedge clk);
                end
            expect_idle();
        end
    endtask

    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, tb);
        repeat (3) @(negedge clk);
        expect_idle();
        rst_n = 1;
        send_frame(8'h00);
        send_frame(8'ha5);
        send_frame(8'hff);
        uio_in = 1;
        @(negedge clk);
        if (uo_out[1:0] !== 2'b10) $fatal(1, "UART did not start before the enable test");
        ena = 0;
        repeat (3) @(negedge clk);
        expect_idle();
        $display("UART shuttle pin, frame, reset, and enable checks passed");
        $finish;
    end

    initial begin
        #10000;
        $fatal(1, "UART test timed out");
    end
endmodule
"""

_MAKEFILE = """SOURCES = @RTL@
ifeq ($(GATES),yes)
HD_VERILOG = $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog
SOURCES = gate_level_netlist.v $(HD_VERILOG)/primitives.v $(HD_VERILOG)/sky130_fd_sc_hd.v
SIM_FLAGS = -DGL_TEST -DFUNCTIONAL -DUSE_POWER_PINS -DSIM -DUNIT_DELAY=\\#1
endif

.PHONY: all clean
all:
	rm -f results.xml
	if iverilog -g2012 -s tb $(SIM_FLAGS) -o uart_sim tb.v $(SOURCES) && vvp uart_sim; then \\
	    printf '%s\\n' '<testsuite name="UART shuttle pins" tests="1" failures="0"><testcase name="frames_reset_enable"/></testsuite>' > results.xml; \\
	else \\
	    printf '%s\\n' '<testsuite name="UART shuttle pins" tests="1" failures="1"><testcase name="frames_reset_enable"><failure message="See the simulator log"/></testcase></testsuite>' > results.xml; \\
	    exit 1; \\
	fi

clean:
	rm -f uart_sim tb.vcd results.xml
"""

_WORKFLOW = f"""name: Tiny Tapeout SKY 26e
on: workflow_dispatch
permissions:
  contents: read
jobs:
  harden:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803
      - uses: TinyTapeout/tt-gds-action@{ACTION}
        with:
          pdk: sky130A
          tools-ref: {SUPPORT}
          librelane-version: '{LIBRELANE}'
  precheck:
    needs: harden
    runs-on: ubuntu-24.04
    steps:
      - uses: TinyTapeout/tt-gds-action/precheck@{ACTION}
        with:
          pdk: sky130A
          tools-ref: {SUPPORT}
  gate-level-test:
    needs: harden
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803
      - uses: TinyTapeout/tt-gds-action/gl_test@{ACTION}
"""

_IGNORE = """tt/
runs/
src/user_config.json
src/config_merged.json
test/gate_level_netlist.v
test/results.xml
test/uart_sim
test/tb.vcd
"""

_DESIGN_NOTES = """## How it works

The UART sends one start bit, eight data bits least-significant bit first,
and one stop bit. Each serial bit lasts four rising edges of clk. The
100 MHz clock is a design target pending physical timing verification.

## How to test

With ena high, hold rst_n low across at least one rising edge. Release rst_n,
set ui_in to the byte, and pulse uio_in[0] for one clock while busy is low.
Watch uo_out[0] for the serial frame and uo_out[1] for busy.
Run `make -C test` with Icarus Verilog to check the source and pin mapping.

## External hardware

An external UART receiver or logic analyzer can observe TX. Use a shared
ground and the voltage levels of the shuttle carrier board.
"""

_README = """# Tiny Tapeout SKY 26e UART source

Run `make -C test` with Icarus Verilog for source simulation.
Place the extracted contents at the root of a GitHub repository, including
the hidden workflow directory, and preserve the source license. Run the
**Tiny Tapeout SKY 26e** workflow in Actions to generate the physical
artifacts, run the shuttle precheck, and test the mapped netlist.
Review the resulting reports before sending the required artifacts through
the documented Tiny Tapeout submission process.

The original Studio timing constraints and source package checksums are in
`studio/`. This ZIP contains sources. Physical hardening, stream precheck,
gate-level simulation, and shuttle acceptance are pending at export time.

[Tiny Tapeout specifications](https://tinytapeout.com/specs/)
"""
