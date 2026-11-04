"""Saved-bench LVS projection must preserve simulation and physical mismatches."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.catalog import create_device
from icstudio.catalog_migration import emit
from icstudio.hierarchical_flow import prepare_lvs_reference, check_lvs_reference, verify_integrity
from icstudio.model import file_digest
from scripts.qualify_standard_mos import load_technology


class SavedBenchLvsReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tech=load_technology('ihp-sg13g2')[0]
        device=create_device(cls.tech,'sg13g2_pr/cap_cmim.sym','C1')
        device['nets']={'c0':'TOP','c1':'BOTTOM'}
        cls.original=('* original simulation reference\n.subckt coupon TOP BOTTOM\n'+
                      emit(device,cls.tech,'simulation')+'\n.ends coupon\n').encode('utf-8')

    def prepare(self, root, source=None, technology=None):
        source=self.original if source is None else source
        (root/'schematic.spice').write_bytes(source)
        target,record=prepare_lvs_reference(root,self.tech if technology is None else technology,
                                            hashlib.sha256(source).hexdigest())
        return target,record

    def test_actual_catalog_projection_retains_original_and_ordered_magic_x(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target,record=self.prepare(root)
            self.assertEqual((root/'schematic.spice').read_bytes(),self.original)
            self.assertEqual(target.read_bytes(),self.original.replace(b' mm_ok=1',b''))
            self.assertIn(b'X_C1 TOP BOTTOM cap_cmim ',target.read_bytes())
            self.assertNotIn(b'CX_C1',target.read_bytes())
            self.assertEqual(record['extractor'],'magic')
            self.assertTrue(record['defaults'][0]['changed'])
            self.assertEqual(json.loads((root/'lvs-reference.json').read_bytes()),record)
            self.assertEqual(check_lvs_reference(root,self.tech,record),record)

    def test_canonical_x_keeps_source_proof_without_rewriting_parameters(self):
        source=self.original.replace(b' mm_ok=1',b'')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target,record=self.prepare(root,source)
            self.assertEqual(target.read_bytes(),source)
            self.assertFalse(record['defaults'][0]['changed'])
            self.assertIn('model_sha256',record['defaults'][0]['proof'])
            check_lvs_reference(root,self.tech,record)

    def test_wrong_geometry_and_reversed_pins_survive_for_native_lvs_to_reject(self):
        for source in (self.original.replace(b'w=7e-06',b'w=8u'),
                       self.original.replace(b'X_C1 TOP BOTTOM',b'X_C1 BOTTOM TOP')):
            self.assertNotEqual(source,self.original)
            with self.subTest(source=source),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);target,record=self.prepare(root,source)
                self.assertEqual(target.read_bytes(),source.replace(b' mm_ok=1',b''))
                self.assertEqual((root/'schematic.spice').read_bytes(),source)
                check_lvs_reference(root,self.tech,record)

    def test_non_cmim_reference_is_byte_preserved(self):
        source=b'* unchanged\r\n.subckt a P N\r\nR1 P N 10k\r\n.ends a\r\n'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target,record=self.prepare(root,source,{})
            self.assertEqual(target.read_bytes(),source)
            self.assertEqual(record['defaults'],[])
            check_lvs_reference(root,{},record)

    def test_preexisting_original_change_is_rejected_before_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'schematic.spice').write_bytes(self.original+b'* changed\n')
            with self.assertRaisesRegex(ValueError,'changed before LVS'):
                prepare_lvs_reference(root,self.tech,hashlib.sha256(self.original).hexdigest())
            self.assertFalse((root/'schematic-lvs.spice').exists())

    def test_original_comparison_and_receipt_mutations_are_rejected(self):
        for name in ('schematic.spice','schematic-lvs.spice','lvs-reference.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,record=self.prepare(root)
                path=root/name;path.write_bytes(path.read_bytes()+b'\n')
                with self.assertRaisesRegex(ValueError,'changed'):
                    check_lvs_reference(root,self.tech,record)

    def test_model_and_symbol_mutation_after_comparison_is_rejected(self):
        for name in ('cap_cmim.sym','capacitors_mod.lib'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,record=self.prepare(root)
                def altered(path):
                    return '0'*64 if Path(path).name==name else file_digest(path)
                with patch('icstudio.model.file_digest',side_effect=altered):
                    with self.assertRaisesRegex(ValueError,'source is missing or changed'):
                        check_lvs_reference(root,self.tech,record)

    def test_changed_catalog_and_nonliteral_geometry_still_fail_closed(self):
        technology=copy.deepcopy(self.tech)
        technology['simulation']['catalog']['sg13g2_pr/cap_cmim.sym']['pin_order'].reverse()
        for source,tech in ((self.original,technology),
                            (self.original.replace(b'w=7e-06',b'w={width}'),self.tech)):
            with self.subTest(source=source),tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):self.prepare(Path(directory),source,tech)

    def test_final_integrity_rejects_a_changed_comparison_or_proof(self):
        for name in ('schematic-lvs.spice','lvs-reference.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);self.prepare(root)
                files={n:file_digest(root/n) for n in ('schematic.spice','schematic-lvs.spice','lvs-reference.json')}
                self.assertTrue(verify_integrity(root,files,{}, {})['verified'])
                path=root/name;path.write_bytes(path.read_bytes()+b'\n')
                with self.assertRaisesRegex(ValueError,'evidence changed'):
                    verify_integrity(root,files,{}, {})


if __name__=='__main__':unittest.main()
