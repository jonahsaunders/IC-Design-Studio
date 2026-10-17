"""Keep semantic model terminals, fixed geometry and package revisions explicit."""
import json,tempfile,unittest
from pathlib import Path
from icstudio.model import clone,file_digest,save_project,load_project
from icstudio.catalog import parameter_values
from icstudio.interchange import export_xschem
from icstudio.xschem_io import import_package
from scripts.prepare_sky130_vpp_binding import prepare as vpp,correct as correct_vpp
from scripts.prepare_ihp_svaricap_binding import prepare as svaricap,correct as correct_svaricap
from scripts.qualify_four_terminal_capacitors import fixture
ROOT=Path(__file__).resolve().parents[1]


class FourTerminalTests(unittest.TestCase):
    def test_revised_packages_retain_assets_and_terminal_identity_through_handoff(self):
        for target,prepare,key in [('sky130A',vpp,'sky130_fd_pr/vpp_cap.sym'),('ihp-sg13g2',svaricap,'sg13g2_pr/sg13_svaricap.sym')]:
            source=ROOT/'icstudio/assets/pdks'/target;original=json.loads((source/'package.json').read_bytes())
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);record=prepare(source,root/'package');package=json.loads((root/'package/package.json').read_bytes())
                self.assertNotEqual(record['revision'],original['revision'])
                for name,h in original['files'].items():self.assertEqual(file_digest(root/'package'/name),h)
                tech=clone(package['technology']);tech.update(package_root=str(root/'package'),package_lock={k:package[k] for k in ('id','revision','files')})
                p=fixture(tech,target,0,.5,[]);save_project(p,root/'input.icproj')
                self.assertEqual(load_project(root/'input.icproj')['pdk']['revision'],record['revision'])
                export_xschem(p,root/'handoff');q,_=import_package(root/'handoff')
                from icstudio.catalog_migration import instance_name
                for d in p['cells'][0]['devices']:
                    if not d.get('model_ref'):continue
                    entry=tech['simulation']['catalog'][key]
                    after=next(a for a in q['cells'][0]['devices'] if a['name']==instance_name(d,entry))
                    self.assertEqual(after['nets'],d['nets']);self.assertEqual(after['model_ref'],d['model_ref'])
                    self.assertEqual(parameter_values(entry,after),parameter_values(entry,d))
                d=next(d for d in p['cells'][0]['devices'] if d.get('model_ref'));entry=tech['simulation']['catalog'][key]
                faults=[('w',2)] if target=='sky130A' else [('w','3.739u'),('w','9.741u'),('l','0.299u'),('l','0.801u'),('nx',0),('nx',11),('nx',1.5)]
                for name,value in faults:
                    bad=clone(d);bad['model_params'][name]=value
                    with self.subTest(parameter=name,value=value),self.assertRaises(ValueError):parameter_values(entry,bad)
                self.assertEqual(file_digest(source/'package.json'),record['original_manifest_sha256'])

    def test_unknown_models_cannot_change_binding(self):
        for target,key,correct in [('sky130A','sky130_fd_pr/vpp_cap.sym',correct_vpp),('ihp-sg13g2','sg13g2_pr/sg13_svaricap.sym',correct_svaricap)]:
            package=json.loads((ROOT/'icstudio/assets/pdks'/target/'package.json').read_bytes())
            entry=package['technology']['simulation']['catalog'][key];before=clone(entry)
            with self.assertRaisesRegex(ValueError,'Unreviewed'):correct(entry,b'changed source')
            self.assertEqual(entry,before)


if __name__=='__main__':unittest.main()
