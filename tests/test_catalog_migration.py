"""Native catalog conversion must preserve model identity and circuit meaning."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from icstudio.model import clone,digest,save_project,load_project
from icstudio.pdks import PDKRegistry
from icstudio.native_migration import review_path
from icstudio.native_spice import netlist
from icstudio.catalog_migration import review
from tests.test_pdk_templates import install_fixture


def fixture(root,identifier='future-process'):
    registry=PDKRegistry(root/'registry');technology=registry.technology(registry.install(install_fixture(root/'pdk',identifier)))
    source=root/'source';source.mkdir()
    shutil.copyfile(root/'pdk/models.spice',source/'models.spice')
    (source/'n.sym').write_text('v {xschem version=3.4.7 file_version=1.2}\nK {type=nmos format="@name @pinlist nfet w=@w l=@l" template="name=X1 w=2 l=1"}\nB 5 18 -52 22 -48 {name=D dir=inout}\nB 5 -52 -2 -48 2 {name=G dir=inout}\nB 5 18 48 22 52 {name=S dir=inout}\nB 5 48 -2 52 2 {name=B dir=inout}\n')
    path=source/'top.sch';path.write_text('v {xschem version=3.4.7 file_version=1.2}\nS {.include models.spice}\nC {n.sym} 100 100 0 0 {name=X1 w=2 l=1}\n')
    return technology,path


class CatalogMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.tech,self.path=fixture(self.root);self.source=review_path(self.path)['candidate']

    def test_all_process_ids_use_same_conversion_with_real_native_bindings(self):
        for identifier in ('gf180mcuD','sky130A','ihp-sg13g2','future-process'):
            tech=clone(self.tech);tech['package_lock']['id']=identifier
            before=digest(self.source);record=review(self.source,tech);self.assertEqual(record['status'],'Complete',record['items'])
            self.assertEqual(digest(self.source),before);p=record['candidate'];d=p['cells'][0]['devices'][0];old=self.source['cells'][0]['devices'][0]
            self.assertEqual(d['kind'],'NMOS');self.assertNotIn('native_spice',d);self.assertEqual(d['model_ref']['pdk'],identifier)
            self.assertEqual(d['id'],old['id']);self.assertEqual(d['nets']['d'],old['nets']['D'])
            self.assertEqual(d['terminal_ids']['d'],old['terminal_ids']['D']);self.assertEqual(d['net_ids']['d'],old['net_ids']['D'])
            self.assertEqual(d['symbol']['pins']['g'],old['symbol']['pins']['G']);self.assertAlmostEqual(float(d['params']['w']),2e-6)
            text=netlist(p,self.root/identifier);line=next(s for s in text.splitlines() if s.startswith('X1 '))
            self.assertTrue(line.endswith('nfet w=2 l=1'),line)
            d['params']['w']='3u';self.assertIn('nfet w=3 l=1',netlist(p,self.root/(identifier+'-edited')))

    def test_complete_mode_blocks_unmatched_and_draft_preserves_original(self):
        tech=clone(self.tech);tech['simulation']['catalog']['nfet']['model']='different'
        record=review(self.source,tech);self.assertIsNone(record['candidate']);self.assertEqual(record['unmatched'],1)
        draft=review(self.source,tech,require_complete=False)['candidate']
        self.assertEqual(draft['cells'][0]['devices'][0]['native_spice'],self.source['cells'][0]['devices'][0]['native_spice'])

    def test_ambiguous_models_require_stable_explicit_choice(self):
        tech=clone(self.tech);tech['simulation']['catalog']['alias']=clone(tech['simulation']['catalog']['nfet'])
        self.assertIsNone(review(self.source,tech)['candidate'])
        record=review_path(self.path,technology=tech,choices={'top/X1':'alias'})
        self.assertEqual(record['candidate']['cells'][0]['devices'][0]['model_ref']['device'],'alias')

    def test_changed_model_source_or_parameter_contract_is_not_silently_accepted(self):
        p=clone(self.source);archive=p['native_migration']['archive'];source=next(a for a in archive['source_files'].values() if a['kind'].startswith('Model'))
        source['text']+='\n* changed';self.assertRaisesRegex(ValueError,'provenance',review,p,self.tech)
        tech=clone(self.tech);tech['simulation']['catalog']['nfet']['emit_parameters']['m']='m';tech['simulation']['catalog']['nfet']['parameters']['m']={'default':'1'}
        record=review(self.source,tech);self.assertIsNone(record['candidate']);self.assertIn('parameter sets differ',record['items'][0]['detail'])

    def test_save_reopen_and_netlist_do_not_need_original_pdk_or_schematic(self):
        p=review(self.source,self.tech)['candidate'];save_project(p,self.root/'native.icproj')
        shutil.rmtree(self.path.parent);shutil.rmtree(self.root/'registry');shutil.rmtree(self.root/'pdk')
        q=load_project(self.root/'native.icproj');self.assertIn('nfet w=2 l=1',netlist(q,self.root/'relocated'))
        q['pdk']['simulation']['catalog']['nfet']['model']='wrong'
        self.assertRaisesRegex(ValueError,'catalog changed',netlist,q,self.root/'wrong')

    def test_catalog_roundtrip_preserves_reference_and_accepts_width_edit(self):
        from icstudio.native_exchange import export_project,review_project
        p=review(self.source,self.tech)['candidate'];result=export_project(p,self.root/'exchange');path=Path(result['directory'])/result['top']
        record=review_project(path);self.assertEqual(record['errors'],[])
        self.assertEqual(record['candidate']['cells'][0]['devices'][0]['model_ref'],p['cells'][0]['devices'][0]['model_ref'])
        path.write_text(path.read_text().replace('w="2"','w="4"'))
        q=review_project(path);self.assertEqual(q['errors'],[])
        self.assertAlmostEqual(float(q['candidate']['cells'][0]['devices'][0]['params']['w']),4e-6)
        self.assertTrue(any(r['change']=='Changed' and r['object']=='X1' for r in q['changes']))
        row=next(r for r in q['changes'] if r['object']=='X1')
        self.assertEqual(json.loads(row['after'])['parameters']['w'],'4e-06')

    def test_exchange_after_original_registry_removed(self):
        from icstudio.native_exchange import export_project,review_project
        p=review(self.source,self.tech)['candidate'];shutil.rmtree(self.root/'registry')
        exported=export_project(p,self.root/'export');record=review_project(Path(exported['directory'])/exported['top'])
        self.assertEqual(record['errors'],[])

    def test_exchange_model_edits_require_a_new_migration_review(self):
        from icstudio.native_exchange import export_project,review_project
        p=review(self.source,self.tech)['candidate'];exported=export_project(p,self.root/'export')
        model=next((self.root/'export/models').glob('*.spice'));before=model.read_text();after=before.replace('.subckt nfet','.subckt altered_nfet',1)
        self.assertNotEqual(before,after);model.write_text(after)
        record=review_project(Path(exported['directory'])/exported['top'])
        self.assertIsNone(record['candidate']);self.assertIn('model files changed',record['errors'][0])

    def test_real_bundled_catalogs_preserve_models_units_lvs_and_live_formulas(self):
        from icstudio.bundled_pdks import packages
        from icstudio.catalog import binding_for,parameter_values
        from icstudio.catalog_migration import emit,symbol_context
        from icstudio.native_spice import render
        from icstudio.native_exchange import export_project,review_project
        registry=PDKRegistry(self.root/'real')
        for package in packages():
            technology=registry.technology(registry.install(Path(package['path'])/'package.json'))
            gf=package['family']=='gf180mcu'
            path=Path(__file__).resolve().parents[1]/('examples/gf180-bandgap/5vfullv2-original.sch' if gf else 'examples/sky130-simulation/inverter.sch')
            source=review_path(path)['candidate'];record=review(source,technology)
            self.assertEqual(record['unmatched'],0,record['items']);self.assertEqual(record['converted'],60 if gf else 2)
            p=record['candidate'];original={d['id']:d for c in source['cells'] for d in c['devices']}
            self.assertTrue(any(row['status']=='Needs attention' for row in record['items']))
            for cell in p['cells']:
                for d in cell['devices']:
                    if not d.get('model_ref'):continue
                    self.assertEqual(sorted(d['nets'].values()),sorted(original[d['id']]['nets'].values()))
                    if gf and original[d['id']]['native_spice'].get('lvs_tokens'):
                        from icstudio.spice_import import tokens,assignments
                        before=tokens(render(original[d['id']],mode='lvs'));after=tokens(emit(d,technology,'lvs'))
                        count=len(d['nets'])+2;self.assertEqual(before[:count],after[:count])
                        from icstudio.catalog import numeric_formula
                        values=assignments(after[count:])
                        self.assertEqual(set(values),set(assignments(before[count:])))
                        for k,v in assignments(before[count:]).items():self.assertAlmostEqual(numeric_formula(v,{})/numeric_formula(values[k],{}),1)
            d=next(d for c in p['cells'] for d in c['devices'] if d.get('model_ref') and d['kind']=='NMOS')
            entry=binding_for(technology,d);before=parameter_values(entry,d);d['params']['w']=str(float(d['params']['w'])*2)
            after=parameter_values(entry,d);self.assertAlmostEqual(after['ad'],before['ad']*2)
            self.assertAlmostEqual(float(symbol_context(d,technology)['W']),before['w']*2)
            netlist(p,self.root/(package['name']+'-deck'))
            # A small selection is sufficient to verify the catalog/LVS exchange path.
            if gf:
                exported=export_project(p,self.root/'real-exchange');record=review_project(Path(exported['directory'])/exported['top'])
                self.assertEqual(record['errors'],[],record['errors'])
                import os
                engine=os.environ.get('ICSTUDIO_TEST_XSCHEM')
                if engine:
                    from icstudio.external_tools import xschem_netlist
                    external=xschem_netlist(Path(exported['directory'])/exported['top'],self.root/'xschem-netlist',engine)
                    self.assertEqual(external['status'],'complete')


if __name__=='__main__':unittest.main()
