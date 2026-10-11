import json
from pathlib import Path
import tempfile
import unittest
from scripts.check_sky130_circuit_invariance import audit


DEVICE='device msubckt sky130_fd_pr__nfet_01v8 10 20 11 21 l=30 w=200 "VSS" "IN" 60 0 "VSS" 200 100,40 "OUT" 200 100,40\n'
DECAP='device msubckt sky130_fd_pr__nfet_01v8 100 200 101 201 l=600 w=100 "VSS" "VDD" 1200 0 "VSS" 0 0 "VSS" 200 100,40\n'
WARNING='box 100 200 700 300\nfeedback add "device missing 1 terminal;\n connecting remainder to node VSS" pale\n'
NATIVE='''scale 1000 1 500000
substrate "VSS" 0 0 0 0 pwell
node "VDD" 0 0 0 0 m1
node "IN" 50 2 10 20 m1
node "OUT" 60 3 30 40 m1
cap "IN" "OUT" 1.25
'''+DEVICE
INVENTORY=dict(nets=[dict(alias=name,sig_type=kind) for name,kind in
                     (('VSS','GROUND'),('VDD','POWER'),('IN','SIGNAL'),('OUT','SIGNAL'))])


class CircuitInvarianceTests(unittest.TestCase):
    def run_audit(self, filled, feedback='',original=NATIVE,original_feedback=''):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,data in (('original.ext',original),('filled.ext',filled),('original.feedback',original_feedback),('filled.feedback',feedback)):
                (root/name).write_text(data,encoding='ascii')
            return audit(root/'original.ext',root/'filled.ext',INVENTORY,root/'original.feedback',root/'filled.feedback')

    def test_identical_original_and_rail_decaps(self):
        result=self.run_audit(NATIVE+DECAP,WARNING)
        self.assertEqual(result['protected_capacitor_pairs'],3)
        self.assertEqual(result['added_rail_decaps'],1)
        self.assertEqual(result['explained_decap_warnings'],1)
        self.assertFalse(result['qualified']);self.assertFalse(result['chunk_complete'])
        self.assertEqual(self.run_audit(NATIVE)['status'],'native-circuit-identical')

    def test_arbitrarily_small_circuit_change_fails(self):
        with self.assertRaisesRegex(ValueError,'capacitance changed'):
            self.run_audit(NATIVE.replace('1.25','1.250000000000000000000000000001'))

    def test_new_fill_coupling_is_not_dropped(self):
        with self.assertRaisesRegex(ValueError,'capacitance changed'):
            self.run_audit(NATIVE+'node "FILL" 0 0 200 200 m1\ncap "IN" "FILL" 0.001\n')

    def test_resistance_and_scale_changes_fail(self):
        for before,after,message in (('"IN" 50','"IN" 51','resistance'),('1000 1 500000','1000 1 1000000','scale')):
            with self.subTest(message=message),self.assertRaisesRegex(ValueError,message):
                self.run_audit(NATIVE.replace(before,after))

    def test_original_devices_cannot_change(self):
        with self.assertRaisesRegex(ValueError,'device record'):
            self.run_audit(NATIVE.replace('l=30','l=31'))

    def test_additional_device_must_have_exact_decap_topology(self):
        for broken in (DECAP.replace('"VDD"','"OUT"'),DECAP.replace('"VSS" 200','"VDD" 200')):
            with self.subTest(device=broken),self.assertRaisesRegex(ValueError,'rail-only decap'):
                self.run_audit(NATIVE+broken,WARNING)

    def test_warning_must_match_added_device_and_terminal(self):
        for broken in ('',WARNING.replace('node VSS','node VDD'),WARNING.replace('box 100','box 99'),WARNING+WARNING):
            with self.subTest(feedback=broken),self.assertRaisesRegex(ValueError,'warnings'):
                self.run_audit(NATIVE+DECAP,broken)

    def test_unexplained_feedback_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unexplained'):
            self.run_audit(NATIVE,'box 0 0 10 10\nfeedback add "short" pale\n')
        with self.assertRaisesRegex(ValueError,'Original extraction'):
            self.run_audit(NATIVE,original_feedback=WARNING)

    def test_supply_only_changes_have_explicitly_limited_scope(self):
        result=self.run_audit(NATIVE+'cap "VDD" "VSS" 1000000\n')
        self.assertEqual(result['status'],'native-circuit-identical')
        self.assertIn('ideal supplies',result['scope'])
        self.assertFalse(result['qualified'])

    def test_missing_alias_duplicate_node_and_nan_are_rejected(self):
        for broken in (NATIVE.replace('node "IN" 50 2 10 20 m1\n',''),
                       NATIVE+'node "IN" 0 0 0 0 m1\n',
                       NATIVE.replace('1.25','NaN')):
            with self.subTest(native=broken),self.assertRaises(ValueError):self.run_audit(broken)

    def test_original_diode_and_resistor_records_are_preserved(self):
        diode='device ndiode sky130_fd_pr__diode_pw2nd_05v5 10 20 11 21 a=17388 p=528 "VSS" "OUT" 544 0 "VSS" 0 0\n'
        resistor='device devres sky130_fd_pr__res_generic_po 30 40 31 41 9 96 "VSS" 0 0 "IN" 96 27072,756 "OUT" 96 20256,614\n'
        original=NATIVE+diode+resistor
        self.assertEqual(self.run_audit(original,original=original)['original_devices'],3)
        for changed in (original.replace('a=17388','a=17389'),original.replace('9 96','10 96')):
            with self.assertRaisesRegex(ValueError,'device record'):self.run_audit(changed,original=original)
        with self.assertRaisesRegex(ValueError,'rail-only decap'):self.run_audit(NATIVE+diode)


if __name__=='__main__':unittest.main()
