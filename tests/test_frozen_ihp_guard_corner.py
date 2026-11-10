"""Adversarial source fixtures for the separate frozen guard gate, not installed evidence."""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from icstudio.model import example, clone
from icstudio.catalog import create_device
from icstudio.ihp_layout import install_mos
from icstudio.physical_cells import assign_port, transform_selection
from icstudio.interchange import export_layout
from scripts.qualify_standard_mos import load_technology
from scripts import verify_frozen_ihp_guard_corner as gate


class FrozenGuardIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.exe=self.root/'app';self.exe.write_bytes(b'unit-test executable identity, never executed')
        self.bundle=self.root/'_internal';self.bundle.mkdir();self.commit='a'*40;self.nonce='b'*32
        self.inputs=dict(package_sha256='c'*64,collection_sha256='d'*64,files={gate.GUARD_ASSETS+'/templates.json':'e'*64})
        self.report=dict(schema=1,status='passed',mode='guard-corner-safe-lifecycle',frozen=True,execution_id=self.nonce,
            build=dict(commit=self.commit,dirty=False,frozen=True),executable=str(self.exe),executable_sha256=gate.sha(self.exe),
            resource_root=str(self.bundle),template_path=str(self.bundle/gate.GUARD_ASSETS/'templates.json'),
            qualified=False,release_ready=False,full_family=False,installed_acceptance=False,native_execution=False,
            package_manifest_sha256='c'*64,bundle_collection_sha256='d'*64,template_sha256='e'*64)
    def check(self):return gate.header(self.report,self.exe,self.commit,self.nonce,self.inputs,self.bundle)
    def test_valid_fixture_and_each_source_or_frozen_identity_rejected(self):
        self.check()
        changes=[('frozen',False),('execution_id','c'*32),('mode','lifecycle'),('executable_sha256','0'*64),
                 ('resource_root',str(self.root)),('template_path',str(self.root/'external.json')),
                 ('package_manifest_sha256','0'*64),('bundle_collection_sha256','0'*64),('template_sha256','0'*64),
                 ('status','failed'),('errors',['failed'])]
        for key,value in changes:
            original=copy.deepcopy(self.report);self.report[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check()
            self.report=original
        for key,value in [('commit','0'*40),('dirty',True),('frozen',False)]:
            original=copy.deepcopy(self.report);self.report['build'][key]=value
            with self.subTest(build=key),self.assertRaises(ValueError):self.check()
            self.report=original
    def test_producer_cannot_claim_native_or_installed_acceptance(self):
        for key in ('qualified','release_ready','full_family','installed_acceptance','native_execution'):
            self.report[key]=True
            with self.subTest(flag=key),self.assertRaisesRegex(ValueError,'overclaim'):self.check()
            self.report[key]=False
    def test_changed_executable_and_missing_required_false_flag(self):
        self.exe.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'executable'):self.check()
        self.report['executable_sha256']=gate.sha(self.exe);self.report.pop('qualified')
        with self.assertRaisesRegex(ValueError,'overclaim'):self.check()
    def test_candidate_head_must_match_before_legacy_scan(self):
        with patch.object(gate.subprocess,'check_output',return_value='0'*40),patch.object(gate.legacy,'candidate') as scan:
            with self.assertRaisesRegex(ValueError,'HEAD'):gate.candidate(self.commit)
            scan.assert_not_called()
    def test_candidate_guard_assets_and_producer_are_required(self):
        names=('scripts/verify_frozen_ihp_guard_corner.py','scripts/verify_windows.ps1',*(gate.GUARD_ASSETS+'/'+n for n in ('templates.json','README.txt','Apache-2.0.txt')))
        for name in names:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'pinned')
        initial=dict(files={'icstudio/ihp_guard_corner_desktop_probe.py':'0'*64})
        with patch.object(gate,'ROOT',self.root),patch.object(gate.subprocess,'check_output',return_value=self.commit),patch.object(gate.legacy,'candidate',side_effect=lambda _:copy.deepcopy(initial)),patch.object(gate,'git_blob',return_value=b'pinned'):
            self.assertTrue(set(names)<=set(gate.candidate(self.commit)['files']))
            (self.root/names[-1]).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Guard candidate input'):gate.candidate(self.commit)
            (self.root/names[-1]).write_bytes(b'pinned');initial['files'].clear()
            with self.assertRaisesRegex(ValueError,'producer'):gate.candidate(self.commit)
    def test_deadline_commit_output_overlap_and_existing_evidence_rejected(self):
        for timeout in (0,-1,float('nan'),float('inf')):
            with self.subTest(timeout=timeout),self.assertRaises(ValueError):gate.verify(self.exe,self.root.parent/'unused-guard-test',self.commit,timeout)
        with self.assertRaises(ValueError):gate.verify(self.exe,self.root/'evidence','not-a-commit')
        with self.assertRaisesRegex(ValueError,'overlap'):gate.verify(self.exe,self.root/'evidence',self.commit)
    def test_evidence_inventory_detects_changed_missing_extra_and_escape(self):
        d=self.root/'evidence';d.mkdir();p=d/'raw';p.write_bytes(b'original');expected=gate.inventory(d)
        p.write_bytes(b'changed');self.assertNotEqual(gate.inventory(d),expected)
        p.unlink();self.assertNotEqual(gate.inventory(d),expected)
        p.write_bytes(b'original');(d/'extra').write_bytes(b'extra');self.assertNotEqual(gate.inventory(d),expected)
        with self.assertRaisesRegex(ValueError,'escaped'):gate.confined(d,self.exe)
    def test_evidence_symlink_rejected(self):
        link=self.root/'linked'
        try:link.symlink_to(self.exe)
        except OSError as exc:
            if os.name=='nt' and getattr(exc,'winerror',None) in (1,50,1314):self.skipTest('OS does not permit ordinary-user symbolic links')
            raise
        with self.assertRaisesRegex(ValueError,'symlink|junction'):gate.inventory(self.root)
    def test_runtime_changed_before_after_is_rejected_before_use(self):
        with self.assertRaisesRegex(ValueError,'runtime changed'):gate.check_runtime(self.root,dict(managed_runtime_before={'a':1},managed_runtime_after={'a':2}),self.bundle,{},'x')
    def test_linux_windows_wiring_keeps_old_and_adds_new_gate(self):
        for name in ('.github/workflows/build-desktop.yml','scripts/verify_windows.ps1'):
            text=(gate.ROOT/name).read_text()
            self.assertIn('verify_frozen_ihp_resistors.py',text);self.assertIn('verify_frozen_ihp_guard_corner.py',text)
            self.assertIn('--expected-commit',text)
    def test_backend_build_source_hashes_and_clean_state_are_required(self):
        folder=self.root/'backend';folder.mkdir();inputs=dict(workflow_hash='b'*64,engine_hash='c'*64)
        values=dict(BUILD_COMMIT=self.commit,BUILD_DIRTY=False,WORKFLOW_SOURCE_HASH='b'*64,ENGINE_SOURCE_HASH='c'*64)
        def put(): (folder/'build_info.py').write_text('\n'.join(k+' = '+repr(v) for k,v in values.items()))
        put();gate.build_metadata(folder,self.commit,inputs)
        for key,bad in [('BUILD_DIRTY',True),('BUILD_COMMIT','0'*40),('WORKFLOW_SOURCE_HASH','0'*64),('ENGINE_SOURCE_HASH','0'*64)]:
            old=values[key];values[key]=bad;put()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'metadata'):gate.build_metadata(folder,self.commit,inputs)
            values[key]=old
    def test_old_gate_matrix_and_new_matrix_remain_separate(self):
        expected=tuple(f'{m}-r{r}' for m in ('rsil','rppd','rhigh') for r in (0,90))
        self.assertEqual(gate.CASES,expected);self.assertEqual(len(gate.legacy.CASES),60)
        self.assertEqual(sum(1+5*(c.endswith('-r0'))+int('-v1-' in c and c.endswith('-r0')) for c in gate.legacy.CASES),225)
        self.assertEqual(gate.legacy.FAULTS,('terminal-open','body-open','terminal-short','reference-width','reference-model'))


class FrozenGuardLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        tech=load_technology('ihp-sg13g2')[0];self.lock=gate.load(Path(tech['package_root'])/'package.json')
        registry=self.root/'registry';shutil.copytree(tech['package_root'],registry);tech['package_root']=str(registry)
        self.templates=gate.load(gate.ROOT/gate.GUARD_ASSETS/'templates.json');self.projects={};rows=[];nonce='b'*32
        for case in gate.CASES:
            model,rotation=case.split('-r');rotation=int(rotation);folder=self.root/case;folder.mkdir()
            p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c.update(name=f'guard_{model}_r{rotation}_{nonce[:12]}',ports=['R1','R2','B'])
            d=create_device(tech,'sg13g2_pr/'+model+'.sym','R1');d['nets']=dict(p='R1',m='R2',body='B');d['model_params']={k:v['default'] for k,v in self.lock['technology']['simulation']['catalog']['sg13g2_pr/'+model+'.sym']['parameters'].items()};d['model_params'].update(w='2u',l='7u',m='1');d['physical_guard_routing']='corner-safe-m2-v1';d['physical_terminal_vias']=False;c['devices']=[d]
            install_mos(p,c['id'],d['id'])
            if rotation:transform_selection(p,c['id'],[s['id'] for s in c['shapes']],rotation=rotation)
            for pin,name in (('p','R1'),('m','R2'),('body','B')):
                port=next(v for v in c['layout_pins'] if v['pin']==pin);assign_port(p,c['id'],name,port['layer'],port['point'])
            params=c['pdk_layouts'][0]['spec']['values'];ref=folder/'reference.spice';ref.write_text(f'.subckt {c["name"]} R1 R2 B\nX_R1 R1 R2 B {model} '+ ' '.join(f'{k}={v}' for k,v in params.items())+f'\n.ends {c["name"]}\n')
            row=dict(case=case,model=model,rotation=rotation,width_um=2,length_um=7,terminal_access='Metal1',guard_routing='corner-safe-m2-v1',generation_undo_redo=True,same_option_regeneration=True,guard_option_stale=True,dimensions_stale=True,stale_preview_rejected=True,
                switches=[dict(iteration=i,guard_routing=label,undo_redo=True) for i in range(2) for label in ('Native Metal1 body','Corner-safe Metal2 body (2/7 um only)')],
                with_ports=dict(project=str(folder/'project.icproj'),reference=str(ref),schematic=str(ref)))
            blocked=clone(p);blocked['cells'][0]['devices'][0]['model_params'].update(w='7u',l='2u');bp=folder/'invalid.icproj';bp.write_text(json.dumps(blocked));h=gate.digest(blocked)
            row.update(interruption_controls=dict(form_cancel=True,review_cancel=True,selection_not_persisted=True),invalid_regeneration=dict(cell_id=c['id'],project=str(bp),project_sha256=gate.sha(bp),before_hash=h,after_hash=h,apply_disabled=True,unchanged=True,requested_guard=gate.CORNER_LABEL,requested_terminal_access='Metal1'))
            rows.append(row);self.projects[case]=p
        self.report=dict(execution_id=nonce,execution_root=str(self.root),template_sha256=gate.sha(gate.ROOT/gate.GUARD_ASSETS/'templates.json'),lifecycle=rows)
        spec=self.projects[gate.CASES[0]]['cells'][0]['pdk_layouts'][0]['spec'];self.report.update(source_hashes=spec['source_hashes'],guard_cifout_sha256=spec['guard_cifout_sha256'])
        self.publish()
    def publish(self,streams=True):
        for row in self.report['lifecycle']:
            p=self.projects[row['case']];c=p['cells'][0];folder=self.root/row['case'];path=Path(row['with_ports']['project']);path.write_text(json.dumps(p))
            row['with_ports'].update(project_sha256=gate.sha(path),design_hash=gate.design_hash(p),package_lock=clone(p['pdk']['package_lock']));prior=clone(p);prior['cells'][0]['layout_ports']=[];prior_path=folder/'prior.icproj';prior_path.write_text(json.dumps(prior));row['saved']=dict(project=str(prior_path),project_sha256=gate.sha(prior_path),design_hash=gate.design_hash(prior),package_lock=clone(prior['pdk']['package_lock']));row.update(generation=clone(c['pdk_layouts']),layout_pins=clone(c['layout_pins']),layout_ports=clone(c['layout_ports']))
            if streams:export_layout(p,folder/'layout.gds');export_layout(p,folder/'layout.oas')
    def check(self):return gate.lifecycle(self.root,self.report,self.lock,self.templates)
    def test_all_six_real_geometry_fixtures(self):self.assertEqual(len(self.check()),6)
    def test_missing_duplicate_reordered_cases_rejected(self):
        rows=self.report['lifecycle']
        for altered in (rows[:-1],rows+[rows[0]],[rows[1],rows[0],*rows[2:]]):
            self.report['lifecycle']=altered
            with self.assertRaisesRegex(ValueError,'cases'):self.check()
        self.report['lifecycle']=rows
    def test_rehashed_dimensions_ports_recipe_and_actual_masks_rejected(self):
        case=gate.CASES[0];original=clone(self.projects[case])
        mutations=[lambda c:c['devices'][0]['model_params'].update(w='3u'),lambda c:c['ports'].append('EXTRA'),lambda c:c['pdk_layouts'][0]['spec'].update(recipe='ihp-resistor-selected-v1'),lambda c:c['pdk_layouts'][0]['spec'].update(guard_cifout_sha256='0'*64),lambda c:c['pdk_layouts'][0]['spec'].update(guard_native_equivalence=True),lambda c:c['shapes'][0]['points'][0].__setitem__(0,c['shapes'][0]['points'][0][0]+5)]
        for mutate in mutations:
            self.projects[case]=clone(original);mutate(self.projects[case]['cells'][0]);self.publish()
            with self.subTest(mutation=mutations.index(mutate)),self.assertRaises(ValueError):self.check()
        self.projects[case]=original
    def test_rehashed_pin_layer_and_duplicate_pin_rejected(self):
        case=gate.CASES[0];original=clone(self.projects[case]);c=self.projects[case]['cells'][0];c['layout_pins'].append(clone(c['layout_pins'][0]));self.publish(streams=False)
        with self.assertRaisesRegex(ValueError,'pins'):self.check()
        self.projects[case]=original;c=original['cells'][0];next(p for p in c['layout_pins'] if p['pin']=='body')['layer']='Metal1.drawing';self.publish(streams=False)
        with self.assertRaisesRegex(ValueError,'layer'):self.check()
    def test_missing_lifecycle_action_and_changed_project_rejected(self):
        self.report['lifecycle'][0]['generation_undo_redo']=False
        with self.assertRaisesRegex(ValueError,'lifecycle'):self.check()
        self.report['lifecycle'][0]['generation_undo_redo']=True;Path(self.report['lifecycle'][0]['with_ports']['project']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'Changed'):self.check()
    def test_exact_switch_sequence_cancellation_and_invalid_preview_proof(self):
        row=self.report['lifecycle'][0];original=clone(row)
        changes=[('switches',[{}, {}, {}, {}]),('interruption_controls',dict(form_cancel=True,review_cancel=False,selection_not_persisted=True))]
        for key,value in changes:
            row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check()
            row.clear();row.update(clone(original))
        row['invalid_regeneration']['after_hash']='0'*64
        with self.assertRaisesRegex(ValueError,'Invalid regeneration'):self.check()
    def controls_fixture(self):
        legacy=[];inputs={'files':{}};controls=[]
        for name in ('mos.icproj','resistor.icproj'):
            source=gate.ROOT/gate.LEGACY/name;saved=self.root/('legacy-'+name);shutil.copyfile(source,saved)
            legacy.append(dict(source=str(source),source_sha256=gate.sha(source),saved=str(saved),saved_sha256=gate.sha(saved)));inputs['files'][gate.LEGACY+'/'+name]=gate.sha(source)
        for model in ('rsil','rppd','rhigh'):
            for suffix,size,kind in [(f'invalid-size-{i}',size,'invalid-size') for i,size in enumerate(((7,2),(.5,.5),(1,7),(2,7.000001)))]+[('corner-metal2',(2,7),'unsupported-corner-metal2'),('legacy-metal2',(2,7),'legacy-metal2-preserved')]:
                case=model+'-'+suffix;p=clone(self.projects[model+'-r0']);c=p['cells'][0];d=c['devices'][0];d.pop('physical_guard_routing');d['physical_terminal_vias']=suffix=='legacy-metal2';d['model_params'].update(w=str(size[0])+'u',l=str(size[1])+'u');c.update(shapes=[],layout_pins=[],layout_ports=[],layout_texts=[],pdk_layouts=[])
                if suffix=='legacy-metal2':install_mos(p,c['id'],d['id'])
                path=self.root/(case+'.icproj');path.write_text(json.dumps(p));row=dict(case=case,model=model,kind=kind)
                if suffix=='legacy-metal2':row.update(legacy_metal2_access_preserved=True,saved=dict(project=str(path),project_sha256=gate.sha(path)))
                else:row.update(project=str(path),project_sha256=gate.sha(path),cell_id=c['id'],before_hash=gate.digest(p),after_hash=gate.digest(p),apply_disabled=True,unchanged=True,requested_guard=gate.CORNER_LABEL,requested_terminal_access='Metal2' if suffix=='corner-metal2' else 'Metal1')
                controls.append(row)
        return dict(legacy=legacy,controls=controls),inputs
    def test_exact_eighteen_controls_two_legacy_and_relabel_rejection(self):
        report,inputs=self.controls_fixture();check=lambda:gate.producer_controls(self.root,report,gate.ROOT,inputs);check()
        for section in ('legacy','controls'):
            original=report[section]
            for rows in (original[:-1],original+[original[0]]):
                report[section]=rows
                with self.subTest(section=section),self.assertRaises(ValueError):check()
            report[section]=original
        first=report['controls'][0];first['kind']='legacy-metal2-preserved';first['saved']=report['controls'][5]['saved']
        with self.assertRaisesRegex(ValueError,'kind/model'):check()
    def test_source_inventory_missing_changed_extra_never_enters_installed_gate(self):
        controls,_=self.controls_fixture();report=clone(self.report);report.update(controls);report.update(schema=1,status='passed',mode='guard-corner-safe-lifecycle',frozen=False,source_unchanged=True,native_execution=False,qualified=False,installed_acceptance=False,release_ready=False,full_family=False,package_manifest_semantic_sha256=gate.digest(self.lock))
        marker=self.root/'marker';marker.write_bytes(b'original');gate.write(self.root/'files.json',gate.inventory(self.root,('report.json','files.json')));report['files_sha256']=gate.sha(self.root/'files.json');gate.write(self.root/'report.json',report)
        result=gate.source_audit(self.root,gate.ROOT);self.assertFalse(result['installed_acceptance']);self.assertFalse(result['native_execution'])
        marker.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'inventory'):gate.source_audit(self.root,gate.ROOT)
        marker.unlink()
        with self.assertRaisesRegex(ValueError,'inventory'):gate.source_audit(self.root,gate.ROOT)
        marker.write_bytes(b'original');(self.root/'extra').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError,'inventory'):gate.source_audit(self.root,gate.ROOT)
    def test_rehashed_control_dimensions_and_legacy_semantics_rejected(self):
        report,inputs=self.controls_fixture();row=report['controls'][0];path=Path(row['project']);p=gate.load(path);p['cells'][0]['devices'][0]['model_params']['w']='2u';path.write_text(json.dumps(p));row.update(project_sha256=gate.sha(path),before_hash=gate.digest(p),after_hash=gate.digest(p))
        with self.assertRaisesRegex(ValueError,'dimension'):gate.producer_controls(self.root,report,gate.ROOT,inputs)
        report,inputs=self.controls_fixture();row=report['legacy'][0];path=Path(row['saved']);p=gate.load(path);p['cells'][0]['name']='changed';path.write_text(json.dumps(p));row['saved_sha256']=gate.sha(path)
        with self.assertRaisesRegex(ValueError,'legacy project semantics'):gate.producer_controls(self.root,report,gate.ROOT,inputs)
    def test_full_guard_cut_control_changes_only_via_shapes(self):
        for model in ('rsil','rppd','rhigh'):
            p=self.projects[model+'-r0'];q=gate.guard_via_open(p);a=p['cells'][0];b=q['cells'][0]
            self.assertEqual(len(a['shapes'])-len(b['shapes']),54)
            self.assertEqual({k:v for k,v in a.items() if k!='shapes'},{k:v for k,v in b.items() if k!='shapes'})
            self.assertEqual(p,self.projects[model+'-r0'])
    def test_managed_failure_or_missing_proof_stops_next_job(self):
        rows=self.check();prepared=({},rows[0][1],{},['not executed'],{},0)
        for stage in ('execute','audit'):
            with patch.object(gate.legacy,'prepare_job',return_value=prepared),patch.object(gate,'execute_job',side_effect=ValueError('failed native launch') if stage=='execute' else None) as execute,patch.object(gate.legacy,'audit_job',side_effect=ValueError('missing managed proof')) as audit:
                with self.subTest(stage=stage),self.assertRaisesRegex(ValueError,'failed native|missing managed'):gate.run_jobs(None,rows,self.root,{}, {},{}, {},{},'b'*32,123)
                self.assertEqual(execute.call_count,1);self.assertEqual(audit.call_count,0 if stage=='execute' else 1)
    def test_managed_job_selection_and_guard_fault_proof_delegation(self):
        rows=self.check();calls=[]
        def prepare(executable,project,row,folder,runtime,inputs,physical,fault):
            calls.append((row['case'],fault));return {},project,{},['not executed'],{},0
        def audit(folder,row,job,project,ref,runtime,physical,records,fault):
            return dict(case=row['case'],fault=fault,execution=dict(native_directory=str(folder)))
        with patch.object(gate.legacy,'prepare_job',side_effect=prepare),patch.object(gate,'execute_job') as execute,patch.object(gate.legacy,'audit_job',side_effect=audit):
            result=gate.run_jobs(None,rows,self.root,{}, {},{}, {},{},'b'*32,123)
        expected=[(case,fault) for case in gate.CASES for fault in ((None,*gate.GUARD_FAULTS) if case.endswith('-r0') else (None,))]
        self.assertEqual([(x['case'],x['fault']) for x in result],expected);self.assertEqual(len(result),21);self.assertEqual(execute.call_count,21)
        self.assertTrue(all(c.kwargs['deadline']==123 for c in execute.call_args_list))
        self.assertEqual(calls[1],('rsil-r0',None))


if __name__=='__main__':unittest.main()
