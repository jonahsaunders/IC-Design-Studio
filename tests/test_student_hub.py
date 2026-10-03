"""Learning state, stale/corrupt evidence, independent RTL checks and capstone faults."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from icstudio.model import clone,digest,save_project,validate,atomic_write,device
from icstudio.student_hub import (Portfolio,curriculum,validate_curriculum,complete,earned,
    missing_prerequisites,evaluate,prepare_lesson,campaign_jobs)
from icstudio.student_projects import create,DIGITAL
from icstudio.student_capstone import project as sensor_project,report,case_project,CASES


def engines():
    return {n:os.environ.get('ICSTUDIO_TEST_'+n.upper()) or shutil.which(n) for n in ('ngspice','iverilog','vvp')}


def execute(project, root, tools=None, job=None):
    job=job or prepare_lesson(project,tools);root=Path(root);root.mkdir(parents=True,exist_ok=True)
    atomic_write(root/'input.json',json.dumps(job))
    if job['engine']=='digital':from icstudio.digital_flow import run
    elif job['engine']=='mixed_signal':from icstudio.mixed_signal import run
    else:
        from icstudio.simulation import run as analog
        result=analog(project,project['top'],project['analysis'])
        run=lambda *args:result
    result=run(job,root)
    atomic_write(root/'result.json',json.dumps(result));atomic_write(root/'status.json',json.dumps({'status':'complete'}))
    return dict(state='Complete',path=root,job=job,result=result)


def repaired(lesson,project):
    """Documented student edits, not a copy of the checkpoint implementation."""
    if lesson['id'] in ('f-connect','a-load'):
        name='R2' if lesson['id']=='f-connect' else 'Rload'
        cell=project['cells'][0]
        resistor=device('R',name,650,300,value='10k',nets={'p':'out','n':'0'})
        cell['devices'].append(resistor)
        # Use the same terminal-label edit as the inspector. In a routed
        # drawing, the derived nets table is not itself a connection.
        from icstudio.wiring import set_label
        for pin,net in (('p','out'),('n','0')):set_label(cell,resistor['id'],pin,net,project)
    changes={'f-edit':('R1','value','20k'),'f-debug':('Rload','value','1Meg'),
             'a-bandwidth':('C1','value','2n'),'a-bias':('MOUT','w','4u'),
             'a-differential':('VIN','value','5m'),'m-weight':('Rbit3','value','10k')}
    if lesson['id'] in changes:
        name,field,value=changes[lesson['id']]
        d=next(d for c in project['cells'] for d in c['devices'] if d['name']==name)
        if field=='w':d['params'][field]=value
        else:d[field]=value
    if lesson['id']=='m-codes':project['mixed_signal']['stimuli']['vin']=[[0,1.2]]
    if lesson['id']=='m-settling':project['mixed_signal']['period']=1e-6
    changes={
        'a-gmid-bias':{'VG':{'value':'.65'}},
        'a-gmid-size':{'M1':{'w':'9.804u'}},
        'a-gmid-headroom':{'VD':{'value':'.4'}},
        'a-gmid-tradeoff':{'VG':{'value':'.55'},'M1':{'w':'19.608u'}},
    }
    for name,fields in changes.get(lesson['id'],{}).items():
        d=next(d for d in project['cells'][0]['devices'] if d['name']==name)
        for key,value in fields.items():
            if key=='w':d['params'][key]=value
            else:d[key]=value
    if lesson['starter'] in ('mux_repair','saturating_sum','pipeline_valid'):
        from icstudio.student_projects import digital_project
        project['cells'][0]['digital']=digital_project(lesson['starter'])['cells'][0]['digital']
    return project


class StudentProgressTests(unittest.TestCase):
    def test_digital_lesson_honors_selected_included_or_custom_tools(self):
        from icstudio import digital_flow, digital_runtime
        project=create('counter');included={'kind':'linux','root':'/included','sha256':'fixture'}
        with patch.object(digital_runtime,'installed',return_value=included), \
             patch.object(digital_flow,'environment',return_value={}), \
             patch.object(digital_flow.shutil,'which',side_effect=AssertionError('Included must not search PATH')):
            job=prepare_lesson(project,{'iverilog':'/stale/iverilog','ngspice':'/stale/ngspice'},toolchain='included')
        self.assertEqual(job['settings']['runtime'],included)
        self.assertEqual(job['settings']['tools']['iverilog'],'opt/icstudio/bin/iverilog')
        with tempfile.TemporaryDirectory() as td:
            executable=Path(td)/'native tool';executable.write_text('fixture')
            with patch.object(digital_runtime,'installed',side_effect=AssertionError('Custom must not use Included')):
                job=prepare_lesson(project,{name:str(executable) for name in ('iverilog','vvp')},toolchain='custom')
            self.assertNotIn('runtime',job['settings'])

    def test_frozen_app_uses_build_identity_without_loose_sources(self):
        from icstudio.student_hub import checker_stamp
        from icstudio.mixed_signal import environment
        from icstudio.build_info import WORKFLOW_SOURCE_HASH
        checker_stamp.cache_clear()
        try:
            with patch('sys.frozen',True,create=True),patch('icstudio.student_hub.file_digest',side_effect=AssertionError('Loose source read')):
                self.assertEqual(checker_stamp(),WORKFLOW_SOURCE_HASH)
                with patch('icstudio.mixed_signal.file_digest',return_value='tool-hash') as hashed:
                    stamp=environment({'settings':{'tools':{'ngspice':'selected-executable'}}})
                    hashed.assert_called_once_with('selected-executable')
                    self.assertEqual(stamp['sources'],{})
        finally:checker_stamp.cache_clear()

    def test_curriculum_has_six_paths_and_executable_starters(self):
        data=curriculum()
        self.assertEqual([sum(l['path']==p['id'] for l in data['lessons']) for p in data['paths']],[6,10,9,6,4,2])
        self.assertEqual(sum(l['path']=='capstone' for l in data['lessons']),4)
        for l in data['lessons']:validate(create(l['starter']))
        bad=clone(data);bad['lessons'][0]['requires']=[bad['lessons'][-1]['id']]
        with self.assertRaisesRegex(ValueError,'Cyclic'):validate_curriculum(bad)
        bad=clone(data);bad['lessons'][0]['requires']=['missing']
        with self.assertRaisesRegex(ValueError,'Unknown prerequisite'):validate_curriculum(bad)

    def test_resume_prerequisites_conflicts_and_curriculum_revisions(self):
        data=curriculum();first,second=data['lessons'][:2]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Portfolio(root);p=create(first['starter']);path=root/'lab.icproj';save_project(p,path)
            store.attach(first,p,path);row=execute(p,root/'run')
            with self.assertRaisesRegex(ValueError,'earlier steps'):
                store.award(first,first['steps'][1],dict(project_id=p['id']),data)
            for step in first['steps']:
                note='The capacitor acquires charge gradually; at one time constant the voltage is about 1.14 V.'
                evidence=evaluate(step,first,p,[row],path,answer=step.get('answer'),note=note)
                store.award(first,step,evidence,data)
            self.assertTrue(complete(Portfolio(root).state,first));self.assertFalse(missing_prerequisites(store.state,second,data))
            with patch('icstudio.student_hub.checker_stamp',return_value='different-application-build'):
                self.assertTrue(complete(store.state,first))
            with patch('icstudio.student_hub.CHECKER_REVISION',2):
                self.assertFalse(complete(store.state,first))
            revised=clone(first);revised['steps'][0]['instructions']+=' Revised.'
            self.assertFalse(earned(store.state,revised))
            stale=Portfolio(root);store.save_note(first,first['steps'][-1],'A saved draft')
            with self.assertRaisesRegex(ValueError,'another window'):stale.save_note(first,first['steps'][-1],'lost update')
            self.assertEqual(Portfolio(root).state['lessons'][first['id']]['notes']['explain'],'A saved draft')
            store.export(root/'record.json',data);export=json.loads((root/'record.json').read_text())
            self.assertEqual(export['projects'][first['workspace']]['project']['id'],p['id'])

    def test_wrong_answer_practice_and_wrong_project_do_not_earn_credit(self):
        data=curriculum();lesson=data['lessons'][0];step=lesson['steps'][0];p=create(lesson['starter'])
        with self.assertRaisesRegex(ValueError,'Try again'):evaluate(step,lesson,p,answer=0)
        with tempfile.TemporaryDirectory() as td:
            store=Portfolio(td);store.attach(lesson,p,Path(td)/'p.icproj')
            with self.assertRaisesRegex(ValueError,'another lesson'):store.award(lesson,step,dict(project_id='other'),data)
            advanced=data['lessons'][-1];store.attach(advanced,p,Path(td)/'p.icproj')
            with self.assertRaisesRegex(ValueError,'prerequisites'):store.award(advanced,advanced['steps'][0],dict(project_id=p['id']),data)
            self.assertFalse(complete(store.state,advanced))

    def test_stale_and_corrupt_results_are_rejected(self):
        lesson=curriculum()['lessons'][0];step=lesson['steps'][2];p=create('rc')
        with tempfile.TemporaryDirectory() as td:
            row=execute(p,Path(td)/'run');evaluate(step,lesson,p,[row])
            changed=clone(p);changed['cells'][0]['devices'][1]['value']='20k'
            with self.assertRaisesRegex(ValueError,'latest edits'):evaluate(step,lesson,changed,[row])
            result=clone(row['result']);result['design_hash']='wrong';atomic_write(row['path']/'result.json',json.dumps(result))
            with self.assertRaisesRegex(ValueError,'saved input'):evaluate(step,lesson,p,[row])
            row['state']='Cancelled'
            with self.assertRaisesRegex(ValueError,'latest edits'):evaluate(step,lesson,p,[row])

    def test_every_foundation_and_analog_checkpoint_has_a_reachable_target(self):
        with tempfile.TemporaryDirectory() as td:
            for lesson in curriculum()['lessons']:
                if lesson['path'] not in ('foundations','analog'):continue
                p=repaired(lesson,create(lesson['starter']));root=Path(td)/lesson['id'];root.mkdir()
                path=root/'project.icproj';save_project(p,path)
                rows=[] if lesson['starter']=='layout' else [execute(p,root/'run')]
                for step in lesson['steps']:
                    with self.subTest(lesson=lesson['id'],step=step['id']):
                        evaluate(step,lesson,p,rows,path,step.get('answer'),'A measured observation with an explanation of the model limitations and next experiment.')


@unittest.skipUnless(engines()['iverilog'] and engines()['vvp'],'Install Icarus or set ICSTUDIO_TEST_IVERILOG/VVP')
class StudentDigitalTests(unittest.TestCase):
    def test_all_six_reference_benches_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as td:
            for lesson in curriculum()['lessons']:
                if lesson['path']!='digital':continue
                p=repaired(lesson,create(lesson['starter']));row=execute(p,Path(td)/lesson['id'],engines())
                evaluate(lesson['steps'][2],lesson,p,[row])
                files=p['cells'][0]['digital']['files'];files[1]['text']=files[1]['text'].replace('initial begin','// changed reference\ninitial begin',1)
                other=execute(p,Path(td)/(lesson['id']+'-changed'),engines())
                with self.assertRaisesRegex(ValueError,'reference testbench'):evaluate(lesson['steps'][2],lesson,p,[other])

    def test_broken_rtl_fails_actual_reference_simulation(self):
        p=create('counter');files=p['cells'][0]['digital']['files'];files[0]['text']=files[0]['text'].replace('else if(enable)','else if(!enable)')
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(Exception):execute(p,Path(td)/'bad',engines())


@unittest.skipUnless(all(engines().values()),'Install ngspice/Icarus or set ICSTUDIO_TEST engine paths')
class StudentCapstoneTests(unittest.TestCase):
    def test_all_mixed_lessons_accept_the_documented_repairs(self):
        with tempfile.TemporaryDirectory() as td:
            for l in curriculum()['lessons']:
                if l['path']!='mixed':continue
                p=repaired(l,create(l['starter']));row=execute(p,Path(td)/l['id'],engines())
                evaluate(l['steps'][1],l,p);evaluate(l['steps'][2],l,p,[row])

    def test_capstone_campaign_and_faults(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=sensor_project();rows=[]
            for job in campaign_jobs(p,engines()):
                case=job['student_campaign']['case'];row=execute(job['project'],root/case,job=job);rows.append(row)
                self.assertEqual(report(row['result'],case)['status'],'PASS',case)
            lesson=curriculum()['lessons'][-1];evaluate(lesson['steps'][2],lesson,p,rows)
            p['cells'][0]['devices'][0]['value']='90k'
            with self.assertRaisesRegex(ValueError,'latest design'):evaluate(lesson['steps'][2],lesson,p,rows)
            for fault in ('filter','decision','average','alarm'):
                p=sensor_project();files=p['cells'][1]['digital']['files']
                if fault=='filter':next(d for d in p['cells'][0]['devices'] if d['name']=='Cfilter')['value']='1n'
                elif fault=='decision':files[0]['text']=files[0]['text'].replace('if (!cmp)','if (cmp)')
                elif fault=='average':files[1]['text']=files[1]['text'].replace('>> 2','>> 1')
                else:files[1]['text']=files[1]['text'].replace('>= 10','>= 15')
                row=execute(p,root/fault,engines())
                self.assertEqual(report(row['result'])['status'],'FAIL',fault)


if __name__=='__main__':unittest.main()
