import unittest

from scripts.verify_gf180_banba_physical import cdl, check_extracted, fix_pnp_technology


REFERENCE = '''.subckt banba_layout VDD VSS VREF
X_M VREF CTRL VSS VSS nfet_03v3 w=4u l=2u m=1 nf=1
X_Q VSS VSS VA pnp_05p00x05p00 m=1
X_R VA VREF VSS ppolyf_u_1k r_width=1u r_length=100u m=1
X_C VREF VSS cap_mim_2f0_m3m4_noshield c_width=90u c_length=90u m=1
.ends banba_layout
'''


class PhysicalReferenceTests(unittest.TestCase):
    def test_reader_keeps_terminal_order_and_geometry(self):
        text = cdl(REFERENCE)
        self.assertIn('Q_Q VSS VSS VA pnp_05p00x05p00', text)
        self.assertIn('R_R VA VREF VSS ppolyf_u_1k w=1e-06 l=0.0001', text)
        self.assertIn('C_C VREF VSS cap_mim_2f0_m3m4_noshield w=9e-05 l=9e-05', text)

    def test_multiplicity_is_never_silently_lost(self):
        for field in ('m=2', 'nf=2'):
            with self.assertRaisesRegex(ValueError, 'multiplicity'):
                cdl(REFERENCE.replace(field.split('=')[0]+'=1', field, 1))

    def test_symmetric_devices_and_extracted_junctions_are_accepted(self):
        extracted = REFERENCE.replace('VREF CTRL VSS VSS nfet', 'VSS CTRL VREF VSS nfet')
        extracted = extracted.replace('VA VREF VSS ppoly', 'VREF VA VSS ppoly')
        extracted = extracted.replace('w=4u l=2u', 'w=4u l=2u ad=3.2p pd=9.6u')
        extracted += 'C0 VREF VSS 0.23p\n'
        result = check_extracted(REFERENCE, extracted)
        self.assertEqual(result['devices'], 4)
        self.assertEqual(result['capacitances'], 1)
        self.assertAlmostEqual(result['total_capacitance_f']/1e-12, .23)

    def test_faults_are_rejected_before_simulation(self):
        faults = [REFERENCE.replace('VREF CTRL', 'VREF VSS'),
                  REFERENCE.replace('r_length=100u', 'r_length=99u'),
                  REFERENCE.replace('pnp_05p00x05p00', 'pnp_10p00x00p42'),
                  REFERENCE.replace('X_Q VSS VSS VA pnp_05p00x05p00 m=1\n', ''),
                  REFERENCE.replace('.subckt banba_layout VDD VSS VREF', '.subckt banba_layout VDD VSS'),
                  REFERENCE+'Cbad VREF VSS -1p\n']
        for faulty in faults:
            with self.subTest(fault=faulty), self.assertRaises(ValueError):
                check_extracted(REFERENCE, faulty)

    def test_pnp_patch_preserves_bounded_model_selection(self):
        text = '\n'.join('device msubcircuit '+name+' pnp pwell,space/w *pdiff error a2>'+lo+' a2<'+hi
            for name, lo, hi in [('pnp_10p00x00p42', '4.1', '4.3'), ('pnp_05p00x00p42', '2.0', '2.2'),
                                 ('pnp_10p00x10p00', '99.0', '101.0'), ('pnp_05p00x05p00', '24.0', '26.0')])
        fixed = fix_pnp_technology(text)
        self.assertIn('pnp_05p00x05p00 pnp *pdiff pwell,space/w a1>24.0 a1<26.0', fixed)
        self.assertEqual(fixed.count('device msubcircuit'), 4)
        with self.assertRaisesRegex(ValueError, 'declarations changed'):
            fix_pnp_technology(fixed)


if __name__ == '__main__':
    unittest.main()
