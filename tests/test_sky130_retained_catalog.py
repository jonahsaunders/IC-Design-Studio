import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import sky130_retained_catalog as retained


class RetainedCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base,cls.authentication=retained.load()
        cls.audit=json.loads((retained.ROOT/retained.AUDIT).read_bytes())
        cls.catalog=json.loads((retained.ROOT/retained.queue.CATALOG).read_bytes())

    def validate_change(self,change):
        base=copy.deepcopy(self.base);audit=copy.deepcopy(self.audit)
        change(base,audit)
        with self.assertRaises(ValueError):retained.validate(base,audit,self.catalog)

    def test_complete_baseline_is_authenticated_with_verbatim_integration_snapshots(self):
        self.assertEqual(len(self.authentication['authenticated_sources']),85)
        self.assertEqual(len(self.authentication['historical_application_sources']),3)
        for name,row in self.authentication['historical_application_sources'].items():
            self.assertEqual(row['sha256'],self.base['source_files'][name])
            self.assertNotIn(name,self.authentication['authenticated_sources'])
        self.assertIn('not rerun geometry',self.authentication['execution'])

    def test_changed_dependency_and_path_escape_fail_closed(self):
        with TemporaryDirectory() as td:
            root=Path(td);(root/'input').write_bytes(b'original')
            digest=hashlib.sha256(b'original').hexdigest()
            self.assertEqual(retained.checked(root,'input',digest),b'original')
            (root/'input').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed retained'):retained.checked(root,'input',digest)
            with self.assertRaisesRegex(ValueError,'escapes'):retained.checked(root,'../input',digest)

    def test_all_pinned_dependencies_are_required(self):
        original=retained.checked
        for target in (retained.BASELINE,retained.AUDIT,'icstudio/digital_sky130_family_targets.py',
                       retained.queue.CATALOG,*retained.SNAPSHOTS.values()):
            def reject(root,name,digest):
                if name==target:raise ValueError('Changed dependency')
                return original(root,name,digest)
            with self.subTest(target=target),patch.object(retained,'checked',side_effect=reject):
                with self.assertRaisesRegex(ValueError,'Changed dependency'):retained.load()

    def test_qualification_promotion_is_rejected(self):
        self.validate_change(lambda b,a:b.update(qualified=True))
        self.validate_change(lambda b,a:a.update(chunk_complete=True))

    def test_missing_duplicate_or_reordered_reference_is_rejected(self):
        self.validate_change(lambda b,a:b['cases'].pop())
        self.validate_change(lambda b,a:b['cases'].__setitem__(1,b['cases'][0]))
        self.validate_change(lambda b,a:b['cases'].reverse())

    def test_counts_identity_and_provenance_are_bound(self):
        self.validate_change(lambda b,a:b['cases'][0]['counts'].update(unreviewed=0))
        self.validate_change(lambda b,a:b['cases'][0].update(gds_sha256='0'*64))
        self.validate_change(lambda b,a:b['cases'][0]['provenance'].popitem())

    def test_baseline_source_and_measurement_bindings_cannot_be_replaced(self):
        self.validate_change(lambda b,a:a['source_files'].popitem())
        self.validate_change(lambda b,a:a['measurements'].update(sha256='0'*64))

    def test_failed_skipped_or_partial_prior_validation_is_rejected(self):
        self.validate_change(lambda b,a:a['systems']['linux']['tests'].update(skipped=1))
        self.validate_change(lambda b,a:a['systems']['win32']['tests'].update(status='FAIL'))
        self.validate_change(lambda b,a:a['systems']['linux']['controls']['cases'].pop())
        self.validate_change(lambda b,a:a['systems']['linux']['replays'].pop('uart'))
        self.validate_change(lambda b,a:a['cases'][0]['application'].update(status='FAIL'))

    def test_cross_system_disagreement_is_rejected(self):
        self.validate_change(lambda b,a:a['systems']['linux']['replays']['counter']['result'].update(data_sha256='0'*64))
        self.validate_change(lambda b,a:a['systems']['linux']['controls']['cases'][0].update(report_sha256='0'*64))

    def test_missing_system_is_rejected(self):
        self.validate_change(lambda b,a:a['systems'].pop('linux'))


if __name__=='__main__':unittest.main()
