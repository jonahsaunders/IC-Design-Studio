"""Packaging retains locked platform collateral and materializes dependencies."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.digital_platform import BUNDLED_PLATFORMS, inventory, stage, verify
from icstudio.model import clone, digest
from scripts.check_digital_qualification import validate as validate_qualification

spec=importlib.util.spec_from_file_location('bundle_platforms',Path(__file__).resolve().parents[1]/'packaging/digital/bundle_platforms.py')
bundler=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundler)


class DigitalBundleTests(unittest.TestCase):
    def setUp(self):
        # These fixtures exercise generic catalog/PVT handling. Complete GF180
        # source preparation has separate integration and native controls.
        mock=patch.object(bundler,'gf180_profiles',side_effect=lambda profiles,*args,**kwargs:dict(profiles))
        self.gf180=mock.start();self.addCleanup(mock.stop)

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
        (root/'licenses').mkdir()
        (root/'licenses/Apache-2.0.txt').write_text('fixture Apache notice')
        (root/'licenses/THIRD_PARTY_NOTICES.md').write_text('fixture source notices')
        (root/'orfs/LICENSE_BUILD_RUN_SCRIPTS').write_text('fixture BSD notice')
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

    def preparer(self,values):
        def prepare(orfs,destination,cache):
            value=clone(values['sky130hd']);stage(value,destination)
            folder=destination/'sky130hd/pvt';folder.mkdir()
            (folder/'cells.lef').write_text('matched cell geometry')
            for name in ('min','nom','max'):
                (folder/(name+'.tlef')).write_text('technology '+name)
                (folder/(name+'.rules')).write_text('extraction '+name)
            value['corners']={c:['sky130hd/cells.lib'] for c in ('typical','slow','fast')}
            value['extraction']={'cell_lefs':['sky130hd/pvt/cells.lef'],'coupling_threshold_ff':0.1,
                'corners':{c:{'rules':'sky130hd/pvt/'+n+'.rules','technology_lef':'sky130hd/pvt/'+n+'.tlef'}
                    for c,n in [('minimum','min'),('nominal','nom'),('maximum','max')]}}
            value.pop('root');value.pop('fingerprint')
            value['files']=[p.relative_to(destination).as_posix() for p in (destination/'sky130hd').rglob('*') if p.is_file()]
            path=destination/'platform.json';path.write_text(json.dumps(value));return path
        return prepare

    def test_bundle_retains_every_advertised_platform_with_matching_locks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);values=self.fixture(root)
            with patch.object(bundler,'from_orfs',side_effect=lambda _,name:clone(values[name])), \
                    patch.object(bundler,'prepare',side_effect=self.preparer(values)):
                result=bundler.bundle(root)
            self.gf180.assert_called_once()
            self.assertEqual(list(result['platforms']),list(BUNDLED_PLATFORMS))
            self.assertFalse((root/'orfs/flow/platforms/sky130hs').exists())
            for name,value in result['platforms'].items():
                self.assertTrue(all(item in value['files'] for item in values[name]['files']))
                self.assertTrue(any(item['path'].endswith('LICENSE-Apache-2.0.txt') for item in value['files']))
                self.assertTrue(any(item['path'].endswith('upstream-lock.json') for item in value['files']))
                actual=clone(value);actual['root']=str(root/'orfs/flow/platforms');verify(actual)
            self.assertEqual(json.loads((root/'platform.json').read_text()),result['platforms']['sky130hd'])
            self.assertEqual(json.loads((root/'platforms.json').read_text()),result)
            self.assertEqual(list(result['platforms']['sky130hd']['corners']),['typical','slow','fast'])
            self.assertEqual(list(result['platforms']['sky130hd']['extraction']['corners']),['minimum','nominal','maximum'])

    def test_distinct_profiles_can_share_locked_sources_and_notices(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);values=self.fixture(root)
            values['gf180d']=clone(values['gf180']);values['gf180d']['name']='gf180d'
            names=tuple(values)
            with patch.object(bundler,'BUNDLED_PLATFORMS',names), \
                    patch.object(bundler,'from_orfs',side_effect=lambda _,name:clone(values[name])), \
                    patch.object(bundler,'prepare',side_effect=self.preparer(values)):
                result=bundler.bundle(root)
            first=result['platforms']['gf180'];second=result['platforms']['gf180d']
            self.assertEqual(first['files'],second['files'])
            self.assertEqual(first['fingerprint'],second['fingerprint'])
            self.assertEqual(second['directory'],'gf180')
            self.assertFalse((root/'orfs/flow/platforms/gf180d').exists())
            for value in (first,second):
                actual=clone(value);actual['root']=str(root/'orfs/flow/platforms');verify(actual)

    @unittest.skipIf(os.name=='nt','Real symlinks are verified by the native Linux build')
    def test_linked_decks_are_materialized_before_sibling_platforms_are_pruned(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);values=self.fixture(root,linked=True)
            with patch.object(bundler,'from_orfs',side_effect=lambda _,name:clone(values[name])), \
                    patch.object(bundler,'prepare',side_effect=self.preparer(values)):
                result=bundler.bundle(root)
            for name in BUNDLED_PLATFORMS:
                path=root/'orfs/flow/platforms'/name/'rcx.rules'
                self.assertFalse(path.is_symlink());self.assertEqual(path.read_text(),'captured extraction deck\n')
                value=clone(result['platforms'][name]);value['root']=str(root/'orfs/flow/platforms');verify(value)

    def test_mutated_platform_cannot_be_published_with_old_locks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);values=self.fixture(root)
            (root/'orfs/flow/platforms/gf180/cells.lib').write_text('changed library')
            with patch.object(bundler,'from_orfs',side_effect=lambda _,name:clone(values[name])), \
                    patch.object(bundler,'prepare',side_effect=self.preparer(values)):
                with self.assertRaisesRegex(ValueError,'changed'):bundler.bundle(root)
            self.assertFalse((root/'platforms.json').exists())

    def test_missing_pvt_collateral_or_licenses_cannot_publish_a_catalog(self):
        for failure in ('prepare','notice'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as td:
                root=Path(td);values=self.fixture(root)
                if failure=='notice':(root/'licenses/Apache-2.0.txt').unlink()
                with patch.object(bundler,'from_orfs',side_effect=lambda _,name:clone(values[name])), \
                    patch.object(bundler,'prepare',side_effect=ValueError('missing PVT') if failure=='prepare' else self.preparer(values)):
                    with self.assertRaises((ValueError,FileNotFoundError)):bundler.bundle(root)
                self.assertFalse((root/'platforms.json').exists())

    def test_packaging_requires_every_advertised_library_and_interconnect_corner(self):
        from icstudio.digital_platform import validate_coverage
        coverage={'sky130hd':{'library_corners':['typical','slow','fast'],'interconnect_corners':['min','nom','max']}}
        manifest={'sha256':'a'*64,'platforms':['sky130hd'],'platform_corners':coverage}
        acceptance={'manifest':digest(manifest),'backend':'source','platforms':['sky130hd'],
                    'runtime':{'kind':'linux','sha256':'a'*64}}
        record={'sha256':'a'*64,'acceptance':acceptance}
        with self.assertRaisesRegex(ValueError,'timing corner'):validate_qualification(record,manifest,'source','Linux')
        acceptance['platform_corners']=clone(coverage)
        self.assertEqual(validate_qualification(record,manifest,'source','Linux'),acceptance)
        acceptance['platform_corners']['sky130hd']['interconnect_corners']=['nom']
        with self.assertRaisesRegex(ValueError,'timing corner'):validate_qualification(record,manifest,'source','Linux')
        for bad in ({}, {'sky130hd':None}, {'sky130hd':{'library_corners':[],'interconnect_corners':[]}},
                    {'sky130hd':{'library_corners':['tt','tt'],'interconnect_corners':[]}}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_coverage(bad,['sky130hd'])
