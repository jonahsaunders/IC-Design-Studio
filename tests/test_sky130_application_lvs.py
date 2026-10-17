"""Exercise production LVS with real retained native evidence and physical faults."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from icstudio import digital_sky130_lvs as lvs, digital_sky130_lvs_core as core
from icstudio.digital_flow import artifact
from icstudio.model import clone, file_digest
from tests import test_sky130_lvs as legacy, test_sky130_diode_lvs as diode


def production_functions(test, module, names):
    for name in names:
        context = patch.object(module, name, getattr(core, name))
        context.start(); test.addCleanup(context.stop)


class ProductionPorts(legacy.PortTests):
    def setUp(self):
        super().setUp(); production_functions(self, legacy, ['port_groups_match'])


class ProductionGeometry(legacy.GeometryTests):
    def setUp(self):
        super().setUp(); production_functions(self, legacy, ['label_copy'])


class ProductionIdentity(legacy.IdentityTests):
    def setUp(self):
        production_functions(self, legacy, ['prepare_reference', 'strict_deck'])


class ProductionDiode(diode.DiodeReferenceTests):
    def setUp(self):
        production_functions(self, diode, ['enrich_reference', 'reference_dimensions', 'verify_library'])


class SavedComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with zipfile.ZipFile(Path(__file__).parent/'fixtures/sky130-application-lvs-v1.zip') as archive:
            archive.extractall(self.root)
        self.data = json.loads((self.root/'data.json').read_bytes())

    def path(self, name):
        key = self.data['physical']['sky130_lvs']['evidence'][name]
        return self.root/self.data['artifacts'][key]['path']

    def rehash(self, name):
        key = self.data['physical']['sky130_lvs']['evidence'][name]
        self.data['artifacts'][key] = artifact(self.root, self.path(name))

    def declare(self):
        path = self.root/self.data['artifacts']['sky130_lvs']['path']
        path.write_text(json.dumps(self.data['physical']['sky130_lvs']))
        self.data['artifacts']['sky130_lvs'] = artifact(self.root, path)

    def test_real_native_pass_and_portable_paths(self):
        report = lvs.validate_saved(self.data, self.root)
        self.assertTrue(report['audit']['matched'])
        self.assertFalse(report['qualified'])
        self.assertGreater(sum(report['audit']['inventory']['layout']['devices'].values()), 0)
        relocated = self.root/'relocated'; relocated.mkdir()
        data = clone(self.data)
        for key, item in data['artifacts'].items():
            source = self.root/item['path']; target = relocated/(key+source.suffix)
            shutil.copyfile(source, target); item['path'] = target.name
        self.assertEqual(lvs.validate_saved(data, relocated), report)

    def test_backend_carries_licensed_original_and_independent_diode(self):
        from icstudio.digital_backend import stage_backend
        source = self.root/'source'; source.mkdir(); (source/'module.py').write_text('# source\n')
        staged = self.root/'backend'; stage_backend(source, staged)
        for name, digest in lvs.ASSET_HASHES.items():
            self.assertEqual(file_digest(staged/'assets/verification/sky130/lvs'/name), digest)

    def test_missing_evidence_never_inherits_reference_pass(self):
        for key in list(self.data['artifacts']):
            with self.subTest(key=key):
                data = clone(self.data); del data['artifacts'][key]
                with self.assertRaises(ValueError): lvs.validate_saved(data, self.root)

    def test_missing_or_changed_declaration_rejected(self):
        for value in (None, {}, {**self.data['physical']['sky130_lvs'], 'status':'FAIL'},
                      {**self.data['physical']['sky130_lvs'], 'qualified':True}):
            with self.subTest(value=value):
                data = clone(self.data); data['physical']['sky130_lvs'] = value
                with self.assertRaises(ValueError): lvs.validate_saved(data, self.root)

    def test_stripping_all_evidence_still_fails_captured_policy(self):
        self.data['environment'].pop('sky130_lvs'); self.data['physical'].clear()
        self.data['artifacts'] = {k:v for k,v in self.data['artifacts'].items() if not k.startswith('sky130_lvs')}
        with self.assertRaisesRegex(ValueError, 'captured inputs'): lvs.validate_saved(self.data, self.root)

    def test_unqualified_historical_job_stays_unqualified(self):
        other = self.root/'empty'; other.mkdir()
        self.assertIsNone(lvs.validate_saved({'artifacts':{}}, other))

    def test_rehashed_conversion_or_recipe_changes_rejected(self):
        changes = {
            'reference.cdl':lambda text:text.replace('scale=1e-6','scale=1'),
            'strict.lvs':lambda text:text+'\nconnect_global(SUB, "VNB")\n',
            'aliases.json':lambda text:text.replace('N0000000','N9999999'),
            'conversion.json':lambda text:text.replace('1e-06','1.0'),
            'native.log':lambda text:text.replace('ICSTUDIO_SKY130_LVS_COMPLETE','INCOMPLETE'),
            'reference_engine.py':lambda text:text+'\n# changed capture worker\n',
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                path = self.path(name); original = path.read_bytes(); changed = change(original.decode())
                self.assertNotEqual(changed, original.decode()); path.write_bytes(changed.encode()); self.rehash(name)
                with self.assertRaises(ValueError): lvs.validate_saved(self.data, self.root)
                path.write_bytes(original); self.rehash(name)
                self.assertTrue(lvs.validate_saved(self.data, self.root)['audit']['matched'])

    def test_rehashed_port_audit_cannot_override_native_graph(self):
        name = 'audit.json'; audit = json.loads(self.path(name).read_bytes())
        audit['port_pairs'][0]['layout'] = 'N9999999'
        self.path(name).write_text(json.dumps(audit)); self.rehash(name)
        self.data['physical']['sky130_lvs']['audit'] = audit; self.declare()
        with self.assertRaisesRegex(ValueError, 'native connectivity'): lvs.validate_saved(self.data, self.root)

    def test_real_failed_native_graph_cannot_be_declared_passing(self):
        shutil.copyfile(self.root/'controls/failed.lvsdb', self.path('report.lvsdb'))
        self.rehash('report.lvsdb')
        with self.assertRaisesRegex(ValueError, 'native connectivity'): lvs.validate_saved(self.data, self.root)

    def test_rehashed_label_geometry_cannot_add_a_connection(self):
        import klayout.db as k
        path = self.path('labelled.gds'); layout = k.Layout(); layout.read(str(path))
        layout.top_cell().shapes(layout.layer(68,20)).insert(k.Box(-1000,-1000,1000,1000))
        layout.write(str(path)); self.rehash('labelled.gds')
        with self.assertRaisesRegex(ValueError, 'comparison layout'): lvs.validate_saved(self.data, self.root)

    def test_changed_tool_identity_rejected(self):
        self.data['physical']['sky130_lvs']['engine']['klayout']['sha256'] = '0'*64; self.declare()
        with self.assertRaisesRegex(ValueError, 'engine identity'): lvs.validate_saved(self.data, self.root)

    def test_newline_variants_preserve_identical_extraction(self):
        original = self.path('upstream.lylvs').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(core.strict_deck(original, 'counter'), core.strict_deck(original.replace(b'\n', b'\r\n'), 'counter'))


if __name__ == '__main__': unittest.main()
