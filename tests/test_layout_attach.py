import tempfile
import unittest
from pathlib import Path
from icstudio.model import example, device, clone, uid, History, save_project, load_project
from icstudio.layout import rect
from icstudio.layout_attach import matching_cells, attach


class LayoutAttachmentTests(unittest.TestCase):
    def fixture(self):
        p=example('empty');c=p['cells'][0];c['name']='detector'
        c['devices']=[device('R','R1',0,0,value='2k',nets={'p':'sense','n':'0'})]
        layout=example('empty');top=layout['cells'][0];top['name']='detector'
        child=clone(top);child.update(id=uid(),name='physical_leaf',shapes=[rect('metal1',0,0,200,200)])
        layout['cells'].append(child)
        top['layout_instances']=[dict(id=uid(),name='I1',cell=child['id'],x=1000,y=2000,rotation=90,mirror=True,nx=1,ny=1)]
        return p,layout

    def test_attachment_preserves_electrical_identity_hierarchy_save_and_undo(self):
        p,layout=self.fixture();before=clone(p);incoming=clone(layout)
        candidate=attach(p,layout,matching_cells(p,layout))
        self.assertEqual(p,before);self.assertEqual(layout,incoming)
        self.assertEqual(candidate['cells'][0]['devices'],p['cells'][0]['devices'])
        self.assertEqual(candidate['cells'][0]['layout_instances'][0]['cell'],layout['cells'][1]['id'])
        self.assertIn('requires extraction',candidate['layout_attachment']['verification'])
        history=History(p);history.commit(lambda q:q.update(candidate));history.undo()
        self.assertEqual(history.project['cells'],p['cells']);history.redo()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'combined.icproj';save_project(history.project,path)
            self.assertEqual(load_project(path)['cells'],candidate['cells'])

    def test_reject_wrong_top_existing_layout_and_partial_map_collisions(self):
        p,layout=self.fixture()
        with self.assertRaises(ValueError):attach(p,layout,{})
        c=attach(p,layout,matching_cells(p,layout))
        with self.assertRaisesRegex(ValueError,'already contain'):attach(c,layout,matching_cells(c,layout))
        extra=clone(p['cells'][0]);extra.update(id=uid(),name='PHYSICAL_LEAF',devices=[]);p['cells'].append(extra)
        with self.assertRaisesRegex(ValueError,'collides'):attach(p,layout,matching_cells(p,layout))

    def test_import_export_retains_text_presentation_without_sidecars(self):
        import klayout.db as db
        from icstudio.interchange import import_layout, export_layout
        from scripts.qualify_open_project import geometry_equal
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ly=db.Layout();ly.dbu=.001;cell=ly.create_cell('top');layer=ly.layer(68,5)
            label=db.Text('avdd',db.Trans(1,True,1200,-900));label.size=800;label.font=2
            label.halign=db.Text.HAlignRight;label.valign=db.Text.VAlignCenter
            cell.shapes(layer).insert(label);ly.write(str(root/'source.gds'))
            p,_=import_layout(root/'source.gds');export_layout(p,root/'roundtrip.gds')
            self.assertEqual(geometry_equal(root/'source.gds',root/'roundtrip.gds')['status'],'passed')
