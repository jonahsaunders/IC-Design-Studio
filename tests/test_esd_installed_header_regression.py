"""Actual failed-run decks exercise the complete parser, without running SPICE.

Only staged model content validation is mocked. Names, source paths, package
identity and deck bytes are independently bound to the retained artifact fixture.
Fresh installed acceptance separately validates staged bytes and native results.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import audit_sky130_esd_nvt as reader

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'tests/fixtures/esd-installed-headers-v1.json'
PACKAGE = ROOT/'icstudio/assets/pdks/sky130A'


class InstalledEsdHeaderRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes())
        cls.files = json.loads((PACKAGE/'package.json').read_bytes())['files']
        assert reader.sha(PACKAGE/'package.json') == cls.fixture['package_sha256']
        assert len(cls.fixture['cases']) == 16
        for case in cls.fixture['cases']:
            assert hashlib.sha256(case['deck'].encode()).hexdigest() == case['deck_sha256']
        cls.maps = {}
        for ident, mapping in cls.fixture['maps'].items():
            assert len(set(mapping.values())) == len(mapping)
            for staged, source in mapping.items():
                digest = cls.files[source]
                expected = hashlib.sha256((source+'\0'+digest).encode()).hexdigest()[:24]
                assert staged == 'pdk-models/'+expected+'.spice'
            cls.maps[ident] = {source: staged for staged, source in mapping.items()}

    def audit(self, folder, case, text=None, role=None, corner=None, package_sha=None):
        role = case['role'] if role is None else role
        filename = 'reference.cir' if role == 'independent' else 'input.cir'
        (folder/filename).write_bytes((case['deck'] if text is None else text).encode())
        with patch.object(reader, 'staged_models', return_value=self.maps[case['map_id']]):
            with patch.object(reader, 'sha', return_value=package_sha or self.fixture['package_sha256']):
                reader.deck(folder, PACKAGE, self.files, corner or case['corner'], case['temperature'], case['drive'], role)

    def test_actual_windows_linux_application_fault_and_reference_decks(self):
        with tempfile.TemporaryDirectory() as temp:
            for case in self.fixture['cases']:
                with self.subTest(host=case['host'], role=case['role'], drive=case['drive']):
                    self.audit(Path(temp), case)

    def test_missing_extra_reordered_and_crossed_header_profiles_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            for case in self.fixture['cases']:
                with self.subTest(host=case['host'], role=case['role'], drive=case['drive']):
                    lines = case['deck'].splitlines(keepends=True)
                    indices = [i for i,line in enumerate(lines) if line.lower().startswith(('.lib ', '.include '))]
                    self.assertEqual(len(indices), 4 if case['role']=='independent' else 5)
                    changes = [''.join(lines[:i]+lines[i+1:]) for i in indices]
                    changed = lines.copy(); changed[indices[0]],changed[indices[1]] = changed[indices[1]],changed[indices[0]]
                    changes.append(''.join(changed))
                    changes.append(''.join(lines[:indices[-1]+1]+[lines[indices[-1]]]+lines[indices[-1]+1:]))
                    if case['role']=='independent':
                        extra = '.include '+self.maps[case['map_id']]['libs.tech/ngspice/icstudio-rf-pw2dn/library.spice']+'\n'
                        changes.append(''.join(lines[:indices[-1]+1]+[extra]+lines[indices[-1]+1:]))
                    for changed in changes:
                        self.assertNotEqual(changed,case['deck'])
                        with self.assertRaises((ValueError,KeyError)):
                            self.audit(Path(temp),case,changed)
                    with self.assertRaisesRegex(ValueError,'Model selection or ordering'):
                        self.audit(Path(temp),case,corner='ss')
                    if case['role']!='independent':
                        with self.assertRaises(ValueError):
                            self.audit(Path(temp),case,package_sha=reader.PACKAGE)

    def test_wrong_role_and_changed_terminal_parameters_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            for case in self.fixture['cases']:
                with self.subTest(host=case['host'],role=case['role']):
                    other = 'application' if case['role']=='independent' else 'independent'
                    with self.assertRaises((ValueError,KeyError)):
                        self.audit(Path(temp),case,role=other)
                    with self.assertRaisesRegex(ValueError,'deck role'):
                        self.audit(Path(temp),case,role='unknown')
                    changed = case['deck'].replace('q0d q0g','q0s q0g',1)
                    # The gate-fault deck uses q0s as its intentional gate.
                    if changed == case['deck']:
                        changed = case['deck'].replace('q0d q0s','q0s q0s',1)
                    self.assertNotEqual(changed,case['deck'])
                    with self.assertRaisesRegex(ValueError,'Model or terminal order'):
                        self.audit(Path(temp),case,changed)


if __name__ == '__main__':
    unittest.main()
