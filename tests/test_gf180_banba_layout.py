"""Electrical/geometry fault injection for the saved Banba implementation."""
import unittest
from scripts.create_gf180_banba_layout import Builder, verify, stable
from icstudio.model import clone
from icstudio.physical import connectivity


class BanbaLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b=Builder();cls.p=cls.b.build();cls.cid=cls.b.c['id']

    def test_complete_implementation_and_equal_pnp_centroids(self):
        result=verify(self.p)
        for key in ('erc','geometry','connectivity','matching'):self.assertEqual(result[key],[])
        self.assertEqual(result['devices'],103)
        self.assertEqual(result['terminals'],293)
        self.assertEqual(result['pnp_centroids_nm']['Q1'],result['pnp_centroids_nm']['Q2'])
        ds=self.b.c['devices']
        self.assertEqual(sum(d['name'].startswith('Q2_') for d in ds),8)
        for name,n in [('XAMP_RBIAS',10),('XSTART_RDET',16),('XSTART_RPULL',20)]:
            self.assertEqual(sum(d['name'].startswith(name+'_') for d in ds),n)
        self.assertEqual(sum(d['name'].startswith('COUT_') for d in ds),25)

    def test_mim_dielectric_is_required_and_not_mistaken_for_a_via(self):
        p=clone(self.p);p['pdk']['connectivity']['via_blockers']=[]
        issues=connectivity(p,self.cid)['issues']
        self.assertTrue(any(i['code']=='LVS.SHORT' for i in issues))

    def test_removed_reference_bus_is_detected(self):
        p=clone(self.p);c=next(c for c in p['cells'] if c['id']==self.cid)
        ls=self.b.ls
        c['shapes']=[s for s in c['shapes'] if not (s.get('generated_route') and s['layer']==ls['m3'] and s['net']=='VREF')]
        self.assertTrue(any(i['code']=='LVS.OPEN' and i['net']=='VREF' for i in connectivity(p,self.cid)['issues']))

    def test_shorted_power_rails_are_detected(self):
        p=clone(self.p);c=next(c for c in p['cells'] if c['id']==self.cid)
        c['shapes'].append(dict(id=stable('injected-short'),kind='path',layer=self.b.ls['m3'],
            points=[[-16000,self.b.tracks[n]] for n in ('VDD','VSS')],width=600,net='',device_id=''))
        self.assertTrue(any(i['code']=='LVS.SHORT' for i in connectivity(p,self.cid)['issues']))

    def test_displaced_pnp_unit_breaks_the_saved_centroid_constraint(self):
        from icstudio.analog_constraints import move_device, findings
        p=clone(self.p)
        move_device(p,self.cid,stable('device:Q2_1'),1000,0)
        self.assertTrue(any(i['code']=='ANALOG.COMMON_CENTROID' for i in findings(p,self.cid)))


if __name__=='__main__':unittest.main()
