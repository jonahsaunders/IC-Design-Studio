"""Reject vacuous model agreement and incorrect physical multiplicity."""
import cmath,math,unittest
from copy import deepcopy
from scripts.qualify_resistor_families import probes,compare,scaling


class ResistorFamilyQualificationTests(unittest.TestCase):
    def response(self,target):
        x=[100*10**(i/5) for i in range(26)];mag={};phase={}
        for row in probes(target):
            values=[-row['m']*complex(1e-4,2*math.pi*f*1e-14) for f in x]
            key='v'+row['tag'];mag[key]=[abs(v) for v in values];phase[key]=[math.degrees(cmath.phase(v)) for v in values]
        return dict(x=x,currents=mag,current_phase=phase)

    def test_all_families_require_complete_complex_responses(self):
        for target in ('sky130A','gf180mcuC','gf180mcuD','ihp-sg13g2'):
            ref=self.response(target);self.assertEqual(compare(ref,ref,target)['status'],'PASS')
            self.assertEqual(scaling(ref,target)['status'],'PASS')
            for field in ('currents','current_phase'):
                bad=deepcopy(ref);bad[field].pop(next(iter(bad[field])))
                with self.subTest(target=target,field=field),self.assertRaises(ValueError):compare(bad,ref,target)

    def test_agreeing_wrong_models_do_not_pass_parallel_scaling(self):
        ref=self.response('sky130A');key=next(k for k in ref['currents'] if k.endswith('m3'))
        ref['currents'][key]=[v/3 for v in ref['currents'][key]]
        self.assertEqual(compare(ref,ref,'sky130A')['status'],'PASS')
        result=scaling(ref,'sky130A');self.assertEqual(result['status'],'MISMATCH')
        self.assertGreater(result['channel_errors'][key],1)

    def test_phase_and_geometry_errors_are_detected_per_channel(self):
        ref=self.response('ihp-sg13g2')
        for mode in ('phase','size','open'):
            bad=deepcopy(ref)
            if mode=='phase':bad['current_phase']={k:[p+10 for p in v] for k,v in bad['current_phase'].items()}
            else:bad['currents']={k:[a*(1.2 if mode=='size' else 0) for a in v] for k,v in bad['currents'].items()}
            self.assertTrue(all(e>1 for e in compare(bad,ref,'ihp-sg13g2')['channel_errors'].values()))

    def test_missing_nonfinite_and_nonphysical_references_are_rejected(self):
        for mode in ('zero','negative','nan','frequency','short'):
            ref=self.response('ihp-sg13g2');key=next(iter(ref['currents']))
            if mode=='zero':ref['currents'][key]=[0]*26
            elif mode=='negative':ref['current_phase'][key]=[0]*26
            elif mode=='nan':ref['current_phase'][key][0]=math.nan
            elif mode=='frequency':ref['x'][3]*=1.1
            else:ref['x'].pop()
            with self.subTest(mode=mode),self.assertRaises(ValueError):compare(ref,ref,'ihp-sg13g2')


if __name__=='__main__':unittest.main()
