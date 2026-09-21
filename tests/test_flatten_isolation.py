"""Electrical flattening preserves source objects and instance-specific values."""
import unittest
from icstudio.model import clone, device, example, flatten, uid
from icstudio import wiring
from icstudio.electrical_identity import synchronize


class FlattenIsolationTests(unittest.TestCase):
    def wired(self):
        p=example();c=p['cells'][0]
        wiring.migrate(c,p)
        synchronize(c)
        return p,c

    def test_rebuild_uses_wires_without_mutating_source_or_sharing_results(self):
        p,c=self.wired()
        # Saved labels/wires, rather than stale per-device nets, remain authoritative.
        c['devices'][1]['nets']['p']='stale'
        before=clone(p)
        result=flatten(p)
        self.assertEqual(result[1]['nets'],{'p':'vin','n':'vout'})
        self.assertEqual(p,before)
        result[1]['nets']['p']='changed_output'
        result[1]['params']['w']='99u'
        result[1]['source']['high']='9'
        self.assertEqual(p,before)

    def test_electrical_read_does_not_copy_unrelated_layout(self):
        class LayoutNotCopied(list):
            def __deepcopy__(self,memo):
                raise AssertionError('Electrical flatten copied physical geometry')
        p,c=self.wired()
        expected=flatten(p)
        c['shapes']=LayoutNotCopied([{'id':'physical-only','points':[[0,0],[100,100]]}])
        self.assertEqual(flatten(p),expected)

    def test_shared_master_keeps_parameter_overrides_and_port_mapping(self):
        p=example('empty');root=p['cells'][0]
        child={'id':uid(),'name':'resistor','ports':['a','b'],'parameters':{'r':'1k'},
               'devices':[device('R','R1',value='{r}',nets={'p':'a','n':'b'})],
               'shapes':[], 'wires':[], 'junctions':[]}
        child['devices'][0]['net_labels']={'p':'a','n':'b'}
        p['cells'].append(child)
        root['devices']=[device('X','X1',cell=child['id'],nets={'a':'in','b':'middle'},parameters={'r':'2k'}),
                         device('X','X2',cell=child['id'],nets={'a':'middle','b':'0'},parameters={'r':'3k'})]
        before=clone(p);result=flatten(p)
        self.assertEqual([d['name'] for d in result],['X1/R1','X2/R1'])
        self.assertEqual([float(d['value']) for d in result],[2000,3000])
        self.assertEqual([d['nets'] for d in result],[{'p':'in','n':'middle'},{'p':'middle','n':'0'}])
        result[0]['nets']['p']='output-only'
        self.assertEqual(result[1]['nets']['p'],'middle')
        self.assertEqual(p,before)
        child['devices'][0]['value']='4k'
        self.assertEqual([float(d['value']) for d in flatten(p)],[4000,4000])

    def test_failed_rebuild_does_not_leave_partial_source_changes(self):
        p,c=self.wired()
        c['devices'][1].setdefault('net_labels',{})['p']='conflicting'
        before=clone(p)
        with self.assertRaisesRegex(ValueError,'conflicting labels'):
            flatten(p)
        self.assertEqual(p,before)


if __name__=='__main__':unittest.main()
