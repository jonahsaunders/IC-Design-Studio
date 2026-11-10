"""Storage-only guards; small independent fixtures avoid a full inventory load."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import reconstruct_source_dispositions as r


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.base = {'items':[{'id':'a'},{'id':'b'},{'id':'c'}], 'status':'GAPS'}
        self.target = {'items':[{'id':'first'},{'id':'a'},{'id':'replacement'},{'id':'last'}], 'status':'GAPS'}
        self.b = r.compressed(self.base); self.t = r.compressed(self.target)
        self.delta = dict(schema=1,scope='storage only',base_sha256=r.digest(self.b),target_sha256=r.digest(self.t),replacements={},
                          lists={'items':dict(remove=[1],replace={'2':{'id':'replacement'}},insert={'0':[{'id':'first'}],'3':[{'id':'last'}]})})

    def decode(self, delta=None, base=None, target=None):
        raw = r.compressed(self.delta if delta is None else delta)
        return r.decode_verified(self.b if base is None else base,raw,r.digest(self.b),r.digest(raw),r.digest(self.t) if target is None else target)

    def test_exact_order_and_bytes(self):
        self.assertEqual(self.decode(),self.t)

    def test_wrong_base_and_wrong_patch_bytes(self):
        with self.assertRaisesRegex(ValueError,'historical base'):self.decode(base=self.b+b'bad')
        raw=r.compressed(self.delta)
        with self.assertRaisesRegex(ValueError,'delta bytes'):
            r.decode_verified(self.b,raw+b'bad',r.digest(self.b),r.digest(raw),r.digest(self.t))

    def test_missing_or_altered_row_fails_target_guard(self):
        for mutation in ('missing','changed'):
            d=copy.deepcopy(self.delta)
            if mutation=='missing':del d['lists']['items']['insert']['3']
            else:d['lists']['items']['replace']['2']['id']='wrong'
            with self.assertRaisesRegex(ValueError,'target differs'):self.decode(delta=d)

    def test_target_identity_cannot_be_changed(self):
        with self.assertRaisesRegex(ValueError,'identity differs'):self.decode(target='0'*64)

    def test_malformed_indices_and_overlaps_reject(self):
        for edit in ({'remove':[1,1],'replace':{},'insert':{}},
                     {'remove':[-1],'replace':{},'insert':{}},
                     {'remove':[1],'replace':{'1':{}},'insert':{}},
                     {'remove':[],'replace':{},'insert':{'4':[{}]}},
                     {'remove':[],'replace':{'01':{}},'insert':{}}):
            d=copy.deepcopy(self.delta);d['lists']['items']=edit
            with self.assertRaises(ValueError):r.apply_delta(self.base,d)

    def test_no_output_before_verified_target_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);base=folder/'base';delta=folder/'delta';out=folder/'out'
            base.write_bytes(self.b);delta.write_bytes(r.compressed(self.delta))
            with patch.object(r,'decode_verified',side_effect=ValueError('bad target')):
                with self.assertRaises(ValueError):r.reconstruct(out,base,delta)
            self.assertFalse(out.exists())
            out.write_bytes(b'existing')
            with self.assertRaisesRegex(ValueError,'fresh output'):r.reconstruct(out,base,delta)
            self.assertEqual(out.read_bytes(),b'existing')

    def test_shipped_delta_identity(self):
        self.assertEqual(r.digest(r.PATCH.read_bytes()),r.PATCH_SHA)


if __name__=='__main__':unittest.main()
