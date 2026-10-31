"""The opt-in parallel package preserves original assets and saved bindings."""
import json, tempfile, unittest
from pathlib import Path
from icstudio.catalog import parameter_values
from icstudio.model import clone, file_digest, load_project, save_project
from icstudio.interchange import export_xschem
from icstudio.xschem_io import import_package
from scripts.prepare_sky130_parallel_varactors import prepare, BASE_MANIFEST, WRAPPER
from scripts.qualify_capacitor_families import fixture
from scripts.device_qualification_source import previous_devices

ROOT = Path(__file__).resolve().parents[1]


class ParallelVaractorTests(unittest.TestCase):
    def test_original_assets_and_save_export_terminal_contracts_are_preserved(self):
        source = self.enterContext(previous_devices(ROOT/'icstudio/assets/pdks/sky130A')); original = json.loads((source/'package.json').read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root/'package'; record = prepare(source, out)
            self.assertNotEqual(record['revision'], original['revision'])
            package = json.loads((out/'package.json').read_bytes()); tech = clone(package['technology'])
            tech.update(package_root=str(out), package_lock={k: package[k] for k in ('id', 'revision', 'files')})
            for name, digest in original['files'].items(): self.assertEqual(file_digest(out/name), digest)
            for name in package['files'].keys()-original['files'].keys():
                self.assertIn(name, (WRAPPER, 'ICSTUDIO-PARALLEL-VARACTORS.json'))
            p = fixture(tech, 'sky130A', 0, .5, [])
            # Numerical probes share placeholder positions; handoff needs a real layout of symbols.
            for index, d in enumerate(p['cells'][0]['devices']): d.update(x=1000*(index%8), y=1000*(index//8))
            save_project(p, root/'input.icproj')
            self.assertEqual(load_project(root/'input.icproj')['pdk']['revision'], record['revision'])
            export_xschem(p, root/'handoff'); q, _ = import_package(root/'handoff')
            from icstudio.catalog_migration import instance_name
            for d in p['cells'][0]['devices']:
                if not d.get('model_ref'): continue
                e = tech['simulation']['catalog'][d['model_ref']['device']]
                after = next(v for v in q['cells'][0]['devices'] if v['name'] == instance_name(d, e))
                self.assertEqual(after['model_ref'], d['model_ref']); self.assertEqual(after['nets'], d['nets'])
                self.assertEqual(parameter_values(e, after), parameter_values(e, d))
            self.assertEqual(file_digest(source/'package.json'), BASE_MANIFEST)
            for kind in ('hvt', 'lvt'):
                e = tech['simulation']['catalog']['sky130_fd_pr/cap_var_'+kind+'.sym']
                d = next(d for d in p['cells'][0]['devices'] if d.get('model_ref', {}).get('device', '') == 'sky130_fd_pr/cap_var_'+kind+'.sym')
                for value in (0, -1):
                    bad = clone(d); bad['model_params']['vm'] = value
                    with self.assertRaises(ValueError): parameter_values(e, bad)

    def test_changed_manifest_and_existing_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/'source'; source.mkdir(); (source/'package.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'exact reviewed'): prepare(source, root/'result')
            self.assertFalse((root/'result').exists())
            with self.assertRaisesRegex(ValueError, 'new package'): prepare(source, source)


if __name__ == '__main__': unittest.main()
