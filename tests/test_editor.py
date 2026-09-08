import unittest
from icstudio.model import example,uid,clone,History,validate
from icstudio.layout import rect,polygon,kdb
from icstudio import editor_ops as ops
from icstudio.design_ops import flatten_layout


class EditorTests(unittest.TestCase):
    def project(self):
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',0,0,1000,1000),rect('metal1',2000,0,1000,1000)];return p,c

    def hierarchy(self):
        p,c=self.project();child={'id':uid(),'name':'child','ports':[],'devices':[],'shapes':c['shapes']};p['cells'].append(child);c['shapes']=[]
        i={'id':uid(),'name':'A','cell':child['id'],'x':5000,'y':10000,'rotation':90,'mirror':True,'nx':2,'ny':2,'a':[5000,0],'b':[0,5000]};c['layout_instances']=[i];validate(p);return p,c,child,i

    def test_size_chop_preserve_nets_and_holes(self):
        p,c=self.project();s=c['shapes'][0];s['net']='signal';ids=ops.replace_geometry(p,c['id'],[s['id']],'chop',box=[200,200,800,800]);q=next(s for s in c['shapes'] if s['id'] in ids)
        self.assertEqual(polygon(q).holes(),1);self.assertEqual(q['net'],'signal');self.assertEqual(polygon(q).area(),640000)

    def test_rejected_size_is_atomic_in_history(self):
        p,c=self.project();h=History(p);before=clone(h.project)
        with self.assertRaises(ValueError):h.commit(lambda p:ops.replace_geometry(p,c['id'],[s['id'] for s in c['shapes']],'size',-1000))
        self.assertEqual(h.project,before);self.assertFalse(h.undo_stack)

    def test_vertex_and_edge_grid_and_undo(self):
        p,c=self.project();sid=c['shapes'][0]['id'];h=History(p);h.commit(lambda p:ops.move_vertex(p,c['id'],sid,1,[1500,0],True))
        self.assertEqual(polygon(h.project['cells'][0]['shapes'][0]).bbox().width(),1500);h.undo();self.assertEqual(h.project['cells'],p['cells'])
        with self.assertRaisesRegex(ValueError,'grid'):ops.move_vertex(p,c['id'],sid,1,[1501,0])

    def test_bulk_properties_reject_locked_destination_atomically(self):
        p,c=self.project();h=History(p)
        with self.assertRaisesRegex(ValueError,'Unlock'):h.commit(lambda p:ops.properties(p,c['id'],[s['id'] for s in c['shapes']],layer='metal2',locked={'metal2'}))
        self.assertEqual(h.project,p)

    def test_properties_preserve_identity_and_assign_all(self):
        p,c=self.project();ids=[s['id'] for s in c['shapes']];ops.properties(p,c['id'],ids,net='OUT',layer='metal2')
        self.assertEqual([s['id'] for s in c['shapes']],ids);self.assertTrue(all(s['net']=='OUT' and s['layer']=='metal2' for s in c['shapes']))

    def test_copy_via_uses_new_group_and_keeps_source(self):
        p,c=self.project();group=uid()
        for s in c['shapes']:s['via_group']=group
        ids=ops.copy_selection(p,c['id'],[s['id'] for s in c['shapes']],0,3000)
        copied=[s for s in c['shapes'] if s['id'] in ids];self.assertEqual(len(copied),2);self.assertEqual(len({s['via_group'] for s in copied}),1);self.assertNotEqual(copied[0]['via_group'],group)

    def test_copy_rejects_partial_linked_footprint(self):
        p,c=self.project()
        for s in c['shapes']:s['via_group']='v'
        with self.assertRaisesRegex(ValueError,'complete'):ops.copy_selection(p,c['id'],[c['shapes'][0]['id']],1000,0)

    def test_variant_retains_other_instance_and_remaps_ids(self):
        p,c,child,i=self.hierarchy();j=clone(i);j['id']=uid();j['name']='B';c['layout_instances'].append(j);before=clone(child)
        key=ops.make_variant(p,c['id'],i['id'],'variant');self.assertEqual(j['cell'],child['id']);self.assertEqual(child,before);q=ops.cell(p,key)
        self.assertFalse({s['id'] for s in q['shapes']}&{s['id'] for s in child['shapes']});self.assertEqual(q['shapes'][0]['points'],child['shapes'][0]['points'])

    def test_array_resolution_preserves_exact_transformed_geometry(self):
        p,c,child,i=self.hierarchy();region=lambda:kdb().Region([polygon(s) for s in flatten_layout(p,c['id'])]).merged()
        before=region();ids=ops.resolve_array(p,c['id'],i['id']);self.assertEqual(len(ids),4);self.assertTrue((before^region()).is_empty())

    def test_flatten_preserves_geometry_and_undo(self):
        p,c,child,i=self.hierarchy();before=kdb().Region([polygon(s) for s in flatten_layout(p,c['id'])]);h=History(p);h.commit(lambda p:ops.flatten_instances(p,c['id'],[i['id']]))
        after=kdb().Region([polygon(s) for s in h.project['cells'][0]['shapes']]);self.assertTrue((before^after).is_empty());h.undo();self.assertEqual(h.project['cells'],p['cells'])

    def test_flatten_rejects_linked_electrical_instance(self):
        p,c,child,i=self.hierarchy();i['device_id']='electrical'
        with self.assertRaisesRegex(ValueError,'Linked'):ops.flatten_instances(p,c['id'],[i['id']])

    def test_reference_transform_rejects_locked_descendant_geometry(self):
        from icstudio.layout_edit import selection_groups
        p,c,child,i=self.hierarchy()
        with self.assertRaisesRegex(ValueError,'Unlock'):selection_groups(p,c['id'],[i['id']],{'metal1'})


if __name__=='__main__':unittest.main()
