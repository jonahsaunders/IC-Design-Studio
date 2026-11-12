import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_boundaries as boundary
from icstudio import digital_sky130_pins as pins
from icstudio.digital_flow import artifact
from icstudio.model import file_digest


class BoundaryExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'source.gds';self.target=self.root/'final.gds'
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')
        self.top.shapes(self.layout.layer(70,20)).insert(k.Box(0,1000,2000,1300))
        self.top.shapes(self.layout.layer(70,16)).insert(k.Box(0,1000,800,1300))
        self.top.shapes(self.layout.layer(70,5)).insert(k.Text('clk',k.Trans(400,1150)))
        self.inventory=dict(schema=1,top='control',checkpoint_sha256='a'*64,die_nm=[0,0,5000,5000],
            ports=[dict(name='clk',net='clk',kind='SIGNAL',boxes=[dict(layer='met3',box_nm=[0,1000,800,1300])])])

    def outline(self,box=None):
        self.top.shapes(self.layout.layer(*boundary.OUTLINE)).insert(k.Box(*(box or self.inventory['die_nm'])))

    def write(self):
        self.layout.write(str(self.source));digest=file_digest(self.source)
        result=pins.write(self.source,self.target,self.inventory)
        self.assertEqual(file_digest(self.source),digest)
        return result

    def test_exact_die_outline_is_removed_and_other_purposes_are_preserved(self):
        self.outline();self.top.shapes(self.layout.layer(235,0)).insert(k.Box(0,0,5000,5000))
        report=self.write();self.assertEqual(report['schema'],2)
        self.assertEqual(report['boundary_export']['removed_top_die_outlines'],1)
        self.assertEqual(sum(row['added_area_nm2'] for row in report['layers']),0)
        self.assertTrue(all(row['raw_shapes']==0 for row in boundary.validate_delivery(self.target)))
        out=k.Layout();out.read(str(self.target))
        self.assertEqual(out.top_cell().shapes(out.layer(235,0)).size(),1)
        self.assertEqual(pins.verify(self.source,self.target,self.inventory)['boundary_export'],report['boundary_export'])

    def test_clean_stream_is_accepted_without_inventing_an_outline(self):
        self.assertEqual(self.write()['boundary_export']['removed_top_die_outlines'],0)

    def test_wrong_die_outline_is_not_removed(self):
        self.outline([0,0,4999,5000])
        with self.assertRaisesRegex(ValueError,'independently captured'):self.write()

    def test_multiple_or_nested_outlines_are_rejected(self):
        self.outline();self.outline()
        with self.assertRaisesRegex(ValueError,'multiple'):self.write()
        self.top.shapes(self.layout.layer(*boundary.OUTLINE)).clear()
        child=self.layout.create_cell('child');child.shapes(self.layout.layer(*boundary.OUTLINE)).insert(k.Box(0,0,5000,5000))
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans()))
        with self.assertRaisesRegex(ValueError,'nested'):self.write()

    def test_text_or_nonrectangular_outline_is_rejected(self):
        shapes=self.top.shapes(self.layout.layer(*boundary.OUTLINE))
        shapes.insert(k.Text('not a die',k.Trans()))
        with self.assertRaisesRegex(ValueError,'independently captured'):self.write()
        shapes.clear();shapes.insert(k.Polygon([k.Point(0,0),k.Point(5000,0),k.Point(5000,5000)]))
        with self.assertRaisesRegex(ValueError,'independently captured'):self.write()

    def test_each_other_forbidden_purpose_is_rejected_including_raw_text(self):
        for pair in boundary.FORBIDDEN:
            if pair==boundary.OUTLINE:continue
            shapes=self.top.shapes(self.layout.layer(*pair))
            for shape in (k.Box(0,0,100,100),k.Text('annotation',k.Trans())):
                shapes.insert(shape)
                with self.assertRaisesRegex(ValueError,'poly/diff/tap'):self.write()
                shapes.clear()

    def test_each_forbidden_output_purpose_fails_independent_delivery_check(self):
        for pair in boundary.FORBIDDEN:
            shapes=self.top.shapes(self.layout.layer(*pair));shapes.insert(k.Box(0,0,100,100))
            self.layout.write(str(self.source))
            with self.assertRaisesRegex(ValueError,'Forbidden'):boundary.validate_delivery(self.source)
            shapes.clear()

    def test_restored_outline_or_lost_manufacturing_shape_fails_readback(self):
        self.outline();self.write()
        out=k.Layout();out.read(str(self.target));out.top_cell().shapes(out.layer(*boundary.OUTLINE)).insert(k.Box(0,0,5000,5000))
        out.write(str(self.target))
        with self.assertRaisesRegex(ValueError,'Forbidden'):pins.verify(self.source,self.target,self.inventory)
        self.write();out=k.Layout();out.read(str(self.target));out.top_cell().shapes(out.layer(70,20)).clear();out.write(str(self.target))
        with self.assertRaisesRegex(ValueError,'mask change'):pins.verify(self.source,self.target,self.inventory)

    def test_missing_correction_claim_cannot_bypass_current_sky130_delivery(self):
        self.outline();self.layout.write(str(self.source))
        data=dict(platform=dict(name='sky130hd'),artifacts=dict(gds=artifact(self.root,self.source)))
        with self.assertRaisesRegex(ValueError,'Forbidden'):pins.validate_saved(data,self.root)
        data['platform']['name']='ihp-sg13g2';self.assertIsNone(pins.validate_saved(data,self.root))
        self.write();data['platform']['name']='sky130hd';data['artifacts']['gds']=artifact(self.root,self.target)
        self.assertIsNone(pins.validate_saved(data,self.root))

    def test_source_bindings_match_all_eight_literal_catalog_messages(self):
        root=Path(__file__).resolve().parents[1]
        from scripts.sky130_rule_errors import validate
        catalog=json.loads((root/'docs/qualification/sky130-error-rule-inventory.json').read_bytes());validate(catalog)
        inventory=json.loads((root/'docs/qualification/sky130-rule-inventory.json').read_bytes())
        self.assertEqual(boundary.SOURCE['sha256'],inventory['source_files'][boundary.SOURCE['path']]['sha256'])
        self.assertEqual(boundary.SOURCE['revision'],inventory['source_revision'])
        indexed={row['id']:row for row in catalog['rows']}
        names={(235,4):'prBoundary',(66,4):'poly',(65,4):'diff',(65,60):'tap'}
        for pair,ids in boundary.FORBIDDEN.items():
            for key in ids:
                self.assertEqual(indexed[key]['description'],names[pair]+'.boundary not allowed in layout')
                self.assertEqual(indexed[key]['rule'],'metblk.6' if pair==boundary.OUTLINE else 'metblk.7')


if __name__=='__main__':unittest.main()
