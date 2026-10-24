import math,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from scripts.qualify_bipolar_families import probes,compare,fixture
from scripts.qualify_standard_mos import load_technology
from scripts.prepare_sky130_bipolar_qualification import prepare,inputs
from icstudio.catalog import parameter_values,binding_for
from icstudio.pdks import PDKRegistry,model_lines
ROOT=Path(__file__).resolve().parents[1]


class BipolarFamilyQualificationTests(unittest.TestCase):
    def response(self,target,polarity):
        sign=1 if polarity=='n' else -1;x=[sign*(.45+i*.01) for i in range(31)];currents={}
        for row in probes(target,polarity):
            ic=[-sign*row['factor']*1e-4*math.exp((abs(v)-.75)/.026) for v in x];ib=[v*.01 for v in ic];sub=[-sign*1e-12]*31 if polarity=='n' else [0]*31
            ie=[-sum(v) for v in zip(ic,ib,sub)]
            for pin,values in [('c',ic),('b',ib),('e',ie)]+([('s',sub)] if polarity=='n' else []):currents['v'+row['tag']+pin]=values
        return dict(x=x,currents=currents)

    def test_every_catalog_bipolar_family_and_electrical_terminal_is_exercised(self):
        vectors=0;devices=0
        for target in ('sky130A','gf180mcuC','gf180mcuD','ihp-sg13g2'):
            for polarity in ('n','p'):
                ref=self.response(target,polarity);result=compare(ref,ref,target,polarity);self.assertEqual(result['status'],'PASS');vectors+=result['terminal_vectors'];devices+=len(list(probes(target,polarity)))
                for key in ref['currents']:
                    bad=deepcopy(ref);bad['currents'].pop(key)
                    with self.subTest(target=target,key=key),self.assertRaises(ValueError):compare(bad,ref,target,polarity)
        self.assertEqual(devices,57);self.assertEqual(vectors,208)

    def test_agreeing_zero_flat_wrong_sign_and_kcl_broken_references_fail(self):
        for mode in ('zero','flat','sign','kcl','nan','axis'):
            ref=self.response('ihp-sg13g2','n');key=next(iter(ref['currents']))
            if mode=='zero':ref['currents']={k:[0]*31 for k in ref['currents']}
            elif mode=='flat':ref['currents']={k:[v[-1]]*31 for k,v in ref['currents'].items()}
            elif mode=='sign':ref['currents']={k:[-v for v in values] for k,values in ref['currents'].items()}
            elif mode=='kcl':ref['currents'][key]=[v*1.2 for v in ref['currents'][key]]
            elif mode=='nan':ref['currents'][key][2]=math.nan
            else:ref['x'][5]+=.01
            with self.subTest(mode=mode),self.assertRaises(ValueError):compare(ref,ref,'ihp-sg13g2','n')

    def test_terminal_mismatch_and_open_collector_are_detected(self):
        ref=self.response('gf180mcuC','p')
        for factor in (0,1.2):
            bad=deepcopy(ref)
            for key in bad['currents']:
                if key.endswith('c'):bad['currents'][key]=[v*factor for v in bad['currents'][key]]
            r=compare(bad,ref,'gf180mcuC','p');self.assertEqual(r['status'],'MISMATCH')
            self.assertTrue(all(e>1 for k,e in r['channel_errors'].items() if k.endswith('c')))

    def test_ihp_five_terminal_length_override_reaches_the_actual_parameter(self):
        tech,_=load_technology('ihp-sg13g2');p=fixture(tech,'ihp-sg13g2','n',.6,{})
        selected=[d for d in p['cells'][0]['devices'] if d.get('model_ref') and 'npn13G2l_5t' in d['model_ref']['device']]
        self.assertEqual(len(selected),2)
        for d in selected:self.assertEqual(parameter_values(binding_for(tech,d),d)['el'],1)

    def test_public_corner_package_preserves_npn_equations_and_rejects_unmapped_corners(self):
        source=ROOT/'icstudio/assets/pdks/sky130A';lock=inputs(source);self.assertEqual(lock['license'],'Apache-2.0')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'adapter';result=prepare(source,out);registry=PDKRegistry(Path(tmp)/'registry');key=registry.install(out/'package.json');tech=registry.technology(key)
            self.assertEqual(tech['revision'],result['revision'])
            for corner,section in [('nominal','t'),('tt','t'),('ss','s'),('ff','f')]:self.assertTrue(model_lines(tech,corner)[-1].endswith(' '+section))
            for corner in ('sf','fs','mc','tt_mm'):
                with self.assertRaisesRegex(ValueError,'Missing model section'):model_lines(tech,corner)
            rel='libs.ref/sky130_fd_pr/spice/sky130_fd_pr__npn_05v5_W1p00L2p00.model.spice';self.assertEqual((source/rel).read_bytes(),(out/rel).read_bytes())
            (out/'libs.tech/ngspice/icstudio-npn-corners.lib').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):registry.install(out/'package.json')


if __name__=='__main__':unittest.main()
