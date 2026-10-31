"""Rehashed producer-input changes cannot bypass independent physical identity."""
import copy,json,pathlib,shutil,tempfile,unittest
from unittest.mock import patch
from icstudio.model import example,clone,save_project
from icstudio.catalog import create_device
from icstudio.ihp_resistors import geometry
from icstudio.physical_cells import assign_port
from icstudio.interchange import export_layout
from scripts.qualify_standard_mos import load_technology
from scripts import verify_frozen_ihp_resistors as gate

class FrozenIhpGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
        tech,_=load_technology('ihp-sg13g2');self.lock=gate.load(pathlib.Path(tech['package_root'])/'package.json')
        registry=self.root/'registry';shutil.copytree(tech['package_root'],registry);tech['package_root']=str(registry)
        p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];nonce='a'*32;top='ihp_rsil_g0_v0_r0_'+nonce[:12]
        c.update(name=top,ports=['R1','R2','B']);d=create_device(tech,'sg13g2_pr/rsil.sym','R1');d['nets']=dict(p='R1',m='R2',body='B');d['model_params'].update(w='0.5u',l='0.5u',m='1',mm_ok='1');d['physical_terminal_vias']=False;c['devices']=[d]
        drawn=geometry(tech,d);c['shapes']=drawn['shapes'];c['layout_pins']=drawn['pins'];c['pdk_layouts']=[drawn['record']]
        for pin,name in (('p','R1'),('m','R2'),('body','B')):
            port=next(v for v in c['layout_pins'] if v['pin']==pin);assign_port(p,c['id'],name,port['layer'],port['point'])
        self.project=p;self.case='rsil-g0-v0-r0';self.folder=self.root/self.case;self.folder.mkdir()
        reference=f'.subckt {top} R1 R2 B\nX_R1 R1 R2 B rsil w=0.5u l=0.5u m=1 mm_ok=1\n.ends {top}\n'
        (self.folder/'reference.spice').write_text(reference);(self.folder/'schematic.spice').write_text('.lib "'+str(registry/'libs.tech/ngspice/models/cornerRES.lib')+'" res_typ\n'+reference)
        self.row=dict(case=self.case,model='rsil',geometry_index=0,width_um=.5,length_um=.5,terminal_vias=False,rotation=0,
            cell_id=c['id'],top=top,instance_id=d['id'],nets=d['nets'],top_port_assignment='application cell-port dialog',undo_redo=True,
            model_ref=d['model_ref'],generation=c['pdk_layouts'],layout_pins=c['layout_pins'],layout_ports=c['layout_ports'],package_lock=p['pdk']['package_lock'])
        for key,name in [('project','project.icproj'),('reopened_project','reopened.icproj'),('reference','reference.spice'),('schematic','schematic.spice'),('gds','layout.gds'),('oasis','layout.oas')]:self.row[key]=str(self.folder/name)
        self.report=dict(execution_id=nonce,execution_root=str(self.root),template_sha256=drawn['record']['spec']['template_sha256'],source_hashes=drawn['record']['spec']['source_hashes'],lifecycle=[self.row])
        self.templates=gate.load(pathlib.Path(__import__('icstudio.ihp_resistors',fromlist=['__file__']).__file__).parent/'assets/qualification/ihp-resistor-templates/templates.json')
        self.publish()
    def publish(self,forged=False):
        if forged:
            for name in ('project.icproj','reopened.icproj'):(self.folder/name).write_text(json.dumps(self.project))
        else:
            save_project(self.project,self.folder/'project.icproj');save_project(self.project,self.folder/'reopened.icproj')
            export_layout(self.project,self.folder/'layout.gds');export_layout(self.project,self.folder/'layout.oas')
        self.row.update(design_hash=gate.design_hash(self.project),layout_pins=self.project['cells'][0]['layout_pins'],layout_ports=self.project['cells'][0]['layout_ports'],generation=self.project['cells'][0]['pdk_layouts'])
        for key in ('project','reopened_project','reference','schematic','gds','oasis'):self.row[key+'_sha256']=gate.sha(self.row[key])
    def check(self):
        with patch.object(gate,'CASES',(self.case,)):return gate.lifecycle(self.root,self.report,self.lock,self.templates)
    def test_real_fixture_and_rehashed_schematic_parameter_change(self):
        self.assertEqual(len(self.check()),1)
        self.project['cells'][0]['devices'][0]['model_params']['w']='0.6u';self.publish()
        with self.assertRaisesRegex(ValueError,'Actual saved schematic parameters'):self.check()
    def test_rehashed_duplicate_pin_or_port_is_rejected(self):
        for key in ('layout_pins','layout_ports'):
            original=clone(self.project);self.project['cells'][0][key].append(clone(self.project['cells'][0][key][0]));self.publish(forged=True)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Missing or duplicated'):self.check()
            self.project=original
    def test_rehashed_catalog_and_geometry_changes_are_rejected(self):
        self.project['pdk']['simulation']['catalog']['sg13g2_pr/rsil.sym']['prefix']='R';self.publish()
        with self.assertRaisesRegex(ValueError,'catalog binding'):self.check()
        self.project['pdk']['simulation']['catalog']['sg13g2_pr/rsil.sym']['prefix']='X'
        shape=self.project['cells'][0]['shapes'][0];shape['points'][0][0]+=5;self.publish()
        with self.assertRaisesRegex(ValueError,'masks or labels'):self.check()
    def test_source_report_cannot_satisfy_frozen_header_or_write_inside_deliverable(self):
        with self.assertRaisesRegex(ValueError,'frozen GUI-only'):gate.header(dict(schema=1,status='passed',mode='lifecycle',frozen=False,native_execution=False),self.root/'app','a'*40,'b'*32,{},self.root)
        app=self.root/'deliverable/app';app.parent.mkdir();app.write_bytes(b'not executed')
        out=app.parent/'evidence'
        with self.assertRaisesRegex(ValueError,'overlap installed'):gate.verify(app,out,'a'*40)
        self.assertFalse(out.exists())
    def test_uid_is_recorded_without_a_product_privilege_gate(self):
        completed=__import__('subprocess').CompletedProcess([],0,stdout='0\n',stderr='')
        with patch.object(gate.subprocess,'run',return_value=completed):value=gate.runtime_uid(dict(kind='wsl',distro='private'),{})
        self.assertEqual(value['uid'],0);self.assertFalse(value['privilege_claim'])
    def test_managed_receipt_tool_paths_remain_posix_on_windows(self):
        wsl=gate.native_tool_paths(dict(kind='wsl',root=r'\\wsl.localhost\private'))
        self.assertEqual(wsl,{name:'/opt/icstudio/bin/'+name for name in ('magic','netgen','ngspice','klayout')})
        linux=gate.native_tool_paths(dict(kind='linux',root='/native runtime'))
        self.assertEqual(linux['magic'],'/native runtime/opt/icstudio/bin/magic')
        self.assertTrue(all('\\' not in value for value in (*wsl.values(),*linux.values())))
    def test_rehashed_eco_masks_and_pin_anchors_are_independently_checked(self):
        from icstudio.physical_cells import transform_selection
        p=clone(self.project);cell=p['cells'][0];device=cell['devices'][0];device['model_params'].update(w='2u',l='7u')
        drawn=geometry(p['pdk'],device);cell.update(shapes=drawn['shapes'],layout_pins=drawn['pins'],pdk_layouts=[drawn['record']],layout_ports=[],layout_texts=[])
        transform_selection(p,cell['id'],[v['id'] for v in cell['shapes']],rotation=90)
        eco=dict(orientation=dict(rotation=90,mirror=False));gate.eco_binding(p,eco,self.lock,self.templates)
        altered=clone(p);altered['cells'][0]['shapes'][0]['points'][0][0]+=5
        with self.assertRaisesRegex(ValueError,'Actual ECO masks'):gate.eco_binding(altered,eco,self.lock,self.templates)
        altered=clone(p);altered['cells'][0]['layout_pins'][0]['point'][0]+=5
        with self.assertRaisesRegex(ValueError,'pin anchor'):gate.eco_binding(altered,eco,self.lock,self.templates)



class FrozenIhpSchedulerTests(unittest.TestCase):
    """Real subprocess fixtures exercise scheduling, not physical acceptance."""
    CHILD = r'''
import json,pathlib,sys,time,uuid
folder=pathlib.Path(sys.argv[1]);mode=sys.argv[2];case=sys.argv[3];fault=sys.argv[4]
started=time.monotonic();(folder/'started').write_text('started')
if mode=='fail':
    sibling=pathlib.Path(sys.argv[5])
    limit=time.monotonic()+5
    while not sibling.exists() and time.monotonic()<limit:time.sleep(.005)
    raise SystemExit(7)
if mode=='cancel':
    limit=time.monotonic()+10
    while not (folder/'digital-cancel').exists() and time.monotonic()<limit:time.sleep(.005)
    (folder/'cancel-observed').write_text('cancel')
    raise SystemExit(9)
if mode=='hang':time.sleep(60)
time.sleep(.04 if case.endswith('r0') and fault=='None' else .005)
value=dict(case=case,fault=None if fault=='None' else fault,started=started,ended=time.monotonic(),execution=dict(native_directory=uuid.uuid4().hex))
(folder/'fixture-result.json').write_text(json.dumps(value))
'''
    def setUp(self):
        import threading
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
        self.parent_thread=threading.get_ident();self.prepared=[];self.audited=[];self.modes={}
    def rows(self,cases=None):
        result=[]
        for case in cases or gate.CASES:
            model,g,v,r=case.split('-');result.append((dict(case=case,rotation=int(r[1:]),terminal_vias=bool(int(v[1:]))),{},None))
        return result
    def prepare(self,exe,project,row,folder,runtime,inputs,physical,fault):
        import sys,time,threading
        self.assertEqual(threading.get_ident(),self.parent_thread)
        self.prepared.append((row['case'],fault));folder.mkdir(parents=True,exist_ok=False)
        mode=self.modes.get(row['case'],'ok');sibling=self.root/'native/b-g0-v0-r90/positive/started'
        command=[sys.executable,'-c',self.CHILD,str(folder),mode,row['case'],str(fault),str(sibling)]
        attempt=dict(status='RUNNING',command=command);gate.write(folder/'invocation.json',attempt)
        return {},{},{},command,attempt,time.monotonic()
    def audit(self,folder,row,job,project,ref,runtime,physical,records,fault):
        import threading
        self.assertEqual(threading.get_ident(),self.parent_thread)
        self.assertEqual(gate.load(folder/'invocation.json')['status'],'complete')
        value=gate.load(folder/'fixture-result.json');self.assertEqual((value['case'],value['fault']),(row['case'],fault))
        self.audited.append((row['case'],fault));return value
    def run_matrix(self,rows,seconds=60):
        import time
        with patch.object(gate,'prepare_job',side_effect=self.prepare),patch.object(gate,'audit_job',side_effect=self.audit):
            return gate.run_jobs(None,rows,self.root,gate.git_environment(),{},{},{},{},'a'*32,time.monotonic()+seconds)
    def test_all225_fresh_processes_are_bounded_and_receipts_remain_ordered(self):
        rows=self.rows();expected=[]
        # Independently spell the finite physical matrix, including the15 via controls.
        for case in gate.CASES:
            expected.append((case,None))
            if case.endswith('-r0'):
                expected.extend((case,fault) for fault in ('terminal-open','body-open','terminal-short','reference-width','reference-model'))
                if '-v1-' in case:expected.append((case,'missing-via'))
        jobs=self.run_matrix(rows)
        self.assertEqual(len(jobs),225);self.assertEqual(sum(j['fault'] is None for j in jobs),60)
        self.assertEqual([(j['case'],j['fault']) for j in jobs],expected)
        self.assertEqual(self.prepared,expected);self.assertEqual(set(self.audited),set(expected))
        self.assertEqual(gate.load(self.root/'native-progress.json')['jobs'],jobs)
        self.assertEqual(len({j['execution']['native_directory'] for j in jobs}),225)
        active=maximum=0
        for _,change in sorted([(j['started'],1) for j in jobs]+[(j['ended'],-1) for j in jobs]):
            active+=change;maximum=max(maximum,active)
        self.assertEqual(maximum,2);self.assertEqual(active,0)
    def test_worker_failure_cancels_sibling_and_never_launches_third(self):
        import subprocess
        cases=('a-g0-v0-r90','b-g0-v0-r90','c-g0-v0-r90');self.modes={cases[0]:'fail',cases[1]:'cancel'}
        with self.assertRaises(subprocess.CalledProcessError):self.run_matrix(self.rows(cases))
        self.assertEqual(self.prepared,[(cases[0],None),(cases[1],None)]);self.assertFalse(self.audited)
        self.assertTrue((self.root/'native'/cases[1]/'positive/cancel-observed').exists())
        for case in cases[:2]:
            record=gate.load(self.root/'native'/case/'positive/invocation.json')
            self.assertEqual(record['status'],'failed');self.assertIsNotNone(record['returncode'])
    def test_parent_deadline_cancels_and_reaps_both_without_more_launches(self):
        cases=('a-g0-v0-r90','b-g0-v0-r90','c-g0-v0-r90');self.modes={case:'cancel' for case in cases}
        with self.assertRaisesRegex(ValueError,'Parent physical deadline'):self.run_matrix(self.rows(cases),seconds=.5)
        self.assertEqual(len(self.prepared),2);self.assertFalse(self.audited)
        for case in cases[:2]:
            folder=self.root/'native'/case/'positive';record=gate.load(folder/'invocation.json')
            self.assertTrue((folder/'cancel-observed').exists());self.assertEqual(record['status'],'failed');self.assertIsNotNone(record['returncode'])
    def test_audit_rejection_cancels_active_sibling_before_return(self):
        cases=('a-g0-v0-r90','b-g0-v0-r90','c-g0-v0-r90');self.modes={cases[1]:'cancel'}
        with patch.object(self,'audit',side_effect=ValueError('independent audit rejected')):
            with self.assertRaisesRegex(ValueError,'independent audit rejected'):self.run_matrix(self.rows(cases))
        self.assertEqual(len(self.prepared),2)
        record=gate.load(self.root/'native'/cases[1]/'positive/invocation.json')
        self.assertEqual(record['status'],'failed');self.assertIsNotNone(record['returncode'])
    def test_unresponsive_worker_is_killed_and_reaped_at_parent_deadline(self):
        import time
        case='a-g0-v0-r90';self.modes={case:'hang'};tick=time.monotonic()
        with self.assertRaisesRegex(ValueError,'Parent physical deadline'):self.run_matrix(self.rows((case,)),seconds=.3)
        self.assertLess(time.monotonic()-tick,6)
        record=gate.load(self.root/'native'/case/'positive/invocation.json')
        self.assertEqual(record['status'],'failed');self.assertIsNotNone(record['returncode'])

    def test_cancelled_native_supervisor_receipt_is_bound_to_runtime(self):
        runtime=dict(kind='wsl',root=str(self.root/'private-runtime'),distro='private')
        native='/var/tmp/icstudio-physical/'+'a'*32;folder=self.root/'host';folder.mkdir()
        work=pathlib.Path(runtime['root'])/native.lstrip('/');work.mkdir(parents=True)
        gate.write(folder/'physical-backend.json',dict(runtime=runtime,native_directory=native))
        gate.write(work/'supervisor-exit.json',dict(returncode=-15))
        result=gate.native_shutdown(folder,runtime)
        self.assertEqual(result['status'],'supervisor-exited');self.assertEqual(result['returncode'],-15)
        self.assertEqual(result['receipt_sha256'],gate.sha(work/'supervisor-exit.json'))
        with self.assertRaisesRegex(ValueError,'runtime receipt differs'):gate.native_shutdown(folder,dict(runtime,distro='other'))
        gate.write(folder/'physical-backend.json',dict(runtime=runtime,native_directory='/var/tmp/another-job/'+'a'*32))
        with self.assertRaisesRegex(ValueError,'native directory differs'):gate.native_shutdown(folder,runtime)

    def test_failed_cancel_marker_cannot_prevent_worker_reaping(self):
        case='a-g0-v0-r90';self.modes={case:'hang'}
        with patch.object(gate,'signal_cancel',return_value='fixture cannot create marker'):
            with self.assertRaisesRegex(ValueError,'Parent physical deadline'):self.run_matrix(self.rows((case,)),seconds=.3)
        record=gate.load(self.root/'native'/case/'positive/invocation.json')
        self.assertEqual(record['status'],'failed');self.assertIsNotNone(record['returncode'])
        self.assertEqual(record['cancellation_error'],'fixture cannot create marker')

if __name__=='__main__':unittest.main()
