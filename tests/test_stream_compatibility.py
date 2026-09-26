import tempfile
import unittest
from pathlib import Path
import klayout.db as db
from icstudio.model import example
from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.stream_contract import canonicalize, compare


class StreamCompatibilityTests(unittest.TestCase):
    def test_oasis_appearance_survives_external_rewrite_without_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=example('empty'); c=p['cells'][0]
            c['layout_texts']=[dict(layer=p['pdk']['layers'][0]['name'], text='VDD', x=1200,y=3400,
                                    rotation=90,mirror=True,size=600,font=2,halign=1,valign=2)]
            c['layout_label_mode']='explicit'
            export_layout(p,root/'source.oas'); export_layout(p,root/'source.gds')
            ly=db.Layout();ly.read(str(root/'source.oas'));ly.write(str(root/'external.oas'))
            actual,notes=read_layout(root/'external.oas')
            label=actual['cells'][0]['layout_texts'][0]
            for key in ('text','x','y','rotation','mirror','size','font','halign','valign'):
                self.assertEqual(label[key],c['layout_texts'][0][key])
            self.assertTrue(any('electrical labels' in n for n in notes))
            export_layout(actual,root/'restored.gds'); compare(root/'source.gds',root/'restored.gds')
            export_layout(actual,root/'again.oas')
            # External edits to the stream anchor win over stale metadata.
            shape=next(s for i in ly.layer_indexes() for s in ly.top_cell().shapes(i).each() if s.is_text())
            text=shape.text;text.x+=100;text.string='VSS';shape.text=text
            ly.write(str(root/'edited.oas'));edited,notes=read_layout(root/'edited.oas')
            label=edited['cells'][0]['layout_texts'][0]
            self.assertEqual((label['text'],label['x']),('VSS',1300));self.assertEqual(label['rotation'],0)
            self.assertTrue(any('stale or invalid' in n for n in notes))

    def test_canonicalization_preserves_hierarchy_and_rejects_electrical_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ly=db.Layout();ly.dbu=.001
            child=ly.create_cell('child');top=ly.create_cell('top');layer=ly.layer(68,16)
            child.shapes(layer).insert(db.Box(0,0,100,100))
            top.insert(db.CellInstArray(child.cell_index(),db.Trans(1,True,1000,2000),db.Vector(500,0),db.Vector(0,600),2,3))
            top.shapes(layer).insert(db.Text('ena',db.Trans(20,30)));ly.write(str(root/'raw.gds'))
            record=canonicalize(root/'raw.gds',root/'canonical.gds')
            self.assertEqual(record['comparison']['cells'],2)
            shape=next(s for s in top.shapes(layer).each() if s.is_text());shape.delete()
            ly.write(str(root/'broken.gds'))
            with self.assertRaisesRegex(ValueError,'text changed'):compare(root/'raw.gds',root/'broken.gds')


if __name__=='__main__':unittest.main()
