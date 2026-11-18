import tempfile,unittest,json
from pathlib import Path
from icstudio.interchange import export_layout
from icstudio.sky130_flow import subcircuit,logic_metrics,native_project,run,TOP

class Sky130FlowTests(unittest.TestCase):
    def test_editable_inverter_exports_referenced_geometry_and_pin_labels(self):
        try:
            import klayout.db as db
        except ImportError:
            self.skipTest('KLayout Python bindings are unavailable.')
        reference=(f'.subckt {TOP} A VGND VNB VPB VPWR Y\n'
                   'XM0 Y A VGND VNB sky130_fd_pr__nfet_01v8 w=0.65 l=0.15\n'
                   'XM1 Y A VPWR VPB sky130_fd_pr__pfet_01v8_hvt w=1 l=0.15\n.ends\n')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'reference.gds'
            layout=db.Layout();layout.dbu=.001
            inverter=layout.create_cell(TOP);contact=layout.create_cell('contact')
            pin_layer=layout.layer(67,5);label_layer=layout.layer(67,16)
            contact.shapes(pin_layer).insert(db.Box(0,0,30,40))
            inverter.insert(db.CellInstArray(contact.cell_index(),db.Trans(100,200)))
            inverter.shapes(label_layer).insert(db.Text('A',db.Trans(115,220)))
            layout.write(str(source))

            project=native_project(root,reference,source,{})
            destination=root/'Export with spaces.gds'
            export_layout(project,destination)
            exported=db.Layout();exported.read(str(destination))
            exported_inverter=exported.cell(TOP)
            self.assertEqual([inst.cell.name for inst in exported_inverter.each_inst()],['contact'])
            pins=db.Region(exported_inverter.begin_shapes_rec(exported.find_layer(67,5)))
            self.assertEqual(pins.bbox(),db.Box(100,200,130,240))
            labels=exported_inverter.shapes(exported.find_layer(67,16))
            self.assertEqual([(s.text.string,s.text.x,s.text.y) for s in labels.each()],[('A',115,220)])

    def test_missing_assets_fail_closed_and_write_each_stage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);r=run(root/'absent',root/'run',ngspice='not-an-installed-tool',magic='not-an-installed-tool',netgen='not-an-installed-tool')
            self.assertEqual(r['status'],'blocked');self.assertEqual(r['stages'][0]['status'],'failed');self.assertTrue(all(s['status']=='not_run' for s in r['stages'][1:]));self.assertEqual(json.loads((root/'run/report.json').read_text()),r)
    def test_reference_parser_handles_continuations_without_guessing(self):
        text='.subckt '+TOP+' A VGND\n+ VNB VPB VPWR Y\nX0 VGND A Y VNB nfet w=0.65 l=0.15\n.ends\n'
        ports,body,source=subcircuit(text,TOP);self.assertEqual(ports,['A','VGND','VNB','VPB','VPWR','Y']);self.assertIn('nfet',body)
        with self.assertRaises(ValueError):subcircuit(text,'wrong')
    def test_logic_gate_rejects_flat_or_nonfinite_output(self):
        xs=[i*1e-10 for i in range(621)];vin=[1.8 if t>2e-9 and (t-2e-9)%20e-9<10e-9 else 0 for t in xs]
        for out in ([0]*len(xs),[float('nan')]*len(xs)):
            with self.assertRaises(ValueError):logic_metrics({'x':xs,'traces':{'vin':vin,'vout':out}})
