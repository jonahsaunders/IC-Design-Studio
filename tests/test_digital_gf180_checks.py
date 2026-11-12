"""Complete native database coverage and combined finish-result integrity."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import klayout.db as k

from icstudio import digital_gf180_checks as check
from icstudio.gf180_cdl import enable_geometry
from icstudio.model import file_digest

MOS = '.SUBCKT design A B VDD VSS\nM0 B A VSS VSS nfet_05v0 W=1u L=.5u\nM1 B A VDD VDD pfet_05v0 W=2u L=.5u\n.ENDS\n'
DIODE = '.SUBCKT design A B VDD VSS\nD0 A VDD diode_pd2nw_06v0 A=.2034p P=1.85u M=1\nD1 VSS B diode_nd2ps_06v0 A=.2034p P=1.85u M=1\n.ENDS\n'


def comparison(folder, left=MOS, right=MOS, *, geometry=True):
    """Real serialized KLayout comparison, without claiming physical extraction."""
    folder.mkdir(exist_ok=True)
    a=folder/'layout.cdl';b=folder/'reference.cdl'
    a.write_text(left,encoding='utf-8');b.write_text(right,encoding='utf-8')
    db=k.LayoutVsSchematic('design',.001);db.extract_netlist()
    db.netlist().read(str(a),k.NetlistSpiceReader())
    reference=k.Netlist();reference.read(str(b),k.NetlistSpiceReader())
    if geometry:
        enable_geometry(db.netlist());enable_geometry(reference)
    db.reference=reference;db.compare(k.NetlistComparer())
    path=folder/'comparison.lvsdb';db.write(str(path));return path


class DigitalGF180ChecksTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.reference=dict(top='design',device_counts={'m':2},top_ports=4)

    def test_real_database_checks_complete_terminal_and_primary_geometry_mapping(self):
        r=check.inspect_database(comparison(self.root),self.reference)
        self.assertTrue(r['passed'],r);self.assertEqual(r['checked_device_terminals'],8)
        self.assertEqual(r['checked_primary_parameters'],4);self.assertEqual(r['extraction_logs'],[])

    def test_native_width_length_gate_and_bulk_faults_fail(self):
        for before,after in [('W=1u','W=1.1u'),('L=.5u','L=.6u'),('B A VSS VSS','B VDD VSS VSS'),('B A VSS VSS','B A VSS VDD')]:
            with self.subTest(before=before):
                r=check.inspect_database(comparison(self.root,right=MOS.replace(before,after)),self.reference)
                self.assertFalse(r['passed'],r)

    def test_diode_dimensions_must_be_primary_and_faults_fail(self):
        expected=dict(top='design',device_counts={'d':2},top_ports=4)
        self.assertTrue(check.inspect_database(comparison(self.root,DIODE,DIODE),expected)['passed'])
        self.assertFalse(check.inspect_database(comparison(self.root,DIODE,DIODE,geometry=False),expected)['passed'])
        for old,new in [('A=.2034p','A=.3p'),('P=1.85u','P=2u'),('D0 A VDD','D0 VDD A')]:
            with self.subTest(old=old):
                self.assertFalse(check.inspect_database(comparison(self.root,DIODE,DIODE.replace(old,new)),expected)['passed'])

    def test_false_counts_ports_and_top_cannot_accept_a_matching_subset(self):
        path=comparison(self.root)
        for field,value in [('device_counts',{'m':1}),('device_counts',{'d':2}),('top_ports',3)]:
            expected={**self.reference,field:value};self.assertFalse(check.inspect_database(path,expected)['passed'])
        with self.assertRaisesRegex(ValueError,'another top'):
            check.inspect_database(path,{**self.reference,'top':'wrong'})

    def test_unsupported_primitives_and_unflattened_circuits_fail(self):
        resistor='.SUBCKT design A B VDD VSS\nR0 A B 1k\n.ENDS\n'
        self.assertFalse(check.inspect_database(comparison(self.root,resistor,resistor),self.reference)['passed'])
        hierarchical='.SUBCKT child A B\nR0 A B 1k\n.ENDS\n.SUBCKT design A B VDD VSS\nX0 A B child\n.ENDS\n'
        with self.assertRaisesRegex(ValueError,'complete captured top'):
            check.inspect_database(comparison(self.root,hierarchical,hierarchical),self.reference)

    def test_extraction_warnings_remain_blocking_even_when_graph_matches(self):
        from tests.test_klayout_lvs_exchange import resistor_database
        path=resistor_database(self.root,extra_island=True)
        r=check.inspect_database(path,dict(top='TEST',device_counts={'m':1},top_ports=2))
        self.assertFalse(r['passed']);self.assertTrue(r['extraction_logs'])
        self.assertIn('Native extraction has unresolved diagnostics.',r['issues'])

    def test_both_independent_checks_are_required(self):
        for a in (False,True):
            for b in (False,True):
                r=check.verdict({'passed':a},{'passed':b})
                self.assertEqual(r['passed'],a and b);self.assertFalse(r['qualified'])

    def platform(self):
        master='gf180mcu_fd_sc_mcu9t5v0__test_1'
        files=[dict(path='rules/'+n,sha256=h,bytes=1) for n,h in check.LOCK['files'].items()]
        files += [dict(path='cell.gds',sha256='a'*64,bytes=1),dict(path='cell.cdl',sha256='b'*64,bytes=1)]
        return dict(name='gf180',fingerprint='c'*64,files=files,
            lvs_reference=dict(recipe='gf180-9t-opendb-reference-v1',library_revision='fixture',masters={master:'cell.cdl'}),
            gf180_connectivity=dict(recipe=check.RECIPE,rules_root='rules',masters={master:'cell.gds'}))

    def test_platform_requires_exact_locked_recipe_and_complete_independent_views(self):
        platform=self.platform();check.validate(platform)
        cases=[]
        p=copy.deepcopy(platform);p['files'][0]['sha256']='0'*64;cases.append(p)
        p=copy.deepcopy(platform);p['files'].pop(0);cases.append(p)
        p=copy.deepcopy(platform);p['files'].append(dict(path='rules/extra.lvs',sha256='0'*64,bytes=1));cases.append(p)
        p=copy.deepcopy(platform);p['gf180_connectivity']['masters']={};cases.append(p)
        p=copy.deepcopy(platform);p['gf180_connectivity']['rules_root']='../rules';cases.append(p)
        p=copy.deepcopy(platform);p['name']='sky130hd';cases.append(p)
        p=copy.deepcopy(platform);p.pop('lvs_reference');cases.append(p)
        for index,p in enumerate(cases):
            with self.subTest(index=index),self.assertRaises(ValueError):check.validate(p)

    def test_policy_changes_invalidate_finish_only(self):
        from icstudio.digital import counter_project
        from icstudio.digital_identity import stage_key
        cfg=counter_project()['digital'];cfg['platform']={}
        finish=stage_key(cfg,'finish');mapped=stage_key(cfg,'mapped')
        cfg['platform']['gf180_connectivity']=self.platform()['gf180_connectivity']
        self.assertNotEqual(finish,stage_key(cfg,'finish'));self.assertEqual(mapped,stage_key(cfg,'mapped'))

    def runner(self):
        from tests.test_gf180_connectivity import GF180ConnectivityTests
        from icstudio.digital_flow import artifact
        fixture=GF180ConnectivityTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        root=fixture.root;self.fixture=fixture
        (root/'checkpoint.odb').write_bytes(b'checkpoint-fixture')
        platform=self.platform();folder=root/'platform';folder.mkdir()
        shutil.copy2(fixture.library[fixture.master]['path'],folder/'cell.gds')
        (folder/'cell.cdl').write_text(MOS,encoding='utf-8')
        rule=folder/'rules/klayout/lvs/gf180mcu.lvs';rule.parent.mkdir(parents=True);rule.write_text('fixture',encoding='utf-8')
        lock=copy.deepcopy(check.LOCK);lock['files']={'klayout/lvs/gf180mcu.lvs':file_digest(rule)}
        platform['files']=[dict(path=p.relative_to(folder).as_posix(),sha256=file_digest(p),bytes=p.stat().st_size) for p in folder.rglob('*') if p.is_file()]
        r=SimpleNamespace(root=root,platform=platform,config=dict(top='design'),tools=dict(klayout='klayout'),artifacts={})
        r.add_artifact=lambda key,path:r.artifacts.update({key:artifact(root,path)})
        def save(key,data,name):
            path=root/name;path.write_text(json.dumps(data),encoding='utf-8');r.add_artifact(key,path)
        r.save_json=save
        for key,p in [('checkpoint',root/'checkpoint.odb'),('database',fixture.db),('layout_preview',fixture.view),('gds',fixture.gds),('lvs_reference',folder/'cell.cdl')]:r.add_artifact(key,p)
        ref={**self.reference,'schema':1,'status':'reference_generated','qualified':False,'scope':'reference fixture',
             'instances':[dict(cell=fixture.master)],'checkpoint_sha256':r.artifacts['checkpoint']['sha256'],
             'reference_sha256':r.artifacts['lvs_reference']['sha256'],'platform_fingerprint':platform['fingerprint'],
             'explicit_bulk_bindings':[],'intentional_unused_outputs':[]}
        save('lvs_reference_report',ref,'reference-report.json')
        from icstudio.digital_lvs_reference import summary
        r.reference=summary(ref)
        native=comparison(root/'native')
        def command(args,message,**kwargs):
            self.assertIn('metal_level=5LM',args);self.assertIn('combine=false',args);self.assertIn('top_lvl_pins=true',args)
            shutil.copy2(native,root/'gf180-connectivity/comparison.lvsdb')
            (root/'gf180-connectivity/extracted.cir').write_text(MOS,encoding='utf-8')
        r.command=command
        return r,lock

    def test_finish_adapter_and_semantic_saved_readback(self):
        r,lock=self.runner()
        with patch.object(check,'LOCK',lock):
            report=check.execute(r,r.reference)
            data=dict(artifacts=r.artifacts,physical=dict(gf180_connectivity=report),platform=dict(name='gf180',fingerprint=r.platform['fingerprint']),
                      environment=dict(gf180_connectivity=r.platform['gf180_connectivity']))
            self.assertEqual(check.validate_saved(data,r.root),report)
            self.assertTrue(report['passed']);self.assertFalse(report['qualified'])
            self.assertIn('gf180_check_master_0',r.artifacts);self.assertIn('gf180_check_rule_0',r.artifacts)
            report['native']['checked_device_terminals']=7
            r.save_json('gf180_connectivity',report,'gf180-connectivity/report.json')
            with self.assertRaisesRegex(ValueError,'no longer reproduces'):check.validate_saved(data,r.root)

    def test_verification_layout_preserves_masks_top_texts_and_original_file(self):
        r,_=self.runner();source=self.fixture.gds;sha=file_digest(source);dest=r.root/'prepared.gds'
        result=check.prepare_layout(source,dest,'design')
        self.assertEqual(result['removed_child_labels'],2);self.assertEqual(file_digest(source),sha)
        self.assertTrue(result['all_physical_masks_unchanged']);self.assertEqual(check.verify_layout(source,dest,'design'),result)
        with self.assertRaisesRegex(ValueError,'Preserve'):check.prepare_layout(source,dest,'design')
        with self.assertRaisesRegex(ValueError,'child-cell labels'):check.verify_layout(source,source,'design')

    def test_changed_physical_masks_or_top_labels_cannot_be_used_for_verification(self):
        r,_=self.runner();source=self.fixture.gds
        for name in ('geometry','labels'):
            dest=r.root/(name+'.gds');check.prepare_layout(source,dest,'design')
            layout=k.Layout();layout.read(str(dest));top=layout.top_cell()
            if name=='geometry':top.shapes(layout.layer(34,0)).insert(k.Box(100,100,200,200))
            else:top.shapes(layout.layer(34,10)).insert(k.Text('invented',k.Trans(100,100)))
            layout.write(str(dest))
            with self.subTest(name=name),self.assertRaises(ValueError):check.verify_layout(source,dest,'design')

    def test_saved_policy_inputs_and_stack_tampering_are_rejected(self):
        r,lock=self.runner()
        with patch.object(check,'LOCK',lock):
            report=check.execute(r,r.reference)
            data=dict(artifacts=r.artifacts,physical=dict(gf180_connectivity=report),platform=dict(name='gf180',fingerprint=r.platform['fingerprint']),
                      environment=dict(gf180_connectivity=copy.deepcopy(r.platform['gf180_connectivity'])))
            data['platform']['name']='gf180d'
            with self.assertRaisesRegex(ValueError,'stack'):check.validate_saved(data,r.root)
            data['platform']['name']='gf180';data['environment']['gf180_connectivity']['rules_root']='other'
            with self.assertRaisesRegex(ValueError,'rules differ'):check.validate_saved(data,r.root)
            data['environment']['gf180_connectivity']['rules_root']='rules';report['inputs'].pop('checkpoint')
            r.save_json('gf180_connectivity',report,'gf180-connectivity/report.json')
            with self.assertRaisesRegex(ValueError,'input coverage'):check.validate_saved(data,r.root)

    def test_metal_failure_retains_both_reports_and_rejects_finish(self):
        r,lock=self.runner();self.fixture.top.shapes(self.fixture.layout.layer(35,0)).clear();self.fixture.save_sources()
        r.add_artifact('gds',self.fixture.gds)
        with patch.object(check,'LOCK',lock),self.assertRaisesRegex(ValueError,'connectivity failed'):
            check.execute(r,r.reference)
        report=json.loads((r.root/'gf180-connectivity/report.json').read_text(encoding='utf-8'))
        self.assertTrue(report['native']['passed']);self.assertFalse(report['metal']['passed'])
        self.assertIn('gf180_check_database',r.artifacts)

    def test_modified_reference_cannot_reuse_the_generator_identity(self):
        r,lock=self.runner();(r.root/'platform/cell.cdl').write_text(MOS.replace('W=1u','W=1.1u'),encoding='utf-8')
        r.add_artifact('lvs_reference',r.root/'platform/cell.cdl')
        with patch.object(check,'LOCK',lock),self.assertRaisesRegex(ValueError,'exact completed reference'):
            check.execute(r,r.reference)

    def test_old_jobs_and_missing_new_evidence_are_distinct(self):
        self.assertIsNone(check.execute(SimpleNamespace(platform={}),None))
        self.assertIsNone(check.validate_saved(dict(artifacts={}),self.root))
        with self.assertRaisesRegex(ValueError,'incomplete'):
            check.validate_saved(dict(artifacts={},physical=dict(gf180_connectivity={})),self.root)


if __name__=='__main__':unittest.main()
