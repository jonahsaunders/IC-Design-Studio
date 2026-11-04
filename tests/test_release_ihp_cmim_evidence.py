"""Release-boundary controls; aggregation fixtures are not native acceptance."""
import copy
import hashlib
import io
import json
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import release_ihp_cmim_evidence as gate

COMMIT = 'a' * 40


def aggregation_receipt(platform, commit=COMMIT):
    from tests.test_release_pw2dn_evidence import EXE, runtime_payload
    values = {'ICDesignStudio.exe' if platform == 'Windows' else 'ICDesignStudio': EXE,
              **{'_internal/' + name: data for name, data in runtime_payload(platform).items()}}
    return dict(schema=1, status='PASS', gate='ihp-cmim-installed-reference', expected_commit=commit,
                execution_id='b' * 32, platform=platform, installed_acceptance=True,
                qualified=False, full_family=False, release_ready=False,
                counts=dict(gui_layouts=1, fresh_managed_jobs=2),
                executable_sha256=hashlib.sha256(EXE).hexdigest(), distribution_links={},
                distribution_files={name: hashlib.sha256(data).hexdigest() for name, data in values.items()})


def aggregation_files(platform, commit=COMMIT):
    return {'verification.json': json.dumps(aggregation_receipt(platform, commit)).encode(),
            'RAW-UNIT-FIXTURE.txt': b'Aggregation fixture; native reader stubbed only inside unit tests.'}


def install_aggregation_reader(test):
    """Isolate older release-aggregation fixtures from the separately tested raw reader."""
    def fixture_reader(root, commit):
        if (root / 'RAW-UNIT-FIXTURE.txt').read_bytes() != aggregation_files('Linux')['RAW-UNIT-FIXTURE.txt']:
            raise ValueError('Not a unit aggregation fixture')
        return json.loads((root / 'verification.json').read_bytes())
    mock = patch('scripts.verify_frozen_ihp_cmim.verify_evidence', side_effect=fixture_reader)
    test.addCleanup(mock.stop)
    return mock.start()


class ReleaseCmimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def tree(self):
        path = self.root / 'evidence'; path.mkdir()
        for name, value in aggregation_files('Windows').items(): (path / name).write_bytes(value)
        return path

    def test_directory_requires_independent_readback_and_exact_typed_verdict(self):
        root = self.tree(); receipt = aggregation_receipt('Windows')
        with patch('scripts.verify_frozen_ihp_cmim.verify_evidence', return_value=receipt) as reader:
            self.assertEqual(gate.from_directory(root, COMMIT), receipt)
            reader.assert_called_once_with(root, COMMIT)
            altered = copy.deepcopy(receipt); altered['counts']['gui_layouts'] = True
            (root / 'verification.json').write_text(json.dumps(altered))
            with self.assertRaises(ValueError): gate.from_directory(root, COMMIT)
        with patch('scripts.verify_frozen_ihp_cmim.verify_evidence', side_effect=ValueError('raw reference differs')):
            with self.assertRaisesRegex(ValueError, 'raw reference'): gate.from_directory(root, COMMIT)

    def test_duplicate_or_nonfinite_verdict_is_rejected(self):
        root = self.tree(); receipt = aggregation_receipt('Windows')
        for text in ('{"status":"FAIL",'+json.dumps(receipt)[1:], json.dumps(receipt)[:-1]+',"extra":NaN}'):
            (root / 'verification.json').write_text(text)
            with self.subTest(text=text[:30]), patch('scripts.verify_frozen_ihp_cmim.verify_evidence', return_value=receipt), self.assertRaises(ValueError):
                gate.from_directory(root, COMMIT)

    def test_unqualified_wrong_count_and_resource_aliases_reject(self):
        receipt = aggregation_receipt('Windows')
        for field, value in (('expected_commit', 'c'*40), ('installed_acceptance', False),
                             ('full_family', True), ('counts', {'gui_layouts': 1.0, 'fresh_managed_jobs': 2})):
            bad = copy.deepcopy(receipt); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): gate.validate_receipt(bad, COMMIT)
        bad = copy.deepcopy(receipt); bad['distribution_files']['icdesignstudio.EXE'] = '0'*64
        with self.assertRaises(ValueError): gate.validate_receipt(bad, COMMIT)

    def test_zip_readback_and_unsafe_members(self):
        install_aggregation_reader(self)
        for extra in (None, '../escape', 'a/../../escape', 'C:/escape', 'a\\escape', 'verification.JSON', 'bad\x00name'):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr('gate/', b'')
                for name, data in aggregation_files('Windows').items(): z.writestr('gate/'+name, data)
                if extra:
                    info = zipfile.ZipInfo('placeholder')
                    info.filename = info.orig_filename = 'gate/' + extra
                    z.writestr(info, b'bad')
            stream.seek(0)
            with zipfile.ZipFile(stream) as z:
                if extra:
                    with self.subTest(extra=extra), self.assertRaises(ValueError): gate.from_zip(z, 'gate', COMMIT)
                else: self.assertEqual(gate.from_zip(z, 'gate', COMMIT), aggregation_receipt('Windows'))

    def test_zip_link_and_size_limit_reject_before_readback(self):
        for linked in (True, False):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                info = zipfile.ZipInfo('gate/verification.json')
                info.external_attr = ((stat.S_IFLNK if linked else stat.S_IFREG) | 0o600) << 16
                z.writestr(info, b'outside')
            stream.seek(0)
            with zipfile.ZipFile(stream) as z, patch.object(gate, 'MAX_BYTES', 1), self.assertRaises(ValueError):
                gate.from_zip(z, 'gate', COMMIT)

    def test_whole_distributions_reject_missing_changed_extra_files(self):
        from tests.test_release_pw2dn_evidence import distribution
        for platform in ('Windows', 'Linux'):
            receipt = aggregation_receipt(platform)
            path = self.root / ('app.zip' if platform == 'Windows' else 'app.tar.gz')
            distribution(path, platform); gate.check_distribution(path, platform, receipt)
            exe = 'ICDesignStudio/ICDesignStudio' + ('.exe' if platform == 'Windows' else '')
            for changed in ({exe: b'changed'}, {exe: None}, {'ICDesignStudio/extra.txt': b'unchecked'}):
                distribution(path, platform, changed)
                with self.subTest(platform=platform, changed=changed), self.assertRaises(ValueError):
                    gate.check_distribution(path, platform, receipt)

    def test_linux_confined_symlink_and_internal_hardlink(self):
        receipt = aggregation_receipt('Linux')
        receipt['distribution_files'] = {'ICDesignStudio': hashlib.sha256(b'app').hexdigest(),
            '_internal/icstudio/assets/value': hashlib.sha256(b'value').hexdigest(),
            '_internal/copy': hashlib.sha256(b'value').hexdigest()}
        receipt['executable_sha256'] = receipt['distribution_files']['ICDesignStudio']
        receipt['distribution_links'] = {'_internal/alias': 'icstudio/assets/value'}
        path = self.root / 'links.tar.gz'
        def archive(target):
            with tarfile.open(path, 'w:gz') as z:
                for name, data in [('ICDesignStudio', b'app'), ('_internal/icstudio/assets/value', b'value')]:
                    item = tarfile.TarInfo('ICDesignStudio/'+name); item.size = len(data); z.addfile(item, io.BytesIO(data))
                item = tarfile.TarInfo('ICDesignStudio/_internal/alias'); item.type = tarfile.SYMTYPE; item.linkname = target; z.addfile(item)
                item = tarfile.TarInfo('ICDesignStudio/_internal/copy'); item.type = tarfile.LNKTYPE; item.linkname = 'ICDesignStudio/_internal/icstudio/assets/value'; z.addfile(item)
        archive('icstudio/assets/value'); gate.check_distribution(path, 'Linux', receipt)
        archive('../../../outside')
        with self.assertRaises(ValueError): gate.check_distribution(path, 'Linux', receipt)
        receipt['distribution_links']['_internal/alias'] = '../../../outside'
        with self.assertRaises(ValueError): gate.validate_receipt(receipt, COMMIT)

    def test_linked_ancestor_is_rejected_before_leaf_metadata(self):
        leaf = self.root / 'parent' / 'child'; seen = []
        def linked(path):
            seen.append(path)
            return path == leaf.parent
        with patch.object(Path, 'is_symlink', linked), self.assertRaises(ValueError): gate.safe_tree(leaf)
        self.assertNotIn(leaf, seen)


if __name__ == '__main__': unittest.main()
