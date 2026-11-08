import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import example,file_digest
from icstudio.physical_backend import copy_grouping_manifest,stage
from icstudio.mos_grouping import authenticate
from scripts.qualify_standard_mos import load_technology

class ManagedMosManifestTests(unittest.TestCase):
    def test_all_reviewed_packages_survive_actual_stage_and_authentication(self):
        for target in ('gf180mcuC','gf180mcuD','ihp-sg13g2'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as td:
                root=Path(td);technology,_=load_technology(target);p=example('empty');p['pdk']=technology
                job=dict(project=p,cell=p['top'],settings=dict(type='silicon'));before=copy.deepcopy(job)
                native=stage(job,root/'work',str(root/'work'),'/')
                self.assertEqual(job,before)
                self.assertEqual((root/'work/pdk/package.json').read_bytes(),(Path(technology['package_root'])/'package.json').read_bytes())
                self.assertIn(str((root/'work/pdk/package.json').resolve()),authenticate(native['project']['pdk']))

    def fixture(self,root):
        source=root/'source';source.mkdir();technology,_=load_technology('gf180mcuC');document=json.loads((Path(technology['package_root'])/'package.json').read_bytes());path=source/'package.json';path.write_text(json.dumps(document));return technology,document,path

    def test_lock_substitution_and_duplicate_or_nonfinite_values_reject(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech,doc,path=self.fixture(root);raw=path.read_bytes()
            for field in ('id','revision','files'):
                altered=copy.deepcopy(tech);altered['package_lock'][field]='gf180mcuD' if field=='id' else 'unrelated'
                with self.subTest(field=field),self.assertRaisesRegex(ValueError,'saved package lock'):copy_grouping_manifest(altered,path.parent,root/'out')
            for tail in (',"id":"gf180mcuC"',',"extra":NaN',',"extra":1e400',',"extra":{"x":1,"x":2}'):
                path.write_bytes(raw.rstrip()[:-1]+tail.encode()+b'}')
                with self.subTest(tail=tail),self.assertRaises(ValueError):copy_grouping_manifest(tech,path.parent,root/'out')

    def test_missing_is_not_synthesized_and_conflicting_destination_rejects(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech,doc,path=self.fixture(root);raw=path.read_bytes();path.unlink()
            self.assertIsNone(copy_grouping_manifest(tech,path.parent,root/'out'));self.assertFalse((root/'out/package.json').exists())
            path.write_bytes(raw);dest=root/'out';dest.mkdir();(dest/'package.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Conflicting'):copy_grouping_manifest(tech,path.parent,dest)

    def test_formatting_is_preserved_and_semantic_change_still_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech,doc,path=self.fixture(root);path.write_text(json.dumps(doc,indent=5,ensure_ascii=False),encoding='utf-8');raw=path.read_bytes()
            copy_grouping_manifest(tech,path.parent,root/'out');self.assertEqual(raw,(root/'out/package.json').read_bytes())
            altered=copy.deepcopy(doc);altered['technology']['name']='unreviewed';path.write_text(json.dumps(altered),encoding='utf-8')
            copy_grouping_manifest(tech,path.parent,root/'changed');staged=copy.deepcopy(tech);staged['package_root']=str(root/'changed')
            with self.assertRaisesRegex(ValueError,'package semantics'):authenticate(staged)

    def test_source_changed_during_write_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech,doc,path=self.fixture(root);original=Path.write_bytes
            def mutate(p,raw):
                result=original(p,raw)
                if p==root/'out/package.json':original(path,b'{}')
                return result
            with patch.object(Path,'write_bytes',mutate),self.assertRaisesRegex(ValueError,'changed during transfer'):copy_grouping_manifest(tech,path.parent,root/'out')

if __name__=='__main__':unittest.main()
