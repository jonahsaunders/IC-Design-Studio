"""The project density gate cannot be bypassed by disabling fill or editing reports."""
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import klayout.db as k

from icstudio import digital_sky130_density as density
from icstudio.digital_flow import artifact, environment
from icstudio.model import clone, file_digest
from tests.test_digital_macro import DigitalMacroTests


class ApplicationDensityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.gds = self.root/'layout.gds'
        self.layout = k.Layout(); self.layout.dbu = .001
        self.top = self.layout.create_cell('generic_block')
        self.top.shapes(self.layout.layer(68, 20)).insert(k.Box(0, 0, 1000, 1000))
        self.layout.write(str(self.gds))
        checkpoint = self.root/'checkpoint'; checkpoint.write_bytes(b'independent checkpoint fixture')
        self.files = {key:artifact(self.root, path) for key, path in
                      [('gds', self.gds), ('checkpoint', checkpoint)]}
        self.bounds([0, 0, 700000, 700000])
        self.data = dict(platform={'name':'sky130hd'}, artifacts=self.files,
            environment={'sky130_density':clone(density.POLICY)}, physical={'settings':{'sky130_fill':False}})
        (self.root/'input.json').write_text(json.dumps({'environment':self.data['environment']}))
        self.runner = SimpleNamespace(root=self.root, platform=self.data['platform'],
            config={'top':self.top.name}, artifacts=self.files)
        self.runner.add_artifact = lambda key,path:self.files.update({key:artifact(self.root, path)})
        def save(key, value, path):
            (self.root/path).write_text(json.dumps(value)); self.runner.add_artifact(key, self.root/path)
        self.runner.save_json = save

    def bounds(self, value):
        path = self.root/'inventory.json'
        path.write_text(json.dumps(dict(schema=1, top=self.top.name, die_nm=value,
            checkpoint_sha256=self.files['checkpoint']['sha256'])))
        self.files['sky130_pin_inventory'] = artifact(self.root, path)

    def dense_layout(self):
        for pair, _ in density.oxide.LAYERS.values():
            for x in range(0, 700000, 2000):
                self.top.shapes(self.layout.layer(*pair)).insert(k.Box(x, 0, x+1000, 700000))
        self.layout.write(str(self.gds)); self.files['gds'] = artifact(self.root, self.gds)

    def execute(self):
        result = density.execute(self.runner); self.data['physical']['sky130_density'] = result
        return result

    def rewrite(self, value):
        self.data['physical']['sky130_density'] = value
        self.runner.save_json('sky130_density', value, 'sky130-density/report.json')

    def test_unfilled_full_window_fails_and_retains_measurements(self):
        with self.assertRaisesRegex(ValueError, 'below 80%'): self.execute()
        report = json.loads((self.root/'sky130-density/report.json').read_bytes())
        self.assertEqual(report['status'], 'FAIL'); self.assertEqual(report['full_window_findings'], 8)
        self.assertEqual(report['full_windows'], 1)
        self.assertFalse(self.data['physical']['settings']['sky130_fill'])
        self.rewrite(report)
        with self.assertRaisesRegex(ValueError, 'prevent export'): density.validate_saved(self.data, self.root)

    def test_real_dense_geometry_passes_with_fill_disabled_and_relocates(self):
        self.dense_layout(); report = self.execute()
        self.assertEqual(report['status'], 'sampled-full-windows-pass')
        self.assertEqual(density.validate_saved(self.data, self.root), report)
        moved = self.root/'moved'; moved.mkdir(); data = clone(self.data)
        for i, (key, item) in enumerate(data['artifacts'].items()):
            path = moved/(str(i)+Path(item['path']).suffix)
            shutil.copyfile(self.root/item['path'], path); item['path'] = path.name
        self.assertEqual(density.validate_saved(data, moved), report)
        self.assertFalse(report['qualified']); self.assertFalse(report['acceptance_established'])

    def test_small_block_requires_surroundings_and_has_no_density_acceptance(self):
        self.bounds([0, 0, 200000, 200000]); report = self.execute()
        self.assertEqual(report['status'], 'surrounding-layout-required')
        self.assertEqual(report['full_windows'], 0)
        self.assertFalse(report['acceptance_established'])
        self.assertEqual(density.validate_saved(self.data, self.root), report)

    def test_missing_bounds_or_inventory_cannot_produce_pass(self):
        del self.files['sky130_pin_inventory']
        with self.assertRaisesRegex(ValueError, 'missing input'): self.execute()

    def test_rehashed_geometry_and_forged_pass_are_remeasured(self):
        self.dense_layout(); report = self.execute()
        for pair, _ in density.oxide.LAYERS.values(): self.top.shapes(self.layout.layer(*pair)).clear()
        self.layout.write(str(self.gds)); self.files['gds'] = artifact(self.root, self.gds)
        report['inputs']['gds'] = self.files['gds']['sha256']
        report['observation']['gds_sha256'] = self.files['gds']['sha256']; self.rewrite(report)
        with self.assertRaisesRegex(ValueError, 'actual layout'): density.validate_saved(self.data, self.root)

    def test_rehashed_changed_bounds_do_not_preserve_observations(self):
        self.bounds([0, 0, 200000, 200000]); report = self.execute()
        self.bounds([0, 0, 700000, 700000])
        report['inputs']['sky130_pin_inventory'] = self.files['sky130_pin_inventory']['sha256']; self.rewrite(report)
        with self.assertRaisesRegex(ValueError, 'actual layout'): density.validate_saved(self.data, self.root)

    def test_stripping_claim_cannot_remove_captured_policy(self):
        self.data['environment'].clear()
        with self.assertRaisesRegex(ValueError, 'captured inputs'): density.validate_saved(self.data, self.root)

    def test_missing_or_changed_artifact_and_declaration_rejected(self):
        self.bounds([0, 0, 200000, 200000]); self.execute()
        for key in self.files:
            data = clone(self.data); del data['artifacts'][key]
            with self.subTest(key=key), self.assertRaises(ValueError): density.validate_saved(data, self.root)
        data = clone(self.data); data['physical'].pop('sky130_density')
        with self.assertRaises(ValueError): density.validate_saved(data, self.root)

    def test_rehashed_source_change_is_not_accepted(self):
        self.bounds([0, 0, 200000, 200000]); self.execute()
        key = 'sky130_density_met_density_tiled_drc'; path = self.root/self.files[key]['path']
        path.write_bytes(path.read_bytes()+b'\n# changed\n'); self.files[key] = artifact(self.root, path)
        with self.assertRaisesRegex(ValueError, 'public source'): density.validate_saved(self.data, self.root)

    def test_no_bounds_and_wrong_checkpoint_fail(self):
        self.bounds(None)
        with self.assertRaisesRegex(ValueError, 'no declared bounds'): self.execute()

    def test_other_process_and_historical_jobs_gain_no_claim(self):
        self.assertIsNone(density.execute(SimpleNamespace(platform={'name':'gf180d'})))
        other = self.root/'historical'; other.mkdir()
        self.assertIsNone(density.validate_saved({'artifacts':{}}, other))

    def test_prepare_captures_policy_for_both_fill_choices_and_stages_sources(self):
        from icstudio.digital_backend import stage_backend
        child = self.root/'job'; child.mkdir()
        job, _ = DigitalMacroTests().fixture(child, name='sky130hd')
        job['settings'] = dict(stage='finish', tools={})
        for enabled in (False, True):
            job['project']['digital']['physical'] = {'sky130_fill':enabled}
            with patch('icstudio.digital_platform.verify', return_value={}): actual = environment(job)
            self.assertEqual(actual['sky130_density'], density.POLICY)
        source = self.root/'source'; source.mkdir(); (source/'module.py').write_text('# test\n')
        stage_backend(source, self.root/'backend')
        for name, digest in density.ASSET_HASHES.items():
            self.assertEqual(file_digest(self.root/'backend/assets/verification/sky130/density'/name), digest)


if __name__ == '__main__': unittest.main()
