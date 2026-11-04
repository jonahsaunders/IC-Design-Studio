"""MiM package isolation, historical reconstruction and real export semantics."""
import json
from pathlib import Path
import tempfile
import unittest

from icstudio.catalog import create_device
from icstudio.interchange import spice
from icstudio.model import clone, example, file_digest, save_project, load_project
from icstudio.pdks import PDKRegistry
from scripts.prepare_sky130_mim_binding import prepare, KEY
from scripts.sky130_mim_source import BASE, PROMOTED, REVISION, previous_mim

ROOT = Path(__file__).resolve().parents[1]


def project(tech, count=4):
    p = example('empty'); p['pdk'] = clone(tech)
    d = create_device(tech, KEY, 'C1'); d['model_params'].update(w=2, l=2, mf=count)
    d['nets'] = dict(c0='P', c1='N'); p['cells'][0]['devices'] = [d]
    return p


class Sky130MimBindingTests(unittest.TestCase):
    def test_scanner_corrects_only_exact_reviewed_sources(self):
        from icstudio.sky130_mim_binding import reviewed_parameters
        from icstudio.pdk_import import scan_local
        from scripts.prepare_sky130_mim_binding import SYMBOL,MODEL
        root=ROOT/'icstudio/assets/pdks/sky130A'
        symbol=(root/SYMBOL).read_bytes();model=(root/MODEL).read_bytes()
        old={'w':'w','l':'l','vm':'mf','m':'mf'};new={'w':'w','l':'l','mf':'mf','m':'mf'}
        self.assertEqual(reviewed_parameters(symbol,model,old),new)
        for s,m,e in ((symbol+b'\n',model,old),(symbol,model+b'\n',old),(symbol,model,new)):
            with self.assertRaisesRegex(ValueError,'Unreviewed'):reviewed_parameters(s,m,e)
        scanned=scan_local(root)['technology']['simulation']['catalog'][KEY]
        self.assertFalse(scanned['unavailable']);self.assertEqual(scanned['emit_parameters'],new)

    def test_rebuild_only_changes_reviewed_metadata_and_preserves_all_original_assets(self):
        source = ROOT/'icstudio/assets/pdks/sky130A'
        with previous_mim(source) as old, tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'rebuilt'; before = json.loads((old/'package.json').read_bytes())
            self.assertEqual(file_digest(old/'package.json'), BASE)
            result = prepare(source, out); after = json.loads((out/'package.json').read_bytes())
            self.assertEqual(result['manifest_sha256'], PROMOTED)
            self.assertEqual(result['revision'], REVISION)
            self.assertEqual({n:h for n,h in after['files'].items() if n in before['files']}, before['files'])
            for name, h in before['files'].items():self.assertEqual(file_digest(out/name), h)
            a, b = clone(before['technology']), clone(after['technology'])
            a.pop('revision'); b.pop('revision')
            first, second = a['simulation']['catalog'][KEY], b['simulation']['catalog'][KEY]
            self.assertEqual(first['emit_parameters'], {'w':'w','l':'l','vm':'mf','m':'mf'})
            self.assertEqual(second['emit_parameters'], {'w':'w','l':'l','mf':'mf','m':'mf'})
            second['emit_parameters'] = first['emit_parameters']; second['notes'] = first['notes']
            self.assertEqual(a, b)
            with self.assertRaisesRegex(ValueError, 'new'):prepare(source, out)

    def test_saved_old_and_fresh_projects_keep_distinct_mappings_and_physical_recipes(self):
        from icstudio.sky130_devices import install
        from icstudio.physical import connectivity
        source = ROOT/'icstudio/assets/pdks/sky130A'
        with previous_mim(source) as old, tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); registry = PDKRegistry(folder/'registry')
            original = registry.install(old/'package.json')
            older = project(registry.technology(original)); save_project(older, folder/'older.icproj')
            current = registry.install(source/'package.json'); self.assertNotEqual(original, current)
            for key, p, emitted in [(original,load_project(folder/'older.icproj'),'vm'), (current,project(registry.technology(current)),'mf')]:
                with self.subTest(revision=key):
                    line = next(s for s in spice(p).splitlines() if s.startswith('X_C1 '))
                    self.assertEqual(set(line.split()[4:]), {'w=2','l=2',emitted+'=4','m=4'})
                    cell=p['cells'][0];install(p,cell['id'],cell['devices'][0]['id'])
                    self.assertFalse(connectivity(p,cell['id'])['issues'])
            self.assertEqual(load_project(folder/'older.icproj')['pdk'], older['pdk'])
            registry.verify(original);registry.verify(current)

    def test_nonpositive_and_unknown_bindings_remain_rejected_and_fractional_mf_exports(self):
        source=ROOT/'icstudio/assets/pdks/sky130A';manifest=json.loads((source/'package.json').read_bytes())
        tech=clone(manifest['technology']);tech.update(package_root=str(source),package_lock={k:manifest[k] for k in ('id','revision','files')})
        p=project(tech,.5);self.assertIn('mf=0.5',spice(p));self.assertIn('m=0.5',spice(p))
        for count in (0,-1):
            p['cells'][0]['devices'][0]['model_params']['mf']=count
            with self.assertRaisesRegex(ValueError,'positive'):spice(p)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'package.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'exact reviewed'):prepare(folder,folder/'out')
            self.assertFalse((folder/'out').exists())


if __name__ == '__main__':unittest.main()
