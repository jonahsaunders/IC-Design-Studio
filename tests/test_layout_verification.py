import json
import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import klayout.db as db
from icstudio.layout_verification import reference,verification_stream,run
from icstudio import layout_verification as verification
from icstudio.model import example


class LayoutVerificationTests(unittest.TestCase):
    def test_legacy_labels_and_repeated_child_labels_do_not_merge_local_nets(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ly=db.Layout();ly.dbu=.001
            top=ly.create_cell('top');child=ly.create_cell('child');metal=ly.layer(68,20);label=ly.layer(68,5)
            child.shapes(metal).insert(db.Box(0,0,100,100));child.shapes(label).insert(db.Text('local',db.Trans(50,50)))
            top.insert(db.CellInstArray(child.cell_index(),db.Trans(),db.Vector(1000,0),db.Vector(0,0),3,1))
            top.shapes(label).insert(db.Text('IN',db.Trans(50,50)));top.shapes(label).insert(db.Text('OUT',db.Trans(2050,50)))
            ly.write(str(root/'original.gds'))
            r=verification_stream(root/'original.gds','top',['IN','OUT'],root/'engine.gds',pin_layers={(68,16)})
            actual=db.Layout();actual.read(str(root/'engine.gds'));c=actual.cell('top')
            self.assertEqual(list(c.each_inst()),[])
            self.assertEqual(sorted(s.text.string for s in c.shapes(actual.layer(68,5)).each()),['IN','OUT'])
            self.assertEqual(db.Region(c.shapes(actual.layer(68,20))).area(),30000)
            self.assertEqual(r['removed_noninterface_labels'],1)
            with self.assertRaisesRegex(ValueError,'Missing top-level'):
                verification_stream(root/'original.gds','top',['IN','missing'],root/'absent.gds',pin_layers={(68,16)})
            top.shapes(ly.layer(68,16)).insert(db.Text('UNEXPECTED',db.Trans(50,50)));ly.write(str(root/'extra.gds'))
            with self.assertRaisesRegex(ValueError,'extra explicit'):
                verification_stream(root/'extra.gds','top',['IN','OUT'],root/'extra-out.gds',pin_layers={(68,16)})

    def test_reference_requires_real_interface_and_closed_sources(self):
        text='.subckt dut a b\nR1 a b 1k\n.ends\n'
        self.assertEqual(reference(text,'dut')['ports'],['a','b'])
        for other in (text+'.include missing.spice\n',text.replace('a b\n','a A\n'),text.replace('R1 a b 1k','')):
            with self.assertRaises(ValueError):reference(other,'dut')

    def test_missing_runtime_is_reported_as_blocked_without_simulation(self):
        p=example('empty');ref=reference('.subckt dut a b\nR1 a b 1k\n.ends','dut')
        with tempfile.TemporaryDirectory() as td:
            r=run(p,p['top'],td,{},ref,blocked_reason='Install the physical runtime')
            self.assertEqual(r['status'],'blocked');self.assertEqual(len(r['stages']),6)
            self.assertEqual(r['stages'][0]['error'],'Install the physical runtime')
            self.assertTrue(all(s['status']=='not_run' for s in r['stages'][1:]))

    def test_varactor_default_is_omitted_only_in_lvs_with_multiplicity_retained(self):
        from icstudio.native_spice import render
        def device(vm,model='sky130_fd_pr__cap_var_lvt'):
            return {'native_spice':{'type':'device','tokens':[{'kind':'literal','value':f'XC1 a b c {model} W=2 L=1 VM={vm} m=3'}]}}
        self.assertIn('VM=1',render(device('1')))
        self.assertNotIn('VM=',render(device('1'),mode='lvs'))
        self.assertIn('m=3',render(device('1'),mode='lvs'))
        self.assertIn('VM=2',render(device('2'),mode='lvs'))
        self.assertIn('VM=1',render(device('1','unknown_model'),mode='lvs'))

    def test_external_varactor_defaults_preserve_unrelated_parameters_and_source(self):
        from icstudio.native_spice import lvs_defaults
        source='* sky130_fd_pr__cap_var_lvt VM=1\n.subckt sky130_fd_pr__cap_var_lvt a b VM=1\nXC1 a b sky130_fd_pr__cap_var_lvt\n+ VM=1.0 W=2 L=1 m=3\nXC2 a b sky130_fd_pr__cap_var_lvt VM=2\nXC3 a b other_model VM=1\nXC4 a b sky130_fd_pr__cap_var_lvt VM={gain}\n.ends\n'
        text,changes=lvs_defaults(source)
        self.assertEqual(text,source.replace('sky130_fd_pr__cap_var_lvt\n+ VM=1.0 W=2','sky130_fd_pr__cap_var_lvt W=2'))
        self.assertEqual(changes,[dict(instance='XC1',parameter='VM',default='1')])
        ambiguous='XC1 a b sky130_fd_pr__cap_var_lvt VM=2 VM=1'
        self.assertEqual(lvs_defaults(ambiguous),(ambiguous,[]))


class IHPMIMCoverageTests(unittest.TestCase):
    def project(self,process='ihp-sg13g2'):
        p=example('empty');p['pdk']['package_lock']={'id':process};return p

    def blocked(self,root,engine='magic',process='ihp-sg13g2'):
        p=self.project(process);ref=reference('.subckt dut a b\nX1 a b cap_cmim w=7u l=7u m=1\n.ends\n','dut')
        return run(p,p['top'],root,{},ref,blocked_reason='Fixture stops before native execution',
                   drc_engine=engine,lvs_extractor='ihp-klayout' if engine=='ihp-public' else 'magic')

    def fixture(self,root):
        from icstudio.ihp_klayout_drc import LOCK_SHA256,ENTRIES
        from icstudio.model import file_digest
        report=self.blocked(root/'blocked','ihp-public');source=root/'source.gds';source.write_bytes(b'captured input fixture')
        directory=root/'drc';rows=[]
        for name,entry in ENTRIES.items():
            path=directory/name/'findings.lyrdb';path.parent.mkdir(parents=True);path.write_bytes((name+' native report fixture').encode())
            rows.append(dict(name=name,entry=entry,report=name+'/findings.lyrdb',report_sha256=file_digest(path),violations=0))
        result=dict(schema=1,source_lock_sha256=LOCK_SHA256,input_sha256=file_digest(source),top=report['cell_name'],decks=rows,violations=0)
        return report,result,source,directory

    def test_magic_and_unfinished_public_never_claim_the_maximum_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            for engine,reason in (('magic','unsupported_by_selected_checker'),('ihp-public','not_completed')):
                report=self.blocked(Path(temp)/engine,engine)
                self.assertEqual(report['status'],'blocked')
                self.assertEqual(report['drc_coverage']['MIM.g']['status'],'NOT_CHECKED')
                self.assertEqual(report['drc_coverage']['MIM.g']['reason'],reason)
                self.assertIn('not checked',report['qualification'])
                self.assertIn('public geometry decks',report['qualification'])
            self.assertNotIn('drc_coverage',self.blocked(Path(temp)/'other',process='sky130A'))

    def test_both_bound_public_decks_record_execution_even_with_findings(self):
        with tempfile.TemporaryDirectory() as temp:
            report,result,source,directory=self.fixture(Path(temp))
            result['violations']=1;result['decks'][1].update(violations=1,categories=['MIM.g'])
            verification.record_public_mim_coverage(report,result,source,directory)
            row=report['drc_coverage']['MIM.g']
            self.assertEqual(row['status'],'EXECUTED')
            self.assertEqual(row['report_sha256'],result['decks'][1]['report_sha256'])
            self.assertEqual(row['input_sha256'],result['input_sha256'])
            self.assertEqual(row['source_lock_sha256'],result['source_lock_sha256'])
            self.assertNotIn('qualified',row)
            self.assertNotIn('not checked',report['qualification'])

    def test_partial_wrong_input_source_or_report_stays_unchecked(self):
        with tempfile.TemporaryDirectory() as temp:
            report,result,source,directory=self.fixture(Path(temp))
            mutations=[lambda r:r['decks'].pop(0),lambda r:r['decks'].pop(1),
                       lambda r:r.update(input_sha256='0'*64),lambda r:r.update(source_lock_sha256='0'*64),
                       lambda r:r.update(top='other'),lambda r:r['decks'][1].update(report_sha256='0'*64),
                       lambda r:r['decks'][1].update(report='../outside.lyrdb')]
            for mutate in mutations:
                changed=copy.deepcopy(result);mutate(changed)
                with self.subTest(result=changed),self.assertRaisesRegex(ValueError,'public IHP MIM.g'):
                    verification.record_public_mim_coverage(report,changed,source,directory)
                self.assertEqual(report['drc_coverage']['MIM.g']['status'],'NOT_CHECKED')


class IHPMIMCoverageDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_clean_magic_result_visibly_retains_the_missing_rule(self):
        from PySide6.QtWidgets import QLabel,QTableWidget
        from icstudio.silicon_ui import SiliconMixin
        with tempfile.TemporaryDirectory() as temp:
            helper=IHPMIMCoverageTests();report=helper.blocked(Path(temp)/'report')
        p=helper.project();report.pop('error');report.update(status='passed',drc_engine='magic',stages=[dict(name='drc',status='passed',evidence={'violations':0})])
        view=SimpleNamespace(project=p,cell=p['cells'][0],silicon_status=QLabel(),silicon_metrics=QLabel(),silicon_table=QTableWidget(0,3),
            _silicon_result={'project_id':p['id'],'design_hash':verification.design_digest(p),'silicon_report':report})
        SiliconMixin.refresh_silicon(view)
        self.assertIn('PASSED',view.silicon_status.text())
        self.assertIn('MIM.g',view.silicon_status.text())
        self.assertIn('not checked',view.silicon_table.item(0,2).text())
        self.assertIn('public geometry decks',view.silicon_table.item(0,2).text())
        self.assertEqual(view.silicon_table.item(0,0).text(),'Magic DRC')
        report['drc_engine']='ihp-public';SiliconMixin.refresh_silicon(view)
        self.assertEqual(view.silicon_table.item(0,0).text(),'IHP public DRC')

    def test_magic_dialog_names_the_existing_public_route(self):
        from icstudio.silicon_ui import SiliconMixin
        p=IHPMIMCoverageTests().project();notes=[]
        view=SimpleNamespace(project=p,cell=p['cells'][0],simple_form=lambda title,fields,note:notes.append(note))
        SiliconMixin.run_layout_verification(view)
        self.assertIn('MIM.g',notes[0]);self.assertIn('Verify IHP layout with public geometry decks',notes[0])
        notes.clear();SiliconMixin.run_layout_verification(view,lvs_extractor='ihp-klayout',drc_engine='ihp-public')
        self.assertIn('Run both public IHP geometry decks',notes[0])
        self.assertNotIn('do not establish MIM.g',notes[0])


if __name__=='__main__':unittest.main()
