from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import warnings
from zipfile import ZipFile

from scripts import check_sky130_reference_replay as replay


class ReferenceReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checkpoint = json.loads((replay.ROOT / replay.retained.CHECKPOINT).read_text())
        cls.original = json.loads((replay.ROOT / checkpoint['data']['path']).read_text())[0]
        cls.profiles = {key: cls.original[key] for key in replay.retained.PROFILES}

    def validate(self, profiles):
        replay.validate_profiles(profiles, self.original['gds_sha256'], self.original['top'])

    def test_complete_real_reference_passes_without_mutation(self):
        before = deepcopy(self.profiles)
        self.validate(self.profiles)
        self.assertEqual(before, self.profiles)

    def test_every_profile_rejects_missing_duplicate_failed_and_stale_evidence(self):
        for name in self.profiles:
            mutations = (
                lambda report: report['checks'].pop(),
                lambda report: report['checks'].append(deepcopy(report['checks'][0])),
                lambda report: report['checks'][0].update(violations=1),
                lambda report: report['checks'][0].update(violations=False),
                lambda report: report['checks'][0].update(violations=0.0),
                lambda report: report.update(violations=False),
                lambda report: report.update(top='different'),
                lambda report: report.update(gds_sha256='0' * 64),
                lambda report: report.update(checker_sha256='0' * 64),
                lambda report: report.update(status='FAIL'),
                lambda report: report.update(qualified=True),
            )
            for index, mutate in enumerate(mutations):
                with self.subTest(profile=name, mutation=index):
                    reports = deepcopy(self.profiles)
                    mutate(reports[name])
                    with self.assertRaises(ValueError):
                        self.validate(reports)
            reports = deepcopy(self.profiles)
            reports.pop(name)
            with self.assertRaises(ValueError):
                self.validate(reports)

    def test_hidden_unaccounted_conductor_and_wrong_layer_map_cannot_pass(self):
        for field, value in (('nets', False), ('anchored_nets', 0), ('floating', [{}])):
            with self.subTest(field=field):
                reports = deepcopy(self.profiles)
                reports['floating_connectivity'][field] = value
                with self.assertRaises(ValueError):
                    self.validate(reports)
        reports = deepcopy(self.profiles)
        reports['floating_connectivity']['covered_area_nm2']['poly'] += 1
        with self.assertRaises(ValueError):
            self.validate(reports)
        reports = deepcopy(self.profiles)
        reports['global_geometry']['layer_map_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.validate(reports)

    def test_missing_or_duplicate_archive_member_is_refused(self):
        data = io.BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.writestr('final.gds', b'first')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr('final.gds', b'second')
        with ZipFile(data) as archive:
            for name in ('final.gds', 'absent.gds'):
                with self.assertRaises(ValueError):
                    replay.member_bytes(archive, name)

    def test_wrong_archive_is_rejected_before_any_geometry_execution(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'evidence.zip'
            with ZipFile(path, 'w') as archive:
                archive.writestr('final.gds', b'not the locked reference')
            with self.assertRaisesRegex(ValueError, 'locked artifact'):
                replay.build(path)


if __name__ == '__main__':
    unittest.main()
