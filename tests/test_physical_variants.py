import unittest
from icstudio.model import example, device, uid, clone, History, validate
from icstudio.physical_variants import propose, electrical_signature


class PhysicalVariantsTests(unittest.TestCase):
    def project(self):
        p=example('empty');top=p['cells'][0]
        leaf={'id':uid(),'name':'leaf','ports':['a','b'],'parameters':{'r':'1k'},'shapes':[],
              'devices':[device('R','R1',0,0,value='{r*2}',nets={'p':'a','n':'b'})]}
        p['cells'].append(leaf)
        top['devices']=[device('X','X'+str(i),i*200,0,cell=leaf['id'],nets={'a':'n'+str(i),'b':'0'},parameters={'r':v}) for i,v in enumerate(('2k','2k','3k'))]
        return validate(p)

    def test_deduplicates_parameters_preserves_electrical_values_and_undo(self):
        p=self.project();before=clone(p);q,report=propose(p,p['top'])
        self.assertEqual(p,before);self.assertEqual(report['variants'],2)
        ds=q['cells'][0]['devices'];self.assertEqual(ds[0]['cell'],ds[1]['cell']);self.assertNotEqual(ds[1]['cell'],ds[2]['cell'])
        self.assertEqual(electrical_signature(q,p['top']),electrical_signature(p,p['top']))
        h=History(p);h.commit(lambda target:(target.clear(),target.update(clone(q))),'Specialize');h.undo()
        self.assertEqual(h.project['cells'],p['cells']);h.redo();self.assertEqual(h.project['cells'],q['cells'])

    def test_nested_override_uses_parent_context(self):
        p=self.project();top=p['cells'][0];leaf=p['cells'][1]
        wrapper={'id':uid(),'name':'wrapper','ports':['a','b'],'parameters':{'outer':'2k'},'shapes':[],
                 'devices':[device('X','Xleaf',0,0,cell=leaf['id'],nets={'a':'a','b':'b'},parameters={'r':'{outer*2}'})]}
        p['cells'].append(wrapper);top['devices']=[device('X','Xwrap',0,0,cell=wrapper['id'],nets={'a':'n','b':'0'},parameters={'outer':'3k'})]
        validate(p);q,report=propose(p,p['top']);self.assertEqual(report['variants'],2)
        self.assertEqual(electrical_signature(q,p['top']),electrical_signature(p,p['top']))
        with self.assertRaisesRegex(ValueError,'no differing'):propose(q,q['top'])
