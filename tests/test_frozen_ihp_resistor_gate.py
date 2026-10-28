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

if __name__=='__main__':unittest.main()
