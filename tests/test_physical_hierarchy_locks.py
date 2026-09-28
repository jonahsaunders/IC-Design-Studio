"""Layer locks cover effective hierarchical geometry, not only master edits."""
import unittest
from types import SimpleNamespace
from icstudio.model import clone, device, uid
from icstudio.physical_cells import place
from icstudio.physical_hierarchy_ui import check_layers
from tests.test_physical_materialization import physical_project


class PhysicalHierarchyLockTests(unittest.TestCase):
    def studio(self,p,layers):
        return SimpleNamespace(project=p,layout=SimpleNamespace(locked_layers=set(layers)))

    def test_placing_unchanged_child_obeys_its_mask_layers(self):
        p,cid,_=physical_project();p['cells'][0]['devices'][0]['parameters']={}
        q=clone(p);place(q,cid,q['cells'][0]['devices'][0]['id'],0,0)
        self.assertEqual(p['cells'][1]['shapes'],q['cells'][1]['shapes'])
        with self.assertRaisesRegex(ValueError,'Unlock.*poly'):
            check_layers(self.studio(p,{'poly'}),q)
        check_layers(self.studio(p,{'metal2'}),q)

    def test_moving_nested_instance_checks_descendant_masks(self):
        p,cid,leaf=physical_project();top=p['cells'][0]
        wrapper={'id':uid(),'name':'wrapper','ports':['a','b'],'devices':[], 'shapes':[],
                 'layout_instances':[{'id':uid(),'cell':leaf,'name':'inner','x':0,'y':0}]}
        p['cells'].append(wrapper)
        outer={'id':uid(),'cell':wrapper['id'],'name':'outer','x':0,'y':0}
        top['layout_instances']=[outer]
        q=clone(p);q['cells'][0]['layout_instances'][0]['rotation']=90
        with self.assertRaisesRegex(ValueError,'Unlock.*poly'):
            check_layers(self.studio(p,{'poly'}),q)
        # No effective geometry changes means a locked descendant is harmless.
        check_layers(self.studio(p,{'poly'}),clone(p))

    def test_removing_placement_and_moving_port_are_protected(self):
        p,cid,_=physical_project();p['cells'][0]['devices'][0]['parameters']={}
        place(p,cid,p['cells'][0]['devices'][0]['id'],0,0)
        q=clone(p);q['cells'][0]['layout_instances']=[]
        with self.assertRaisesRegex(ValueError,'Unlock.*poly'):
            check_layers(self.studio(p,{'poly'}),q)
        q=clone(p);q['cells'][1]['layout_ports'][0]['point'][0]+=100
        layer=q['cells'][1]['layout_ports'][0]['layer']
        with self.assertRaisesRegex(ValueError,'Unlock'):
            check_layers(self.studio(p,{layer}),q)


if __name__=='__main__':unittest.main()
