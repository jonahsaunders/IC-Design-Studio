"""Actual resistor Qt lifecycle and fail-closed installed-probe boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from icstudio.metal_resistor_desktop_probe import CASES, MODELS, SIZES, main, widened_vertices
from icstudio.model import file_digest, load_project

ROOT = Path(__file__).resolve().parents[1]
NONCE = '123456789abcdef0123456789abcdef0'


class ProbeBoundaries(unittest.TestCase):
    def test_width_control_changes_only_right_edge_and_requires_selected_rectangle(self):
        before = [[50, -500], [2050, 5500]]
        self.assertEqual(widened_vertices(before, 50, 2000), [[50, -500], [2450, 5500]])
        polygon = [[50, 0], [50, 5000], [2050, 5000], [2050, 0]]
        self.assertEqual(widened_vertices(polygon, 50, 2000),
                         [[50, 0], [50, 5000], [2450, 5000], [2450, 0]])
        for points, width in ((before, 1000), ([[50, 0], [2050, 1], [50, 2]], 2000),
                              ([[50, 0], [2050, 0]], 2000)):
            with self.subTest(points=points, width=width):
                with self.assertRaisesRegex(ValueError, 'two-micrometre rectangle'):
                    widened_vertices(points, 50, width)
        self.assertEqual(before, [[50, -500], [2050, 5500]])

    def test_frozen_custom_runtime_is_rejected_before_gui(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sys, 'frozen', True, create=True):
            out = Path(temporary)/'output'
            self.assertEqual(main(['--out', str(out), '--execution-id', NONCE, '--magic', 'external']), 1)
            report = json.loads((out/'report.json').read_bytes())
            self.assertEqual(report['status'], 'failed')
            self.assertIn('requires included engines', report['error'])
            self.assertFalse(report['native_execution'])
            self.assertFalse(report['installed_acceptance'])
            self.assertFalse(report['full_family'])

    def test_invalid_nonce_and_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/'output'
            with self.assertRaisesRegex(ValueError, 'Invalid execution identity'):
                main(['--out', str(out), '--execution-id', '0'*31])
            self.assertFalse(out.exists())
            out.mkdir()
            with self.assertRaises(FileExistsError):
                main(['--out', str(out), '--execution-id', NONCE])


class SourceQtProbeTests(unittest.TestCase):
    def test_real_shape_inspector_rectangle_and_polygon_width_controls(self):
        code = r'''
import json,sys
from pathlib import Path
from PySide6.QtCore import QSettings,QStandardPaths
from PySide6.QtWidgets import QApplication
from icstudio.gui import Studio
from icstudio.layout import rect
from icstudio.model import clone,example
from icstudio.metal_resistor_desktop_probe import edit_width,content
root=Path(sys.argv[1])
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(root/'settings'))
QStandardPaths.writableLocation=staticmethod(lambda kind:str(root/'profile'/str(kind.value)))
app=QApplication([]);studio=Studio(recover=False);studio.maybe_save=lambda:True
try:
    for kind in ('rect','polygon'):
        project=example('empty');shape=rect('metal1',50,-500,2000,6000)
        if kind=='polygon':
            shape.update(kind='polygon',points=[[50,-500],[50,5500],[2050,5500],[2050,-500]],holes=[])
        project['cells'][0]['shapes']=[shape];studio.set_project(project)
        before=clone(content(studio.project))
        edited=edit_width(app,studio,shape,50,2000)
        assert max(p[0] for p in studio.cell['shapes'][0]['points'])==2450
        assert edited['before_points']==shape['points']
        studio.undo();assert content(studio.project)==before
    print('REAL_INSPECTOR_RECTANGLE_AND_POLYGON_PASS')
finally:
    studio.close();app.processEvents()
'''
        with tempfile.TemporaryDirectory() as temporary:
            environment = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
            environment['QT_QPA_PLATFORM'] = 'offscreen'
            run = subprocess.run([sys.executable, '-B', '-X', 'pycache_prefix='+str(Path(temporary)/'unused-cache'),
                                  '-c', code, temporary], cwd=ROOT, env=environment, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout[-4000:]+run.stderr[-4000:])
            self.assertIn('REAL_INSPECTOR_RECTANGLE_AND_POLYGON_PASS', run.stdout)

    def test_actual_library_editor_exports_and_saved_revision_lifecycle(self):
        import klayout.db as db
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/'probe with spaces'
            command = [sys.executable, '-B', '-X', 'pycache_prefix='+str(Path(temporary)/'unused-cache'),
                       '-m', 'icstudio.metal_resistor_desktop_probe', '--mode', 'lifecycle',
                       '--out', str(out), '--execution-id', NONCE]
            environment = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
            environment['QT_QPA_PLATFORM'] = 'offscreen'
            run = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', timeout=240)
            self.assertEqual(run.returncode, 0, run.stdout[-5000:]+run.stderr[-5000:])
            report = json.loads((out/'report.json').read_bytes())
            self.assertEqual(report['status'], 'passed')
            self.assertEqual(report['execution_id'], NONCE)
            for key in ('frozen', 'native_execution', 'qualified', 'release_ready', 'full_family', 'installed_acceptance'):
                self.assertIs(report[key], False)
            self.assertEqual([(row['model'], row['geometry_index'], row['rotation'])
                              for row in report['lifecycle']], list(CASES))
            regions, layouts = {}, []
            for row in report['lifecycle']:
                model, index, angle = row['model'], row['geometry_index'], row['rotation']
                width, length = SIZES[index]
                self.assertEqual(row['case'], f'{model}-g{index}-r{angle}')
                self.assertEqual(row['multiplicity'], 1)
                self.assertIn(NONCE[:12], row['top'])
                project = load_project(row['project'])
                cell = project['cells'][0]
                self.assertEqual(cell['name'], row['top'])
                self.assertEqual(cell['ports'], ['R1', 'R2'])
                self.assertEqual(cell['devices'][0]['nets'], {'m': 'R1', 'p': 'R2'})
                line = next(line.split() for line in Path(row['reference']).read_text().splitlines()
                            if line.startswith('R_R1 '))
                self.assertEqual(line[1:4], ['R1', 'R2', 'sky130_fd_pr__res_generic_'+model])
                self.assertEqual(dict(field.split('=', 1) for field in line[4:]),
                                 dict(w=f'{width:g}', l=f'{length:g}', m='1'))
                self.assertEqual(row['reference_sha256'], file_digest(row['reference']))
                self.assertEqual(row['schematic_sha256'], file_digest(row['schematic']))
                self.assertEqual(row['gds_sha256'], file_digest(row['gds']))
                checks = row['editor_checks']
                self.assertEqual(checks['initial_pin_ids'], checks['resized_pin_ids'])
                self.assertTrue(checks['undo_redo'])
                if (index, angle) == (1, 0):
                    self.assertTrue(checks['late_layer_lock']['rejected'])
                    self.assertEqual(checks['late_layer_lock']['before_design_hash'],
                                     checks['late_layer_lock']['blocked_design_hash'])
                else:
                    self.assertIsNone(checks['late_layer_lock'])
                layout = db.Layout()
                layouts.append(layout)
                layout.read(row['gds'])
                top = layout.cell(row['top'])
                self.assertIsNotNone(top)
                layer = 67+MODELS.index(model)
                marker = db.Region(top.begin_shapes_rec(layout.layer(layer, 13)))
                conductor = db.Region(top.begin_shapes_rec(layout.layer(layer, 20)))
                self.assertAlmostEqual(marker.area()*layout.dbu**2, width*length, places=8)
                self.assertAlmostEqual(conductor.area()*layout.dbu**2, width*(length+1), places=8)
                regions[row['case']] = marker
            for model in MODELS:
                for index in range(3):
                    self.assertTrue((regions[f'{model}-g{index}-r0'].transformed(db.Trans(db.Trans.R90))
                                     ^ regions[f'{model}-g{index}-r90']).is_empty())
                rows = {row['kind']: row for row in report['binding_lifecycle'] if row['model'] == model}
                old, reopened, current = [rows[key] for key in ('historical-before', 'historical-after-current-install', 'current')]
                self.assertEqual(old['package_lock'], reopened['package_lock'])
                self.assertEqual(old['binding']['model_ref'], reopened['binding']['model_ref'])
                self.assertNotEqual(old['package_lock'], current['package_lock'])
                self.assertEqual(Path(old['reference']).read_bytes(), Path(reopened['reference']).read_bytes())
                for row in rows.values():
                    line = next(line.split() for line in Path(row['reference']).read_text().splitlines()
                                if line.startswith('R_R1 '))
                    self.assertEqual(line[1:4], ['R1', 'R2', 'sky130_fd_pr__res_generic_'+model])
                    self.assertEqual(set(line[4:]), {'w=2', 'l=5', 'm=3'})
            files = json.loads((out/'files.json').read_bytes())
            self.assertEqual(files, {path.relative_to(out).as_posix(): file_digest(path)
                                    for path in out.rglob('*') if path.is_file()
                                    and path not in (out/'files.json', out/'report.json')})
            self.assertEqual(report['files_sha256'], file_digest(out/'files.json'))


if __name__ == '__main__':
    unittest.main()
