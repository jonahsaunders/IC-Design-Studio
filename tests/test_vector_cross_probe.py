"""Scalar net probes retain compact capture identity through vector hierarchy."""
import unittest
from icstudio.model import example, device, uid, validate
from icstudio.cross_probe import net_occurrences, net_names


class VectorCrossProbeTests(unittest.TestCase):
    def test_array_member_and_ordered_slice_reach_the_correct_child_terminal(self):
        p=example('empty');root=p['cells'][0]
        r=device('R','RLOAD',nets={'p':'a[1:0]','n':'0'});r['array']={'start':1,'end':0}
        child={'id':uid(),'name':'child','ports':['a[1:0]'],'devices':[r],'shapes':[]}
        p['cells'].append(child)
        x=device('X','XBANK',cell=child['id'],nets={'a[1:0]':'input[3:0]'})
        x['array']={'start':1,'end':0};root['devices']=[x];validate(p)
        self.assertEqual(net_names(p,root['id']),['input[0]','input[1]','input[2]','input[3]'])
        rows=net_occurrences(p,root['id'],'input[2]')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['objects'],[x['id']])
        self.assertEqual(rows[0]['array_members'],{x['id']:[1]})
        selected=rows[1]
        self.assertEqual(selected['net'],'a[0]')
        self.assertEqual(selected['path'],[x['id']])
        self.assertEqual(selected['array_path'],[{'device_id':x['id'],'index':1}])
        self.assertEqual(selected['objects'],[r['id']])
        self.assertEqual(selected['array_members'],{r['id']:[0]})
        self.assertIn('XBANK__1',selected['name'])

    def test_global_bus_bit_is_global_in_each_repeated_child(self):
        p=example('empty');root=p['cells'][0]
        r=device('R','RLOAD',nets={'p':'a','n':'supply[1]'})
        child={'id':uid(),'name':'child','ports':['a'],'devices':[r],'shapes':[]}
        p['cells'].append(child)
        x=device('X','XBANK',cell=child['id'],nets={'a':'input[1:0]'})
        x['array']={'start':1,'end':0};root['devices']=[x]
        p['global_nets']=['supply[1:0]'];validate(p)
        self.assertIn('supply[1]',net_names(p,root['id']))
        rows=net_occurrences(p,root['id'],'supply[1]')
        self.assertEqual([row['net'] for row in rows],['supply[1]','supply[1]'])
        self.assertEqual({row['array_path'][0]['index'] for row in rows},{0,1})
        self.assertTrue(all(row['objects']==[r['id']] for row in rows))


if __name__=='__main__':unittest.main()
