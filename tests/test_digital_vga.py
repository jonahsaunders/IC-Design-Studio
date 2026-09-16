"""Source ownership, compiler inputs and the VGA asset server boundary."""
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from icstudio.digital import counter_project
from icstudio.digital_design import config, new_cell
from icstudio.digital_vga import AssetServer, REVISION, preset_config, preview_inputs
from icstudio.model import History, load_project, save_project


def preset():
    return {'id': 'test', 'name': 'Test', 'author': 'Test author', 'topModule': 'tt_um_test',
            'sources': {'rtl/project.sv': 'module tt_um_test; endmodule', 'rtl/defs.svh': '`define COLOR 3'},
            'dataFiles': {'mem.hex': '01\n'}, 'licenses': {'LICENSE.txt': 'Test license'}}


class VGATests(unittest.TestCase):
    def test_preset_is_owned_saved_and_undoable_without_replacing_cell(self):
        project = counter_project(); original = project['digital']; history = History(project); created = []
        history.commit(lambda p: created.append(new_cell(p, 'VGA_Test', preset_config(preset()))))
        self.assertEqual(history.project['digital'], original)
        value = config(history.project, created[0])
        self.assertEqual(value['testbench'], 'tb_vga')
        self.assertTrue(any(f['path'] == 'LICENSE.txt' for f in value['files']))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'vga.icproj'; save_project(history.project, path)
            self.assertEqual(config(load_project(path), created[0]), value)
        history.undo(); self.assertEqual(len(history.project['cells']), len(project['cells']))

    def test_preview_uses_explicit_top_nested_sources_data_and_defines(self):
        value = preset_config(preset()); value['defines'] = {'COLOR': '2'}; value['include_dirs'] = ['rtl']
        result = preview_inputs(value)
        self.assertEqual(result['topModule'], 'tt_um_test')
        self.assertEqual(set(result['sources']), {'rtl/project.sv', 'rtl/defs.svh'})
        self.assertEqual(result['dataFiles']['mem.hex'], '01\n')
        self.assertEqual(result['includeDirs'], ['rtl'])
        self.assertEqual(result['defines'], {'COLOR': '2'})
        self.assertNotIn('tb_vga.sv', result['sources'])

    def test_invalid_source_paths_and_collisions_are_rejected(self):
        for path in ('../escape.v', '/tmp/a.v', 'RTL/project.sv', 'tb_vga.sv'):
            item = preset(); item['sources'][path] = 'module bad; endmodule'
            with self.subTest(path=path), self.assertRaises(ValueError): preset_config(item)
        item = preset(); item['topModule'] = 'bad; injected'
        with self.assertRaises(ValueError): preset_config(item)

    def test_static_server_is_bounded_and_shuts_down(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'assets'; root.mkdir()
            (root / 'index.html').write_text('<html>VGA</html>')
            (root / 'icstudio-build.json').write_text(json.dumps({'revision': REVISION}))
            (root / 'engine.wasm').write_bytes(b'wasm')
            (Path(td) / 'private.txt').write_text('not a web asset')
            server = AssetServer(root)
            try:
                with urlopen(server.url, timeout=2) as response:
                    self.assertIn(b'VGA', response.read())
                    self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
                with urlopen(server.url + 'engine.wasm', timeout=2) as response:
                    self.assertEqual(response.headers['Content-Type'], 'application/wasm')
                for path in ('../private.txt', '%2e%2e/private.txt'):
                    with self.assertRaises(HTTPError): urlopen(server.url + path, timeout=2)
                with self.assertRaises(HTTPError):
                    urlopen(Request(server.url, headers={'Host': 'untrusted.example'}), timeout=2)
            finally: server.close()
            self.assertFalse(server.thread.is_alive())
            server.close()


if __name__ == '__main__': unittest.main()
