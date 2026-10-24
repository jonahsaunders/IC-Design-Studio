"""Primitive calls must agree with actual public SPICE definitions."""
import math,re,unittest
from copy import deepcopy
from pathlib import Path
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_sky130_primitive_diodes import PROBES,compare


class SKY130PrimitiveQualificationTests(unittest.TestCase):
    def test_catalog_prefixes_match_source_model_types(self):
        tech,_=load_technology('sky130A');root=Path(tech['package_root'])
        for symbol,prefix,model_type in [(f'res_generic_m{i}','R','r') for i in range(1,5)]+[('diode','D','d'),('lvsdiode','D','d')]:
            entry=tech['simulation']['catalog']['sky130_fd_pr/'+symbol+'.sym']
            self.assertEqual(entry['prefix'],prefix)
            text=(root/entry['model_source']).read_text()
            self.assertRegex(text,re.compile(r'(?im)^\s*\.model\s+'+re.escape(entry['model'])+r'\s+'+model_type+r'\b'))

    def response(self):
        x=[-.2+i*.025 for i in range(41)]
        return dict(x=x,currents={'v'+r['tag']:[-r['area']*1e-24*math.expm1(v/.026) for v in x] for r in PROBES})

    def test_rectifying_reference_and_polarity_area_faults(self):
        ref=self.response();self.assertEqual(compare(ref,ref)['status'],'PASS')
        for scale in (-1,0,1.2):
            bad=deepcopy(ref);bad['currents']={k:[x*scale for x in v] for k,v in bad['currents'].items()}
            self.assertTrue(all(e>1 for e in compare(bad,ref)['channel_errors'].values()))

    def test_zero_constant_reverse_nonfinite_and_missing_references_fail(self):
        for mode in ('zero','constant','reverse','nan','missing','range'):
            ref=self.response();key=next(iter(ref['currents']))
            if mode=='zero':ref['currents'][key]=[0]*41
            elif mode=='constant':ref['currents'][key]=[-1e-3]*41
            elif mode=='reverse':ref['currents'][key]=[-v for v in ref['currents'][key]]
            elif mode=='nan':ref['currents'][key][20]=math.nan
            elif mode=='missing':ref['currents'].pop(key)
            else:ref['x'][20]+=.01
            with self.subTest(mode=mode),self.assertRaises(ValueError):compare(ref,ref)


if __name__=='__main__':unittest.main()
