import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
import zipfile

import klayout.db as k
from icstudio import digital_sky130_catalog_context as context
from icstudio.digital_sky130_boundaries import FORBIDDEN

ROOT=Path(__file__).resolve().parents[1]


class CatalogContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')
        self.top.shapes(self.layout.layer(68,20)).insert(k.Box(0,0,1000,1000))
        self.path=self.root/'layout.gds'

    def audit(self):
        self.layout.write(str(self.path));return context.audit(self.path)

    def test_empty_subjects_resolve_only_the_45_explicit_messages(self):
        report=self.audit()
        self.assertEqual(report['counts'],{'absent-operand':37,'executed-reviewed':8})
        self.assertEqual(len({r['id'] for r in report['rows']}),45)
        self.assertFalse(report['qualified']);self.assertFalse(report['chunk_complete'])
        self.assertEqual(context.evaluate(report,report['gds_sha256'],'control'),report)
        self.assertEqual(context.validate_saved(report,self.path),report)

    def test_present_core_geometry_or_text_never_claims_an_absent_selector(self):
        for shape in (k.Box(0,0,1000,1000),k.Text('core',k.Trans())):
            shapes=self.top.shapes(self.layout.layer(81,2));shapes.insert(shape)
            report=self.audit();self.assertEqual(report['status'],'review-required')
            self.assertEqual(report['counts'],{'unreviewed':34,'absent-operand':3,'executed-reviewed':8})
            self.assertTrue(all(r['disposition']=='unreviewed' for r in report['rows'] if r['subject']=='memory_core'))
            shapes.clear()

    def test_present_implant_reopens_its_enclosure_targets_and_prohibition(self):
        for shape in (k.Box(0,0,1000,1000),k.Text('implant',k.Trans())):
            shapes=self.top.shapes(self.layout.layer(11,44));shapes.insert(shape)
            report=self.audit();self.assertEqual(report['counts'],{'absent-operand':34,'unreviewed':3,'executed-reviewed':8})
            self.assertEqual({r['id'] for r in report['rows'] if r['disposition']=='unreviewed'},{'r1037','r1485','r1486'})
            shapes.clear()

    def test_standard_cells_and_a_floorplan_box_are_not_memory_core(self):
        self.top.shapes(self.layout.layer(81,4)).insert(k.Box(0,0,5000,5000))
        self.top.shapes(self.layout.layer(235,0)).insert(k.Box(0,0,5000,5000))
        self.assertEqual(self.audit()['counts']['absent-operand'],37)

    def test_nested_array_markers_are_counted(self):
        child=self.layout.create_cell('memory');child.shapes(self.layout.layer(81,2)).insert(k.Box(0,0,100,100))
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.R90,1000,1000),k.Vector(100,0),k.Vector(0,100),2,3))
        report=self.audit();self.assertEqual(report['raw_counts']['memory_core'],6)
        self.assertEqual(report['counts']['unreviewed'],34)

    def test_each_forbidden_boundary_is_a_failure_not_an_unreviewed_waiver(self):
        for pair in FORBIDDEN:
            shapes=self.top.shapes(self.layout.layer(*pair));shapes.insert(k.Text('forbidden',k.Trans()))
            with self.subTest(pair=pair),self.assertRaisesRegex(ValueError,'Forbidden'):self.audit()
            shapes.clear()

    def test_tampered_missing_or_rebound_reports_are_rejected(self):
        report=self.audit()
        for fault in ('source','row','count','status','qualified','missing-raw','negative','boolean'):
            bad=copy.deepcopy(report)
            if fault=='source':bad['source']['revision']='changed'
            elif fault=='row':bad['rows'].pop()
            elif fault=='count':bad['counts']['absent-operand']=38
            elif fault=='status':bad['status']='PASS'
            elif fault=='qualified':bad['qualified']=True
            elif fault=='missing-raw':bad['raw_counts'].pop('memory_core')
            elif fault=='negative':bad['raw_counts']['memory_core']=-1
            else:bad['raw_counts']['memory_core']=False
            with self.subTest(fault=fault),self.assertRaises(ValueError):context.evaluate(bad,report['gds_sha256'],'control')
        for value,sha,top in ((None,report['gds_sha256'],'control'),(report,'0'*64,'control'),(report,report['gds_sha256'],'other')):
            with self.assertRaises(ValueError):context.evaluate(value,sha,top)

    def test_a_rehashed_layout_cannot_keep_a_false_absence_claim(self):
        report=self.audit();self.top.shapes(self.layout.layer(81,2)).insert(k.Box(0,0,100,100));self.layout.write(str(self.path))
        report['gds_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        context.evaluate(report,report['gds_sha256'],'control')
        with self.assertRaisesRegex(ValueError,'actual layout'):context.validate_saved(report,self.path)

    def test_unknown_hierarchy_or_grid_is_rejected(self):
        self.layout.dbu=.002
        with self.assertRaisesRegex(ValueError,'database unit'):self.audit()
        self.layout.dbu=.001;self.layout.create_cell('other')
        with self.assertRaisesRegex(ValueError,'one top'):self.audit()

    def test_every_binding_matches_the_pinned_primary_source(self):
        inventory=json.loads((ROOT/'docs/qualification/sky130-rule-inventory.json').read_bytes())
        catalog=json.loads((ROOT/'docs/qualification/sky130-error-rule-inventory.json').read_bytes())
        from scripts.sky130_rule_errors import validate
        validate(catalog);indexed={r['id']:r for r in catalog['rows']}
        self.assertEqual(context.SOURCE['revision'],inventory['source_revision'])
        with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as archive:
            source={name:archive.read('sources/'+name) for name in context.SOURCE['files']}
        for name,digest in context.SOURCE['files'].items():
            self.assertEqual(hashlib.sha256(source[name]).hexdigest(),digest)
            self.assertEqual(inventory['source_files'][name]['sha256'],digest)
        descriptions=list(csv.reader(io.StringIO(source['docs/rules/layers/table-c4b-layer-description.csv'].decode())))
        row=next(r for r in descriptions if r and r[0]=='areaid.ce{81:2}')
        self.assertEqual(row[1:4],['areaid core','areaid.cor','Memory core (memory cells and approved on-pitch only)'])
        layers=list(csv.reader(io.StringIO(source['docs/rules/gds_layers.csv'].decode())))
        self.assertEqual([r[:3] for r in layers if r and r[0]=='ldntm'],[['ldntm','drawing','11:44']])
        self.assertEqual(len(context.CORE_IDS),33)
        for key in context.CORE_IDS:self.assertRegex(indexed[key]['description'],r'\bin (core|COREID)\b')
        expected={'r1132':'Unapproved cells contain areaid.ce layer','r1037':'ldntm not allowed outside areaid.ce',
            'r1485':'0 min. enclosure of ldntm by CLNTM','r1486':'ldntm must be enclosed by CLNTM'}
        for key,text in expected.items():self.assertEqual(indexed[key]['description'],text)
        chosen={key for item in context.SUBJECTS.values() for key in item['ids']}
        self.assertTrue(chosen.isdisjoint({'r258','r411','r471','r487','r520','r521','r1035','r1481','r1482'}))


if __name__=='__main__':unittest.main()
