"""Reference generation must preserve complete physical instance connectivity."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
import zipfile

from icstudio import digital_lvs_reference as ref
from icstudio.model import file_digest

MASTER = ref.PREFIX + 'inv_1'
CELL = f'''* Independent source; keep this comment.
.SUBCKT {MASTER} I ZN VDD VNW VPW VSS
M0 ZN I VSS VPW nfet_05v0 W=1.32U L=0.6U
M1 ZN I VDD VNW pfet_05v0 W=1.83U L=0.5U
.ENDS
'''
RAW = f'''* OpenROAD export
.SUBCKT top IN OUT VDD VSS
Xu0 IN OUT VDD _unconnected_0 _unconnected_1 VSS {MASTER}
.ENDS top
'''


class DigitalLVSReferenceTests(unittest.TestCase):
    def setUp(self):
        self.db = dict(version=1, dbu_per_micron=2000, instances=[dict(name='u0', master=MASTER,
            database_id=1, orientation='R0', bbox=[0,0,4000,10000], pins=[
                dict(name=p,net=n,direction=d) for p,n,d in
                [('I','IN','INPUT'),('ZN','OUT','OUTPUT'),('VDD','VDD','INOUT'),('VSS','VSS','INOUT')]])])
        self.observed = dict(schema=1, top='top', database=copy.deepcopy(self.db),
            ports=[dict(name=n,net=n,direction='INOUT') for n in ('IN','OUT','VDD','VSS')],
            global_connections=[dict(inst_pattern='.*',pin_pattern='^'+p+'$',net=n,region=None)
                                for p,n in [('VNW','VDD'),('VPW','VSS')]])
        self.library = {MASTER:CELL}

    def assemble(self, raw=RAW):
        return ref.assemble(raw,self.observed,self.db,self.library,top='top')

    def test_complete_reference_preserves_library_and_records_only_bulk_changes(self):
        text, report = self.assemble()
        self.assertIn(CELL,text)
        self.assertIn('Xu0 IN OUT VDD VDD VSS VSS '+MASTER,text)
        self.assertEqual(report['device_counts'], {'m':2})
        self.assertEqual([(c['pin'],c['after']) for c in report['explicit_bulk_bindings']], [('VNW','VDD'),('VPW','VSS')])
        self.assertEqual(report['intentional_unused_outputs'],[])
        self.assertFalse(report['qualified'])

    def test_continuations_preserve_pin_order(self):
        raw=RAW.replace('VDD _unconnected_0','VDD\n+ _unconnected_0')
        self.assertEqual(self.assemble(raw),self.assemble())
        with self.assertRaisesRegex(ValueError,'Orphan'):self.assemble('+ lost\n'+RAW)

    def test_missing_extra_and_duplicate_instances_fail(self):
        line=next(x for x in RAW.splitlines() if x.startswith('X'))
        for raw in (RAW.replace(line,''),RAW.replace(line,line+'\n'+line),RAW.replace('Xu0','Xu1')):
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.assemble(raw)

    def test_unknown_master_missing_pins_and_swapped_connections_fail(self):
        for before,after in ((MASTER,MASTER+'_unknown'),('IN OUT VDD _','OUT IN VDD _'),
                             ('_unconnected_0 ',''),('VDD _unconnected_0','OUT _unconnected_0')):
            with self.subTest(before=before),self.assertRaises(ValueError):self.assemble(RAW.replace(before,after))

    def test_every_captured_pin_must_be_present(self):
        self.db['instances'][0]['pins'].append(dict(name='extra',net='IN',direction='INPUT'))
        self.observed['database']=copy.deepcopy(self.db)
        with self.assertRaisesRegex(ValueError,'terminal coverage'):self.assemble()

    def test_changed_fresh_database_and_top_fail(self):
        self.observed['database']['instances'][0]['bbox'][0]=1
        with self.assertRaisesRegex(ValueError,'readback differs'):self.assemble()
        self.observed['database']=copy.deepcopy(self.db);self.observed['top']='another'
        with self.assertRaisesRegex(ValueError,'readback differs'):self.assemble()

    def test_top_port_omission_duplicate_and_wrong_net_fail(self):
        for raw in (RAW.replace('IN OUT VDD VSS','IN VDD VSS'), RAW.replace('IN OUT VDD VSS','IN IN VDD VSS')):
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'port coverage'):self.assemble(raw)
        self.observed['ports'][0]['net']='WRONG'
        with self.assertRaisesRegex(ValueError,'top ports'):self.assemble()

    def test_port_alias_uses_the_recorded_net_bijection(self):
        self.observed['ports'][1]['net']='internal'
        self.db['instances'][0]['pins'][1]['net']='internal'
        self.observed['database']=copy.deepcopy(self.db)
        text,report=self.assemble()
        self.assertIn('Xu0 IN OUT VDD VDD VSS VSS',text)
        self.assertIn(dict(port='OUT',net='internal'),report['top_port_net_mapping'])
        with self.assertRaisesRegex(ValueError,'differs from OpenDB'):
            self.assemble(RAW.replace('Xu0 IN OUT','Xu0 IN internal'))
        self.observed['ports'][0]['net']='internal'
        with self.assertRaisesRegex(ValueError,'distinct captured'):self.assemble()

    def test_bulk_rules_must_be_stored_literal_unambiguous_and_correct(self):
        old=copy.deepcopy(self.observed['global_connections'])
        for key,value in [('net','OUT'),('inst_pattern','u0'),('pin_pattern','.*'),('region','island')]:
            self.observed['global_connections']=copy.deepcopy(old)
            self.observed['global_connections'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.assemble()
        self.observed['global_connections']=old+[old[0]]
        with self.assertRaisesRegex(ValueError,'duplicate'):self.assemble()
        self.observed['global_connections']=old[:1]
        with self.assertRaisesRegex(ValueError,'explicit stored'):self.assemble()

    def test_absent_lef_bulk_cannot_already_be_silently_connected(self):
        with self.assertRaisesRegex(ValueError,'absent LEF'):self.assemble(RAW.replace('_unconnected_0','VDD'))

    def test_only_observed_unused_outputs_can_remain_open(self):
        self.db['instances'][0]['pins'][1]['net']='';self.observed['database']=copy.deepcopy(self.db)
        raw=RAW.replace('Xu0 IN OUT','Xu0 IN _unconnected_2')
        _,report=self.assemble(raw)
        self.assertEqual(report['intentional_unused_outputs'],[dict(instance='u0',pin='ZN',node='_unconnected_2',direction='OUTPUT')])
        with self.assertRaisesRegex(ValueError,'share a net'):self.assemble(raw.replace('_unconnected_2','_unconnected_0'))
        self.db['instances'][0]['pins'][1]['direction']='INPUT';self.observed['database']=copy.deepcopy(self.db)
        with self.assertRaisesRegex(ValueError,'differs from OpenDB'):self.assemble(raw)

    def test_real_net_cannot_alias_generated_open_names(self):
        self.db['instances'][0]['pins'][0]['net']='_unconnected_0';self.observed['database']=copy.deepcopy(self.db)
        with self.assertRaisesRegex(ValueError,'collides'):self.assemble()

    def test_library_missing_duplicate_hierarchical_or_parameterless_devices_fail(self):
        for bad in (CELL.replace('M1 ','M0 '),CELL.replace('M1 ','X1 '),CELL.replace(' L=0.5U',''),CELL.replace('.ENDS','')):
            self.library={MASTER:bad}
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.assemble()
        self.library={}
        with self.assertRaisesRegex(ValueError,'CDL coverage'):self.assemble()

    def test_top_commands_and_unterminated_subcircuits_fail(self):
        for raw in (RAW.replace('.ENDS top',''),RAW.replace('.ENDS top','.include external\n.ENDS top'),RAW+'Rextra A B 1k\n'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.assemble(raw)

    def test_diode_normalization_retains_polarity_geometry_and_multiplicity(self):
        name=ref.PREFIX+'antenna'
        self.library={name: f'.SUBCKT {name} I ZN VDD VNW VPW VSS\nD0 VPW I diode_nd2ps_06v0 0.2034p 1.85u $m=1\n.ENDS\n'}
        self.db['instances'][0]['master']=name;self.observed['database']=copy.deepcopy(self.db)
        text,report=self.assemble(RAW.replace(MASTER,name))
        self.assertIn('D0 VPW I diode_nd2ps_06v0 A=0.2034p P=1.85u M=1',text)
        self.assertEqual(report['device_counts'],{'d':1})

    def test_preparation_and_finalize_reject_stale_files_and_preserve_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);checkpoint=root/'checkpoint.odb';checkpoint.write_bytes(b'fixture')
            cdl=root/'cell.cdl';cdl.write_text(CELL,encoding='utf-8')
            masters={MASTER:dict(path=cdl,sha256=file_digest(cdl))}
            output=root/'reference';driver,request=ref.prepare(checkpoint,masters,output,top='top')
            self.assertTrue(driver.is_file())
            with self.assertRaisesRegex(ValueError,'new reference directory'):ref.prepare(checkpoint,masters,output,top='top')
            (output/'raw-reference.cdl').write_text(RAW,encoding='utf-8')
            observed={**self.observed,'checkpoint_sha256':file_digest(checkpoint),'raw_cdl_sha256':file_digest(output/'raw-reference.cdl')}
            (output/'engine-reference.json').write_text(json.dumps(observed),encoding='utf-8')
            cdl.write_text(CELL+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'source changed'):ref.finalize(output,self.db,top='top')
            cdl.write_text(CELL,encoding='utf-8')
            report=ref.finalize(output,self.db,top='top');self.assertEqual(report['reference_sha256'],file_digest(output/'reference.cdl'))
            with self.assertRaisesRegex(ValueError,'already exists'):ref.finalize(output,self.db,top='top')

    def runner(self, root):
        from icstudio.digital_flow import artifact
        checkpoint=root/'final.odb';checkpoint.write_bytes(b'fixture')
        database=root/'database.json';database.write_text(json.dumps(self.db),encoding='utf-8')
        cell=root/'platform/cell.cdl';cell.parent.mkdir(exist_ok=True);cell.write_text(CELL,encoding='utf-8')
        r=SimpleNamespace(root=root, config=dict(top='top'),tools=dict(openroad='openroad'),artifacts={},
            platform=dict(name='gf180', fingerprint='a'*64,files=[dict(path='cell.cdl',sha256=file_digest(cell),bytes=cell.stat().st_size)],
                lvs_reference=dict(recipe=ref.RECIPE,library_revision='fixture',masters={MASTER:'cell.cdl'})))
        r.add_artifact=lambda key,path:r.artifacts.update({key:artifact(root,path)})
        def save(key,data,name):
            path=root/name;path.write_text(json.dumps(data),encoding='utf-8');r.add_artifact(key,path)
        r.save_json=save
        def command(args,message,**kwargs):
            self.assertEqual(args[1:4],['-no_init','-exit','-python'])
            folder=root/'lvs-reference';request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
            raw=RAW.replace('.SUBCKT top ','.SUBCKT '+r.config['top']+' ').replace('.ENDS top','.ENDS '+r.config['top'])
            (folder/'raw-reference.cdl').write_text(raw,encoding='utf-8')
            observed={**self.observed,'checkpoint_sha256':request['checkpoint']['sha256'],'raw_cdl_sha256':file_digest(folder/'raw-reference.cdl')}
            (folder/'engine-reference.json').write_text(json.dumps(observed),encoding='utf-8')
        r.command=command;r.add_artifact('checkpoint',checkpoint);r.add_artifact('database',database)
        return r

    def test_finish_adapter_and_saved_semantic_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);r=self.runner(root);declared=ref.execute(r)
            data=dict(artifacts=r.artifacts,physical=dict(reference=declared),platform=dict(fingerprint=r.platform['fingerprint']),
                      environment=dict(lvs_reference=copy.deepcopy(r.platform['lvs_reference'])))
            report=ref.validate_saved(data,root)
            self.assertEqual(report['device_counts'],{'m':2})
            self.assertEqual(declared['placed_cells'],1)
            self.assertFalse(declared['qualified'])
            self.assertIn('lvs_reference_master_0',data['artifacts'])
            data['environment']['lvs_reference']['library_revision']='changed'
            with self.assertRaisesRegex(ValueError,'different implementation'):ref.validate_saved(data,root)
            data['environment']['lvs_reference']['library_revision']='fixture'
            report['instances'][0]['pins']['I']='wrong'
            r.save_json('lvs_reference_report',report,'lvs-reference-report.json')
            with self.assertRaisesRegex(ValueError,'no longer reproduces'):ref.validate_saved(data,root)

    def test_missing_saved_reference_and_unconfigured_jobs_have_different_status(self):
        self.assertIsNone(ref.validate_saved(dict(artifacts={}),Path('.')))
        with self.assertRaisesRegex(ValueError,'incomplete'):
            ref.validate_saved(dict(artifacts={},physical=dict(reference={'status':'reference_generated'})),Path('.'))
        self.assertIsNone(ref.execute(SimpleNamespace(platform={})))

    def test_platform_recipe_rejects_missing_unknown_and_aliased_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.runner(Path(temp));original=copy.deepcopy(r.platform);ref.validate(original)
            for key,value in [('recipe','unknown'),('library_revision',''),('masters',{MASTER:'missing.cdl'}),('masters',{})]:
                platform=copy.deepcopy(original);platform['lvs_reference'][key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):ref.validate(platform)
            platform=copy.deepcopy(original);platform['name']='sky130hd'
            with self.assertRaises(ValueError):ref.validate(platform)
            platform=copy.deepcopy(original);platform['lvs_reference']['masters'][MASTER+'_2']='cell.cdl'
            with self.assertRaisesRegex(ValueError,'own captured CDL'):ref.validate(platform)

    def test_reference_policy_invalidates_finished_result_identity(self):
        from icstudio.digital import counter_project
        from icstudio.digital_identity import stage_key
        cfg=counter_project()['digital'];cfg['platform']={}
        before=stage_key(cfg,'finish');mapped=stage_key(cfg,'mapped')
        cfg['platform']['lvs_reference']=dict(recipe=ref.RECIPE,library_revision='fixture',masters={MASTER:'cell.cdl'})
        self.assertNotEqual(stage_key(cfg,'finish'),before)
        self.assertEqual(stage_key(cfg,'mapped'),mapped)

    def test_macro_carries_reference_library_and_preserves_unqualified_lvs_status(self):
        from tests.test_digital_macro import DigitalMacroTests
        from icstudio import digital, digital_design, digital_identity
        from icstudio.digital_macro import export
        from icstudio.model import digest, design_digest
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);job,result=DigitalMacroTests().fixture(root,name='gf180')
            r=self.runner(root);r.config['top']='counter';self.observed['top']='counter'
            value=digital_design.config(job['project'],job['cell'])
            value['platform']['files']+=r.platform['files']
            value['platform']['fingerprint']=digest(value['platform']['files'])
            value['platform']['lvs_reference']=r.platform['lvs_reference']
            r.platform=value['platform'];digital_design.set_config(job['project'],job['cell'],value)
            declared=ref.execute(r);data=result['digital_result']
            data['artifacts'].update(r.artifacts);data['physical']=dict(reference=declared)
            data['environment']=dict(lvs_reference=copy.deepcopy(r.platform['lvs_reference']))
            data['platform']['fingerprint']=r.platform['fingerprint']
            result['design_hash']=design_digest(job['project'])
            data['source_hash']=digital.source_hash(value);data['input_key']=digital_identity.stage_key(value,'finish')
            (root/'input.json').write_text(json.dumps(job),encoding='utf-8')
            contract=export(result,root,root/'macro.zip')
            self.assertEqual(contract['qualification']['lvs'],'Not qualified by this export')
            self.assertEqual(contract['qualification']['generated_reference']['status'],'reference_generated')
            with zipfile.ZipFile(root/'macro.zip') as archive:
                for key in ('lvs_reference','lvs_reference_raw','lvs_reference_report','lvs_reference_master_0'):
                    self.assertEqual(archive.read(contract['artifacts'][key]['path']),
                                     (root/data['artifacts'][key]['path']).read_bytes())


if __name__=='__main__':unittest.main()
