import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from scripts.reconcile_primitive_inventory import git_hash,verified_tree,compare


class CompleteTreeTests(unittest.TestCase):
    def fixture(self):
        blob=git_hash('blob',b'public source')
        subtree=git_hash('tree',b'100644 device.sym\0'+bytes.fromhex(blob))
        root=git_hash('tree',b'40000 symbols\0'+bytes.fromhex(subtree))
        return dict(sha=root,truncated=False,tree=[dict(path='symbols',type='tree',mode='040000',sha=subtree),
            dict(path='symbols/device.sym',type='blob',mode='100644',sha=blob)])

    def test_complete_tree_matches_its_content_identity(self):
        p=self.fixture();self.assertEqual(len(verified_tree(p,p['sha'])),2)

    def test_omitted_or_changed_leaf_is_rejected_even_if_response_claims_complete(self):
        for mode in ('omit','rename','hash','duplicate','missing-parent'):
            p=self.fixture();root=p['sha']
            if mode=='omit':p['tree'].pop()
            if mode=='rename':p['tree'][1]['path']='symbols/other.sym'
            if mode=='hash':p['tree'][1]['sha']='0'*40
            if mode=='duplicate':p['tree'].append(copy.deepcopy(p['tree'][1]))
            if mode=='missing-parent':p['tree'].pop(0)
            with self.subTest(mode=mode),self.assertRaises(ValueError):verified_tree(p,root)

    def test_wrong_root_or_truncated_response_is_rejected(self):
        p=self.fixture()
        with self.assertRaises(ValueError):verified_tree(p,'0'*40)
        p['truncated']=True
        with self.assertRaises(ValueError):verified_tree(p,p['sha'])

    def test_missing_extra_or_changed_catalog_symbols_are_not_a_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=b'public device symbol';(root/'device.sym').write_bytes(data)
            package=dict(revision='test',files={'device.sym':hashlib.sha256(data).hexdigest()},
                technology={'simulation':{'catalog':{'device.sym':{'source':'device.sym','model':'model'}}}})
            (root/'package.json').write_text(json.dumps(package))
            expected={'device.sym':{'source':'upstream/device.sym','git_blob_sha1':git_hash('blob',data)}}
            self.assertEqual(compare(root,expected)['status'],'PASS')
            for bad in ({},dict(expected,missing=expected['device.sym']),
                        {'device.sym':dict(expected['device.sym'],git_blob_sha1='0'*40)}):
                with self.subTest(expected=bad),self.assertRaises(ValueError):compare(root,bad)
            (root/'device.sym').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed bundled'):compare(root,expected)


if __name__=='__main__':unittest.main()
