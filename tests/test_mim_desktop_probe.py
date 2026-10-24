"""Real source Qt lifecycle plus fail-closed MiM probe boundary tests."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from icstudio.mim_desktop_probe import historical_package, verified_package, wait_job
from icstudio.model import file_digest, load_project

ROOT = Path(__file__).resolve().parents[1]
NONCE = '0123456789abcdef0123456789abcdef'


class ProbeBoundaryTests(unittest.TestCase):
    def test_package_missing_changed_and_escaping_assets_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'package'
            root.mkdir()
            outside = Path(tmp)/'outside'
            outside.write_bytes(b'locked')
            for name, expected in [('missing', hashlib.sha256(b'locked').hexdigest()),
                                   ('asset', '0'*64), ('../outside', file_digest(outside))]:
                with self.subTest(asset=name):
                    (root/'asset').write_bytes(b'locked')
                    (root/'package.json').write_text(json.dumps(dict(id='sky130A', files={name: expected})))
                    with self.assertRaisesRegex(ValueError, 'Changed package asset'):
                        verified_package(root)
            with self.assertRaisesRegex(ValueError, 'Unexpected package manifest'):
                verified_package(root, '0'*64)
            (root/'package.json').write_text(json.dumps(dict(id='sky130A', files={'asset': file_digest(root/'asset')})))
            with patch.object(Path, 'is_symlink', lambda path: path == root/'asset'):
                with self.assertRaisesRegex(ValueError, 'Linked package asset'):
                    verified_package(root)

    def test_historical_manifest_mutation_rejects_before_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root/'icstudio/assets/qualification/sky130-mim-base-v1/package.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'Changed retained'):
                historical_package(root, root, root/'output')
            self.assertFalse((root/'output').exists())

    def test_reused_and_incomplete_queued_results_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, 'did not complete'):
            wait_job(None, None, dict(state='Failed'))
        with self.assertRaisesRegex(ValueError, 'fresh queued'):
            wait_job(None, None, dict(state='Complete', result={'reused_from': {'run_id': 'old'}}))
        with self.assertRaisesRegex(ValueError, 'no report'):
            wait_job(None, None, dict(state='Complete', result={}))

    def test_frozen_custom_engine_run_fails_without_entering_gui(self):
        from icstudio.mim_desktop_probe import main
        with tempfile.TemporaryDirectory() as tmp, patch.object(sys, 'frozen', True, create=True):
            out = Path(tmp)/'out'
            self.assertEqual(main(['--out', str(out), '--execution-id', NONCE,
                                   '--magic', 'external-magic']), 1)
            result = json.loads((out/'report.json').read_bytes())
            self.assertEqual(result['status'], 'failed')
            self.assertIn('requires included engines', result['error'])
            self.assertFalse(result['native_execution'])
            self.assertFalse(result['full_mim_installed'])


class SourceQtProbeTests(unittest.TestCase):
    def test_real_place_edit_generate_rotate_save_reopen_and_old_binding(self):
        import klayout.db as db
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'probe with spaces'
            command = [sys.executable, '-B', '-X', 'pycache_prefix='+str(Path(tmp)/'unused-pycache'),
                       str(ROOT/'main.py'), '--mim-acceptance', '--mode', 'lifecycle',
                       '--out', str(out), '--execution-id', NONCE]
            environment = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
            environment['QT_QPA_PLATFORM'] = 'offscreen'
            run = subprocess.run(command, cwd=ROOT, env=environment,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            self.assertEqual(run.returncode, 0, run.stdout[-4000:]+run.stderr[-4000:])
            report = json.loads((out/'report.json').read_bytes())
            self.assertEqual(report['status'], 'passed')
            self.assertFalse(report['frozen'])
            for key in ('full_mim_installed', 'qualified', 'release_ready', 'native_execution'):
                self.assertIs(report[key], False)
            self.assertEqual(report['execution_id'], NONCE)
            expected = {f'p{plate}-r{angle}' for plate in (1, 2) for angle in (0, 90)}
            self.assertEqual({row['case'] for row in report['lifecycle']}, expected)
            regions = {}
            layouts = []  # Recursive regions retain a reference to their layout.
            for row in report['lifecycle']:
                self.assertEqual(row['execution_id'], NONCE)
                self.assertIn(NONCE[:12], row['top'])
                project = load_project(row['project'])
                cell = project['cells'][0]
                self.assertEqual(cell['name'], row['top'])
                self.assertEqual(cell['ports'], ['P', 'N'])
                self.assertEqual(cell['devices'][0]['nets'], {'c0': 'P', 'c1': 'N'})
                line = next(s for s in Path(row['reference']).read_text().splitlines() if s.startswith('X_C1 '))
                self.assertEqual(line.split()[1:4], ['P', 'N', f"sky130_fd_pr__cap_mim_m3_{row['plate']}"])
                self.assertEqual(set(line.split()[4:]), {'w=2', 'l=10', 'm=1', 'mf=1'})
                layout = db.Layout()
                layouts.append(layout)
                layout.read(row['gds'])
                top = layout.cell(row['top'])
                self.assertIsNotNone(top)
                pair = (89, 44) if row['plate'] == 1 else (97, 44)
                region = db.Region(top.begin_shapes_rec(layout.layer(*pair)))
                self.assertEqual(region.area()*layout.dbu**2, 20)
                regions[row['case']] = region
            for plate in (1, 2):
                self.assertTrue((regions[f'p{plate}-r0'].transformed(db.Trans(db.Trans.R90))
                                 ^ regions[f'p{plate}-r90']).is_empty())
            rows = {row['kind']: row for row in report['binding_lifecycle']}
            self.assertEqual(rows['historical-before']['package_lock'],
                             rows['historical-after-current-install']['package_lock'])
            self.assertNotEqual(rows['historical-before']['package_lock'], rows['current']['package_lock'])
            for kind, parameter in [('historical-before', 'vm'), ('historical-after-current-install', 'vm'), ('current', 'mf')]:
                line = next(s for s in Path(rows[kind]['reference']).read_text().splitlines() if s.startswith('X_C1 '))
                self.assertEqual(set(line.split()[4:]), {'w=2', 'l=10', 'm=4', parameter+'=4'})
            files = json.loads((out/'files.json').read_bytes())
            actual = {p.relative_to(out).as_posix(): file_digest(p) for p in out.rglob('*')
                      if p.is_file() and p not in (out/'files.json', out/'report.json')}
            self.assertEqual(files, actual)
            self.assertEqual(report['files_sha256'], file_digest(out/'files.json'))


if __name__ == '__main__':
    unittest.main()
