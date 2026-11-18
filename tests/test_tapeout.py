"""Source handoff coverage without a PDK install or network access."""

import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from icstudio import digital, tapeout
from icstudio.digital_cli import main
from icstudio.digital_examples import uart_project
from icstudio.model import save_project


class TinyTapeoutSourceTests(unittest.TestCase):
    def setUp(self):
        self.project = uart_project()
        self.metadata = {'title': 'UART: 8-bit', 'author': 'Renée', 'top': 'tt_um_uart_regression'}

    def test_reproducible_zip_and_shuttle_inputs(self):
        package = tapeout.prepare(self.project, **self.metadata)
        self.assertEqual(package, tapeout.prepare(self.project, **self.metadata))
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            info = json.loads(archive.read('info.yaml'))
            self.assertEqual(info['yaml_version'], 6)
            self.assertEqual(info['project']['author'], 'Renée')
            self.assertEqual(info['project']['source_files'], ['tt_wrapper.v', 'uart_tx.sv'])
            self.assertEqual(info['project']['clock_hz'], 100_000_000)
            self.assertEqual(info['pinout']['uio[0]'], 'send')
            self.assertEqual(info['pinout']['uo[1]'], 'busy')
            self.assertEqual(len(info['pinout']), 24)
            source, _, sdc = self.project['digital']['files']
            self.assertEqual(archive.read('src/uart_tx.sv'), source['text'].encode())
            self.assertEqual(archive.read('studio/constraints.sdc'), sdc['text'].encode())
            wrapper = archive.read('src/tt_wrapper.v')
            self.assertIn(b'.reset(!rst_n || !ena)', wrapper)
            self.assertIn(b'.tx(uo_out[0]), .busy(uo_out[1])', wrapper)
            config = json.loads(archive.read('src/config.json'))
            self.assertEqual((config['CLOCK_PERIOD'], config['CLOCK_PORT'], config['IO_DELAY_CONSTRAINT']), (10, 'clk', 10))
            workflow = archive.read('.github/workflows/gds.yaml').decode()
            self.assertIn(f'TinyTapeout/tt-gds-action@{tapeout.ACTION}', workflow)
            self.assertIn(f'TinyTapeout/tt-gds-action/precheck@{tapeout.ACTION}', workflow)
            self.assertIn(f'TinyTapeout/tt-gds-action/gl_test@{tapeout.ACTION}', workflow)
            manifest = tapeout.verify_package(io.BytesIO(package))
            self.assertEqual(manifest['project']['rtl_config_sha256'], digital.source_hash(self.project['digital']))
            self.assertTrue(all(value == 'not_run' for value in manifest['status'].values()))

    def test_release_metadata_and_scope_validation(self):
        for field, bad_value, message in (
            ('author', '   ', 'author'),
            ('title', 'one\ntwo', 'title'),
            ('top', 'top;invalid', 'top module'),
            ('cell_id', 'unknown-cell', 'digital cell'),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                tapeout.prepare(self.project, **{**self.metadata, field: bad_value})
        with self.assertRaisesRegex(ValueError, 'uart_tx'):
            tapeout.prepare(digital.counter_project(), **self.metadata)
        self.project['digital']['files'][0]['path'] = 'subdir/uart.sv'
        with self.assertRaisesRegex(ValueError, 'flat Verilog'):
            tapeout.prepare(self.project, **self.metadata)
        self.project['digital']['files'][0]['path'] = 'uart_tx.sv'
        self.project['digital']['files'][2]['text'] += 'set_false_path -from [get_ports reset]\n'
        with self.assertRaisesRegex(ValueError, '10 ns clock'):
            tapeout.prepare(self.project, **self.metadata)

    def test_missing_and_changed_members_fail_verification(self):
        package = tapeout.prepare(self.project, **self.metadata)
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        for name, changed, message in (
            ('src/uart_tx.sv', b'// changed', 'checksum differs'),
            ('test/tb.v', None, 'invalid file inventory'),
            ('../payload.v', b'// outside directory', 'invalid path'),
        ):
            with self.subTest(name=name):
                altered = io.BytesIO()
                with zipfile.ZipFile(altered, 'w') as archive:
                    for original_name, original_data in files.items():
                        if original_name != name:
                            archive.writestr(original_name, original_data)
                    if changed is not None:
                        archive.writestr(name, changed)
                with self.assertRaisesRegex(ValueError, message):
                    tapeout.verify_package(altered)

    def test_cli_export_verify_and_preserve_previous_zip_on_error(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            project_path = Path(folder) / 'source project.icproj'
            zip_path = Path(folder) / 'source export.zip'
            save_project(self.project, project_path)
            arguments = ['tapeout', str(project_path), '--output', str(zip_path), '--author', 'Studio Test']
            self.assertEqual(main(arguments), 0)
            initial = zip_path.read_bytes()
            self.assertIn('stream precheck are pending', out.getvalue())
            self.assertEqual(main(['verify-tapeout', str(zip_path)]), 0)
            self.assertEqual(main(arguments + ['--top-module', 'invalid']), 1)
            self.assertIn('tt_um_', err.getvalue())
            self.assertEqual(zip_path.read_bytes(), initial)
