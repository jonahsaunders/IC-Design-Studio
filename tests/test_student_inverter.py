"""Course identity, evidence rejection, and opt-in real process simulation."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from icstudio.model import clone, atomic_write, save_project, file_digest, design_digest
from icstudio.pdks import PDKRegistry
from icstudio.student_hub import curriculum, evaluate, Portfolio, earned
from icstudio.student_learning import study_guide
from icstudio import student_inverter as course


def library(folder):
    profiles, errors = course.inventory(PDKRegistry(Path(folder)/'registry'))
    data, material = course.expand(curriculum(),study_guide(curriculum()),profiles)
    return profiles, data, material


def lesson(data, item, stage):
    return next(l for l in data['lessons'] if l.get('inverter_profile')==item['token'] and l['inverter_stage']==stage)


def run(p, l, root, tools, runtime=None):
    from icstudio.worker import main
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    job=course.prepare(p,l,tools)
    if runtime:
        job['settings'].pop('physical_blocked_reason',None)
        job['settings']['physical_runtime']=runtime
    atomic_write(root/'input.json',json.dumps(job))
    if main(str(root/'input.json'),str(root/'result.json'))!=0:raise AssertionError('Course worker failed: '+str(root))
    result=json.loads((root/'result.json').read_text(encoding='utf-8'))
    return dict(state='Complete',path=str(root),job=job,result=result)


class InverterCourseTests(unittest.TestCase):
    def test_all_revisions_have_guidance_and_independent_progress(self):
        with tempfile.TemporaryDirectory() as td:
            profiles,data,material=library(td)
            self.assertEqual(len(data['lessons']),41+8*len(profiles))
            self.assertEqual(set(material['lessons']),{l['id'] for l in data['lessons']})
            ready=[p for p in profiles if p['ready']];self.assertEqual(len(ready),2)
            p=course.create(ready[0]);l=lesson(data,ready[0],'process');path=Path(td)/'inv.icproj';save_project(p,path)
            portfolio=Portfolio(Path(td)/'progress');portfolio.attach(l,p,path)
            for step in l['steps']:
                evidence=evaluate(step,l,p,answer=step.get('answer'),note='Selected process revision, model names and nominal supply were checked against the starter.')
                portfolio.award(l,step,evidence,data)
            self.assertEqual(len(earned(portfolio.state,l)),4)
            self.assertEqual(earned(portfolio.state,lesson(data,ready[1],'process')), {})
            relocated=clone(ready[0]['technology']);relocated['package_root']='another/folder'
            self.assertEqual(course.profile(relocated)['token'],ready[0]['token'])
            relocated['package_lock']['revision']='new-revision'
            self.assertNotEqual(course.profile(relocated)['token'],ready[0]['token'])
            with self.assertRaisesRegex(ValueError,'another PDK'):course.context(p,lesson(data,ready[1],'process'))

    def test_missing_models_and_physical_decks_never_become_generic_passes(self):
        with tempfile.TemporaryDirectory() as td:
            profiles,data,_=library(td);item=next(p for p in profiles if p['name'].startswith('gf180'))
            p=course.create(item);l=lesson(data,item,'schematic')
            d=next(c for c in p['cells'] if c['id']==p['student_inverter']['cell'])['devices'][0]
            d.pop('model_ref');d['model_mode']='generic'
            with self.assertRaisesRegex(ValueError,'core model'):course.check(p,l,dict(check='schematic'),[])
            with self.assertRaisesRegex(ValueError,'native physical'):course.build_layout(p)
            with self.assertRaisesRegex(ValueError,'Build or import'):course.prepare(p,lesson(data,item,'drc'))
            missing=next(p for p in profiles if p['token']=='ihp-setup')
            with self.assertRaisesRegex(ValueError,'OSDI'):course.create(missing)

    def test_bad_waveforms_cannot_earn_electrical_credit(self):
        with tempfile.TemporaryDirectory() as td:
            profiles,_,_=library(td);p=course.create(next(p for p in profiles if p['ready']))
            result=dict(engine='builtin',settings={'type':'dc'},x=[0,.9,1.8],traces={'in':[0,.9,1.8],'out':[1.8,.9,0]})
            with self.assertRaisesRegex(ValueError,'real process'):course.measurements(p,result,'dc')
            result['engine']='ngspice (installed executable)';result['traces']['out']=[0,0,0]
            with self.assertRaisesRegex(ValueError,'invert'):course.measurements(p,result,'dc')
            result['traces']['out']=[1.8,float('nan'),0]
            with self.assertRaisesRegex(ValueError,'finite'):course.measurements(p,result,'dc')

    def test_physical_setup_failures_are_not_credited_as_rule_failures(self):
        # Contract fixture only: actual engine faults/repairs are exercised by
        # scripts/qualify_student_inverter.py with a complete physical PDK.
        with tempfile.TemporaryDirectory() as td:
            profiles,data,_=library(td);item=next(p for p in profiles if p['ready'])
            p=course.create(item);l=lesson(data,item,'drc');root=Path(td)/'run';root.mkdir()
            job=dict(project=p,cell=p['student_inverter']['cell'],engine='physical',settings={'type':'silicon'},student_lesson=l['id'])
            report=dict(mode='drc_lvs',design_hash=design_digest(p),stages=[dict(name='preflight',status='failed',error='Missing tool')])
            result=dict(project_id=p['id'],cell_id=job['cell'],design_hash=design_digest(p),settings=job['settings'],
                        engine='Magic / Netgen / ngspice',traces={},x=[],silicon_report=report,evidence_directory=str(root))
            atomic_write(root/'input.json',json.dumps(job))
            def captured():
                atomic_write(root/'result.json',json.dumps(result))
                return [dict(state='Complete',path=str(root),job=job,result=result)]
            with self.assertRaisesRegex(ValueError,'integrity'):course.check(p,l,dict(check='drc-failure'),captured())
            report['stages']=[dict(name='drc',status='failed',error='Engine crashed'),
                              dict(name='integrity',status='passed',evidence=dict(verified=True,files={}))]
            with self.assertRaisesRegex(ValueError,'actual rule violation'):course.check(p,l,dict(check='drc-failure'),captured())
            report['drc_count']=2
            proof=root/'drc.log';proof.write_text('STUDIO_DRC_COUNT 2')
            report['stages'][1]['evidence']['files']['drc.log']=file_digest(proof)
            course.check(p,l,dict(check='drc-failure'),captured())
            proof.write_text('STUDIO_DRC_COUNT 0')
            with self.assertRaisesRegex(ValueError,'changed'):course.check(p,l,dict(check='drc-failure'),captured())


NGSPICE=os.environ.get('ICSTUDIO_TEST_NGSPICE') or shutil.which('ngspice')


@unittest.skipUnless(NGSPICE,'Native ngspice required for process-model inverter tests')
class InverterProcessTests(unittest.TestCase):
    def test_both_bundled_processes_dc_switching_and_stale_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            profiles,data,_=library(td)
            for item in [p for p in profiles if p['ready']]:
                p=course.create(item)
                for stage,check in [('dc','dc'),('transient','tran')]:
                    with self.subTest(process=item['name'],stage=stage):
                        l=lesson(data,item,stage);row=run(p,l,Path(td)/item['token']/stage,dict(ngspice=NGSPICE))
                        evidence=course.check(p,l,dict(check=check),[row]);self.assertIn('inverter_measurements',evidence)
                        changed=clone(p);changed['cells'][0]['devices'][0]['value']='1.7'
                        with self.assertRaisesRegex(ValueError,'latest edits'):course.check(changed,l,dict(check=check),[row])
                        wrong=clone(row);wrong['job']['student_lesson']='another-lesson'
                        with self.assertRaisesRegex(ValueError,'latest edits'):course.check(p,l,dict(check=check),[wrong])


if __name__=='__main__':unittest.main()
