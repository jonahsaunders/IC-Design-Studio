"""Packaging retains locked platform collateral and materializes dependencies."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.digital_platform import BUNDLED_PLATFORMS, inventory, verify
from icstudio.model import clone, digest
from scripts.check_digital_qualification import validate as validate_qualification

spec=importlib.util.spec_from_file_location('bundle_platforms',Path(__file__).resolve().parents[1]/'packaging/digital/bundle_platforms.py')
bundler=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundler)


class DigitalBundleTests(unittest.TestCase):
    def test_packaging_rejects_stale_partial_or_other_os_qualification(self):
        manifest={'sha256':'a'*64,'platforms':list(BUNDLED_PLATFORMS)}
        acceptance={'manifest':digest(manifest),'backend':'current-source',
                    'platforms':list(BUNDLED_PLATFORMS),'runtime':{'kind':'linux','sha256':'a'*64}}
        record={'sha256':'a'*64,'acceptance':acceptance}
        self.assertEqual(validate_qualification(record,manifest,'current-source','Linux'),acceptance)
        for fault in ('archive','manifest','backend','platforms','runtime','os','missing'):
            with self.subTest(fault=fault):
                bad=clone(record)
                if fault=='archive':bad['sha256']='b'*64
                elif fault=='manifest':bad['acceptance']['manifest']='old'
                elif fault=='backend':bad['acceptance']['backend']='old-source'
                elif fault=='platforms':bad['acceptance']['platforms']=['sky130hd']
                elif fault=='runtime':bad['acceptance']['runtime']['sha256']='b'*64
                elif fault=='os':bad['acceptance']['runtime']['kind']='wsl'
                else:bad.pop('acceptance')
                with self.assertRaises(ValueError):validate_qualification(bad,manifest,'current-source','Linux')
        windows=clone(record);windows['acceptance']['runtime']['kind']='wsl'
        validate_qualification(windows,manifest,'current-source','Windows')

    def test_legacy_payload_keeps_its_original_platform_scope(self):
        manifest={'sha256':'a'*64}
        record={'sha256':'a'*64,'acceptance':{'manifest':digest(manifest),'backend':'source',
                                           'runtime':{'kind':'linux','sha256':'a'*64}}}
        validate_qualification(record,manifest,'source','Linux')

    def fixture(self,root,linked=False):
        flow=root/'orfs/flow';platforms=flow/'platforms';platforms.mkdir(parents=True)
        (flow/'Makefile').write_text('all:\n')
        extra=platforms/'sky130hs';extra.mkdir();(extra/'rcx.rules').write_text('captured extraction deck\n')
        values={}
        for name in BUNDLED_PLATFORMS:
            folder=platforms/name;folder.mkdir();(folder/'cells.lib').write_text('library fixture {}\n')
            paths=[name+'/cells.lib']
            if linked:
                (folder/'rcx.rules').symlink_to('../sky130hs/rcx.rules');paths.append(name+'/rcx.rules')
            records=inventory(platforms,paths)
            values[name]={'version':1,'name':name,'root':str(platforms),'directory':name,'revision':'fixture',
                          'corner':'typical','corners':{'typical':[paths[0]]},'files':records,'fingerprint':digest(records)}
        return values

    def test_bundle_retains_every_advertised_platform_with_matching_locks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);values=self.fixture(root)
            with patch.object(bundler,'from_orfs',side_effect=lambda _,name:clone(values[name])):
                result=bundler.bundle(root)
            self.assertEqual(list(result['platforms']),list(BUNDLED_PLATFORMS))
            self.assertFalse((root/'orfs/flow/platforms/sky130hs').exists())
            for name,value in result['platforms'].items():
                self.assertEqual(value['files'],values[name]['files'])
                actual=clone(value);actual['root']=str(root/'orfs/flow/platforms');verify(actual)
            self.assertEqual(json.loads((root/'platform.json').read_text()),result['platforms']['sky130hd'])
            self.assertEqual(json.loads((root/'platforms.json').read_text()),result)

    @unittest.skipIf(os.name=='nt','Real symlinks are verified by the native Linux build')
    def test_linked_decks_are_materialized_before_sibling_platforms_are_pruned(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);values=self.fixture(root,linked=True)
            with patch.object(bundler,'from_orfs',side_effect=lambda _,name:clone(values[name])):
                bundler.bundle(root)
            for name in BUNDLED_PLATFORMS:
                path=root/'orfs/flow/platforms'/name/'rcx.rules'
                self.assertFalse(path.is_symlink());self.assertEqual(path.read_text(),'captured extraction deck\n')
                verify(values[name])

    def test_mutated_platform_cannot_be_published_with_old_locks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);values=self.fixture(root)
            (root/'orfs/flow/platforms/gf180/cells.lib').write_text('changed library')
            with patch.object(bundler,'from_orfs',side_effect=lambda _,name:clone(values[name])):
                with self.assertRaisesRegex(ValueError,'changed'):bundler.bundle(root)
            self.assertFalse((root/'platforms.json').exists())
