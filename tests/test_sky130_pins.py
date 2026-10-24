"""Independent pin intent must constrain every physical stream correction."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as k
from icstudio.digital_sky130_pins import write, verify, validate_saved
from icstudio.digital_flow import artifact
from scripts.sky130_pin_coverage import audit


class PinExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target = self.root/'source.gds', self.root/'target.gds'
        self.ly = k.Layout(); self.ly.dbu = .001; self.top = self.ly.create_cell('test')
        self.top.shapes(self.ly.layer(70,20)).insert(k.Box(460,1000,2000,1300))
        self.top.shapes(self.ly.layer(70,16)).insert(k.Box(0,1000,800,1300))
        self.top.shapes(self.ly.layer(70,5)).insert(k.Text('clk',k.Trans(400,1150)))
        self.inventory = dict(schema=1, top='test', checkpoint_sha256='a'*64, die_nm=[0,0,5000,5000],
            ports=[dict(name='clk',net='clk',kind='SIGNAL',boxes=[dict(layer='met3',box_nm=[0,1000,800,1300])])])

    def run_export(self):
        self.ly.write(str(self.source))
        return write(self.source, self.target, self.inventory)

    def test_exact_missing_physical_metal_is_added(self):
        result = self.run_export()
        self.assertEqual(audit(self.source)['violations'],1)
        self.assertEqual(audit(self.target)['violations'],0)
        self.assertEqual(sum(row['added_area_nm2'] for row in result['layers']),138000)
        self.assertEqual(verify(self.source,self.target,self.inventory)['status'],'verified')
        out = k.Layout();out.read(str(self.target));top = out.top_cell()
        pins=k.Region(top.begin_shapes_rec(out.layer(70,16)))
        metal=k.Region(top.begin_shapes_rec(out.layer(70,20)))
        self.assertTrue((pins-metal).is_empty())

    def test_existing_pin_metal_is_unchanged(self):
        self.top.shapes(self.ly.layer(70,20)).insert(k.Box(0,1000,800,1300))
        result = self.run_export()
        self.assertEqual(sum(row['added_area_nm2'] for row in result['layers']),0)

    def test_pin_annotations_cannot_invent_metal(self):
        self.top.shapes(self.ly.layer(70,16)).insert(k.Box(800,1000,900,1300))
        with self.assertRaisesRegex(ValueError,'annotations differ'):self.run_export()

    def test_independent_pin_change_is_rejected(self):
        self.inventory['ports'][0]['boxes'][0]['box_nm'][2] = 900
        with self.assertRaisesRegex(ValueError,'annotations differ'):self.run_export()

    def test_wrong_label_is_rejected(self):
        self.top.shapes(self.ly.layer(70,5)).clear()
        self.top.shapes(self.ly.layer(70,5)).insert(k.Text('other',k.Trans(400,1150)))
        with self.assertRaisesRegex(ValueError,'labels differ'):self.run_export()

    def test_disconnected_routes_are_not_bridged(self):
        self.top.shapes(self.ly.layer(70,20)).insert(k.Box(0,1000,200,1300))
        with self.assertRaisesRegex(ValueError,'disconnected routed'):self.run_export()

    def test_missing_route_is_not_filled(self):
        self.top.shapes(self.ly.layer(70,20)).clear()
        with self.assertRaisesRegex(ValueError,'missing or disconnected'):self.run_export()

    def test_wrong_layer_or_grid_or_top_is_rejected(self):
        original = copy.deepcopy(self.inventory)
        for key, value in [('top','wrong'),('schema',2)]:
            self.inventory=copy.deepcopy(original);self.inventory[key]=value
            with self.assertRaises(ValueError):self.run_export()
        self.inventory=original;self.ly.dbu=.002
        with self.assertRaises(ValueError):self.run_export()

    def test_foreign_mask_change_fails_readback(self):
        self.run_export()
        out=k.Layout();out.read(str(self.target))
        out.top_cell().shapes(out.layer(65,20)).insert(k.Box(100,100,300,300));out.write(str(self.target))
        with self.assertRaisesRegex(ValueError,'Unexpected.*mask'):verify(self.source,self.target,self.inventory)

    def test_annotation_change_fails_readback(self):
        self.run_export()
        out=k.Layout();out.read(str(self.target));out.top_cell().shapes(out.layer(70,5)).clear();out.write(str(self.target))
        with self.assertRaisesRegex(ValueError,'annotation changed'):verify(self.source,self.target,self.inventory)

    def test_outside_die_is_rejected(self):
        self.inventory['die_nm']=[100,0,5000,5000]
        with self.assertRaisesRegex(ValueError,'outside.*die'):self.run_export()

    def test_pwell_pin_uses_the_published_substrate_definition(self):
        self.top.shapes(self.ly.layer(122,16)).insert(k.Box(2500,2500,2700,2700))
        self.run_export()
        self.assertEqual(audit(self.target)['violations'],0)
        self.top.shapes(self.ly.layer(64,20)).insert(k.Box(2400,2400,2800,2800))
        self.ly.write(str(self.source))
        rows={r['layer']:r for r in audit(self.source)['layers']}
        self.assertEqual(rows['pwell']['violations'],1)

    def test_nested_cell_pin_is_checked(self):
        child=self.ly.create_cell('child')
        child.shapes(self.ly.layer(68,16)).insert(k.Box(0,0,200,200))
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(3000,3000)))
        self.run_export()
        rows={r['layer']:r for r in audit(self.target)['layers']}
        self.assertEqual(rows['met1']['violations'],1)

    def saved_fixture(self):
        checkpoint=self.root/'design.odb';checkpoint.write_bytes(b'unit checkpoint identity')
        self.inventory['checkpoint_sha256']=artifact(self.root,checkpoint)['sha256']
        report=self.run_export()
        report['source']=artifact(self.root,self.source)
        files={'gds':self.target,'checkpoint':checkpoint,'sky130_pin_source':self.source}
        for key,content in [('sky130_pin_inventory',self.inventory),('sky130_pin_export',report)]:
            path=self.root/(key+'.json');path.write_text(json.dumps(content));files[key]=path
        worker=self.root/'worker.py';worker.write_text('# fixture worker identity\n');files['sky130_pin_worker']=worker
        return dict(artifacts={key:artifact(self.root,path) for key,path in files.items()})

    def test_saved_geometry_is_reconstructed(self):
        data=self.saved_fixture()
        self.assertEqual(validate_saved(data,self.root)['status'],'pin-metal-exported')

    def test_false_saved_area_claim_is_rejected(self):
        data=self.saved_fixture();path=self.root/data['artifacts']['sky130_pin_export']['path']
        report=json.loads(path.read_text());report['layers'][0]['added_area_nm2']=1;path.write_text(json.dumps(report))
        data['artifacts']['sky130_pin_export']=artifact(self.root,path)
        with self.assertRaisesRegex(ValueError,'geometry report differs'):validate_saved(data,self.root)

    def test_missing_saved_evidence_is_rejected(self):
        data=self.saved_fixture();del data['artifacts']['sky130_pin_source']
        with self.assertRaisesRegex(ValueError,'Incomplete'):validate_saved(data,self.root)

    def test_stale_gds_binding_is_rejected(self):
        data=self.saved_fixture();data['artifacts']['gds']=data['artifacts']['sky130_pin_source']
        with self.assertRaisesRegex(ValueError,'bindings differ'):validate_saved(data,self.root)

    def test_missing_or_changed_boundary_export_evidence_is_rejected(self):
        data=self.saved_fixture();path=self.root/data['artifacts']['sky130_pin_export']['path']
        original=json.loads(path.read_text())
        for change in ('missing','count'):
            report=copy.deepcopy(original)
            if change=='missing':del report['boundary_export']
            else:report['boundary_export']['removed_top_die_outlines']=1
            path.write_text(json.dumps(report));data['artifacts']['sky130_pin_export']=artifact(self.root,path)
            with self.assertRaisesRegex(ValueError,'boundary-export evidence'):validate_saved(data,self.root)


if __name__=='__main__':unittest.main()
