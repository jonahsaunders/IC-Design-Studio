"""Supplemental native execution and independent installed receipt protections."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import klayout.db as db
import klayout.rdb as rdb
from icstudio import ihp_klayout_drc as public
from icstudio import ihp_metal_spacing as spacing
from scripts import verify_frozen_ihp_cmim as reader


class MetalSpacingReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'original.gds'
        ly = db.Layout(); ly.dbu = .001
        cell = ly.create_cell('coupon')
        cell.shapes(ly.layer(67, 0)).insert(db.Box(0, 0, 8200, 8200))
        ly.write(str(self.source))
        self.bundle = self.root / 'drc/rules'
        public.copy_assets(self.bundle)
        self.inputs = dict(files={reader.PUBLIC[1] + '/' + name: reader.sha(path)
                                 for name, path in public.assets(self.bundle).items()})
        self.code = Path(spacing.__file__).read_bytes()
        self.inputs['files']['icstudio/ihp_metal_spacing.py'] = hashlib.sha256(self.code).hexdigest()
        self.output = self.root / 'drc/metal-spacing'
        self.fault = None

    def engine(self, command, cwd, **kwargs):
        values = dict(arg.split('=', 1) for arg in command if '=' in arg)
        report = rdb.ReportDatabase('native test fixture')
        report.top_cell_name = 'other' if self.fault == 'top' else 'coupon'
        cell = report.create_cell(report.top_cell_name)
        category = report.create_category('M5.e')
        if self.fault == 'finding':
            report.create_item(cell.rdb_id(), category.rdb_id()).add_value(db.DBox(0, 0, .22, 8.2))
        if self.fault != 'missing-report':
            report.save(values['report'])
        if self.fault == 'input':
            self.source.write_bytes(b'changed')
        if self.fault == 'recipe':
            (Path(cwd) / 'check.drc').write_bytes(b'changed')
        rules = spacing.RULES[:-1] if self.fault == 'missing-rule' else spacing.RULES
        lines = ['ICSTUDIO_IHP_METAL_SPACING_RULE ' + rule for rule in rules]
        if self.fault != 'unfinished':
            lines.append(spacing.MARKER)
        return '\n'.join(lines) + '\n'

    def run_fixture(self):
        with patch('icstudio.engines.execute', side_effect=self.engine):
            row = spacing.run('/native/klayout', self.source, 'coupon', self.output, self.bundle)
        # Installed Windows jobs execute in managed Linux. Preserve that recorded
        # origin when exercising the independent reader on either host.
        path = self.output / 'command.json'
        command = json.loads(path.read_bytes())
        command = [value.replace(str(self.root.resolve()), '/native/job').replace('\\', '/') for value in command]
        path.write_text(json.dumps(command))
        return row

    def read(self, row):
        reader.supplemental_metal_spacing(self.root, row, self.inputs, '/native/job',
                                         '/native/klayout', self.code)

    def test_completed_native_report_and_independent_readback(self):
        row = self.run_fixture()
        self.read(row)
        self.assertEqual(row['rules'], list(spacing.RULES))
        self.assertEqual(row['violations'], 0)

    def test_native_findings_remain_failures_for_installed_acceptance(self):
        self.fault = 'finding'; row = self.run_fixture()
        self.assertEqual(row['violations'], 1)
        with self.assertRaisesRegex(ValueError, 'spacing has findings'):
            self.read(row)

    def test_incomplete_or_changed_native_execution_fails(self):
        for fault in ('missing-report', 'top', 'missing-rule', 'unfinished', 'input', 'recipe'):
            with self.subTest(fault=fault):
                self.output = self.root / ('failure-' + fault)
                self.fault = fault
                with self.assertRaises(ValueError):
                    self.run_fixture()

    def test_rehashed_wrong_recipe_command_source_and_completion_cannot_pass(self):
        row = self.run_fixture()
        paths = ('check.drc', 'command.json', 'console.log', 'findings.lyrdb')
        original = {name: (self.output / name).read_bytes() for name in paths}
        for fault in ('recipe', 'command', 'source', 'missing-rule', 'extra-rule', 'finding'):
            with self.subTest(fault=fault):
                current = copy.deepcopy(row)
                for name, raw in original.items():
                    (self.output / name).write_bytes(raw)
                if fault == 'recipe':
                    (self.output / 'check.drc').write_bytes(original['check.drc'].replace(b'transparent,', b'shielded,'))
                    current['recipe_sha256'] = reader.sha(self.output / 'check.drc')
                elif fault == 'command':
                    command = json.loads(original['command.json'])
                    command[command.index('topcell=coupon')] = 'topcell=other'
                    (self.output / 'command.json').write_text(json.dumps(command))
                elif fault == 'source':
                    current['source_inputs'][spacing.SOURCE_FILES[0]] = '0' * 64
                elif fault in ('missing-rule', 'extra-rule'):
                    marker = b'ICSTUDIO_IHP_METAL_SPACING_RULE M5.f\n'
                    (self.output / 'console.log').write_bytes(original['console.log'].replace(marker, b'') if fault == 'missing-rule' else original['console.log'] + marker)
                else:
                    report = rdb.ReportDatabase(); report.load(str(self.output / 'findings.lyrdb'))
                    cell = next(report.each_cell()); cat = report.create_category('M5.e')
                    report.create_item(cell.rdb_id(), cat.rdb_id()).add_value(db.DBox(0, 0, .22, 8.2))
                    report.save(str(self.output / 'findings.lyrdb'))
                    current['report_sha256'] = reader.sha(self.output / 'findings.lyrdb')
                with self.assertRaises(ValueError):
                    self.read(current)


if __name__ == '__main__':
    unittest.main()
