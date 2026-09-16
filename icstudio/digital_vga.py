"""VGA Playground source exchange and a read-only, loopback asset server."""
from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import digital

UPSTREAM = 'https://github.com/TinyTapeout/vga-playground'
REVISION = '3e3c77e46ae7bd51609f680851aabb81a30564a6'


def assets():
    bundled = Path(__file__).parent / 'assets' / 'vga-playground'
    return bundled if (bundled / 'index.html').is_file() else Path(__file__).resolve().parents[1] / 'build/vga-playground/dist'


def preview_inputs(config):
    """Capture the working copy without including testbenches or constraints."""
    digital.validate_config(config)
    digital.check_dependencies(config)
    return {
        'topModule': config['top'],
        'sources': {f['path']: f['text'] for f in config['files'] if f['role'] in ('rtl', 'include')},
        'dataFiles': {f['path']: f['text'] for f in config['files'] if f['role'] == 'data'},
        'includeDirs': config.get('include_dirs', ['.']),
        'defines': config.get('defines', {}),
    }


def preset_config(preset):
    """Make a project-owned preset, including attribution and a bounded testbench."""
    top = preset['topModule']
    if not isinstance(top, str) or not digital.IDENT.fullmatch(top):
        raise ValueError('The VGA preset has an invalid top module.')
    files = [{'path': path, 'text': text, 'role': 'include' if path.endswith(('.vh', '.svh')) else 'rtl'}
             for path, text in preset['sources'].items()]
    files += [{'path': path, 'text': text, 'role': 'data'} for path, text in preset.get('dataFiles', {}).items()]
    files += [{'path': path, 'text': text, 'role': 'data'} for path, text in preset['licenses'].items()]
    files.append({'path': 'VGA-ORIGIN.txt', 'role': 'data', 'text':
                  f"{preset['name']} by {preset['author']}\n{UPSTREAM}\nRevision: {REVISION}\n"})
    files.append({'path': 'tb_vga.sv', 'role': 'testbench', 'text': f'''// IC Design Studio VGA smoke test. Two 800 x 525 pixel frames.
`timescale 1ns/1ps
module tb_vga;
  reg clk = 0;
  reg rst_n = 0;
  reg [7:0] ui_in = 0;
  wire [7:0] uo_out, uio_out, uio_oe;
  {top} dut (.clk(clk), .rst_n(rst_n), .ena(1'b1),
    .ui_in(ui_in), .uo_out(uo_out), .uio_in(8'b0),
    .uio_out(uio_out), .uio_oe(uio_oe));
  always #19.861 clk = ~clk;
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(1, tb_vga);
    repeat (10) @(negedge clk);
    rst_n = 1;
    repeat (840000) @(negedge clk);
    $finish;
  end
endmodule
'''})
    value = {'version': 1, 'top': top, 'testbench': 'tb_vga', 'files': files,
             'include_dirs': ['.'], 'defines': {}, 'waveform': 'wave.vcd', 'timeout': 120}
    digital.validate_config(value)
    digital.check_dependencies(value)
    return value


class _AssetHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.wasm': 'application/wasm', '.js': 'text/javascript'}

    def do_GET(self):
        # Serve only built assets, never project sources or arbitrary local files.
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            self.send_error(403); return
        root = Path(self.directory).resolve()
        path = root / unquote(urlsplit(self.path).path).lstrip('/')
        if not path.resolve().is_relative_to(root) or path.is_dir() and path != root:
            self.send_error(404); return
        super().do_GET()

    def do_HEAD(self):
        self.send_error(405)

    def list_directory(self, path):
        self.send_error(404)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "worker-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
        super().end_headers()

    def log_message(self, *args):
        pass


class AssetServer:
    def __init__(self, directory=None):
        root = Path(directory or assets()).resolve()
        if not (root / 'index.html').is_file():
            raise ValueError('VGA Playground assets are missing. See docs/VGA_PLAYGROUND.md for source setup.')
        manifest = json.loads((root / 'icstudio-build.json').read_text(encoding='utf-8'))
        if manifest.get('revision') != REVISION:
            raise ValueError('Rebuild VGA Playground assets for this Studio revision.')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(_AssetHandler, directory=str(root)))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/'

    def close(self):
        if self.thread.is_alive():
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=1)
