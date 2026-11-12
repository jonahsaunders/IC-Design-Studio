"""Focused checks for the finite CMIM physical multiplicity reader."""
import unittest
from scripts.check_ihp_cmim_multiplicity import extracted_conversion, native, netlist, source_inventory

class MultiplicityControls(unittest.TestCase):
    def test_source_inventory_rejects_missing_helper(self):
        expected={'icstudio/model.py','scripts/helper.py'}
        source_inventory(expected,{'icstudio/model.py':'a','scripts/helper.py':'b'})
        with self.assertRaises(ValueError):source_inventory(expected,{'icstudio/model.py':'a'})

    def test_comparison_input_preserves_raw_units_after_port_reorder(self):
        raw='.SUBCKT coupon C2 C1\nC$1 C1 C2 cap_cmim w=7u l=7u A=49p P=28u m=1\n.ENDS coupon\n'
        converted=raw.replace('coupon C2 C1','coupon C1 C2')
        proof={'top_port_order':{'before':['C2','C1'],'after':['C1','C2']},'interface_conversion':[]}
        extracted_conversion(raw,converted,proof)
        for altered in (converted.replace('A=49p','A=50p'),converted.replace('C1 C2 cap_cmim','C2 C1 cap_cmim')):
            with self.assertRaises(ValueError):extracted_conversion(raw,altered,proof)

    def test_uncombined_two_unit_circuit_rejects_lumping_or_changed_units(self):
        unit='C$1 C1 C2 cap_cmim w=7u l=7u A=49p P=28u m=1'
        raw='.SUBCKT coupon C2 C1\n'+unit+'\n'+unit.replace('$1','$2')+'\n.ENDS coupon\n'
        native(raw)
        for broken in (raw.replace(unit+'\n','',1),raw.replace('A=49p','A=50p',1),
                       raw.replace('C$2 C1 C2','C$2 C2 C1'),raw.replace('m=1','m=2',1),
                       raw.replace('C$2','C$1')):
            with self.subTest(broken=broken),self.assertRaises(ValueError):native(broken)

    def test_catalog_m2_and_two_explicit_units_have_per_unit_geometry(self):
        x='.subckt coupon C1 C2\nX_C1 C1 C2 cap_cmim l=7e-6 m=2 mm_ok=1 w=7e-6\n.ends coupon\n'
        c='.subckt coupon C1 C2\nCX_C1 C1 C2 cap_cmim w=7e-6 l=7e-6 m=2 A=4.9e-11 P=28e-6\n.ends coupon\n'
        netlist(x,'m2');netlist(c,'m2',True)
        pair=x.replace('m=2','m=1').replace('.ends','X_C2 C1 C2 cap_cmim l=7e-6 m=1 mm_ok=1 w=7e-6\n.ends')
        netlist(pair,'pair')
        for broken in (c.replace('A=4.9e-11','A=9.8e-11'),c.replace('m=2','m=1.5'),
                       pair.replace('X_C2 C1 C2','X_C2 C2 C1'),pair.replace('.ends','.include x\n.ends')):
            with self.subTest(broken=broken),self.assertRaises(ValueError):
                netlist(broken,'m2' if broken.startswith(c[:20]) and 'CX_C1' in broken else 'pair','CX_C1' in broken)

if __name__=='__main__':unittest.main()
