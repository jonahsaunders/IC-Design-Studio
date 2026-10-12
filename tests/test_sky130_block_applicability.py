import unittest
from scripts.sky130_block_applicability import review_row, selector_for, named_cell_counts, tap_interactions
import klayout.db as k


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

    def test_photodiode_review_requires_both_drawn_inputs_absent(self):
        for i in range(1,12):
            r=row('photo.'+str(i));good={'(64, 18)':0,'(81, 81)':0}
            self.assertEqual(review_row(r,good)['disposition'],'absent-operand')
            for key in good:
                self.assertEqual(review_row(r,{**good,key:1})['disposition'],'execution-review-required')
                self.assertEqual(review_row(r,{k:v for k,v in good.items() if k!=key})['disposition'],'execution-review-required')

    def test_named_cell_exceptions_use_published_names(self):
        cases=(('li.1a.-','li_vpp_exception_cells','s8rf2_xcmvpp_hd5_test'),
               ('m1.4a','m1_contact_exception_cells','s8fs_cmux4_fm'),
               ('licon.11c','phv_contact_exception_cells','s8fs_hvrsw_x4'),
               ('licon.11d','nshort_contact_exception_cells','s8fs_rdec32'))
        for rule,key,name in cases:
            self.assertEqual(review_row(row(rule),named_cell_counts(['sky130_fd_sc_hd__inv_1']))['disposition'],'absent-operand')
            self.assertEqual(review_row(row(rule),named_cell_counts([name]))['disposition'],'execution-review-required')
            self.assertEqual(named_cell_counts([name])[key],1)
            self.assertEqual(review_row(row(rule),{})['disposition'],'execution-review-required')
        self.assertEqual(named_cell_counts(['s8fs_cmux4_fm_unlisted'])['m1_contact_exception_cells'],0)

    def test_module_via_options_are_not_blanket_via_exemptions(self):
        for rule in ('via.1b','via.4b','via.4c','via.5b','via.5c','via2.1d','via2.4a','via3.1a'):
            self.assertEqual(review_row(row(rule),{'(81, 10)':0})['disposition'],'absent-operand')
            self.assertEqual(review_row(row(rule),{'(81, 10)':1})['disposition'],'execution-review-required')
            self.assertEqual(review_row(row(rule),{})['disposition'],'execution-review-required')
        for rule in ('via.1a','via.4a','via2.1a','via3.1'):
            self.assertEqual(review_row(row(rule),{'(81, 10)':0})['disposition'],'execution-review-required')

    def test_optional_targets_use_their_actual_identifiers(self):
        for rule,key in (('x.2a','(81, 79)'),('x.2c','(74, 22)'),('poly.1b','(125, 44)'),('licon.10','Var_channel')):
            self.assertEqual(review_row(row(rule),{key:0})['disposition'],'absent-operand')
            self.assertEqual(review_row(row(rule),{key:1})['disposition'],'execution-review-required')
            self.assertEqual(review_row(row(rule),{})['disposition'],'execution-review-required')

    def test_non_gate_label_warning_does_not_exempt_floating_connectivity(self):
        self.assertEqual(review_row(row('x.17'),{})['disposition'],'advisory')
        self.assertEqual(review_row(row('x.22',['RC']),{})['disposition'],'execution-review-required')

    def test_butting_rule_absence_refuses_touching_and_overlapping_active(self):
        diff=k.Region(k.Box(0,0,1000,1000))
        for box,expected in (((1000,0,1500,1000),1),((1000,250,1500,750),1),
                             ((1000,1000,1500,1500),1),((995,0,1500,1000),1),
                             ((1270,0,1500,1000),0)):
            count=tap_interactions(diff,k.Region(k.Box(*box)))
            self.assertEqual(count,expected)
            for name in ('difftap.4','difftap.5','difftap.6','difftap.7'):
                self.assertEqual(review_row(row(name),{'tap_interacting_diff':count})['disposition'],
                                 'execution-review-required' if expected else 'absent-operand')
                self.assertEqual(review_row(row(name),{})['disposition'],'execution-review-required')


if __name__=='__main__':unittest.main()
