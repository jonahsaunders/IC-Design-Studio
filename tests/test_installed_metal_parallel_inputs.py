"""Original-byte normalization and immutable candidate input bindings."""
import hashlib
import unittest
from unittest import mock
from scripts import installed_metal_parallel_inputs as inputs


class ParallelInputTests(unittest.TestCase):
    def test_only_declared_top_tokens_change_even_with_crlf(self):
        data=b'* actual saved extraction\r\n.subckt unique_top R1 R2\r\nR0 R1 R2 sky130_fd_pr__res_generic_l1 w=2 l=5\r\nR1 R2 R1 sky130_fd_pr__res_generic_l1 w=2 l=5\r\n.ends unique_top\r\n'
        value,proof=inputs.normalize_top(data,'unique_top')
        self.assertEqual(value,data.replace(b'unique_top',b'coupon'));self.assertEqual(len(proof['edits']),2)
        row=dict(model='l1',width_um=2,length_um=5,multiplicity=2)
        inputs.circuit(data,row,application=False,top='unique_top');inputs.circuit(value,row,application=False,top='coupon')
        for changed in (data+b'.include external.spice\n',data.replace(b'R1 R2\r\n',b'R2 R1\r\n',1),data.replace(b'.ends unique_top',b'.ends wrong')):
            with self.assertRaises(ValueError):inputs.normalize_top(changed,'unique_top')

    def test_candidate_batch_matches_bytes_and_rejects_stale_or_missing_objects(self):
        files={'scripts/one.py':hashlib.sha256(b'one\n').hexdigest(),'scripts/two.py':hashlib.sha256(b'two\n').hexdigest()}
        stream=b'1'*40+b' blob 4\none\n\n'+b'2'*40+b' blob 4\ntwo\n\n'
        with mock.patch.object(inputs,'git',return_value=stream) as request:
            inputs.candidate_sources(files,'a'*40)
            self.assertEqual(request.call_args.kwargs['data'],b'a'*40+b':scripts/one.py\n'+b'a'*40+b':scripts/two.py\n')
        for response in (stream.replace(b'two',b'bad'),b'missing missing\n',stream+b'other'):
            with mock.patch.object(inputs,'git',return_value=response),self.assertRaises(ValueError):inputs.candidate_sources(files,'a'*40)

    def test_current_contract_preserves_original_analysis_and_scope(self):
        installed,spec,_=inputs.contracts()
        self.assertEqual(installed['electrical']['analyses'],['dc','ac']);self.assertEqual(installed['electrical']['path_samples'],3870)
        self.assertEqual(spec['electrical']['tolerance']['relative'],1e-6)
        self.assertFalse(installed['qualified']);self.assertFalse(installed['signoff'])


if __name__=='__main__':unittest.main()
