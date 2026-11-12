"""Receipt substitution controls; synthetic fixtures never claim native execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_installed_mim as check


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.gr, self.pr, self.er = [self.root/name for name in ('gui', 'public', 'electrical')]
        for root in (self.gr/'probe', self.pr, self.er):
            root.mkdir(parents=True)
        self.commit, self.nonce = 'a'*40, 'b'*32
        self.app = self.root/'app'; self.app.write_bytes(b'synthetic executable')
        self.gv = dict(schema=1, status='PASS', gate='mim-installed-gui-queued-layout', expected_commit=self.commit,
                       execution_id=self.nonce, qualified=False, release_ready=False, full_mim_installed=False)
        self.invocation = dict(expected_commit=self.commit, execution_id=self.nonce)
        cases = {}; lifecycle = []; physical = []
        for name in check.gui.CASES:
            folder = self.gr/'probe'/name; folder.mkdir()
            job = folder/'job'; evidence = job/'physical-flow'; extraction = evidence/'lvs-extraction'
            extraction.mkdir(parents=True)
            self.write(job/'input.json', {'fixture': name}); self.write(job/'result.json', {'fixture': name})
            files = {}
            for kind in ('project', 'reference', 'schematic', 'gds', 'native'):
                path = extraction/'extracted.spice' if kind == 'native' else folder/kind
                path.write_text(name+' '+kind)
                files[kind] = str(path)
            item = dict(case=name, plate=int(name[1]), rotation=int(name[4:]), top=name.replace('-', '_'),
                        **{kind: path for kind, path in files.items() if kind != 'native'})
            native = dict(case=name, top=item['top'], job_id=name, job_directory=str(job), evidence_directory=str(evidence),
                          design_hash='d'*64, input_sha256=check.sha(job/'input.json'), result_sha256=check.sha(job/'result.json'))
            lifecycle.append(item); physical.append(native)
            cases[name] = dict(plate=item['plate'], rotation=item['rotation'],
                              **{key: native[key] for key in ('top', 'job_id', 'job_directory', 'design_hash', 'input_sha256', 'result_sha256')},
                              files=files, hashes={k: check.sha(v) for k, v in files.items()})
        self.write(self.gr/'probe/report.json', dict(lifecycle=lifecycle, physical=physical))
        self.binding = dict(mode='installed', expected_commit=self.commit, execution_id=self.nonce,
                            gui_root=str(self.gr/'probe'), supplied_root=str(self.gr), cases=cases,
                            application=dict(path=str(self.app), sha256=check.sha(self.app)))
        self.record = dict(schema=1, status='PASS', gate='mim-installed-public-drc', mode='installed', installed=True,
                           execution_id='c'*32, qualified=False, release_ready=False, full_mim_installed=False)
        self.pv = dict(status='PASS', gate='mim-installed-public-drc', mode='installed', installed=True,
                       expected_commit=self.commit, gui_execution_id=self.nonce, execution_id='c'*32,
                       positive_layouts=4, detected_geometry_controls=1, raw_categories_per_layout=255,
                       qualified=False, release_ready=False, full_mim_installed=False)
        self.eq = dict(schema=1, status='PASS', gate='mim-installed-electrical60', mode='installed',
                       expected_commit=self.commit, pilot=False, installed_electrical_acceptance=True,
                       qualified=False, release_ready=False, signoff=False, full_mim_installed=False,
                       context_identity=dict(gui_execution_id=self.nonce))
        self.ea = dict(schema=1, status='PASS', mode='installed', installed_electrical_acceptance=True,
                       qualified=False, signoff=False, full_mim_installed=False, counts=copy.deepcopy(check.COUNTS))
        self.write(self.pr/'raw.xml', {'fixture': True})
        self.write(self.er/'raw.json', {'fixture': True})
        self.seal()
        self.mock = patch.object(check.gui, 'git_blob', side_effect=lambda commit, name: (check.ROOT/name).read_bytes())
        self.mock.start(); self.addCleanup(self.mock.stop)

    def write(self, path, value):
        path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

    def seal(self):
        self.write(self.gr/'probe/files.json', check.gui.inventory(self.gr/'probe', ('files.json', 'report.json')))
        self.gv.update(report_sha256=check.sha(self.gr/'probe/report.json'), files_sha256=check.sha(self.gr/'probe/files.json'))
        self.write(self.gr/'verification.json', self.gv); self.write(self.gr/'invocation.json', self.invocation)
        for key, path in (('report_sha256', 'probe/report.json'), ('files_sha256', 'probe/files.json'),
                          ('verification_sha256', 'verification.json'), ('invocation_sha256', 'invocation.json')):
            self.binding[key] = check.sha(self.gr/path)
        self.write(self.er/'inputs.json', self.binding)
        self.record['binding'] = copy.deepcopy(self.binding)
        self.write(self.pr/'files.json', check.gui.inventory(self.pr, ('files.json', 'record.json', 'verification.json')))
        self.record['files_sha256'] = check.sha(self.pr/'files.json')
        self.write(self.pr/'record.json', self.record)
        self.pv.update(record_sha256=check.sha(self.pr/'record.json'), files_sha256=self.record['files_sha256'])
        self.write(self.pr/'verification.json', self.pv)
        self.eq['inputs_sha256'] = self.eq['context_identity']['inputs_sha256'] = check.sha(self.er/'inputs.json')
        self.write(self.er/'qualification.json', self.eq)
        self.ea.update(qualification_sha256=check.sha(self.er/'qualification.json'), inputs_sha256=self.eq['inputs_sha256'])
        self.write(self.er/'audit.json', self.ea)
        self.write(self.er/'manifest.json', check.gui.inventory(self.er, ('manifest.json', 'audit.json')))

    def verify(self):
        return check.verify(self.gr, self.pr, self.er, self.commit)

    def test_matching_receipts_keep_full_qualification_open(self):
        result = self.verify()
        self.assertTrue(result['installed_selected_workflow_acceptance'])
        self.assertFalse(result['full_mim_installed'])
        self.assertFalse(result['signoff'])
        self.assertEqual(result['counts'], check.COUNTS)

    def test_rehashed_semantic_substitutions_reject(self):
        mutations = [
            (self.gv, 'expected_commit', 'd'*40), (self.invocation, 'execution_id', 'e'*32),
            (self.binding, 'mode', 'source-pilot'), (self.pv, 'installed', False),
            (self.pv, 'gui_execution_id', 'e'*32), (self.pv, 'raw_categories_per_layout', 254),
            (self.eq, 'pilot', True), (self.eq, 'installed_electrical_acceptance', False),
            (self.eq, 'full_mim_installed', True), (self.ea, 'status', 'FAIL'),
            (self.eq, 'release_ready', True),
            (self.ea, 'signoff', True), (self.ea['counts'], 'contexts', 4),
            (self.eq['context_identity'], 'gui_execution_id', 'e'*32),
        ]
        for target, key, value in mutations:
            with self.subTest(key=key, value=value):
                original = target[key]; target[key] = value; self.seal()
                with self.assertRaises(ValueError):
                    self.verify()
                target[key] = original; self.seal()

    def test_public_and_electrical_binding_mismatch_rejects(self):
        self.record['binding']['execution_id'] = 'e'*32
        self.write(self.pr/'record.json', self.record)
        self.pv['record_sha256'] = check.sha(self.pr/'record.json')
        self.write(self.pr/'verification.json', self.pv)
        with self.assertRaisesRegex(ValueError, 'different GUI inputs'):
            self.verify()

    def test_changed_raw_output_rejects(self):
        (self.er/'raw.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            self.verify()

    def test_installed_application_change_rejects(self):
        self.app.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'application changed'):
            self.verify()

    def test_missing_independent_audit_rejects(self):
        (self.er/'audit.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.verify()

    def test_unselected_checker_source_rejects(self):
        with patch.object(check.gui, 'git_blob', return_value=b'other source'):
            with self.assertRaisesRegex(ValueError, 'checker differs'):
                self.verify()

    def test_duplicate_cases_reject_after_rehash(self):
        self.binding['cases'].pop('p2-r90')
        self.seal()
        with self.assertRaisesRegex(ValueError, 'Four ordered'):
            self.verify()

    def test_rehashed_cross_case_native_substitution_rejects(self):
        first, second = [self.binding['cases'][key] for key in ('p1-r0', 'p2-r0')]
        for key in ('files', 'hashes'):
            first[key]['native'], second[key]['native'] = second[key]['native'], first[key]['native']
        self.seal()
        with self.assertRaisesRegex(ValueError, 'another case'):
            self.verify()

    def test_rehashed_job_identity_substitution_rejects(self):
        self.binding['cases']['p1-r0']['job_id'] = 'another-job'
        self.seal()
        with self.assertRaisesRegex(ValueError, 'original GUI/native job'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
