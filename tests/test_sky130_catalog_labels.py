import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

import klayout.db as k
from icstudio import digital_sky130_catalog_labels as subjects

ROOT=Path(__file__).resolve().parents[1]


class CatalogLabelTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')
        self.top.shapes(self.layout.layer(68,20)).insert(k.Box(0,0,1000,1000));self.path=self.root/'layout.gds'

    def audit(self):
        self.layout.write(str(self.path));return subjects.audit(self.path)

    def test_complete_absence_resolves_exactly_37_selected_messages(self):
        report=self.audit();self.assertEqual(report['counts'],{'absent-operand':37})
        self.assertEqual(len({r['id'] for r in report['rows']}),37)
        self.assertFalse(report['qualified']);self.assertFalse(report['chunk_complete'])
        self.assertEqual(subjects.evaluate(report,report['gds_sha256'],'control'),report)
        self.assertEqual(subjects.validate_saved(report,self.path),report)

    def test_every_floating_and_tie_token_reopens_its_four_messages_on_any_purpose(self):
        for name,selection in subjects.LABELS.items():
            for token in selection['tokens']:
                for pair in ((83,44),(1,99),(68,20)):
                    shapes=self.top.shapes(self.layout.layer(*pair));shapes.insert(k.Text('prefix_'+token.upper()+'_suffix',k.Trans()))
                    report=self.audit()
                    self.assertEqual({r['id'] for r in report['rows'] if r['disposition']=='unreviewed'},set(selection['ids']))
                    self.assertEqual(report['status'],'review-required');shapes.clear()

    def test_compatibility_and_whitespace_variants_prevent_false_absence(self):
        selection=subjects.LABELS['m1']
        for value in ('M1_FLOAT',' m1 _ float ','prefix_m1_tie_suffix','ｍ１＿ｆｌｏａｔ'):
            self.assertTrue(subjects.matches(value,selection),value)
        self.assertFalse(subjects.matches('ordinary_metal_pin',selection))

    def test_nested_array_labels_are_measured_outside_the_top_cell(self):
        child=self.layout.create_cell('child');child.shapes(self.layout.layer(66,5)).insert(k.Text('poly_float',k.Trans()))
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.R90,1000,1000),k.Vector(100,0),k.Vector(0,100),2,3))
        self.assertEqual(self.audit()['census']['labels']['poly'],6)

    def test_each_raw_target_reopens_only_its_own_messages(self):
        for name,selection in subjects.RAW.items():
            for shape in (k.Box(0,0,100,100),k.Text('present',k.Trans())):
                shapes=self.top.shapes(self.layout.layer(*selection['pair']));shapes.insert(shape)
                report=self.audit()
                self.assertEqual({r['id'] for r in report['rows'] if r['disposition']=='unreviewed'},set(selection['ids']))
                shapes.clear()

    def test_hierarchy_and_top_cell_names_both_prevent_part_number_absence(self):
        child=self.layout.create_cell('PARTNUM_A_block');self.top.insert(k.CellInstArray(child.cell_index(),k.Trans()))
        self.assertEqual(self.audit()['census']['cells']['partnum'],1)
        self.top.name='prefix_partnum_TOP';self.assertEqual(self.audit()['census']['cells']['partnum'],2)

    def test_other_purposes_do_not_substitute_for_the_literal_raw_target(self):
        for selection in subjects.RAW.values():
            layer,purpose=selection['pair'];self.top.shapes(self.layout.layer(layer,purpose+1)).insert(k.Box(0,0,100,100))
        self.assertEqual(self.audit()['counts'],{'absent-operand':37})

    def test_counts_and_complete_row_set_cannot_be_tampered_with(self):
        report=self.audit()
        for fault in ('row','count','source','status','qualified','missing-group','missing-subject','boolean','negative'):
            bad=copy.deepcopy(report)
            if fault=='row':bad['rows'].pop()
            elif fault=='count':bad['counts']['absent-operand']=38
            elif fault=='source':bad['source']['revision']='changed'
            elif fault=='status':bad['status']='PASS'
            elif fault=='qualified':bad['qualified']=True
            elif fault=='missing-group':bad['census'].pop('labels')
            elif fault=='missing-subject':bad['census']['labels'].pop('m1')
            elif fault=='boolean':bad['census']['labels']['m1']=False
            else:bad['census']['labels']['m1']=-1
            with self.subTest(fault=fault),self.assertRaises(ValueError):subjects.evaluate(bad,report['gds_sha256'],'control')
        with self.assertRaises(ValueError):subjects.evaluate(None,report['gds_sha256'],'control')

    def test_rebound_top_or_layout_identity_is_rejected(self):
        report=self.audit()
        for sha,top in (('a'*64,'control'),(report['gds_sha256'],'other')):
            with self.assertRaises(ValueError):subjects.evaluate(report,sha,top)

    def test_rehashed_layout_with_false_label_or_layer_absence_is_rejected(self):
        for pair,shape in (((83,44),k.Text('condiode',k.Trans())),((89,44),k.Box(0,0,100,100))):
            report=self.audit();shapes=self.top.shapes(self.layout.layer(*pair));shapes.insert(shape);self.layout.write(str(self.path))
            report['gds_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
            subjects.evaluate(report,report['gds_sha256'],'control')
            with self.assertRaisesRegex(ValueError,'actual layout'):subjects.validate_saved(report,self.path)
            shapes.clear()

    def test_unknown_top_set_or_grid_is_rejected(self):
        self.layout.dbu=.002
        with self.assertRaises(ValueError):self.audit()
        self.layout.dbu=.001;self.layout.create_cell('other')
        with self.assertRaises(ValueError):self.audit()

    def test_literal_bindings_match_primary_source_and_leave_unselected_messages_open(self):
        inventory=json.loads((ROOT/'docs/qualification/sky130-rule-inventory.json').read_bytes())
        catalog=json.loads((ROOT/'docs/qualification/sky130-error-rule-inventory.json').read_bytes())
        from scripts.sky130_rule_errors import validate
        validate(catalog);indexed={r['id']:r for r in catalog['rows']}
        with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as archive:
            sources={name:archive.read('sources/'+name) for name in subjects.SOURCE['files']}
        for name,digest in subjects.SOURCE['files'].items():
            self.assertEqual(hashlib.sha256(sources[name]).hexdigest(),digest)
            self.assertEqual(inventory['source_files'][name]['sha256'],digest)
        layers=list(csv.reader(io.StringIO(sources['docs/rules/gds_layers.csv'].decode())))
        aliases={'low_tap_density':'areaid.ld','injection':'areaid.ij','prune':'LVS prune','capm':'capm','cap2m':'cap2m','pad':'pad'}
        for name,entry in subjects.RAW.items():
            purpose='identifier' if name in ('low_tap_density','injection') else 'drawing'
            self.assertEqual([r[2] for r in layers if r and r[0]==aliases[name] and purpose in r[1].split(', ')],['%d:%d'%entry['pair']])
        for prefix,entry in subjects.LABELS.items():
            if prefix=='condiode':continue
            layer='met'+prefix[1:] if prefix.startswith('m') else prefix
            descriptions=[f'Floating {prefix}_float or {prefix}_tie text not over {layer}',
                f'{layer} marked with {prefix}_float not floating',
                f'Floating {layer} marked with {prefix}_tie at chiplevel without connecting',
                f'Metal on {layer} is texted as both tied and floating (Chip level)']
            for key,text in zip(entry['ids'],descriptions):
                self.assertEqual(indexed[key]['description'],text);self.assertEqual(indexed[key]['rule'],'x.22')
        for key,text in {'r1207':'condiode label must be in isolated pwell',
            's7':'partnum*block pcell should be used instead of partnum* pcells',
            'r380':'prune must overlap areaidMTorSC','r326':'0.42 min. enclosure of capm by moduleCutAREA',
            'r327':'0.42 min. spacing of moduleCutAREA & cap2m','r328':'0.42 min. enclosure of cap2m by moduleCutAREA',
            'r1404':'pad inside frame or moduleCut without text label',
            's72':'areaid.ld not allowed within 50.0 um of ESDID','s73':'areaid.ij not allowed within 150.0 um of ESDID'}.items():
            self.assertEqual(indexed[key]['description'],text)
        chosen={key for group in subjects.GROUPS.values() for entry in group.values() for key in entry['ids']}
        self.assertTrue(chosen.isdisjoint({'s0','s1','s2','s3','s4','s5','s6','s11','s16','s21','s26','s31','s36','s41'}))


if __name__=='__main__':unittest.main()
