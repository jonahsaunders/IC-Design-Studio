"""Small transport guard tests; complete reconstruction is recorded separately."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import reconstruct_source_dispositions as prior
from scripts import reconstruct_source_dispositions_v2 as current


class ReconstructionV2Tests(unittest.TestCase):
    def test_retained_delta_identity_and_historical_base(self):
        raw=current.PATCH.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),current.PATCH_SHA)
        delta=json.loads(gzip.decompress(raw))
        self.assertEqual(delta['base_sha256'],prior.BASE_SHA)
        self.assertEqual(delta['target_sha256'],current.TARGET_SHA)
        self.assertEqual(sum(len(v) for v in delta['lists']['items']['insert'].values()),194)
        self.assertEqual(len(delta['lists']['files']['replace']),9)
        self.assertEqual(len(delta['lists']['inventory_gaps']['remove']),9)
        self.assertEqual(prior.TARGET_SHA,'263b17bf6dc2c010e230ded19bb4e0c8c4cc3712b7a321ffc84d5be10d7d7216')

    def test_wrapper_passes_all_pins_and_exclusively_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'base';delta=root/'delta';out=root/'output'
            base.write_bytes(b'base');delta.write_bytes(b'delta')
            with patch.object(current,'decode_verified',return_value=b'exact') as decode:
                result=current.reconstruct(out,base,delta)
                decode.assert_called_once_with(b'base',b'delta',base_sha=current.BASE_SHA,
                                               patch_sha=current.PATCH_SHA,target_sha=current.TARGET_SHA)
            self.assertEqual(out.read_bytes(),b'exact');self.assertFalse(result['qualified'])
            with self.assertRaisesRegex(ValueError,'fresh output'):current.reconstruct(out,base,delta)
            self.assertEqual(out.read_bytes(),b'exact')

    def test_bad_base_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'base';base.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'historical base'):
                current.reconstruct(root/'output',base,current.PATCH)
            self.assertFalse((root/'output').exists())

    def test_verification_failure_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(current,'decode_verified',side_effect=ValueError('target differs')):
                with self.assertRaisesRegex(ValueError,'target differs'):
                    current.reconstruct(root/'output',current.PATCH,current.PATCH)
            self.assertFalse((root/'output').exists())


if __name__ == '__main__':unittest.main()
