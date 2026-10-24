import tempfile,unittest
from pathlib import Path
from icstudio.model import example
from icstudio.layout import rect
from scripts.qualify_sky130_metal_resistor_layouts import audit_extracted,selected_reference,altered,MODELS
from scripts.qualify_ihp_resistor_layouts import regions


class Sky130MetalResistorTests(unittest.TestCase):
    def test_native_units_terminal_order_and_exact_geometry(self):
        for name in MODELS:
            with self.subTest(model=name),tempfile.TemporaryDirectory() as tmp:
                text=f'.subckt coupon R1 R2\nR0 R2 R1 sky130_fd_pr__res_generic_{name} w=2 l=5\n.ends\n';path=Path(tmp)/'native.cir';path.write_text(text)
                self.assertEqual(audit_extracted(path,name,2,5)['width_um'],2)
                self.assertIn(' w=2 l=5 m=1',selected_reference(name,2,5)['text'])
                for bad in (text.replace('w=2','w=2u'),text.replace('l=5','l=6'),text.replace('R2 R1','R1 R1'),text.replace('res_generic_'+name,'res_generic_bad'),text+text):
                    path.write_text(bad)
                    with self.assertRaises(ValueError):audit_extracted(path,name,2,5)

    def test_physical_faults_change_only_intended_conductor_and_keep_marker_ports(self):
        p=example('empty');p['pdk']['layers']=[dict(name='LI',gds=67,datatype=20),dict(name='RES',gds=67,datatype=13)]
        c=p['cells'][0];c['shapes']=[rect('LI',-1000,-3000,2000,6000),rect('RES',-1000,-2500,2000,5000)]
        c['layout_ports']=[dict(name='R1',layer='LI',point=[0,-2800]),dict(name='R2',layer='LI',point=[0,2800])]
        before=regions(p)
        for fault in ('terminal-open','terminal-short'):
            after=altered(p,'l1',fault);masks=regions(after)
            self.assertTrue((before[(67,13)]^masks[(67,13)]).is_empty());self.assertFalse((before[(67,20)]^masks[(67,20)]).is_empty())
            self.assertEqual(c['layout_ports'],after['cells'][0]['layout_ports'])
        self.assertEqual(MODELS['l1'][1],.29)


if __name__=='__main__':unittest.main()
