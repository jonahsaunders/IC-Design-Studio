"""Qualification gates must distinguish missing evidence from real acceptance."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qualify_analog_process import check_equivalent, condition
from qualify_process_rc import passive_values, process_evidence, stale_evidence_probe, accept_short_result, reevaluate, check_capacitance_conservation, maxwell_matrix
from icstudio.external_tools import extraction_commands
from icstudio.model import file_digest


class ProcessRcQualificationTests(unittest.TestCase):
    def test_magic_threshold_is_exact_integer_and_fraction_is_rejected(self):
        commands,profile=extraction_commands('rc')
        self.assertIn('ext2spice rthresh 0\n',commands)
        self.assertNotIn('ext2spice rthresh 0.0',commands)
        self.assertIs(type(profile['resistance_threshold']),int)
        for value in (.5,-1,2147483647):
            with self.subTest(value=value),self.assertRaises(ValueError):
                extraction_commands('rc',{'resistance_threshold':value})
        commands,_=extraction_commands('rc',{'resistance_threshold':25})
        self.assertIn('ext2spice rthresh 25\n',commands)

    def test_magic_rejected_threshold_cannot_hide_behind_completion_marker(self):
        from icstudio.silicon_flow import magic_script
        for kind in ('integer','numeric'):
            log='exttospice: '+kind+' value or "infinite" expected.\nSTUDIO_MAGIC_COMPLETE\n'
            with tempfile.TemporaryDirectory() as tmp,patch('icstudio.silicon_flow.execute',return_value=log):
                with self.assertRaisesRegex(ValueError,'could not complete'):
                    magic_script('magic','technology','layout.gds','dut',[],tmp,'extract all')
                self.assertEqual((Path(tmp)/'console.log').read_text(),log)

    def test_independent_reference_requires_every_measurement(self):
        def result(rows):return {'measurements':{'status':'passed','measurements':rows}}
        rows=[{'name':'bias','value':1.},{'name':'gain','value':10.}]
        check_equivalent(result(rows),result(rows))
        for other in (rows[:1],[rows[0],rows[0]]):
            with self.assertRaises(ValueError):check_equivalent(result(rows),result(other))

    def test_numeric_passives_never_accept_unresolved_or_nonfinite_networks(self):
        parsed=passive_values('R0 IN gate 12.5\nC0 gate VSS 10.692f\n')
        self.assertEqual(parsed['R'][0]['value'],12.5)
        self.assertAlmostEqual(parsed['C'][0]['value'],10.692e-15)
        for line in ('R0 a b {r}','R0 a b 0','C0 a b -1f','R0 a b nan','R0 a b 10 extra'):
            with self.subTest(line=line),self.assertRaises(ValueError):passive_values(line)

    def test_capacitance_or_incomplete_stage_result_cannot_qualify_rc(self):
        for report in ({'status':'passed','physical_extraction':{'mode':'capacitance'}},
                       {'status':'passed','physical_extraction':{'mode':'rc'},'stages':[]},
                       {'status':'blocked','physical_extraction':{'mode':'rc'}}):
            with self.assertRaises(ValueError):process_evidence(report,ROOT)

    def test_uncorrected_rc_cannot_be_promoted_by_a_passing_label(self):
        names=('preflight','schematic_simulation','drc','lvs_extraction','lvs','capacitance_extraction','post_layout_simulation','integrity')
        report={'status':'passed','physical_extraction':{'mode':'rc'},'stages':[{'name':name,'status':'passed'} for name in names]}
        report['stages'][5]['evidence']={'mode':'rc','profile':{'distributed_resistance':True}}
        with self.assertRaisesRegex(ValueError,'conserved capacitance'):
            process_evidence(report,ROOT)

    def test_stale_copy_is_rejected_and_original_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();deck=source/'extracted.spice'
            deck.write_text('R0 IN gate 12.5\nC0 gate VSS 10.692f\n');before=file_digest(deck)
            report={'stages':[{'name':'capacitance_extraction','evidence':{'deck':'extracted.spice'}}]}
            evidence=stale_evidence_probe(report,source,root/'probe')
            self.assertEqual(evidence['status'],'passed');self.assertEqual(file_digest(deck),before)
            self.assertEqual(evidence['source_sha256'],evidence['expected_sha256'])
            self.assertNotEqual(evidence['changed_sha256'],before)

    def test_condition_scope_rejects_statistical_and_nonphysical_temperature(self):
        import argparse
        self.assertEqual(condition('ss:85'),('ss',85))
        for text in ('mc:27','nominal:-273.15','nominal','tt:abc'):
            with self.assertRaises(argparse.ArgumentTypeError):condition(text)

    def test_short_requires_real_completed_extraction_and_one_correlated_port_merge(self):
        from copy import deepcopy
        report={'drc_count':0,'cell_name':'dut','findings':[{'code':'LVS.SHORT','nets':['A','B']}],
                'stages':[{'name':name,'status':'passed'} for name in ('preflight','schematic_simulation','drc')]+
                         [{'name':'lvs_extraction','status':'failed','error':'Extracted port order differs from the schematic: details'},
                          {'name':'lvs','status':'not_run'}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ext=root/'lvs-extraction';ext.mkdir()
            (root/'schematic.spice').write_text('.subckt dut A B VSS\n.ends dut\n')
            (ext/'extracted.spice').write_text('.subckt dut B VSS\n.ends dut\n')
            (ext/'console.log').write_text('STUDIO_MAGIC_COMPLETE\n')
            self.assertTrue(accept_short_result(report,root))
            for error in ('Cannot open technology','missing file','exttospice: integer value expected.'):
                changed=deepcopy(report);changed['stages'][3]['error']=error
                self.assertFalse(accept_short_result(changed,root))
            changed=deepcopy(report);changed['findings']=[]
            self.assertFalse(accept_short_result(changed,root))
            (ext/'console.log').write_text('Magic failed\n')
            self.assertFalse(accept_short_result(report,root))
            (ext/'console.log').write_text('STUDIO_MAGIC_COMPLETE\n')
            (ext/'extracted.spice').write_text('.subckt dut B A VSS\n.ends dut\n')
            self.assertFalse(accept_short_result(report,root))

    def test_reevaluation_never_accepts_partial_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'qualification.json'
            for status in ('running','failed','passed'):
                path.write_text(json.dumps({'status':status,'extraction':'rc','cases':[]}))
                with self.assertRaises(ValueError):reevaluate(tmp)

    def test_capacitance_conservation_rejects_constant_error_hidden_by_length_difference(self):
        check_capacitance_conservation(11.14766e-15,11.14766e-15,11.14766e-15)
        # Actual pinned extresist bug: an8.56aF mutual cap contributes8.56fF
        # extra to either coupon, so the old differential test still passed.
        for extracted,admittance in ((19.70797e-15,19.70797e-15),(11.14766e-15,19.70797e-15)):
            with self.assertRaisesRegex(ValueError,'did not conserve'):
                check_capacitance_conservation(11.14766e-15,extracted,admittance)

    def test_maxwell_reference_preserves_signed_mutual_terms(self):
        matrix=maxwell_matrix([{'nodes':['A','B'],'value':2.},{'nodes':['A','VSS'],'value':3.}],['A','B','VSS'])
        self.assertEqual(matrix,[[5.,-2.,-3.],[-2.,2.,0.],[-3.,0.,3.]])
        self.assertTrue(all(sum(row)==0 for row in matrix))


if __name__=='__main__':unittest.main()
