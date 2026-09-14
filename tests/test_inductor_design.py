"""Shape, synthesis and DC-model acceptance with independent electrical checks."""
import math
import tempfile
import unittest
from pathlib import Path

from icstudio import inductor
from icstudio.model import example,clone,device,scalar,save_project,load_project
from icstudio.layout import polygon,drc,kdb
from icstudio.layout_graph import GeometryGraph
from icstudio.physical import connectivity
from icstudio.inductor_shapes import current_sheet,rectangular_inductance
from icstudio.inductor_synthesis import search,Cancelled
from icstudio.inductor_electrical import resistance,expand_series_rl


def declared_resistance(p):
    # Explicit synthetic coefficients, not process characterization.
    p['pdk']['parasitics']={'metal1':{'sheet_ohm':.08},'metal2':{'sheet_ohm':.04}}
    p['pdk']['via_resistance_ohm']={'M1 to M2':2.}


class ShapeTests(unittest.TestCase):
    def test_every_shape_extremes_continuity_grid_rules_and_device_boundary(self):
        for shape in inductor.SHAPES:
            for n in (1,3,32):
                with self.subTest(shape=shape,turns=n):
                    p=example('empty');spec={**inductor.defaults(p),'shape':shape,'turns':n,'inner_y':120000}
                    r=inductor.plan(p,p['top'],spec);inductor.install(p,r)
                    self.assertFalse(drc(p,p['top']))
                    self.assertFalse(connectivity(p,p['top'])['issues'])
                    graph=GeometryGraph().sync(r['shapes'],p['pdk'])
                    self.assertEqual(len(set(graph.groups.values())),1)
                    self.assertEqual(polygon(r['shapes'][0]).holes(),0)
                    self.assertGreater(r['estimate_h'],0)
                    for s in r['shapes']:
                        for pt in polygon(s).each_point_hull():
                            self.assertEqual(pt.x%p['pdk']['grid'],0);self.assertEqual(pt.y%p['pdk']['grid'],0)

    def test_all_shapes_orientation_regeneration_and_export(self):
        from icstudio.interchange import export_layout
        for shape in inductor.SHAPES:
            p=example('empty');base={**inductor.defaults(p),'shape':shape,'inner_y':130000}
            original=inductor.geometry(p['pdk'],base)
            for rotation in (0,90,180,270):
                for mirror in (False,True):
                    data=inductor.geometry(p['pdk'],{**base,'rotation':rotation,'mirror':mirror,'x':120005,'y':-340005})
                    self.assertEqual(data['estimate_h'],original['estimate_h'])
                    self.assertEqual([polygon(s).area() for s in data['shapes']],[polygon(s).area() for s in original['shapes']])
            r=inductor.plan(p,p['top'],base);inductor.install(p,r)
            again=inductor.plan(p,p['top'],{**base,'inner':100000},did=r['device_id']);inductor.install(p,again)
            self.assertEqual([s['id'] for s in r['shapes']],[s['id'] for s in again['shapes']])
            with tempfile.TemporaryDirectory() as directory:
                for extension in ('gds','oas'):
                    path=Path(directory)/('coil.'+extension);export_layout(p,path)
                    layout=kdb().Layout();layout.read(str(path))
                    for layer in p['pdk']['layers']:
                        index=layout.find_layer(layer['gds'],layer['datatype'])
                        expected=kdb().Region()
                        for s in again['shapes']:
                            if s['layer']==layer['name']:expected.insert(polygon(s))
                        actual=kdb().Region(layout.top_cell().begin_shapes_rec(index)) if index is not None else kdb().Region()
                        self.assertTrue((actual^expected).is_empty())

    def test_new_shapes_keep_external_short_and_tap_detection(self):
        from icstudio.layout import rect
        for shape in inductor.SHAPES:
            p=example('empty');r=inductor.plan(p,p['top'],{**inductor.defaults(p),'shape':shape});inductor.install(p,r)
            c=p['cells'][0];point=max(polygon(r['shapes'][0]).each_point_hull(),key=lambda v:v.x)
            c['shapes'].append(rect(r['spec']['metal'],point.x-100,point.y-100,300,300))
            self.assertIn('INDUCTOR.TAP',{v['code'] for v in connectivity(p,p['top'])['issues']})

    def test_mohan_table_ii_coefficients_at_independent_common_dimensions(self):
        # Evaluate Table II directly with a fixed dimension ratio, independent
        # of shape generation. This tests equation transcription, not RF accuracy.
        for shape,c1,c2,c3,c4 in [('square',1.27,2.07,.18,.13),('hexagon',1.09,2.23,0,.17),
                                  ('octagon',1.07,2.29,0,.19),('circle',1,2.46,0,.20)]:
            expected=math.pi*1e-7*9*150e-6*2*c1*(math.log(3*c2)+c3/3+c4/9)
            self.assertAlmostEqual(current_sheet(shape,3,100000,200000)/expected,1,places=12)

    def test_rectangular_integral_against_independent_midpoint_quadrature(self):
        # Neumann integral, using a different numerical algorithm; the winding
        # includes antiparallel segments with negative mutual inductance.
        points=[[-50000,-40000],[50000,-40000],[50000,40000],[-50000,40000],[-50000,-20000]];width=10000
        pieces=[]
        for index,(a,b) in enumerate(zip(points,points[1:])):
            for j in range(120):
                pieces.append((index,[(a[k]+(j+.5)*(b[k]-a[k])/120) for k in (0,1)],[(b[k]-a[k])/120 for k in (0,1)]))
        total=0
        for i,a,da in pieces:
            for j,b,db in pieces:
                product=sum(x*y for x,y in zip(da,db))
                if product:
                    distance=math.sqrt(sum((x-y)**2 for x,y in zip(a,b))+(width*math.exp(-1.5))**2*(i==j))
                    total+=product/distance
        reference=1e-16*total
        self.assertLess(abs(rectangular_inductance(points,width)/reference-1),.002)
        wide=rectangular_inductance([[x*2,y] for x,y in points],width)
        self.assertGreater(wide,reference)

    def test_structured_fixes_are_explicit_and_do_not_mutate_input(self):
        p=example('empty');s={**inductor.defaults(p),'spacing':10};before=clone(s)
        with self.assertRaises(inductor.ValidationError) as caught:inductor.geometry(p['pdk'],s)
        self.assertEqual(caught.exception.field,'spacing');self.assertEqual(s,before)
        fixed={**s,**caught.exception.fixes};self.assertGreater(inductor.geometry(p['pdk'],fixed)['estimate_h'],0)


class SynthesisTests(unittest.TestCase):
    def test_targets_for_every_shape_obey_ranges_grid_and_complete_footprint(self):
        p=example('empty')
        for shape in inductor.SHAPES:
            base={**inductor.defaults(p),'shape':shape,'inner_y':120000}
            r=search(p['pdk'],base,2e-9,300000,350000,width_range=(9000,11000),spacing_range=(2000,4000),max_results=3)
            self.assertTrue(r['candidates'],shape);self.assertTrue(r['candidates'][0]['within_tolerance'])
            for candidate in r['candidates']:
                s=candidate['spec'];self.assertTrue(9000<=s['width']<=11000);self.assertTrue(2000<=s['spacing']<=4000)
                data=inductor.geometry(p['pdk'],s)
                self.assertLessEqual(data['footprint_nm'][0],300000);self.assertLessEqual(data['footprint_nm'][1],350000)
                self.assertEqual(data['estimate_h'],candidate['estimate_h'])

    def test_no_solution_outside_tolerance_and_cancellation_are_distinct(self):
        p=example('empty');base=inductor.defaults(p)
        self.assertFalse(search(p['pdk'],base,2e-9,1000,1000)['candidates'])
        r=search(p['pdk'],base,1e-6,200000,200000)
        self.assertTrue(r['candidates']);self.assertTrue(all(not c['within_tolerance'] for c in r['candidates']))
        with self.assertRaises(Cancelled):search(p['pdk'],base,2e-9,300000,300000,cancel=lambda:True)
        for target in (0,float('nan'),float('inf')):
            with self.assertRaises(ValueError):search(p['pdk'],base,target,300000,300000)


class ResistanceTests(unittest.TestCase):
    def project(self):
        p=example('empty');declared_resistance(p)
        proposal=inductor.plan(p,p['top'],inductor.defaults(p),series_rl=True);inductor.install(p,proposal)
        return p,proposal

    def test_dc_breakdown_and_parallel_vias_use_only_declared_data(self):
        p,r=self.project();self.assertAlmostEqual(r['resistance']['total_ohm'],7.084,places=10)
        g=inductor.geometry(p['pdk'],{**inductor.defaults(p),'via_rows':4})
        self.assertAlmostEqual(resistance(p['pdk'],g)['components'][-1]['ohm'],.5)
        for missing in ('parasitics','via_resistance_ohm'):
            q=clone(p);q['pdk'].pop(missing)
            self.assertIsNone(resistance(q['pdk'],g)['total_ohm'])
            with self.assertRaises(ValueError):inductor.plan(q,q['top'],inductor.defaults(q),did=r['device_id'],series_rl=True)

    def test_opt_in_shared_spice_and_solver_model_preserves_project_and_value(self):
        from icstudio.interchange import spice
        from icstudio.simulation import run
        p,r=self.project();c=p['cells'][0]
        for kind,name,x,pos,neg,value in [('V','V1',100,'L1_p','0','1'),('R','Rload',600,'L1_n','0','50')]:
            c['devices'].append(device(kind,name,x=x,nets={'p':pos,'n':neg},net_labels={'p':pos,'n':neg},value=value))
        before=clone(p);deck=spice(p);self.assertIn('R_L1_dc',deck);self.assertEqual(spice(p),deck)
        result=run(p,p['top'],{**p['analysis'],'type':'ac','start':'100meg','end':'1g','points':3})
        for f,magnitude in zip(result['x'],result['traces']['L1_n']):
            expected=50/math.hypot(50+r['resistance']['total_ohm'],2*math.pi*f*r['estimate_h'])
            self.assertAlmostEqual(magnitude,expected,places=9)
        self.assertEqual(p,before)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rl.icproj';save_project(p,path);loaded=load_project(path)
            self.assertEqual(loaded['cells'],p['cells']);self.assertIn('R_L1_dc',spice(loaded))

    def test_stale_coefficients_value_geometry_and_explicit_opt_out(self):
        p,r=self.project()
        for change in ('coefficient','value','geometry'):
            q=clone(p)
            if change=='coefficient':q['pdk']['via_resistance_ohm']['M1 to M2']=3
            elif change=='value':q['cells'][0]['devices'][0]['value']='8n'
            else:q['cells'][0]['shapes'][0]['points'][0][0]+=5
            with self.assertRaises(ValueError):expand_series_rl(q)
        regenerated=inductor.plan(p,p['top'],inductor.defaults(p),did=r['device_id']);inductor.install(p,regenerated)
        self.assertTrue(p['cells'][0]['devices'][0]['inductor_rl'])
        regenerated=inductor.plan(p,p['top'],inductor.defaults(p),did=r['device_id'],series_rl=False);inductor.install(p,regenerated)
        self.assertNotIn('inductor_rl',p['cells'][0]['devices'][0])


if __name__=='__main__':unittest.main()
