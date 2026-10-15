"""The application preserves the partial SKY130 scope and rejects stale evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from icstudio import digital, digital_design, digital_identity, digital_platform
from icstudio import digital_sky130_rules as rules
from icstudio.digital_flow import artifact, validate_result
from icstudio.digital_macro import export
from icstudio.model import clone, design_digest, digest, file_digest
from scripts import prepare_sky130_rule_checks as prep, build_digital_runtime
from tests import test_digital_macro as macro_fixtures

ROOT = Path(__file__).resolve().parents[1]


def fixture(root):
    job, result = macro_fixtures.DigitalMacroTests().fixture(root, name='sky130hd')
    value = digital_design.config(job['project'], job['cell'])
    platform = clone(value['platform']); platform['root'] = str(root/'platform')
    platform = prep.prepare(platform, root/'platform/verification')
    value['platform'] = platform
    digital_design.set_config(job['project'], job['cell'], value)
    (root/'input.json').write_text(json.dumps(job))
    data = result['digital_result']; data['source_hash'] = digital.source_hash(value)
    data['input_key'] = digital_identity.stage_key(value, 'finish')
    result['design_hash'] = design_digest(job['project'])
    data['platform']['fingerprint'] = platform['fingerprint']
    data['environment'] = {'sky130_rules': clone(platform['sky130_rules'])}
    with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as archive:
        (root/'filled.gds').write_bytes(archive.read('counter/filled.gds'))
        inventory=json.loads(archive.read('counter/inventory.json'))
    # This unit fixture uses a placeholder checkpoint and retained profile data.
    # Apply the independently bounded stream-only correction so current delivery
    # validation sees valid GDS; actual engine execution is tested separately.
    import klayout.db as k
    from icstudio.digital_sky130_boundaries import remove_outline
    layout=k.Layout();layout.read(str(root/'filled.gds'));remove_outline(layout,inventory)
    options=k.SaveLayoutOptions();options.gds2_write_timestamps=False
    layout.write(str(root/'filled.gds'),options)
    data['artifacts']['gds'] = artifact(root, root/'filled.gds')
    ledger = json.loads((ROOT/'docs/validation/sky130-filled-replay-2026-10-14.json').read_bytes())['cases'][0]['execution']
    from icstudio.digital_sky130_scope import correct
    ledger = correct(ledger)
    from icstudio.digital_sky130_pad_scope import correct as correct_pad_scope
    ledger = correct_pad_scope(ledger)
    def bind_fixture(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='gds_sha256':value[key]=data['artifacts']['gds']['sha256']
                else:bind_fixture(item)
        elif isinstance(value,list):
            for item in value:bind_fixture(item)
    bind_fixture(ledger)
    from icstudio.digital_sky130_catalog_context import audit as catalog_context
    from icstudio.digital_sky130_catalog_labels import audit as catalog_labels
    from icstudio.digital_sky130_vpp import audit as vpp_geometry
    from icstudio.digital_sky130_boundary_interactions import audit as boundary_interactions
    from icstudio.digital_sky130_selected_devices import audit as selected_devices
    from icstudio.digital_sky130_conservative_bounds import audit as conservative_bounds
    from icstudio.digital_sky130_device_roots import audit as device_roots
    from icstudio.digital_sky130_special_subjects import audit as special_subjects
    from icstudio.digital_sky130_selected_targets import audit as selected_targets
    from icstudio.digital_sky130_frame_bounds import audit as frame_bounds
    from icstudio.digital_sky130_well_bounds import audit as well_bounds
    from icstudio.digital_sky130_scribe_bounds import audit as scribe_bounds
    report = dict(schema=1, recipe=rules.RECIPE, status='reviewed-profiles-pass', qualified=False,
                  chunk_complete=False, scope=rules.SCOPE, policy=platform['sky130_rules'],
                  top=ledger['top'], gds_sha256=ledger['gds_sha256'],
                  checkpoint_sha256=data['artifacts']['checkpoint']['sha256'],
                  platform_fingerprint=platform['fingerprint'], ledger=ledger,
                  profiles={key: clone(ledger[key]) for key in rules.PROFILES},
                  coverage=dict(rows=len(ledger['rows']), counts=ledger['counts'], complete=False), resources={},
                  catalog_context=catalog_context(root/'filled.gds'),catalog_labels=catalog_labels(root/'filled.gds'),
                  vpp_geometry=vpp_geometry(root/'filled.gds'),boundary_interactions=boundary_interactions(root/'filled.gds'),
                  selected_devices=selected_devices(root/'filled.gds'),
                  conservative_bounds=conservative_bounds(root/'filled.gds'),device_roots=device_roots(root/'filled.gds'),
                  special_subjects=special_subjects(root/'filled.gds'),selected_targets=selected_targets(root/'filled.gds'),
                  frame_bounds=frame_bounds(root/'filled.gds'),well_bounds=well_bounds(root/'filled.gds'),
                  scribe_bounds=scribe_bounds(root/'filled.gds'))
    paths = rules.resources(root/'platform/verification', platform['sky130_rules']['preparation_sha256'])
    for index, (name, path) in enumerate(sorted(paths.items())):
        key='sky130_rule_resource_'+str(index)
        data['artifacts'][key]=artifact(root,path,allow_empty=True);report['resources'][name]=key
    save_report(root, result, report)
    return job, result, report


def save_report(root, result, report):
    path=root/'accepted.json';path.write_text(json.dumps(report))
    data=result['digital_result'];data['physical']={'sky130_rules':clone(report)}
    data['artifacts']['sky130_rules']=artifact(root,path)


class Sky130ApplicationRuleTests(unittest.TestCase):
    def test_preparation_relocates_without_reference_layouts_or_network(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,report=fixture(root)
            platform=job['project']['digital']['platform']
            self.assertFalse(any(r['path'].endswith(('.gds','.odb')) for r in platform['files']))
            target=root/'moved';digital_platform.stage(platform,target)
            copied=clone(platform);copied['root']=str(target);digital_platform.verify(copied)
            rules.resources(target/'verification',platform['sky130_rules']['preparation_sha256'])
            with self.assertRaisesRegex(ValueError,'once'):
                prep.prepare(platform,root/'platform/another')

    def test_missing_changed_and_relocked_helpers_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,report=fixture(root);platform=job['project']['digital']['platform']
            key='verification/helpers/scripts/sky130_global_geometry.py';path=root/'platform'/key
            path.write_text('raise RuntimeError("must never execute")')
            with self.assertRaisesRegex(ValueError,'resource'):
                rules.resources(root/'platform/verification',platform['sky130_rules']['preparation_sha256'])
            changed=clone(platform)
            next(r for r in changed['files'] if r['path']==key)['sha256']=file_digest(path)
            changed['fingerprint']=digest(changed['files'])
            with self.assertRaisesRegex(ValueError,'resource'):
                digital_platform.validate(changed)
            changed=clone(platform);changed['files']=[r for r in changed['files'] if r['path']!=key]
            changed['fingerprint']=digest(changed['files'])
            with self.assertRaisesRegex(ValueError,'resource'):
                digital_platform.validate(changed)

    def test_changed_source_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'changed.zip'
            with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as original, zipfile.ZipFile(source,'w') as out:
                for name in rules.FILES:
                    if name.startswith('sources/'):
                        out.writestr(name,b'changed' if name.endswith('source-lock.json') else original.read(name))
            with self.assertRaisesRegex(ValueError,'pinned SKY130'):
                prep.payload(source)

    def test_build_context_can_prepare_the_same_authenticated_resources(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);build_digital_runtime.sky130_rule_context(root)
            with patch.object(prep,'ROOT',root):
                captured=prep.payload()
            self.assertEqual(set(captured),set(rules.FILES))
            docker=(ROOT/'packaging/digital/Dockerfile').read_text()
            self.assertIn('COPY tests/fixtures/sky130-filled-references-v1.zip',docker)

    def test_saved_report_exports_and_survives_relocated_artifact_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,report=fixture(root)
            validate_result(result,root)
            contract=export(result,root,root/'macro.zip')
            self.assertFalse(contract['qualification']['sky130_rules']['qualified'])
            self.assertFalse(contract['qualification']['sky130_rules']['coverage']['complete'])
            self.assertEqual(contract['qualification']['sky130_rules']['coverage']['rows'],601)
            self.assertEqual(contract['qualification']['drc'],'Not qualified by this export')
            destination=root/'unpacked';destination.mkdir()
            with zipfile.ZipFile(root/'macro.zip') as archive:archive.extractall(destination)
            data=clone(result['digital_result']);data['artifacts']=contract['artifacts']
            self.assertEqual(rules.validate_saved(data,destination),report)

    def test_changed_profile_rows_counts_or_bindings_cannot_claim_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,report=fixture(root)
            def evaluated(value):
                return rules.evaluate(value,report['gds_sha256'],report['checkpoint_sha256'],report['top'],
                                      report['platform_fingerprint'],report['policy'])
            self.assertEqual(evaluated(report),report)
            changes={
                'missing-profile':lambda r:r['profiles'].pop('raw_geometry'),
                'missing-catalog-context':lambda r:r.pop('catalog_context'),
                'missing-label-subjects':lambda r:r.pop('catalog_labels'),
                'changed-label-subjects':lambda r:r['catalog_labels']['rows'].pop(),
                'missing-vpp-geometry':lambda r:r.pop('vpp_geometry'),
                'changed-vpp-geometry':lambda r:r['vpp_geometry']['rows'].pop(),
                'missing-boundary-interactions':lambda r:r.pop('boundary_interactions'),
                'changed-boundary-interactions':lambda r:r['boundary_interactions']['rows'].pop(),
                'missing-selected-devices':lambda r:r.pop('selected_devices'),
                'changed-selected-devices':lambda r:r['selected_devices']['rows'].pop(),
                'missing-conservative-bounds':lambda r:r.pop('conservative_bounds'),
                'changed-conservative-bounds':lambda r:r['conservative_bounds']['rows'].pop(),
                'missing-device-roots':lambda r:r.pop('device_roots'),
                'changed-device-roots':lambda r:r['device_roots']['rows'].pop(),
                'missing-special-subjects':lambda r:r.pop('special_subjects'),
                'changed-special-subjects':lambda r:r['special_subjects']['rows'].pop(),
                'missing-selected-targets':lambda r:r.pop('selected_targets'),
                'changed-selected-targets':lambda r:r['selected_targets']['rows'].pop(),
                'missing-frame-bounds':lambda r:r.pop('frame_bounds'),
                'changed-frame-bounds':lambda r:r['frame_bounds']['rows'].pop(),
                'missing-well-bounds':lambda r:r.pop('well_bounds'),
                'changed-well-bounds':lambda r:r['well_bounds']['rows'].pop(),
                'missing-scribe-bounds':lambda r:r.pop('scribe_bounds'),
                'changed-scribe-bounds':lambda r:r['scribe_bounds']['rows'].pop(),
                'changed-catalog-context':lambda r:r['catalog_context']['rows'].pop(),
                'duplicate-check':lambda r:r['profiles']['raw_geometry']['checks'].__setitem__(0,r['profiles']['raw_geometry']['checks'][1]),
                'bool-count':lambda r:r['profiles']['raw_geometry'].update(violations=False),
                'real-violation':lambda r:r['profiles']['raw_geometry']['checks'][0].update(violations=1),
                'helper':lambda r:r['profiles']['raw_geometry'].update(checker_sha256='a'*64),
                'qualified':lambda r:r.update(qualified=True),
                'omitted-row':lambda r:r['ledger']['rows'].pop(),
                'source-row':lambda r:r['ledger']['rows'][0].update(source_sha256='a'*64),
                'coverage':lambda r:r['coverage'].update(complete=True),
                'unbound-execution':lambda r:next(x for x in r['ledger']['rows'] if x['id'] not in rules.BINDINGS).update(execution={}),
                'absent-witness':lambda r:next(x for x in r['ledger']['rows'] if x['disposition']=='absent-operand').update(witnesses={}),
                'binding':lambda r:next(x for x in r['ledger']['rows'] if x['id'] in rules.BINDINGS).update(execution={}),
                'gds':lambda r:r.update(gds_sha256='a'*64),
                'checkpoint':lambda r:r.update(checkpoint_sha256='a'*64),
                'platform':lambda r:r.update(platform_fingerprint='a'*64),
                'top':lambda r:r.update(top='another'),
            }
            for name,change in changes.items():
                changed=clone(report);change(changed)
                with self.subTest(fault=name),self.assertRaises(ValueError):evaluated(changed)

    def test_export_refuses_missing_or_changed_policy_and_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,report=fixture(root);destination=root/'macro.zip'
            export(result,root,destination);original=destination.read_bytes()
            for fault in ('report','declaration','policy','resource','entire-claim'):
                changed=clone(result);data=changed['digital_result']
                if fault=='report':data['artifacts'].pop('sky130_rules')
                elif fault=='declaration':data['physical'].pop('sky130_rules')
                elif fault=='policy':data['environment'].pop('sky130_rules')
                elif fault=='resource':data['artifacts'].pop(next(iter(report['resources'].values())))
                else:
                    data.pop('physical');data['environment'].pop('sky130_rules')
                    data['artifacts']={k:v for k,v in data['artifacts'].items() if not k.startswith('sky130_rule')}
                with self.subTest(fault=fault),self.assertRaises(ValueError):export(changed,root,destination)
                self.assertEqual(destination.read_bytes(),original)

    def test_executor_keeps_failed_worker_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,report=fixture(root);data=result['digital_result']
            runner=SimpleNamespace(root=root,platform=job['project']['digital']['platform'],config={'top':'counter'},
                                   artifacts={k:v for k,v in data['artifacts'].items() if not k.startswith('sky130_rule')})
            runner.add_artifact=lambda key,path,**kw:runner.artifacts.update({key:artifact(root,path,**kw)})
            def failed(*args,**kwargs):
                path=root/'sky130-rule-checks/verified';path.mkdir()
                (path/'report.json').write_text(json.dumps({'status':'FAIL','error':'injected worker failure'}))
                raise ValueError('injected worker failure')
            runner.command=failed
            with self.assertRaisesRegex(ValueError,'injected worker failure'):rules.execute(runner)
            self.assertTrue(any(v['path'].endswith('verified/report.json') for v in runner.artifacts.values()))
            self.assertNotIn('sky130_rules',runner.artifacts)
            with self.assertRaises(FileExistsError):rules.execute(runner)

    def test_worker_authenticates_before_import_and_retains_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result,report=fixture(root);data=result['digital_result']
            request=dict(resources=str(root/'platform/verification'),policy=report['policy'],
                         gds=str(root/'filled.gds'),gds_sha256=report['gds_sha256'],
                         checkpoint=str(root/data['artifacts']['checkpoint']['path']),checkpoint_sha256=report['checkpoint_sha256'],
                         top=report['top'],platform_fingerprint=report['platform_fingerprint'],output=str(root/'worker'))
            helper=root/'platform/verification/helpers/scripts/sky130_rule_execution.py'
            helper.write_text('raise RuntimeError("UNTRUSTED CODE WAS EXECUTED")')
            code='import json; from icstudio.digital_sky130_rule_worker import execute; execute(json.loads('+repr(json.dumps(request))+'))'
            process=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(process.returncode,0)
            retained=json.loads((root/'worker/report.json').read_text())
            self.assertEqual(retained['status'],'FAIL')
            self.assertIn('resource',retained['error'])
            self.assertNotIn('UNTRUSTED CODE',retained['error'])

    def test_historical_jobs_do_not_acquire_a_qualification_claim(self):
        self.assertIsNone(rules.validate_saved({'artifacts':{}},Path('.')))
        self.assertIsNone(rules.execute(SimpleNamespace(platform={'name':'sky130hd'})))


if __name__=='__main__':unittest.main()
