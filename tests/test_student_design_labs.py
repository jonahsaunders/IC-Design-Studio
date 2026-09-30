"""Design repairs, bypass resistance, new material and portable portfolio output."""
import json
import tempfile
import unittest
from pathlib import Path

from icstudio.model import clone, save_project
from icstudio.student_hub import curriculum, evaluate, Portfolio, lesson_stamp, earned
from icstudio.student_learning import study_guide, portfolio_html, export_portfolio
from icstudio.student_projects import create
from icstudio.student_design_labs import check_layout, DIGITAL_LABS
from test_student_hub import repaired, execute, engines


def repaired_layout(kind):
    p=create(kind);shapes=p['cells'][0]['shapes']
    if kind=='layout-width':shapes[0]['points']=[[0,0],[2000,200]]
    if kind=='layout-spacing':shapes[1]['points']=[[0,400],[2000,600]]
    if kind=='layout-via':shapes[2]['points']=[[175,175],[325,325]]
    if kind=='layout-centroid':
        shapes[1]['points']=[[2400,0],[2800,400]]
        shapes[3]['points']=[[800,0],[1200,400]]
    return p


class StudentDesignTests(unittest.TestCase):
    def test_layout_faults_repairs_and_deletion_or_rule_bypass(self):
        for kind in ('layout-width','layout-spacing','layout-via','layout-centroid'):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):check_layout(create(kind),kind)
                p=repaired_layout(kind)
                evidence=check_layout(p,kind)
                self.assertIn('measurements',evidence)
                broken=clone(p);broken['cells'][0]['shapes'].pop()
                with self.assertRaisesRegex(ValueError,'original'):check_layout(broken,kind)
                broken=create(kind)
                for layer in broken['pdk']['layers']:layer.update(width=0,space=0)
                with self.assertRaises(ValueError):check_layout(broken,kind)
                broken=clone(p);broken['cells'][0]['shapes'][0]['net']='renamed'
                with self.assertRaisesRegex(ValueError,'net label'):check_layout(broken,kind)

    def test_via_checks_both_layers_and_centroid_rejects_overlap(self):
        p=repaired_layout('layout-via');p['cells'][0]['shapes'][1]['points']=[[0,0],[350,500]]
        with self.assertRaisesRegex(ValueError,'BOTH'):check_layout(p,'layout-via')
        p=repaired_layout('layout-centroid')
        for s in p['cells'][0]['shapes']:s['points']=[[0,0],[400,400]]
        with self.assertRaisesRegex(ValueError,'separation'):check_layout(p,'layout-centroid')

    def test_every_new_layout_and_career_checkpoint_is_reachable(self):
        with tempfile.TemporaryDirectory() as td:
            for lesson in curriculum()['lessons']:
                if lesson['path'] not in ('layout','career'):continue
                p=repaired_layout(lesson['starter']) if lesson['path']=='layout' else create(lesson['starter'])
                path=Path(td)/(lesson['id']+'.icproj');save_project(p,path)
                for step in lesson['steps']:
                    evaluate(step,lesson,p,path=path,answer=step.get('answer'),
                             note='Requirement, assumptions, prediction, observed result and remaining verification are recorded here.')

    def test_gmid_rejects_faulty_and_stale_bias_then_captures_measurements(self):
        with tempfile.TemporaryDirectory() as td:
            for lesson in curriculum()['lessons']:
                if not lesson['id'].startswith('a-gmid-'):continue
                p=create(lesson['starter']);root=Path(td)/lesson['id'];step=lesson['steps'][2]
                bad=execute(p,root/'bad')
                with self.assertRaisesRegex(ValueError,'Bias requirements'):evaluate(step,lesson,p,[bad])
                repaired(lesson,p)
                with self.assertRaisesRegex(ValueError,'latest edits'):evaluate(step,lesson,p,[bad])
                row=execute(p,root/'fixed');evidence=evaluate(step,lesson,p,[row])
                self.assertGreater(evidence['device_metrics']['gm'],0)
                self.assertIn('result_sha256',evidence)

    def test_teaching_edits_do_not_revoke_credit_and_html_escapes_drafts(self):
        data=curriculum();guide=study_guide(data);lesson=data['lessons'][0];step=lesson['steps'][-1]
        with tempfile.TemporaryDirectory() as td:
            portfolio=Portfolio(td)
            portfolio.state['lessons'][lesson['id']]=dict(stamp=lesson_stamp(lesson),steps={
                step['id']:dict(kind='reflection',evidence={'note':'Original captured observation'})},notes={step['id']:'<script>alert("draft")</script>'})
            before=clone(earned(portfolio.state,lesson));guide['lessons'][lesson['id']]['concept']+=' New teaching explanation.'
            self.assertEqual(earned(portfolio.state,lesson),before)
            rendered=portfolio_html(portfolio,data,guide)
            self.assertNotIn('<script>',rendered);self.assertIn('&lt;script&gt;',rendered)
            self.assertIn('Original captured observation',rendered)
            self.assertIn('Not yet earned',rendered)
            destination=Path(td)/'portfolio.html';export_portfolio(portfolio,destination,data,guide)
            self.assertTrue(destination.read_text(encoding='utf-8').startswith('<!doctype html>'))
            self.assertIn('not independently assessed',rendered)


@unittest.skipUnless(engines()['iverilog'] and engines()['vvp'],'Native Icarus required')
class StudentRepairRTLTests(unittest.TestCase):
    def test_each_fault_fails_and_repair_passes_reference_simulation(self):
        lessons={l['starter']:l for l in curriculum()['lessons'] if l['starter'] in DIGITAL_LABS}
        with tempfile.TemporaryDirectory() as td:
            for kind,lesson in lessons.items():
                with self.subTest(kind=kind):
                    p=create(kind)
                    with self.assertRaises(Exception):execute(p,Path(td)/(kind+'-fault'),engines())
                    repaired(lesson,p);row=execute(p,Path(td)/(kind+'-repair'),engines())
                    evaluate(lesson['steps'][2],lesson,p,[row])


if __name__=='__main__':unittest.main()
