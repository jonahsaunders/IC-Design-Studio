"""RF default identity, saved-project isolation and unchanged public originals."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from icstudio.catalog import create_device, parameter_values
from icstudio.interchange import spice
from icstudio.model import clone, file_digest, save_project, load_project
from icstudio.pdks import PDKRegistry
from icstudio.project_hub import inventory, build_project
from scripts.prepare_sky130_rf_default import prepare, KEY, PREFIX, MODEL, PRIMITIVE, ROOT
from scripts.prepare_sky130_rf_qualification import prepare as candidate, public_sources, derivative
from scripts.sky130_rf_source import BASE, PROMOTED, REVISION, previous_rf
from scripts.prepare_sky130_esd_nvt import predecessor


class RFDefaultTests(unittest.TestCase):
    def test_only_reviewed_binding_changes_and_previous_candidate_rebuilds_identically(self):
        source=ROOT/'icstudio/assets/pdks/sky130A'
        with predecessor(source) as source, previous_rf(source) as old, tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);before=json.loads((old/'package.json').read_bytes())
            self.assertEqual(file_digest(old/'package.json'),BASE)
            result=prepare(source,folder/'rebuilt')
            self.assertEqual(result['manifest_sha256'],PROMOTED)
            self.assertEqual(result['revision'],REVISION)
            self.assertEqual((folder/'rebuilt/package.json').read_bytes(),(source/'package.json').read_bytes())
            after=json.loads((source/'package.json').read_bytes())
            for name,h in before['files'].items():self.assertEqual(file_digest(source/name),h,name)
            a,b=clone(before['technology']),clone(after['technology'])
            self.assertEqual({k for k,v in a['simulation']['catalog'].items() if b['simulation']['catalog'][k]!=v},{KEY})
            b['simulation']['catalog'][KEY]=a['simulation']['catalog'][KEY]
            self.assertEqual(b['simulation']['includes'].pop(),{'path':PREFIX+'library.spice'})
            a.pop('revision');b.pop('revision');self.assertEqual(a,b)
            candidate(old,folder/'old-candidate');candidate(source,folder/'new-candidate')
            self.assertEqual((folder/'old-candidate/package.json').read_bytes(),(folder/'new-candidate/package.json').read_bytes())
            lock,originals=public_sources()
            for name in (MODEL,PRIMITIVE):self.assertEqual((source/(PREFIX+'original/'+name)).read_bytes(),originals[name])
            self.assertEqual((source/(PREFIX+MODEL)).read_bytes(),derivative('ps2nw',originals[MODEL]))
            self.assertEqual(file_digest(source/(PREFIX+'LICENSE')),lock['license_sha256'])

    def test_fresh_placement_and_saved_old_project_are_separate(self):
        source=ROOT/'icstudio/assets/pdks/sky130A'
        with previous_rf(source) as old, tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);registry=PDKRegistry(folder/'registry');key=registry.install(old/'package.json')
            rows,notes=inventory(registry);self.assertEqual(notes,[])
            saved=build_project(registry,next(r for r in rows if r['key']==key),'Existing','empty')['project']
            save_project(saved,folder/'old.icproj')
            p=build_project(registry,next(r for r in rows if r['id']=='sky130A' and r['status']=='Available offline'),'New','empty')['project']
            self.assertEqual(p['pdk']['revision'],'47dbd4fe43bfa7e4')
            entry=p['pdk']['simulation']['catalog'][KEY];d=create_device(p['pdk'],KEY,'D1')
            d['model_params'].update(w=4,l=2);d['nets']={'d0':'A','d1':'K'};p['cells'][0]['devices']=[d]
            self.assertEqual(parameter_values(entry,d),dict(w=4,l=2,area=8,perim=12))
            self.assertIn('X_D1 A K sky130_fd_pr__model__parasitic__rf_diode_ps2nw area=8 perim=12',spice(p))
            for change in ({'area':4},{'perim':4},{'m':2},{'w':0},{'l':-1}):
                bad=clone(d);bad['model_params'].update(change)
                with self.assertRaises(ValueError):parameter_values(entry,bad)
            with self.assertRaises(ValueError):create_device(saved['pdk'],KEY,'D1')
            pwkey=KEY.replace('ps2nw','pw2dn')
            pw=create_device(p['pdk'],pwkey,'D2')
            self.assertEqual(parameter_values(p['pdk']['simulation']['catalog'][pwkey],pw),dict(w=2,l=2,area=4,perim=8))
            from scripts.sky130_pw2dn_source import predecessor as before_pw2dn
            with before_pw2dn(source) as esd:
                self.assertTrue(json.loads((esd/'package.json').read_bytes())['technology']['simulation']['catalog'][pwkey]['unavailable'])
            self.assertEqual(load_project(folder/'old.icproj')['pdk'],saved['pdk']);registry.verify(key)

    def test_unknown_and_changed_assets_cannot_be_published_or_reconstructed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);unknown=folder/'unknown';unknown.mkdir();(unknown/'package.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'exact reviewed'):prepare(unknown,folder/'out')
            self.assertFalse((folder/'out').exists())
            source=ROOT/'icstudio/assets/pdks/sky130A';changed=folder/'changed';shutil.copytree(source,changed)
            path=changed/(PREFIX+MODEL);path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'Changed current asset'):prepare(changed,folder/'out')
            self.assertFalse((folder/'out').exists())
            before=(source/'package.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'new'):prepare(source,source)
            self.assertEqual((source/'package.json').read_bytes(),before)


if __name__=='__main__':unittest.main()
