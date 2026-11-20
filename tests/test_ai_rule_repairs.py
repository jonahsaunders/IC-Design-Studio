"""Exercise the physical checker, edge attribution and candidate verification."""
import unittest
from unittest.mock import patch

from icstudio.ai_rule_repairs import rule_repair
from icstudio.layout import drc, rect
from icstudio.model import clone, example


class MeasuredRuleRepairs(unittest.TestCase):
    def setUp(self):
        self.project=example('empty')
        self.cid=self.project['top']
        self.shapes=self.project['cells'][0]['shapes']

    def marker(self,code):
        return next(i for i in drc(self.project,self.cid) if i['code']==code)

    def test_widen_path_on_grid_preserves_bends_and_diagonal_centerlines(self):
        layer=next(l for l in self.project['pdk']['layers'] if l['name']=='metal1')
        layer['width']=203
        for points in ([[0,0],[1000,0],[1000,1000]], [[0,0],[1000,1000]]):
            with self.subTest(points=points):
                path=rect('metal1',0,0,10,10,net='signal')
                path.update(kind='path',width=100,points=points)
                self.shapes[:]=[path]
                marker=self.marker('WIDTH')
                repair=rule_repair(self.project,self.cid,marker)
                self.assertEqual(repair['proposed'],{**path,'width':205})
                self.assertGreaterEqual(repair['after_nm'],203)
                self.assertEqual(path['width'],100)

    def test_widen_away_from_neighbor_or_explain_block(self):
        thin=rect('metal1',0,0,1000,100)
        self.shapes.extend([thin,rect('metal1',0,300,1000,200)])
        marker=self.marker('WIDTH')
        repair=rule_repair(self.project,self.cid,marker)
        self.assertEqual(repair['proposed']['points'],[[0,-100],[1000,100]])
        self.shapes.append(rect('metal1',0,-400,1000,200))
        before=clone(self.project)
        with self.assertRaisesRegex(ValueError,'another layout finding'):
            rule_repair(self.project,self.cid,marker)
        self.assertEqual(self.project,before)

    def test_spacing_keeps_landed_ports_and_rectangles_intact(self):
        low=rect('metal1',0,0,1000,200,net='a')
        high=rect('metal1',0,300,1000,200,net='b')
        self.shapes.extend([low,high])
        cell=self.project['cells'][0]
        cell.update(ports=['b'],layout_ports=[dict(name='b',layer='metal1',point=[500,315])])
        marker=self.marker('SPACE')
        repair=rule_repair(self.project,self.cid,marker)
        self.assertEqual(repair['original']['id'],low['id'])
        self.assertEqual(repair['proposed']['points'],[[0,-100],[1000,100]])
        cell['ports'].append('a')
        cell['layout_ports'].append(dict(name='a',layer='metal1',point=[500,185]))
        with self.assertRaises(ValueError):rule_repair(self.project,self.cid,marker)

    def test_corner_spacing_measures_the_new_gap(self):
        self.shapes.extend([rect('metal1',0,0,400,400),rect('metal1',500,500,400,400)])
        marker=self.marker('SPACE')
        repair=rule_repair(self.project,self.cid,marker)
        self.assertEqual((marker['measured_nm'],repair['after_nm']),(141,202))
        self.assertEqual(repair['proposed']['points'][0],[575,500])

    def test_reversed_checker_edge_order_produces_identical_edits(self):
        from icstudio.live_geometry import full
        from icstudio.student_design_labs import layout_lab
        for kind in ('width','spacing'):
            p=layout_lab('layout-'+kind)
            cid=p['top']
            marker=drc(p,cid)[0]
            expected=rule_repair(p,cid,marker)
            def reversed_checker(project,cell):
                result=full(project,cell)
                for finding in result['issues']:
                    if 'edges' in finding:finding['edges'].reverse()
                return result
            with patch('icstudio.ai_rule_repairs.full',reversed_checker):
                actual=rule_repair(p,cid,marker)
                self.assertEqual(actual,expected)
                marker['edges'].reverse()
                flipped=rule_repair(p,cid,marker)
                self.assertEqual(flipped['proposed'],expected['proposed'])
                self.assertEqual(flipped['after_edges'],expected['after_edges'][::-1])

    def test_polygon_notch_and_ambiguous_or_stale_edges(self):
        shape=rect('metal1',0,0,1,1)
        shape.update(kind='polygon',points=[[0,0],[1000,0],[1000,600],[550,600],
                                            [550,300],[450,300],[450,600],[0,600]])
        self.shapes.append(shape)
        marker=self.marker('SPACE')
        repair=rule_repair(self.project,self.cid,marker)
        self.assertEqual(repair['after_nm'],200)
        self.assertEqual(repair['proposed']['id'],shape['id'])
        self.assertEqual(repair['proposed']['kind'],'polygon')
        with self.assertRaisesRegex(ValueError,'reproduce'):
            rule_repair(self.project,self.cid,{**marker,'minimum_nm':999})
        with self.assertRaisesRegex(ValueError,'Unlock'):
            rule_repair(self.project,self.cid,marker,{'metal1'})
        shape['pcell_id']='owned'
        with self.assertRaisesRegex(ValueError,'owner'):
            rule_repair(self.project,self.cid,marker)
        self.shapes.append({**clone(shape),'id':'coincident'})
        with self.assertRaisesRegex(ValueError,'unique shape owner'):
            rule_repair(self.project,self.cid,marker)
