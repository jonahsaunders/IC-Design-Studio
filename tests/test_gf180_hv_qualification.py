import unittest
from icstudio.model import clone
from scripts.qualify_gf180_hv import compare,points


def response(analysis):
    x=[i/10 for i in range(51)] if analysis=='dc' else [100*10**(i/5) for i in range(26)]
    names=['v'+r['tag']+p for r in points() for p in ('d','g','s','b')]
    return dict(x=x,currents={n:[1e-3*(i+1) for i in range(len(x))] for n in names},current_phase={n:[12.]*len(x) for n in names})


class HighVoltageComparisonTests(unittest.TestCase):
    def test_all_four_terminals_and_complex_phase_are_compared(self):
        for analysis in ('dc','ac'):
            a=response(analysis);self.assertEqual(compare(a,a,analysis)['status'],'PASS')
            b=clone(a);b['currents']['vn0b'][10]*=1.1
            self.assertGreater(compare(b,a,analysis)['errors']['vn0b'],1)
        b=response('ac');b['current_phase']['vp0g'][10]+=5
        self.assertGreater(compare(b,response('ac'),'ac')['errors']['vp0g'],1)

    def test_missing_truncated_nonfinite_and_flat_outputs_are_refused(self):
        for analysis in ('dc','ac'):
            for fault in ('x','missing','short','nan','flat','phase'):
                if fault=='phase' and analysis=='dc':continue
                with self.subTest(analysis=analysis,fault=fault),self.assertRaises(ValueError):
                    a=response(analysis)
                    if fault=='x':a['x'].pop()
                    elif fault=='missing':del a['currents']['vn0g']
                    elif fault=='short':a['currents']['vn0s'].pop()
                    elif fault=='nan':a['currents']['vp0b'][3]=float('nan')
                    elif fault=='phase':a['current_phase']['vp0g'].pop()
                    else:a['currents']['vn0d']=[0]*len(a['x'])
                    compare(response(analysis),a,analysis)


if __name__=='__main__':unittest.main()
