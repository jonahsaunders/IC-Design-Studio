"""Independent current gates, reviewed corrections and portable device identity."""
import json, math, tempfile, unittest
from pathlib import Path
from icstudio.model import clone, file_digest, load_project, save_project
from icstudio.catalog import parameter_values
from icstudio.interchange import export_xschem
from icstudio.xschem_io import import_package
from scripts.qualify_mos_variants import GROUPS, compare, fixture, probes
from scripts.prepare_mos_variant_bindings import prepare, correct_native, correct_clamp
from scripts.device_qualification_source import previous_devices
ROOT=Path(__file__).resolve().parents[1]


class MOSVariantTests(unittest.TestCase):
    def test_comparator_requires_complete_nonflat_reference_and_detects_current_fault(self):
        row=next(probes('ihp-mos'));x=[i*.03 for i in range(41)];tag='v'+row['tag']
        ref=dict(x=x,currents={tag+'d':[-v*1e-3 for v in x],tag+'s':[v*1e-3 for v in x],tag+'g':[0]*41,tag+'b':[0]*41})
        self.assertEqual(compare(ref,ref,[row],'dc')['status'],'PASS')
        bad=clone(ref);bad['currents'][tag+'d'][20]*=1.1
        self.assertEqual(compare(bad,ref,[row],'dc')['status'],'MISMATCH')
        for mutation in ('missing','nonfinite','domain','flat','conservation'):
            bad=clone(ref)
            if mutation=='missing':del bad['currents'][tag+'b']
            elif mutation=='nonfinite':bad['currents'][tag+'g'][0]=float('nan')
            elif mutation=='domain':bad['x'][-1]=1.21
            elif mutation=='flat':bad['currents']={k:[0]*41 for k in bad['currents']}
            else:bad['currents'][tag+'s'][20]=0
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):compare(ref,bad,[row],'dc')

    def test_exact_catalog_scope_includes_hidden_body_isolated_and_rf_views(self):
        self.assertEqual(sum(len(names) for _,names in GROUPS.values()),86)
        for group,(target,names) in GROUPS.items():
            p=json.loads((ROOT/'icstudio/assets/pdks'/target/'package.json').read_bytes())
            c=p['technology']['simulation']['catalog'];rows=list(probes(group))
            self.assertEqual(len(rows),2*len(names))
            for row in rows:
                self.assertIn(row['key'],c);self.assertFalse(c[row['key']]['unavailable'])
                self.assertEqual(set(row['pins']),set(c[row['key']]['pin_order']))

    def test_corrected_packages_preserve_sources_and_handoff_identity(self):
        for target,group in [('gf180mcuC','gf-c'),('gf180mcuD','gf-d'),('ihp-sg13g2','ihp-clamp')]:
            source=self.enterContext(previous_devices(ROOT/'icstudio/assets/pdks'/target));original=json.loads((source/'package.json').read_bytes())
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);record=prepare(source,root/'package');package=json.loads((root/'package/package.json').read_bytes())
                self.assertNotEqual(record['revision'],original['revision'])
                for name,h in original['files'].items():self.assertEqual(file_digest(root/'package'/name),h)
                tech=clone(package['technology']);tech.update(package_root=str(root/'package'),package_lock={k:package[k] for k in ('id','revision','files')})
                p=fixture(tech,group,'dc',[]);save_project(p,root/'input.icproj')
                self.assertEqual(load_project(root/'input.icproj')['pdk']['revision'],record['revision'])
                export_xschem(p,root/'exchange');q,_=import_package(root/'exchange')
                from icstudio.catalog_migration import instance_name
                for d in p['cells'][0]['devices']:
                    if not d.get('model_ref'):continue
                    entry=tech['simulation']['catalog'][d['model_ref']['device']]
                    after=next(a for a in q['cells'][0]['devices'] if a['name']==instance_name(d,entry))
                    self.assertEqual(after['nets'],d['nets']);self.assertEqual(after['model_ref'],d['model_ref'])
                    before_values,after_values=parameter_values(entry,d),parameter_values(entry,after)
                    self.assertEqual(before_values.keys(),after_values.keys())
                    # Xschem's decimal serialization retains twelve significant
                    # digits; binary float spellings need not be identical.
                    for k,v in before_values.items():self.assertTrue(math.isclose(v,after_values[k],rel_tol=5e-11,abs_tol=0),(k,v,after_values[k]))
                self.assertEqual(file_digest(source/'package.json'),record['original_manifest_sha256'])

    def test_unreviewed_source_cannot_silently_rebind_device(self):
        for target,key,correct in [('gf180mcuC','symbols/nfet_06v0_nvt.sym',correct_native),('ihp-sg13g2','sg13g2_pr/nmoscl_2.sym',correct_clamp)]:
            p=json.loads((ROOT/'icstudio/assets/pdks'/target/'package.json').read_bytes());entry=p['technology']['simulation']['catalog'][key];before=clone(entry)
            with self.assertRaisesRegex(ValueError,'Unreviewed'):correct(entry,b'changed symbol',b'changed model')
            self.assertEqual(entry,before)

    def test_fresh_import_uses_reviewed_native_model_and_simulation_pin_numbers(self):
        from icstudio.pdk_import import scan_local
        from icstudio.gf180_native_binding import reviewed_model
        with self.assertRaisesRegex(ValueError,'Unreviewed'):reviewed_model(b'changed symbol',b'changed model')
        gf=scan_local(ROOT/'icstudio/assets/pdks/gf180mcuC')['technology']['simulation']['catalog']
        self.assertEqual(gf['symbols/nfet_06v0_nvt.sym']['model'],'nfet_06v0_nvt')
        self.assertFalse(gf['symbols/nfet_06v0_nvt.sym']['unavailable'])
        ihp=scan_local(ROOT/'icstudio/assets/pdks/ihp-sg13g2')['technology']['simulation']['catalog']
        for name in ('nmoscl_2','nmoscl_4'):
            entry=ihp['sg13g2_pr/'+name+'.sym']
            self.assertEqual(entry['pin_order'],['vdd','vss']);self.assertFalse(entry['unavailable'])


if __name__=='__main__':unittest.main()
