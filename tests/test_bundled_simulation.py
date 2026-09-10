"""Regressions for incomplete installations and the supplied open-PDK circuit."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
from icstudio.runtime_setup import verify_runtime_files
from icstudio.bundled_pdks import packages
from icstudio.xschem_compat import review_project
from icstudio.xschem_runtime import netlist, prepare_program

spec = importlib.util.spec_from_file_location('stage_windows', ROOT/'scripts/stage_windows_ngspice.py')
stage_windows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_windows)


class BundledSimulationTests(unittest.TestCase):
    def test_catalog_model_paths_with_spaces_and_self_includes_are_staged(self):
        from icstudio.pdks import stage_model_deck
        with tempfile.TemporaryDirectory(prefix='PDK profile with spaces ') as td:
            root=Path(td); pdk=root/'PDK models'; pdk.mkdir(); out=root/'run'; out.mkdir()
            source=pdk/'master lib.spice'; child=pdk/'device model.spice'
            source.write_text('.lib tt\n.lib "master lib.spice" devices\n.endl tt\n.lib devices\n.include "device model.spice"\n.endl devices\n')
            child.write_text('.subckt test p n\nR1 p n 1k\n.ends\n')
            files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,child)}
            tech={'package_root':str(pdk),'package_lock':{'files':files},'simulation':{'includes':[]}}
            deck='* test\n.lib "'+source.as_posix()+'" tt\nX1 in 0 test\n.end\n'
            staged=stage_model_deck(tech,deck,out)
            self.assertNotIn(str(pdk),staged)
            self.assertEqual(len(list((out/'pdk-models').glob('*.spice'))),2)
            wrapper=next(p for p in (out/'pdk-models').glob('*.spice') if '.lib tt' in p.read_text())
            self.assertIn('.lib '+wrapper.relative_to(out).as_posix()+' devices',wrapper.read_text())
            self.assertNotIn('device model.spice',wrapper.read_text())
            child.write_text('changed source')
            with self.assertRaisesRegex(ValueError,'changed'):
                stage_model_deck(tech,deck,root/'new-run')

    def test_missing_nested_catalog_model_cannot_escape_its_lock(self):
        from icstudio.pdks import stage_model_deck
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); model=root/'master.lib'; model.write_text('.include ../unlocked.lib\n')
            tech={'package_root':str(root),'package_lock':{'files':{'master.lib':hashlib.sha256(model.read_bytes()).hexdigest()}},'simulation':{'includes':[]}}
            with self.assertRaisesRegex(ValueError,'absent from its lock'):
                stage_model_deck(tech,'.include "'+model.as_posix()+'"\n',root/'run')

    def runtime(self, root):
        files = {}
        for name in ('ngspice.exe', 'libomp140.x86_64.dll', 'spinit', 'COPYING.txt'):
            data = ('fixture-' + name).encode()
            (root/name).write_bytes(data)
            files[name] = hashlib.sha256(data).hexdigest()
        (root/'runtime-manifest.json').write_text(json.dumps({'files': files, 'archive_sha256': stage_windows.SHA256}))

    def test_missing_or_corrupt_dll_is_not_a_valid_installation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.runtime(root)
            verify_runtime_files(root)
            (root/'libomp140.x86_64.dll').write_bytes(b'damaged')
            with self.assertRaisesRegex(ValueError, 'libomp'):
                verify_runtime_files(root)
            (root/'libomp140.x86_64.dll').unlink()
            with self.assertRaisesRegex(ValueError, 'libomp'):
                verify_runtime_files(root)

    def test_healthy_runtime_is_reused_offline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.runtime(root)
            with patch.object(stage_windows, 'check_ngspice'), patch('urllib.request.urlopen', side_effect=AssertionError('network')):
                self.assertEqual(stage_windows.ensure(target=root), root/'ngspice.exe')

    def test_corrupt_runtime_is_repaired_before_probe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.runtime(root)
            (root/'ngspice.exe').unlink()
            with patch.object(stage_windows, 'stage', side_effect=lambda archive, target: self.runtime(target)) as repair, patch.object(stage_windows, 'check_ngspice'):
                stage_windows.ensure(target=root)
                repair.assert_called_once()
                verify_runtime_files(root)

    def test_bad_offline_archive_is_rejected_before_extracting(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root/'truncated.7z'
            archive.write_bytes(b'incomplete')
            with patch.object(stage_windows, 'ROOT', root), self.assertRaisesRegex(ValueError, 'checksum'):
                stage_windows.stage(archive, root/'runtime')
            self.assertFalse((root/'runtime/ngspice.exe').exists())

    def test_all_bundled_pdks_verify_without_network(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('offline')):
            entries = packages(verify=True)
        self.assertEqual({e['family'] for e in entries}, {'sky130', 'gf180mcu'})

    def test_original_schematic_is_exact_and_all_144_cases_are_portable(self):
        folder = ROOT/'examples/gf180-bandgap'
        original = folder/'5vfullv2-original.sch'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), json.loads((folder/'source.json').read_text())['original_sha256'])
        with patch('urllib.request.urlopen', side_effect=AssertionError('offline')):
            review = review_project(original)
        self.assertEqual(review['errors'], [])
        self.assertEqual(review['candidate']['xschem_exchange']['unresolved'], [])
        with tempfile.TemporaryDirectory(prefix='path with spaces ') as td:
            text = netlist(review['candidate'], td)
            program, count, relocations = prepare_program(text, td, {'probes':'v(vref)'})
            self.assertEqual(count, 144)
            self.assertNotIn('/foss/', program)
            self.assertEqual(len(relocations), 1)
            self.assertIn('nfet_03v3', text)
            self.assertIn('pnp_05p00x05p00', text)

    def test_sky130_complete_corner_closure_imports_offline(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('offline')):
            r = review_project(ROOT/'examples/sky130-simulation/inverter.sch')
        self.assertEqual(r['errors'], [])
        exchange = r['candidate']['xschem_exchange']
        self.assertEqual(exchange['unresolved'], [])
        self.assertIn('sky130A', exchange['library_lock']['libraries'])
        self.assertGreater(sum(len(f['text']) for f in exchange['source_files'].values()), 30_000_000)


if __name__ == '__main__':
    unittest.main()
