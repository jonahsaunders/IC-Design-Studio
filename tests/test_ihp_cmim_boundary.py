"""Independent physical-netlist boundary and corruption controls."""
import unittest
from pathlib import Path
import tempfile
from scripts.ihp_cmim_boundary_audit import circuit
from scripts.check_ihp_cmim_boundary import geometry,member,native_fault


class BoundaryNetlistTests(unittest.TestCase):
    def test_actual_native_and_rotated_dimensions(self):
        text='.SUBCKT coupon C2 C1\nC$1 C1 C2 cap_cmim w=75u l=74.98u A=5623.5p P=299.96u m=1\n.ENDS coupon\n'
        self.assertEqual(circuit(text,74.98)['area_um2'],'5623.50')
        circuit(text.replace('w=75u l=74.98u','w=74.98u l=75u'),74.98)
        for altered in (text.replace('C1 C2 cap_cmim','C2 C1 cap_cmim'),text.replace('A=5623.5p','A=5623.6p'),
                text.replace('P=299.96u','P=299.97u'),text.replace('w=75u','w=76u'),text.replace('m=1','m=2'),
                text.replace('cap_cmim','other'),text.replace('.ENDS coupon','C$2 C1 C2 cap_cmim w=75u l=74.98u A=5623.5p P=299.96u m=1\n.ENDS coupon')):
            with self.subTest(text=altered),self.assertRaises(ValueError):circuit(altered,74.98)

    def test_native_open_and_short_controls_require_actual_connectivity(self):
        samples={'missing-contacts':'.SUBCKT coupon C2\nC$1 \\$4 C2 cap_cmim w=75u l=74.98u A=5623.5p P=299.96u m=1\n.ENDS coupon\n',
                 'plate-short':'.SUBCKT coupon C1|C2\nC$1 C1|C2 C1|C2 cap_cmim w=75u l=74.98u A=5623.5p P=299.96u m=1\n.ENDS coupon\n'}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.cir'
            for fault,text in samples.items():
                path.write_text(text);native_fault(path,fault)
                path.write_text(text.replace('cap_cmim','cap_other'))
                with self.assertRaises(ValueError):native_fault(path,fault)
                other='plate-short' if fault=='missing-contacts' else 'missing-contacts'
                path.write_text(text)
                with self.assertRaises(ValueError):native_fault(path,other)

    def test_source_paths_are_confined_before_access(self):
        root=Path(tempfile.gettempdir()).resolve()
        for path in ('../outside','dir/tmpuxoell2b/member','dir\\escape','C:escape'):
            with self.subTest(path=path),self.assertRaises(ValueError):member(root,path)

    def test_written_geometry_requires_rotation_labels_and_contact_array(self):
        try:import klayout.db as k
        except ImportError:self.skipTest('KLayout Python bindings are unavailable.')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'device.gds'
            def make(*,swap=False,short_array=False):
                ly=k.Layout();ly.dbu=.001;c=ly.create_cell('coupon')
                for layer,box in ((36,(-37500,-37490,37500,37490)),(67,(-38100,-38090,38100,38090)),(126,(-37300,-37290,37300,37290))):
                    c.shapes(ly.layer(layer,0)).insert(k.Box(*box))
                for x in range(-29000,29001,1000):
                    for y in range(-29000,29001,1000):
                        if short_array and x==0 and y==0:continue
                        c.shapes(ly.layer(129,0)).insert(k.Box(x,y,x+420,y+420))
                c.shapes(ly.layer(126,2)).insert(k.Text('C2' if swap else 'C1',k.Trans(0,0)))
                c.shapes(ly.layer(67,2)).insert(k.Text('C1' if swap else 'C2',k.Trans(37600,0)))
                ly.write(str(path))
            make();geometry(path,5623500000,75000,74980)
            with self.assertRaises(ValueError):geometry(path,5623500000,75000,74980,90)
            make(swap=True)
            with self.assertRaises(ValueError):geometry(path,5623500000,75000,74980)
            make(short_array=True)
            with self.assertRaises(ValueError):geometry(path,5623500000,75000,74980)


if __name__=='__main__':unittest.main()
