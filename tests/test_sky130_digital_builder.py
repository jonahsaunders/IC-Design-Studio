"""Pinned-archive platform preparation; fixtures do not qualify a process."""
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from backports import zstd
from icstudio import digital_platform
from icstudio.model import file_digest
from scripts import prepare_sky130_digital as builder


class Sky130DigitalBuilderTests(unittest.TestCase):
    def fixture(self,root,duplicate=False,missing=False):
        source=root/'source';folder=source/'sky130hd';folder.mkdir(parents=True)
        (folder/'config.mk').write_text('export SC_LEF = old.lef\n')
        (folder/'tt.lib').write_text('library(tt) {}')
        manifest={'version':1,'name':'sky130hd','directory':'sky130hd','revision':'ORFS fixture',
            'corner':'typical','corners':{'typical':['sky130hd/tt.lib']},
            'files':['sky130hd/config.mk','sky130hd/tt.lib']}
        (source/'platform.json').write_text(json.dumps(manifest));original=digital_platform.read_manifest(source/'platform.json')
        cache=root/'cache';cache.mkdir();pins={};wanted=builder.required_files()
        for archive_name in ('common.tar.zst','sky130_fd_sc_hd.tar.zst'):
            path=cache/archive_name
            names=[n for n in wanted if ('libs.tech' in n)==(archive_name=='common.tar.zst')]
            if duplicate and archive_name=='common.tar.zst':names.append(names[0])
            if missing and archive_name=='common.tar.zst':names.pop()
            with zstd.open(path,'wb') as stream,tarfile.open(fileobj=stream,mode='w|') as archive:
                for name in names:
                    data=('fixture '+name+'\n').encode();item=tarfile.TarInfo(name);item.size=len(data)
                    archive.addfile(item,io.BytesIO(data))
            pins[archive_name]=file_digest(path)
        (root/'examples').mkdir();(root/'licenses').mkdir()
        (root/'licenses/Apache-2.0.txt').write_text('fixture license')
        (root/'examples/sky130-reference-assets.json').write_text(json.dumps({
            'release':'fixture','repository':'fixture/repo','files':pins}))
        return original,cache

    def test_matched_views_and_pvt_rc_locks_survive_preparation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);original,cache=self.fixture(root)
            with patch.object(builder,'ROOT',root),patch.object(digital_platform,'from_orfs',return_value=original):
                path=builder.prepare(root/'unused-orfs',root/'out',cache)
            platform=digital_platform.read_manifest(path);digital_platform.verify(platform)
            self.assertEqual(list(platform['corners']),['typical','slow','fast'])
            self.assertEqual(list(platform['extraction']['corners']),['minimum','nominal','maximum'])
            config=(path.parent/'sky130hd/config.mk').read_text()
            # The pinned ORFS reader treats SC_LEF as one path; additional views
            # must be declared through its separately iterated LEF list.
            self.assertIn('export SC_LEF = $(PLATFORM_DIR)/pvt/sky130_fd_sc_hd.lef\n',config)
            self.assertIn('export ADDITIONAL_LEFS += $(PLATFORM_DIR)/pvt/sky130_ef_sc_hd.lef\n',config)
            provenance=json.loads((path.parent/'sky130hd/pvt/upstream-lock.json').read_text())
            self.assertEqual(set(provenance['captured_files']),set(builder.required_files()))
            self.assertEqual((path.parent/'sky130hd/pvt/orfs-config.mk').read_text(),'export SC_LEF = old.lef\n')
            self.assertEqual((root/'source/sky130hd/config.mk').read_text(),'export SC_LEF = old.lef\n')

    def test_missing_and_duplicate_collateral_never_publish_a_platform(self):
        for failure in ('missing','duplicate'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as td:
                root=Path(td);original,cache=self.fixture(root,**{failure:True})
                with patch.object(builder,'ROOT',root),patch.object(digital_platform,'from_orfs',return_value=original):
                    with self.assertRaises(ValueError):builder.prepare(root/'orfs',root/'out',cache)
                self.assertFalse((root/'out').exists())

    def test_modified_archive_is_not_accepted_from_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);original,cache=self.fixture(root);(cache/'common.tar.zst').write_bytes(b'corrupt')
            with patch.object(builder,'ROOT',root),patch.object(digital_platform,'from_orfs',return_value=original), \
                patch.object(builder,'download_archive',side_effect=ValueError('fixture transport failure')) as download:
                with self.assertRaisesRegex(ValueError,'transport'):builder.prepare(root/'orfs',root/'out',cache)
            download.assert_called_once();self.assertFalse((root/'out').exists())


if __name__=='__main__':unittest.main()
