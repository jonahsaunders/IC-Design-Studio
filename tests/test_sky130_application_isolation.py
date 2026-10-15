"""Actual x.29 worker, Finish/export enforcement and explicit setting persistence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import klayout.db as k
from icstudio import digital, digital_design, digital_identity, digital_platform
from icstudio import digital_sky130_isolation as isolation
from icstudio.digital_flow import artifact, validate_result
from icstudio.digital_macro import export
from icstudio.model import clone, design_digest, digest, file_digest
from scripts import prepare_sky130_isolation as prep, build_digital_runtime
from scripts import sky130_isolation_geometry as geometry, sky130_isolation_policy as reference
from tests import test_digital_macro as macro_fixtures

ROOT = Path(__file__).resolve().parents[1]


def fixture(root, enabled=False, contained=False):
    job, result = macro_fixtures.DigitalMacroTests().fixture(root, name='sky130hd')
    value = digital_design.config(job['project'], job['cell'])
    platform = clone(value['platform']); platform['root'] = str(root/'platform')
    platform = prep.prepare(platform, root/'platform/isolation', nfet_in_dnwell=enabled)
    value['platform'] = platform; digital_design.set_config(job['project'], job['cell'], value)
    (root/'input.json').write_text(json.dumps(job))
    data = result['digital_result']; data['source_hash'] = digital.source_hash(value)
    data['input_key'] = digital_identity.stage_key(value, 'finish'); result['design_hash'] = design_digest(job['project'])
    data['platform']['fingerprint'] = platform['fingerprint']
    data['environment'] = {'sky130_isolation': isolation.selected(value)}
    layout = k.Layout(); layout.dbu = .001; top = layout.create_cell('counter')
    top.shapes(layout.layer(65,20)).insert(k.Box(0,0,1000,500))
    top.shapes(layout.layer(66,20)).insert(k.Box(400,-100,600,600))
    if contained:top.shapes(layout.layer(64,18)).insert(k.Box(300,-100,700,600))
    layout.write(str(root/'design.gds')); data['artifacts']['gds'] = artifact(root,root/'design.gds')
    runner = SimpleNamespace(root=root, platform=platform, config=value, artifacts=data['artifacts'])
    runner.add_artifact = lambda key,path,**kw: runner.artifacts.update({key:artifact(root,path,**kw)})
    def save(key, value, relative):
        path=root/relative; path.write_text(json.dumps(value)); runner.add_artifact(key,path)
    runner.save_json = save
    def command(args, *unused, **kw):
        process=subprocess.run(args,cwd=kw['cwd'],capture_output=True,text=True,
                               env=dict(os.environ,PYTHONPATH=os.pathsep.join(sys.path)))
        (kw['cwd']/'worker.log').write_text(process.stdout+process.stderr)
        if process.returncode:raise ValueError('Isolation worker failed: '+process.stderr)
    runner.command = command
    return job,result,runner


def accepted(root, enabled=False, contained=False):
    job,result,runner=fixture(root,enabled,contained)
    report=isolation.execute(runner);result['digital_result']['physical']={'sky130_isolation':report}
    return job,result,runner,report


class Sky130ApplicationIsolationTests(unittest.TestCase):
    def test_bulk_retains_counts_and_exports_not_requested(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner,report=accepted(root)
            validate_result(result,root)
            self.assertEqual(report['status'],'NOT_REQUESTED');self.assertEqual(report['measurement']['nfet_not_contained'],1)
            contract=export(result,root,root/'macro.zip')
            claim=contract['qualification']['sky130_isolation']
            self.assertEqual(claim['status'],'NOT_REQUESTED');self.assertFalse(claim['enforced']);self.assertFalse(claim['qualified'])
            unpacked=root/'unpacked';unpacked.mkdir()
            with zipfile.ZipFile(root/'macro.zip') as archive:archive.extractall(unpacked)
            data=clone(result['digital_result']);data['artifacts']=contract['artifacts']
            self.assertEqual(isolation.validate_saved(data,unpacked),report)

    def test_required_isolation_passes_only_when_contained(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner,report=accepted(root,True,True)
            self.assertEqual(report['status'],'PASS');self.assertTrue(report['enforced'])
            self.assertEqual(report['measurement']['nfet_not_contained'],0)
            self.assertEqual(export(result,root,root/'macro.zip')['qualification']['sky130_isolation']['status'],'PASS')

    def test_required_isolation_failure_retains_measurements_and_cannot_export(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner=fixture(root,True)
            with self.assertRaisesRegex(ValueError,'Required SKY130 NMOS isolation failed'):isolation.execute(runner)
            raw=json.loads((root/'sky130-isolation/verified/report.json').read_bytes())
            self.assertEqual(raw['status'],'FAIL');self.assertEqual(raw['measurement']['nfet_not_contained'],1)
            self.assertTrue(any(v['path'].endswith('verified/report.json') for v in runner.artifacts.values()))
            self.assertNotIn('sky130_isolation',runner.artifacts)
            with self.assertRaises(ValueError):export(result,root,root/'macro.zip')
            self.assertFalse((root/'macro.zip').exists())

    def test_missing_entire_claim_or_individual_artifacts_blocks_export(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner,report=accepted(root)
            export(result,root,root/'macro.zip');original=(root/'macro.zip').read_bytes()
            for fault in ('entire','policy','declaration','report','resource','request','raw'):
                changed=clone(result);data=changed['digital_result']
                if fault in ('policy','entire'):data['environment'].pop('sky130_isolation')
                if fault in ('declaration','entire'):data['physical'].pop('sky130_isolation')
                if fault=='entire':data['artifacts']={k:v for k,v in data['artifacts'].items() if not k.startswith('sky130_isolation')}
                elif fault in ('report','resource','request','raw'):
                    key={'report':'sky130_isolation','resource':next(iter(report['resources'].values())),
                         'request':report['request_artifact'],'raw':report['raw_artifact']}[fault]
                    data['artifacts'].pop(key)
                with self.subTest(fault=fault),self.assertRaises(ValueError):export(changed,root,root/'macro.zip')
                self.assertEqual((root/'macro.zip').read_bytes(),original)

    def test_changed_policy_status_counts_and_input_identity_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner,report=accepted(root)
            for fault in ('mode','status','gds','top','count','sample','qualified'):
                changed=clone(report)
                if fault=='mode':changed['policy']['nfet_in_dnwell']=True
                elif fault=='status':changed['status']='PASS'
                elif fault=='gds':changed['gds_sha256']='a'*64
                elif fault=='top':changed['measurement']['top']='other'
                elif fault=='count':changed['measurement']['nfet_not_contained']=False
                elif fault=='sample':changed['measurement']['outside_examples_nm']=[]
                else:changed['qualified']=True
                with self.subTest(fault=fault),self.assertRaises(ValueError):
                    isolation.evaluate(changed,report['gds_sha256'],report['checkpoint_sha256'],report['top'],
                                       report['platform_fingerprint'],report['policy'])

    def test_helper_and_relocked_manifest_changes_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner=fixture(root)
            path=root/'platform/isolation/helpers/scripts/sky130_isolation_geometry.py'
            path.write_text('raise RuntimeError("untrusted code executed")')
            with self.assertRaisesRegex(ValueError,'resource'):isolation.execute(runner)
            self.assertFalse((root/'sky130-isolation').exists())
            changed=clone(runner.platform)
            next(r for r in changed['files'] if r['path'].endswith('sky130_isolation_geometry.py'))['sha256']=file_digest(path)
            changed['fingerprint']=digest(changed['files'])
            with self.assertRaisesRegex(ValueError,'resource'):digital_platform.validate(changed)

    def test_worker_authenticates_resources_before_import(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner,report=accepted(root)
            request=json.loads((root/'sky130-isolation/request.json').read_bytes());request['output']=str(root/'changed-worker')
            path=root/'platform/isolation/helpers/scripts/sky130_isolation_geometry.py'
            path.write_text('raise RuntimeError("untrusted code executed")')
            code='import json;from icstudio.digital_sky130_isolation_worker import execute;execute(json.loads('+repr(json.dumps(request))+'))'
            process=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True,
                                   env=dict(os.environ,PYTHONPATH=os.pathsep.join(sys.path)))
            self.assertNotEqual(process.returncode,0)
            retained=json.loads((root/'changed-worker/report.json').read_bytes())
            self.assertIn('resource',retained['error']);self.assertNotIn('untrusted code executed',retained['error'])

    def test_explicit_mode_override_invalidates_finish_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner=fixture(root)
            cfg=clone(runner.config);first=digital_identity.stage_key(cfg,'finish')
            cfg.setdefault('physical',{})['nfet_in_dnwell']=True
            self.assertTrue(isolation.selected(cfg)['nfet_in_dnwell'])
            self.assertNotEqual(first,digital_identity.stage_key(cfg,'finish'))
            cfg=clone(runner.config);cfg['platform']['sky130_isolation']['nfet_in_dnwell']=True
            self.assertNotEqual(first,digital_identity.stage_key(cfg,'finish'))
            cfg.setdefault('physical',{})['nfet_in_dnwell']=False
            self.assertFalse(isolation.selected(cfg)['nfet_in_dnwell'])

    def test_missing_checker_wrong_platform_and_nonboolean_modes_rejected(self):
        for mode in (True,False):
            with self.assertRaises(ValueError):isolation.selected({'physical':{'nfet_in_dnwell':mode}})
        with tempfile.TemporaryDirectory() as td:
            job,result,runner=fixture(Path(td))
            for mode in (None,0,1,'false'):
                cfg=clone(runner.config);cfg.setdefault('physical',{})['nfet_in_dnwell']=mode
                with self.assertRaises(ValueError):isolation.selected(cfg)
            wrong=clone(runner.platform);wrong['name']='ihp-sg13g2'
            with self.assertRaises(ValueError):isolation.validate(wrong)

    def test_prepared_resources_relocate_and_build_context_is_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,runner=fixture(root)
            moved=root/'moved';digital_platform.stage(runner.platform,moved)
            copied=clone(runner.platform);copied['root']=str(moved);digital_platform.verify(copied)
            isolation.resources(moved/'isolation',copied['sky130_isolation']['preparation_sha256'])
            context=root/'context';build_digital_runtime.sky130_rule_context(context)
            with patch.object(prep,'ROOT',context):self.assertEqual(set(prep.payload()),set(isolation.FILES))
            self.assertFalse(any(r['path'].endswith(('.gds','.odb')) for r in copied['files']))

    def test_packaged_geometry_matches_reviewed_checker_on_all_reference_layouts(self):
        with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as archive, tempfile.TemporaryDirectory() as td:
            for case in ('counter','uart','apb'):
                path=Path(td)/(case+'.gds');path.write_bytes(archive.read(case+'/filled.gds'))
                layout=k.Layout();layout.read(str(path))
                for enabled in (False,True):
                    actual=geometry.check(layout,enabled);expected=reference.check(layout,{'nfet_in_dnwell':enabled})
                    self.assertEqual(actual['status'],expected['status']);self.assertEqual(actual['measurement'],expected['measurement'])

    def test_historical_unprepared_jobs_make_no_isolation_claim(self):
        self.assertIsNone(isolation.selected({}))
        self.assertIsNone(isolation.validate_saved({'artifacts':{}},Path('/unused-sky130-isolation-fixture')))

    def test_ui_retains_inherit_bulk_and_required_modes(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        from icstudio.digital_physical_ui import PhysicalEditor
        app=QApplication.instance() or QApplication([])
        for settings,index in (({},0),({'nfet_in_dnwell':False},1),({'nfet_in_dnwell':True},2)):
            editor=PhysicalEditor(None,settings);self.assertEqual(editor.isolation.currentIndex(),index)
            editor.apply();self.assertIsNotNone(editor.value)
            self.assertEqual(editor.value.get('nfet_in_dnwell'),settings.get('nfet_in_dnwell'))
            editor.isolation.setCurrentIndex(0);editor.apply();self.assertNotIn('nfet_in_dnwell',editor.value)
            editor.close()


if __name__=='__main__':unittest.main()
