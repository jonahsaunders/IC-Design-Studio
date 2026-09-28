"""Fixed-cell byte/terminal/topology contracts; physical gates use real engines.

Geometry tests stub only the external technology-file reader because the full
physical PDK is a separately fetched test dependency. GDS and model bytes are
the actual shipped assets. scripts/qualify_sky130_bipolar.py verifies the real
locked technology with Magic and Netgen without stubbing any gate.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from icstudio.catalog import create_device
from icstudio.layout import kdb,polygon
from icstudio.layout_eco import regenerate
from icstudio.model import clone,example
from icstudio.physical import connectivity
from icstudio.sky130_bipolar_rules import TECH_SHA256,corrected_technology
from icstudio.sky130_fixed_devices import ASSET,DRAWING_MASKS,specification
from icstudio.sky130_layout import install_mos,audit
from tests.test_sky130_devices import technology


def project(count=1):
    p=example('empty');p['pdk']=technology();c=p['cells'][0]
    p['pdk']['package_lock']['files']['libs.tech/magic/sky130A.tech']=TECH_SHA256
    d=create_device(p['pdk'],'sky130_fd_pr/pnp_05v5.sym','Q1');d['model_params']['m']=count
    d['nets']=dict(collector='C',base='B',emitter='E');c['devices']=[d]
    return p,c,d


class FixedPNPTests(unittest.TestCase):
    def test_old_or_aliased_deck_is_rejected_before_mutation(self):
        p,c,d=project();p['pdk']['package_lock']['files']['libs.tech/magic/sky130A.tech']='old';before=clone(p)
        with self.assertRaisesRegex(ValueError,'--bipolar'):install_mos(p,c['id'],d['id'])
        self.assertEqual(p,before)
        p,c,d=project();p['pdk'].setdefault('interoperability',{}).setdefault('tools',{}).setdefault('magic',{})['technology']='other.tech'
        p['pdk']['package_lock']['files']['other.tech']='old'
        with self.assertRaisesRegex(ValueError,'--bipolar'):install_mos(p,c['id'],d['id'])

    @patch('icstudio.interoperability.tool_asset')
    def test_fixed_units_have_exact_terminals_and_parallel_connectivity(self,reader):
        for count in (1,2,16):
            p,c,d=project(count);install_mos(p,c['id'],d['id'])
            self.assertFalse(connectivity(p,c['id'])['issues']);self.assertFalse(audit(p,c['id']))
            self.assertEqual({pin['pin']:pin['point'] for pin in c['layout_pins']},dict(collector=[385,3495],base=[1125,3490],emitter=[3350,3350]))
            self.assertEqual(len({s['generator_role'] for s in c['shapes']}),len(c['shapes']))
            self.assertEqual(c['pdk_layouts'][0]['spec']['fixed_cell']['technology_sha256'],TECH_SHA256)
        self.assertTrue(reader.called)

    @patch('icstudio.interoperability.tool_asset')
    def test_original_physical_masks_are_preserved(self,_):
        p,c,d=project();install_mos(p,c['id'],d['id']);db=kdb();layout=db.Layout();layout.read(str(ASSET));source=layout.top_cell()
        names={(row['gds'],row['datatype']):row['name'] for row in p['pdk']['layers']}
        for mask in DRAWING_MASKS:
            original=db.Region(source.begin_shapes_rec(layout.layer(*mask))).merged();generated=db.Region()
            for s in c['shapes']:
                if s['layer']==names[mask]:generated.insert(polygon(s))
            self.assertTrue((original-generated).is_empty(),mask)
            if mask not in ((67,44),(68,20)):self.assertTrue((original^generated).is_empty(),mask)

    @patch('icstudio.interoperability.tool_asset')
    def test_corrupted_asset_or_invalid_multiplicity_is_rejected(self,_):
        p,c,d=project()
        for count in (0,1.5,17):
            d['model_params']['m']=count
            with self.assertRaises(ValueError):specification(p['pdk'],d)
        d['model_params']['m']=1
        with tempfile.TemporaryDirectory() as tmp:
            asset=Path(tmp)/'changed.gds';asset.write_bytes(ASSET.read_bytes()+b'changed')
            with patch('icstudio.sky130_fixed_devices.ASSET',asset),self.assertRaisesRegex(ValueError,'geometry is missing or changed'):specification(p['pdk'],d)

    @patch('icstudio.interoperability.tool_asset')
    def test_multiplicity_eco_preserves_pins_and_surviving_shape_roles(self,_):
        p,c,d=project(2);install_mos(p,c['id'],d['id']);pins=clone(c['layout_pins']);roles={s['generator_role']:s['id'] for s in c['shapes']}
        d['model_params']['m']=3;self.assertTrue(audit(p,c['id']));regenerate(p,c['id'],d['id'])
        self.assertFalse(audit(p,c['id']));self.assertEqual(c['layout_pins'],pins)
        self.assertTrue(all(s['id']==roles[s['generator_role']] for s in c['shapes'] if s['generator_role'] in roles))
        self.assertFalse(connectivity(p,c['id'])['issues'])

    def test_extraction_update_refuses_unrecognized_deck(self):
        with self.assertRaisesRegex(ValueError,'exact locked'):corrected_technology(b'modified source')


if __name__=='__main__':unittest.main()
