"""Capacity and hierarchy ECO acceptance, including rollback and shared masters."""
import tempfile
import unittest
from pathlib import Path
from icstudio.model import example, device, clone, validate, History
from icstudio.layout import rect
from icstudio.layout_graph import GeometryGraph
from icstudio.layout_eco_hierarchy import inventory, propose
from icstudio.layout_eco import apply


class Capacity(unittest.TestCase):
    def test_256_cells_and_50000_conductors_keep_incremental_edit_local(self):
        p=example('empty');c=p['cells'][0]
        p['cells'] += [dict(id='c'+str(i),name='c'+str(i),ports=[],devices=[],shapes=[]) for i in range(255)]
        c['shapes']=[rect('metal1',i*2000,0,600,600) for i in range(50000)];validate(p)
        h=History(p);sid=c['shapes'][25000]['id']
        self.assertTrue(h.commit_layout_move(c['id'],[sid],5,0))
        self.assertEqual(h.layout_stats['polygons_built'],1);self.assertEqual(h.layout_stats['shapes_replaced'],1)
        h.undo();self.assertEqual(h.project['cells'],p['cells']);h.redo();validate(h.project)

    def test_million_instance_gds_and_oasis_keep_masters_and_identities(self):
        from icstudio.interchange import export_layout, import_layout
        from icstudio.layout_import import read_layout
        from icstudio.layout_scene import LayoutScene
        p=example('empty');c=p['cells'][0]
        p['cells'].append(dict(id='tile',name='tile',ports=[],devices=[],shapes=[rect('metal1',0,0,600,600)]))
        c['layout_instances']=[dict(id='array',name='array',cell='tile',x=0,y=0,nx=1000,ny=1000,a=[2000,0],b=[0,2000])]
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ('gds','oas'):
                path=Path(directory)/('large.'+suffix);export_layout(p,path)
                exact,_=import_layout(path);self.assertEqual(exact['cells'],p['cells'])
                native,_=read_layout(path);scene=LayoutScene().update(native,native['top'])
                self.assertEqual(scene.expanded_count,1000000);self.assertEqual(scene.stats['master_shapes'],1)
                self.assertLess(path.stat().st_size,10000)

    def test_dense_contact_budget_fails_without_corrupting_existing_cache(self):
        from unittest.mock import patch
        shapes=[rect('metal1',0,0,600,600) for _ in range(6)]
        graph=GeometryGraph().sync(shapes[:1],example('empty')['pdk']);before=graph.records
        with patch('icstudio.layout_limits.CONTACT_TESTS',2):
            with self.assertRaisesRegex(ValueError,'candidate pairs'):graph.sync(shapes,example('empty')['pdk'])
        self.assertIs(graph.records,before)


class HierarchyECO(unittest.TestCase):
    def fixture(self):
        p=example('empty');top=p['cells'][0]
        leaf=dict(id='leaf',name='leaf',ports=[],devices=[device('R','R1',value='1k',nets={'p':'a','n':'b'})],shapes=[])
        top['devices']=[device('X','X1',cell='leaf',nets={}),device('X','X2',cell='leaf',nets={})];p['cells'].append(leaf);return p

    def test_child_first_add_reused_hierarchy_and_update_is_single_undo(self):
        p=self.fixture();rows=inventory(p,p['top'])['devices'];self.assertEqual(len(rows),3)
        selected=[(r['cell_id'],r['device_id']) for r in rows if r['action']]
        q,r=propose(p,p['top'],selected,preserve_routes=False)
        self.assertEqual(len(q['cells'][1]['parametric_devices']),1);self.assertEqual(len(q['cells'][0]['layout_instances']),2)
        self.assertTrue(all(v['status']=='current' for v in r['after']['devices']))
        h=History(p);h.commit(lambda target:apply(target,q,r),'Hierarchy ECO');h.undo();self.assertEqual(h.project['cells'],p['cells']);h.redo();self.assertEqual(h.project['cells'],q['cells'])
        q['cells'][1]['devices'][0]['value']='2k';before=clone(q);did=q['cells'][1]['devices'][0]['id'];ids={s['pcell_role']:s['id'] for s in q['cells'][1]['shapes']}
        updated,review=propose(q,q['top'],[('leaf',did)],preserve_routes=False)
        self.assertEqual(ids,{s['pcell_role']:s['id'] for s in updated['cells'][1]['shapes']});self.assertEqual(q,before)
        self.assertEqual(len(review['connectivity']),2)

    def test_locks_stale_review_unsupported_and_parameter_variants(self):
        p=self.fixture();rows=inventory(p,p['top'])['devices'];selected=[(r['cell_id'],r['device_id']) for r in rows]
        with self.assertRaisesRegex(ValueError,'Unlock|unlock'):propose(p,p['top'],selected,locked=['metal1'],preserve_routes=False)
        q,r=propose(p,p['top'],selected,preserve_routes=False);p['name']='Edited'
        with self.assertRaisesRegex(ValueError,'stale'):apply(p,q,r)
        q['cells'][1]['parameters']={'r':'1k'};q['cells'][0]['devices'][0]['parameters']={'r':'2k'}
        did=q['cells'][0]['devices'][0]['id']
        with self.assertRaisesRegex(ValueError,'concrete physical cell variant'):propose(q,q['top'],[(q['top'],did)],preserve_routes=False)
        p=example('empty');p['cells'][0]['devices']=[device('D','D1',nets={'p':'a','n':'0'})]
        self.assertEqual(inventory(p,p['top'])['devices'][0]['status'],'unsupported')

    def test_regeneration_retargets_attached_resistor_lead(self):
        from icstudio.parametric import install
        p=example('empty');c=p['cells'][0];d=device('R','R1',value='1k',nets={'p':'a','n':'b'});c['devices']=[d]
        install(p,c['id'],d['id'],{})
        pin=next(v for v in c['layout_pins'] if v['pin']=='n');pt=pin['point']
        c['shapes'].append(dict(id='lead',kind='path',layer='metal1',width=400,points=[clone(pt),[pt[0],pt[1]+10000]],net='b'))
        d['value']='2k';q,r=propose(p,c['id'],[(c['id'],d['id'])])
        self.assertIn('lead',r['adjusted_routes'])
        new=next(v['point'] for v in q['cells'][0]['layout_pins'] if v['pin']=='n')
        self.assertEqual(next(s for s in q['cells'][0]['shapes'] if s['id']=='lead')['points'][0],new)

    def test_selected_orphan_removal_retains_routes_and_unselected_devices(self):
        p=self.fixture();rows=inventory(p,p['top'])['devices'];q,_=propose(p,p['top'],[(r['cell_id'],r['device_id']) for r in rows],preserve_routes=False)
        c=q['cells'][1];did=c['devices'][0]['id'];c['devices']=[];c['layout_pins']=[];route=rect('metal2',0,10000,400,400);c['shapes'].append(route)
        result,report=propose(q,q['top'],[('leaf',did)],preserve_routes=False)
        self.assertEqual(result['cells'][1]['shapes'],[route]);self.assertEqual(report['changes'][0]['action'],'remove');self.assertEqual(len(result['cells'][0]['layout_instances']),2)


if __name__=='__main__':unittest.main()
