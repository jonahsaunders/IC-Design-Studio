"""Regression coverage for the native schematic and the blockers it exposed."""
import unittest

from scripts.create_gf180_banba import build
from icstudio.model import clone, flatten, erc
from icstudio.catalog_migration import symbol_context
from icstudio.interchange import spice
from icstudio import analog_optimizer as opt


class BanbaSchematicTests(unittest.TestCase):
    def setUp(self):
        self.p, self.cid, self.spec = build()
        self.core = next(c for c in self.p['cells'] if c['id'] == self.cid)

    def test_real_models_and_topology_survive_netlisting(self):
        self.assertEqual(erc(self.p), [])
        ds = {d['name']:d for d in flatten(self.p)}
        self.assertEqual(ds['XDUT/Q1']['model_params']['m'], '1')
        self.assertEqual(ds['XDUT/Q2']['model_params']['m'], '8')
        self.assertEqual(ds['XDUT/Q2']['nets']['e'], ds['XDUT/RPTAT']['nets']['m'])
        self.assertEqual(ds['XDUT/XAMP/MPA']['nets']['g'], ds['XDUT/MP1']['nets']['d'])
        self.assertEqual(ds['XDUT/XAMP/MPB']['nets']['g'], ds['XDUT/MP2']['nets']['d'])
        for name in ('MP1','MP2','MP3'):
            self.assertEqual(ds['XDUT/'+name]['nets']['g'], 'XDUT/CTRL')
        text = spice(self.p, settings=self.p['analysis'])
        for model in ('pfet_03v3', 'nfet_03v3', 'pnp_05p00x05p00', 'ppolyf_u_1k', 'cap_mim_2f0_m3m4_noshield'):
            self.assertIn(model, text)
        self.assertNotIn('LEVEL=1', text)
        self.assertNotIn('{mirror_w}', text)

    def test_passive_dimensions_are_searchable_and_linkable(self):
        available = opt.targets(self.p, self.cid)
        self.assertIn('RPTAT.model_params.l', available)
        self.assertIn('RCA.model_params.w', available)
        p = clone(self.p)
        axis = dict(target='RCA.model_params.l', lower='90u', upper='110u', count=3,
                    links=[dict(target='RCB.model_params.l', ratio=1)])
        for values in opt.grid(p, self.cid, [axis]):
            for key, value in values.items(): opt.set_target(p, self.cid, key, value)
            ds = {d['name']:d for d in flatten(p)}
            self.assertEqual(ds['XDUT/RCA']['model_params']['l'], ds['XDUT/RCB']['model_params']['l'])
            spice(p, settings=p['analysis'])
        opt.set_target(p, self.cid, 'RPTAT.model_params.l', '9u')
        self.assertAlmostEqual(opt.get_target(p, self.cid, 'RPTAT.model_params.l'), 9e-6)
        self.assertAlmostEqual(opt.get_target(self.p, self.cid, 'RPTAT.model_params.l'), 11e-6)

    def test_symbolic_mos_artwork_does_not_crash_or_change_geometry(self):
        d = next(d for d in self.core['devices'] if d['name'] == 'MP1')
        before = clone(d)
        context = symbol_context(d, self.p['pdk'])
        self.assertEqual(context['w'], '{mirror_w}')
        self.assertEqual(context['l'], '{mirror_l}')
        self.assertEqual(d, before)
        # Once numeric, the pre-existing evaluated-value contract remains.
        d['params'].update(w='8u', l='4u')
        self.assertAlmostEqual(float(symbol_context(d, self.p['pdk'])['w']), 8e-6)
        self.assertNotIn('MP1.model_params.w', opt.targets(self.p, self.cid))


if __name__ == '__main__': unittest.main()
