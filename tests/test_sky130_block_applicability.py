import unittest
from scripts.sky130_block_applicability import review_row, selector_for


def row(rule,flags=(),value='',source='p018-x_dotdash.csv'):
    return dict(rule=rule,flags=list(flags),value=value,source='docs/rules/periphery/'+source,
                record=1,id='fixture#1',source_sha256='a'*64)


class ApplicabilityTests(unittest.TestCase):
    def test_absent_operand_requires_measured_zero(self):
        rule=row('x.13')
        self.assertEqual(review_row(rule,{'(81, 2)':0})['disposition'],'absent-operand')
        for counts in ({},{'(81, 2)':1},{'(81, 2)':None}):
            self.assertEqual(review_row(rule,counts)['disposition'],'execution-review-required')

    def test_multiple_operands_are_all_required(self):
        rule=row('nsm.3');good={'(61, 20)':0,'(22, 0)':0}
        self.assertEqual(review_row(rule,good)['disposition'],'absent-operand')
        for key in good:
            self.assertEqual(review_row(rule,{**good,key:1})['disposition'],'execution-review-required')
            self.assertEqual(review_row(rule,{k:v for k,v in good.items() if k!=key})['disposition'],'execution-review-required')

    def test_missing_threshold_is_not_a_pass(self):
        result=review_row(row('x.20'),{})
        self.assertEqual(result['disposition'],'definition-required')
        self.assertEqual(result['witnesses'],{})

    def test_rc_rules_remain_required(self):
        for flags,expected in ((['RC'],'execution-review-required'),(['RR'],'advisory'),
                               (['NC'],'advisory'),(['CU','IR'],'other-backend'),(['AL'],'execution-review-required')):
            self.assertEqual(review_row(row('unmapped',flags),{})['disposition'],expected)

    def test_frame_exclusion_requires_both_identifiers_absent(self):
        rule=row('x.12d',['F']);good={'(81, 10)':0,'(81, 12)':0}
        self.assertEqual(review_row(rule,good)['disposition'],'absent-operand')
        for key in good:
            self.assertEqual(review_row(rule,{**good,key:1})['disposition'],'execution-review-required')

    def test_enclosure_does_not_inherit_absent_valid_geometry(self):
        self.assertEqual(selector_for(row('licon.1b')),('prec_resistor',))
        self.assertEqual(review_row(row('licon.1b'),{'prec_resistor':1,'slotted_licon':0})['disposition'],'execution-review-required')
        # RF-device enclosure cannot be dismissed simply because DNW is absent.
        self.assertIsNone(selector_for(row('dnwell.6')))
        self.assertEqual(review_row(row('dnwell.6'),{'(64, 18)':0})['disposition'],'execution-review-required')

    def test_new_rule_has_no_automatic_exemption(self):
        self.assertEqual(review_row(row('dnwell.future'),{'(64, 18)':0})['disposition'],'execution-review-required')
        self.assertEqual(review_row(row('unknown',value='N/A'),{})['disposition'],'upstream-na')

    def test_absent_enclosure_layer_does_not_exempt_enclosed_operand(self):
        self.assertEqual(review_row(row('nwell.6'),{'(64, 18)':0,'nwell_holes':1})['disposition'],'execution-review-required')
        self.assertEqual(review_row(row('nwell.6'),{'nwell_holes':0})['disposition'],'absent-operand')
        self.assertEqual(review_row(row('x.26'),{'(81, 1)':0,'advSeal_6um_cells':1})['disposition'],'execution-review-required')

    def test_hv_well_proof_includes_thin_oxide_hv_well_marker(self):
        for name in ('hvnwell.8','hvdifftap.17','hvdifftap.18','hvdifftap.20'):
            with self.subTest(rule=name):
                rule=row(name);both={'(75, 20)':0,'(81, 63)':0}
                self.assertEqual(review_row(rule,both)['disposition'],'absent-operand')
                for marker in both:
                    self.assertEqual(review_row(rule,{**both,marker:1})['disposition'],'execution-review-required')
                    self.assertEqual(review_row(rule,{k:v for k,v in both.items() if k!=marker})['disposition'],'execution-review-required')

    def test_missing_device_or_voltage_tag_is_not_an_absence_proof(self):
        for name in ('lvtn.4b','ncm.3','ncm.4','hvnwell.11','hv.X.1','hv.X.4','vhvi.3.-','vhvi.4.-','vhvi.vhv.5'):
            with self.subTest(rule=name):
                self.assertIsNone(selector_for(row(name)))
                self.assertEqual(review_row(row(name),{'(75, 20)':0,'(125, 44)':0,'(92, 44)':0,'(74, 21)':0})['disposition'],'execution-review-required')

    def test_precision_resistor_requirements_use_device_operand(self):
        for name in ('rpm.1b','rpm.1g','rpm.3','rpm.4','rpm.5','rpm.9'):
            with self.subTest(rule=name):
                self.assertEqual(selector_for(row(name)),('prec_resistor',))
                self.assertEqual(review_row(row(name),{'(86, 20)':0,'prec_resistor':1})['disposition'],'execution-review-required')
                self.assertEqual(review_row(row(name),{'prec_resistor':0})['disposition'],'absent-operand')

    def test_geometry_specific_hv_rules_require_their_own_operands(self):
        examples={'hvntm.3':(75,20),'hvntm.4':(125,20),'denmos.10':(81,57),
                  'depmos.8':(81,57),'rfdiode.3.-':(81,125),'vhvi.5.-':(74,21)}
        for name,pair in examples.items():
            with self.subTest(rule=name):
                self.assertEqual(review_row(row(name),{str(pair):0})['disposition'],'absent-operand')
                self.assertEqual(review_row(row(name),{str(pair):1})['disposition'],'execution-review-required')
                self.assertEqual(review_row(row(name),{})['disposition'],'execution-review-required')


if __name__=='__main__':unittest.main()
