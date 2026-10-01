"""Readable teaching drawings must retain every original electrical contract."""
import json
from pathlib import Path
import tempfile
import unittest

from icstudio import wiring
from icstudio.example_schematics import arrange
from icstudio.model import clone, digest, load_project, save_project, validate
from icstudio.student_hub import curriculum
from icstudio.student_projects import _create


def electrical(project):
    result=clone(project)
    for cell in result['cells']:
        for key in ('wires','labels','junctions','example_drawing','wiring_migration'):
            cell.pop(key,None)
        for net in cell.get('electrical',{}).get('nets',[]):
            net.pop('wires',None)
        for device in cell['devices']:
            for key in ('x','y','rotation','mirror','net_labels'):
                device.pop(key,None)
            if device.get('symbol'):
                device['symbol'].pop('primitives',None)
    return result


class ExampleSchematicTests(unittest.TestCase):
    def test_two_stage_opamp_presentation_retains_electrical_data(self):
        from tests.test_two_stage_opamp import technology
        from icstudio.two_stage_opamp import reference
        project,_,_=reference(technology());before=electrical(project)
        arrange(project,replace_wires=True)
        self.assertEqual(electrical(project),before)
        validate(project)
        stable=digest(project);arrange(project)
        self.assertEqual(digest(project),stable)

    def test_added_teaching_dut_preserves_existing_user_cells(self):
        from icstudio.analog_guided import teaching_example,TEMPLATES
        from icstudio.model import example
        for template in TEMPLATES:
            with self.subTest(template=template):
                original=validate(example('rc'));before=clone(original['cells'])
                proposal,cid=teaching_example(original,template);expected=electrical(proposal)
                arrange(proposal,{cid},replace_wires=True)
                self.assertEqual(electrical(proposal),expected)
                self.assertEqual(proposal['cells'][:-1],before)
                self.assertTrue(proposal['cells'][-1]['wires'])

    def test_new_pdk_templates_prepare_migrated_wires_and_preserve_catalogs(self):
        from icstudio.project_hub import inventory,preview
        from icstudio.project_templates import create,defaults,TEMPLATES
        from icstudio.pdks import PDKRegistry
        with tempfile.TemporaryDirectory() as td:
            rows=inventory(PDKRegistry(td))[0]
            for row in rows:
                if row['status']!='Available offline':continue
                tech=preview(row);choices=defaults(tech);catalog=digest(tech)
                for kind in TEMPLATES:
                    with self.subTest(pdk=row['id'],template=kind):
                        project,_,_=create(tech,kind,choices['supply'],choices['NMOS'],choices['PMOS'])
                        before=electrical(project)
                        arrange(project,replace_wires=True)
                        self.assertEqual(electrical(project),before)
                        self.assertEqual(digest(tech),catalog)
                        self.assertTrue(all(c.get('example_drawing') for c in project['cells']))
                        for c in project['cells']:
                            for d in c['devices']:
                                if d.get('model_ref'):
                                    self.assertNotIn('@spiceprefix',str(d['symbol']['primitives']))
                        validate(project)

    def test_every_starter_retains_electrical_data_and_survives_reopen(self):
        for name in sorted({lesson['starter'] for lesson in curriculum()['lessons']}):
            with self.subTest(starter=name), tempfile.TemporaryDirectory() as td:
                before=_create(name)
                after=arrange(clone(before))
                self.assertEqual(electrical(before),electrical(after))
                validate(after)
                stable=digest(after)
                arrange(after)
                self.assertEqual(digest(after),stable,'Reopening must not reroute a drawing')
                path=Path(td)/'example.icproj'
                save_project(after,path)
                reopened=load_project(path)
                for cell in reopened['cells']:
                    expected={d['id']:dict(d['nets']) for d in cell['devices']}
                    wiring.migrate(cell,reopened)
                    wiring.rebuild(cell,reopened)
                    self.assertEqual({d['id']:d['nets'] for d in cell['devices']},expected)

    def test_every_saved_example_preserves_its_declared_terminal_map(self):
        root=Path(__file__).resolve().parents[1]/'examples'
        for path in sorted(root.rglob('*.icproj')):
            with self.subTest(example=path.relative_to(root)):
                project=load_project(path)
                for cell in project['cells']:
                    expected={d['id']:dict(d['nets']) for d in cell['devices']}
                    wiring.migrate(cell,project)
                    wiring.rebuild(cell,project)
                    self.assertEqual({d['id']:d['nets'] for d in cell['devices']},expected)

    def test_existing_hand_routed_document_is_untouched(self):
        path=Path(__file__).resolve().parents[1]/'examples/manual-wiring.icproj'
        project=json.loads(path.read_text(encoding='utf-8'))
        before=digest(project)
        arrange(project)
        self.assertEqual(digest(project),before)

    def test_imported_lower_terminal_labels_clear_values_without_rewiring(self):
        from icstudio.example_schematics import imported_labels
        from icstudio.xschem_compat import review_project
        from icstudio.xschem_project import apply_review
        from icstudio.net_labels import point
        path=Path(__file__).resolve().parents[1]/'examples/native-hierarchy/stage.sch'
        project=apply_review(review_project(path))
        before=electrical(project)
        imported_labels(project)
        self.assertEqual(electrical(project),before)
        cell=next(c for c in project['cells'] if c['name']=='stage')
        cap=next(d for d in cell['devices'] if d['name']=='CLOAD')
        bottom=max(wiring.pins(cell,project)[(cap['id'],pin)][1] for pin in cap['nets'])
        label=next(label for label in cell['labels'] if point(label,cell,project)[1]==bottom and label['name']=='vss')
        self.assertGreater(label['offset'][1],0)
        for cell in project['cells']:
            expected={d['id']:dict(d['nets']) for d in cell['devices']}
            wiring.rebuild(cell,project)
            self.assertEqual({d['id']:d['nets'] for d in cell['devices']},expected)


if __name__=='__main__':unittest.main()
