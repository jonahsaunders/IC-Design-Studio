"""Technology identity, compressed-library integrity and explicit physical options."""
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from icstudio import digital, digital_identity
from icstudio.digital_platform import (ORFS_PROFILES, implementation_options, inventory,
                                       liberty_files, pin_flow, read_manifest, stage, validate, from_orfs)
from icstudio.model import clone


class DigitalPlatformTests(unittest.TestCase):
    def fixture(self, root, name='gf180'):
        profile=clone(ORFS_PROFILES[name])
        contents=b'library (test) { time_unit : "1ns"; }\n'
        names=[]
        for files in profile['corners'].values():
            for filename in files:
                path=root/filename;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(gzip.compress(contents) if filename.endswith('.gz') else contents)
                names.append(filename)
        if profile.get('orfs',{}).get('rc_file'):
            rc=profile['orfs']['rc_file'];(root/rc).write_text('# captured RC\n');names.append(rc)
        manifest={'version':1,'name':name,'revision':'test fixture','corner':'typical','files':names,**profile}
        path=root/'platform.json';path.write_text(json.dumps(manifest))
        return read_manifest(path),contents

    def test_every_profile_materializes_its_captured_corner_without_changing_source(self):
        for name in ORFS_PROFILES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                root=Path(td);platform,contents=self.fixture(root,name)
                original=clone(platform)
                stage(platform,root/'captured')
                for corner in platform['corners']:
                    paths=liberty_files(platform,root/'captured',root/'plain',corner)
                    self.assertEqual([p.read_bytes() for p in paths],[contents])
                self.assertEqual(platform,original)
                self.assertEqual(inventory(root,[i['path'] for i in platform['files']]),platform['files'])

    def test_compressed_library_tamper_and_expansion_limit_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);platform,_=self.fixture(root)
            stage(platform,root/'captured')
            with patch('icstudio.digital_platform.MAX_LIBERTY_BYTES',8):
                with self.assertRaisesRegex(ValueError,'decompressed'):
                    liberty_files(platform,root/'captured',root/'plain')
            target=root/'captured'/platform['corners']['typical'][0]
            target.write_bytes(gzip.compress(b'changed model'))
            with self.assertRaisesRegex(ValueError,'changed'):
                liberty_files(platform,root/'captured',root/'plain')
            self.assertFalse((root/'plain').exists())

    def test_bad_gzip_and_empty_library_are_rejected(self):
        for contents in (b'not gzip',gzip.compress(b'')):
            with self.subTest(contents=contents),tempfile.TemporaryDirectory() as td:
                root=Path(td);platform,_=self.fixture(root)
                (root/platform['corners']['typical'][0]).write_bytes(contents)
                platform=read_manifest(root/'platform.json')
                with self.assertRaises(ValueError):liberty_files(platform,root,root/'plain')

    def test_physical_options_follow_selected_corner(self):
        with tempfile.TemporaryDirectory() as td:
            platform,_=self.fixture(Path(td));platform['corner']='slow'
            options=implementation_options(platform)
            self.assertEqual(options['CORNER'],'WC')
            self.assertEqual(options['PWR_NETS_VOLTAGES'],'VDD 4.5')
            self.assertEqual(options['TRACK_OPTION'],'9t')
            self.assertEqual(options['METAL_OPTION'],'5LM_1TM')

    def test_implementation_metadata_invalidates_cached_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            platform,_=self.fixture(Path(td));config=digital.counter_project()['digital'];config['platform']=platform
            before=digital_identity.stage_key(config,'mapped')
            for change in ('ties','stack','voltage'):
                edited=clone(config)
                if change=='ties':edited['platform']['tie_cells']['high'][0]='other_tie'
                elif change=='stack':edited['platform']['orfs']['variables']['METAL_OPTION']='4LM_1TM'
                else:edited['platform']['orfs']['corners']['typical']['PWR_NETS_VOLTAGES']='VDD 3.3'
                self.assertNotEqual(digital_identity.stage_key(edited,'mapped'),before)
                self.assertEqual(digital_identity.stage_key(edited,'simulate'),digital_identity.stage_key(config,'simulate'))

    def test_options_cannot_inject_make_expressions_or_omit_a_corner(self):
        with tempfile.TemporaryDirectory() as td:
            platform,_=self.fixture(Path(td))
            for value in ('$(shell echo bad)','9t\ninclude other.mk','9t;echo bad',' 9t'):
                changed=clone(platform);changed['orfs']['variables']['TRACK_OPTION']=value
                with self.assertRaises(ValueError):validate(changed)
            changed=clone(platform);del changed['orfs']['corners']['fast']
            with self.assertRaisesRegex(ValueError,'every captured'):validate(changed)
            changed=clone(platform);changed['tie_cells']['low']=['bad;cell','port']
            with self.assertRaises(ValueError):validate(changed)

    def test_physical_optimization_binds_all_corners_and_invalidates_checkpoints(self):
        from icstudio.digital_physical import library_options
        with tempfile.TemporaryDirectory() as td:
            platform,_=self.fixture(Path(td));config=digital.counter_project()['digital'];config['platform']=platform
            config['timing_corners']=['typical','fast']
            runner=SimpleNamespace(config=config,platform=platform,
                libraries=lambda corner=None:[Path('/captured')/((corner or platform['corner'])+'.lib')])
            options=library_options(runner)
            self.assertEqual(options[0],'LIB_FILES='+str(Path('/captured/typical.lib')))
            self.assertIn('CORNERS=icstudio_0 icstudio_1',options)
            self.assertIn('ICSTUDIO_1_LIB_FILES='+str(Path('/captured/fast.lib')),options)
            changed=clone(config);changed['timing_corners']=['typical']
            for stage_name in ('floorplan','place','cts','route','finish','timing'):
                self.assertNotEqual(digital_identity.stage_key(config,stage_name),digital_identity.stage_key(changed,stage_name))
            self.assertEqual(digital_identity.stage_key(config,'mapped'),digital_identity.stage_key(changed,'mapped'))

    def test_crlf_executable_scripts_fail_before_launch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'Makefile').write_bytes(b'all:\n')
            (root/'scripts').mkdir();script=root/'scripts/flow.sh'
            script.write_bytes(b'#!/usr/bin/env bash\r\necho broken\r\n')
            with self.assertRaisesRegex(ValueError,'LF line endings'):pin_flow(root)
            script.write_bytes(b'#!/usr/bin/env bash\necho fine\n')
            self.assertEqual(len(pin_flow(root)['files']),2)

    def test_unresolved_git_symlink_is_not_captured_as_an_extraction_deck(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/'flow/platforms/ihp-sg13g2';folder.mkdir(parents=True)
            (folder/'rcx_patterns.rules').write_text('IHP_rcx_patterns.rules')
            with patch('subprocess.run',side_effect=[SimpleNamespace(stdout='a'*40),
                       SimpleNamespace(stdout='120000 '+('b'*40)+' 0\tflow/platforms/ihp-sg13g2/rcx_patterns.rules\0')]):
                with self.assertRaisesRegex(ValueError,'unresolved symbolic link'):from_orfs(root,'ihp-sg13g2')

    def test_corner_lock_spelling_is_portable_to_case_sensitive_engines(self):
        with tempfile.TemporaryDirectory() as td:
            platform,_=self.fixture(Path(td));platform['corners']['typical'][0]=platform['corners']['typical'][0].upper()
            with self.assertRaisesRegex(ValueError,'exact captured spelling'):validate(platform)

    def test_new_platform_import_replaces_incompatible_old_corners_without_mutating_input(self):
        from icstudio.digital_platform import bind
        with tempfile.TemporaryDirectory() as td:
            platform,_=self.fixture(Path(td));config=digital.counter_project()['digital']
            config['timing_corners']=['old_tt'];bound=bind(config,platform)
            self.assertEqual(bound['timing_corners'],['typical','slow','fast'])
            self.assertEqual(config['timing_corners'],['old_tt'])
            digital.validate_config(bound)

    def test_rc_adapter_preserves_locked_files_and_uses_database_resistance_units(self):
        from icstudio.digital_physical import technology_options
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'source';source.mkdir();platform,_=self.fixture(source)
            stage(platform,root/'platform');before=(root/'platform/setRC.tcl').read_bytes()
            (root/'platform/cells.map').write_text('Metal1 : 34/0\n')
            artifacts={};runner=SimpleNamespace(root=root,platform=platform,add_artifact=lambda name,path:artifacts.update({name:path}))
            options=technology_options(runner,root/'flow')
            self.assertEqual(options,['LAYER_PARASITICS_FILE='+str(root/'platform_rc.tcl')])
            text=artifacts['platform_rc'].read_text()
            self.assertIn('getResistance',text);self.assertIn('sta::resistance_sta_ui',text)
            self.assertIn('if {$icstudio_resistance <= 0}',text)
            self.assertEqual((root/'platform/setRC.tcl').read_bytes(),before)
            self.assertEqual((root/'flow/platforms/gf180/cells.map').read_bytes(),(root/'platform/cells.map').read_bytes())
            runner.platform['corner']='slow';self.assertEqual(technology_options(runner,root/'flow'),[])

    def test_qualification_requires_final_router_evidence_not_an_intermediate_iteration(self):
        from scripts.qualify_digital_platforms import require_clean_route
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);path=root/'physical_metrics.json'
            for values in ({},{'detailedroute__route__drc_errors__iter:0':0},
                           {'detailedroute__route__drc_errors':1},{'detailedroute__route__drc_errors':False}):
                path.write_text(json.dumps({'route':values}))
                with self.assertRaisesRegex(ValueError,'missing or not clean'):require_clean_route(root)
            path.write_text(json.dumps({'route':{'detailedroute__route__drc_errors':0}}))
            self.assertEqual(require_clean_route(root)['detailed_route_drc_errors'],[0])
