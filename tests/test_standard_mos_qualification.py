"""Independent numerical/device contracts must reject plausible false passes."""
from copy import deepcopy
import math
import unittest
from scripts.qualify_standard_mos import PROFILES,compare,geometry,independent_device


class StandardMosQualificationTests(unittest.TestCase):
    def response(self,analysis='dc'):
        values=[.1+i*.1 for i in range(12)]
        return dict(x=[i*1e-9 for i in range(12)],traces={'out':values},
                    phase={'out':[-170+i*.2 for i in range(12)]})

    def test_independent_unit_and_multiplicity_contracts(self):
        for target in PROFILES:
            for polarity in ('n','p'):
                text=independent_device(target,polarity,geometry(target,'parallel'))
                fields=text.split();self.assertEqual(fields[1:5],['out','gate',*(['vdd','vdd'] if polarity=='p' else ['0','0'])])
                self.assertEqual(fields[5],PROFILES[target]['models'][polarity=='p'])
                params=dict(v.split('=') for v in fields[6:])
                self.assertEqual(params['m'],'3')
                if target=='ihp-sg13g2':
                    self.assertEqual(params['w'],'4u');self.assertEqual(params['l'],'0.5u');self.assertEqual(params['ng'],'2')
                else:
                    scale=1 if target=='sky130A' else 1e-6
                    self.assertAlmostEqual(float(params['w'])/scale,4)
                    self.assertAlmostEqual(float(params['l'])/scale,.5)
                    self.assertEqual(params['nf'],'2')
                    self.assertGreater(float(params['as']),float(params['ad']))
                    if target=='sky130A':self.assertEqual(params['mult'],'3')

    def test_geometry_corners_do_not_silently_replace_interior(self):
        for target in PROFILES:
            self.assertEqual(geometry(target,'narrow-short')['l'],PROFILES[target]['minimum_length'])
            self.assertEqual(geometry(target,'narrow-short')['w'],1)
            self.assertEqual(geometry(target,'wide-long')['w'],10)
            self.assertEqual(geometry(target,'wide-long')['l'],2)
            self.assertEqual(geometry(target,'interior'),dict(w=4,l=.5,fingers=1,copies=1))

    def test_matching_sweeps_and_complex_phase_pass(self):
        for analysis in ('dc','ac','tran','noise'):
            data=self.response(analysis)
            self.assertEqual(compare(data,deepcopy(data),analysis)['status'],'PASS')

    def test_wrong_scale_empty_nonfinite_and_missing_samples_fail(self):
        for fault in ('scale','empty','nonfinite','missing','duplicate-grid'):
            actual=self.response();reference=deepcopy(actual)
            if fault=='scale':actual['traces']['out']=[v*1.01 for v in actual['traces']['out']]
            if fault=='empty':actual['traces']['out']=[]
            if fault=='nonfinite':actual['traces']['out'][4]=math.nan
            if fault=='missing':actual['traces']['out'].pop()
            if fault=='duplicate-grid':actual['x'][4]=actual['x'][3]
            with self.subTest(fault=fault),self.assertRaises(ValueError):compare(actual,reference,'dc')

    def test_identical_flat_outputs_do_not_prove_a_switching_transistor(self):
        data=self.response();data['traces']['out']=[.7]*12
        for analysis in ('dc','tran'):
            with self.subTest(analysis=analysis),self.assertRaisesRegex(ValueError,'switching device'):
                compare(data,data,analysis)

    def test_magnitude_match_cannot_hide_wrong_or_missing_ac_phase(self):
        for fault in ('wrong','missing','nonfinite'):
            actual=self.response();reference=deepcopy(actual)
            if fault=='wrong':actual['phase']['out'][4]+=1
            if fault=='missing':actual.pop('phase')
            if fault=='nonfinite':actual['phase']['out'][4]=math.inf
            with self.subTest(fault=fault),self.assertRaises(ValueError):compare(actual,reference,'ac')

    def test_adaptive_transient_grid_is_interpolated_with_equal_endpoints(self):
        actual=self.response();reference=deepcopy(actual)
        reference['x']=[i*.5e-9 for i in range(23)]
        reference['traces']['out']=[.1+i*.05 for i in range(23)]
        self.assertEqual(compare(actual,reference,'tran')['status'],'PASS')
        reference['x'][-1]+=1e-9
        with self.assertRaisesRegex(ValueError,'domains differ'):compare(actual,reference,'tran')

    def test_changed_frequency_axis_and_zero_noise_are_rejected(self):
        actual=self.response();reference=deepcopy(actual);actual['x'][5]+=1e-10
        with self.assertRaisesRegex(ValueError,'coordinates differ'):compare(actual,reference,'noise')
        reference['traces']['out']=[0]*12
        with self.assertRaisesRegex(ValueError,'empty or nonphysical'):compare(reference,reference,'noise')


if __name__=='__main__':unittest.main()
