"""Readable fitting for imported symbols and their visible instance text."""
import os
from pathlib import Path
import unittest

from PySide6.QtCore import QPointF,QRectF
from PySide6.QtGui import QFont,QFontDatabase,QFontMetricsF,QTransform
from PySide6.QtWidgets import QApplication
from icstudio.canvas import Canvas
from icstudio.getting_started import example_copy
from icstudio.model import device,digest,example,load_project
from icstudio.symbol_geometry import painter_path,text_bounds


class SchematicFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        if os.name=='nt' and not QFontDatabase.families():
            fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
            for name in ('segoeui.ttf','segoeuib.ttf','arial.ttf'):
                assert QFontDatabase.addApplicationFont(str(fonts/name))>=0

    def setUp(self):
        self.canvas=Canvas('schematic');self.canvas.resize(822,264)

    def tearDown(self):
        self.canvas.close()

    def show(self,project):
        self.canvas.set_data(project['cells'][0],project['pdk']);self.canvas.show()
        self.app.processEvents();self.canvas.fit()

    def assert_framed(self,box):
        c=self.canvas
        visible=QRectF(c.model(QPointF(0,0)),c.model(QPointF(c.width(),c.height())))
        self.assertTrue(visible.contains(box),f'{visible} does not contain {box}')

    def block(self,rotation=0,mirror=False):
        p=example('empty')
        d=device('X','X1',x=300,y=50,rotation=rotation,mirror=mirror,
            symbol={'pins':{'a':[-20,0],'b':[380,0]},'primitives':[
                {'kind':'rect','points':[[0,-18],[360,18]]}]},nets={'a':'in','b':'out'})
        p['cells'][0]['devices']=[d]
        return p,d

    def test_imported_program_remains_readable_in_short_canvas(self):
        p=example_copy({'file':'xschem-analysis/rc-program.sch'});before=digest(p)
        self.show(p)
        # The historical square around the 180-by-44 program box reduced this
        # ordinary results-open viewport to 52%, with barely readable labels.
        self.assertGreater(self.canvas.scale,.8)
        self.assertEqual(digest(p),before)
        for d in p['cells'][0]['devices']:self.assert_framed(self.canvas.fit_bounds(d))

    def test_wide_offset_symbol_uses_width_and_height_separately(self):
        p,d=self.block();self.show(p)
        self.assertGreater(360*self.canvas.scale,350)
        self.assertGreater(self.canvas.bounds(d).height(),700)
        self.assertLess(self.canvas.fit_bounds(d).height(),200)
        self.assert_framed(self.canvas.fit_bounds(d))

    def test_rotated_and_mirrored_terminals_stay_inside_view(self):
        for angle in (0,90,180,270):
            for mirror in (False,True):
                with self.subTest(angle=angle,mirror=mirror):
                    p,d=self.block(angle,mirror);self.show(p)
                    transform=QTransform();transform.translate(d['x'],d['y']);transform.rotate(angle);transform.scale(-1 if mirror else 1,1)
                    self.assert_framed(transform.mapRect(QRectF(-23,-21,406,42)))

    def test_hidden_remote_text_does_not_shrink_the_circuit(self):
        p,d=self.block();self.show(p);scale=self.canvas.scale
        d['symbol']['primitives'].append({'kind':'text','points':[[10000,10000]],'text':'@missing','hidden':True,'font_size':12})
        self.show(p)
        self.assertEqual(self.canvas.scale,scale)

    def test_repeated_fit_does_not_expand_cached_bounds(self):
        p,d=self.block();self.show(p);scale=self.canvas.scale
        bounds=QRectF(self.canvas.fit_bounds(d));picking=QRectF(self.canvas.bounds(d))
        for _ in range(20):self.canvas.fit()
        self.assertEqual(self.canvas.scale,scale)
        self.assertEqual(self.canvas.fit_bounds(d),bounds)
        self.assertEqual(self.canvas.bounds(d),picking)

    def test_live_text_and_long_net_labels_remain_visible_after_refresh(self):
        p,d=self.block();text={'kind':'text','points':[[10,30]],'text':'@value','font_size':12}
        d['symbol']['primitives'].append(text);d['symbol_context']={'value':'short'}
        d['value']='short';d['net_labels']={'b':'output_'+'very_long_net_name_'*6};self.show(p)
        d['value']='live_parameter_value_'*20;self.show(p)
        frame=QTransform();frame.translate(d['x'],d['y'])
        self.assert_framed(text_bounds(text,self.canvas.instance_context(d),frame,xschem=True))
        net=QFontMetricsF(QFont('Sans Serif',8)).boundingRect(d['net_labels']['b']).translated(d['x']+385,d['y']-7)
        self.assert_framed(net)

    def test_layout_framing_keeps_its_existing_geometry(self):
        from icstudio.layout import rect
        c=Canvas('layout');p=example('empty');shape=rect('metal1',0,0,5000,3000)
        p['cells'][0]['shapes']=[shape];c.set_data(p['cells'][0],p['pdk'])
        self.assertEqual(c.fit_bounds(shape),c.bounds(shape));c.close()

    def test_saved_and_new_opamp_captions_clear_symbol_artwork(self):
        from tests.test_two_stage_opamp import technology
        from icstudio.two_stage_opamp import reference
        from icstudio.example_schematics import arrange
        saved=load_project(Path(__file__).resolve().parents[1]/'examples/sky130_two_stage_opamp.icproj')
        new,_,_=reference(technology());arrange(new,replace_wires=True)
        for kind,project in [('saved',saved),('new',new)]:
            with self.subTest(kind=kind):
                cell=next(c for c in project['cells'] if c['name']=='two_stage_opamp')
                self.canvas.set_data(cell,project['pdk']);captions=[];art=[]
                for d in cell['devices']:
                    frame=QTransform();frame.translate(d['x'],d['y']);frame.rotate(d['rotation']);frame.scale(-1 if d.get('mirror') else 1,1)
                    for item in d['symbol']['primitives']:
                        if item['kind']=='text':
                            box=text_bounds(item,self.canvas.instance_context(d),frame,xschem=True)
                            if not box.isEmpty():captions.append((d['name'],item['text'],box))
                        else:
                            art.append((d['name'],frame.map(painter_path(item)).boundingRect().adjusted(-.5,-.5,.5,.5)))
                for name,text,box in captions:
                    for other,body in art:
                        self.assertFalse(box.intersects(body),f'{kind}: {name} {text} overlaps {other} artwork')


if __name__=='__main__':unittest.main()
