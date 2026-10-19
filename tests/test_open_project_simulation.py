"""The detector's independent per-code execution must fail on bad evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import qualify_open_project as q


class DetectorSweepTests(unittest.TestCase):
    def wave(self):
        return dict(plot_kind='dc',x=[3+i*.01 for i in range(301)],traces={'ovout':[0. if i<150 else 1.8 for i in range(301)]})

    def run_pair(self,first,second,log=''):
        with tempfile.TemporaryDirectory() as tmp:
            circuit='.subckt detector avdd dvdd avss dvss ena ibias vbg vtrip[0] vtrip[1] vtrip[2] vtrip[3] ovout\n.ends detector\n'
            job=(7,circuit,circuit,'detector','models.lib','ngspice',tmp,'hsa')
            with patch.object(q,'execute',return_value=log),patch('icstudio.spice_program.read_plot',side_effect=[first,second]),\
                    patch('icstudio.ngspice_compat.prepare',side_effect=lambda deck,*_:deck),\
                    patch('icstudio.dc_startup.seed_deck',side_effect=lambda deck,*_:deck):
                result=q.simulation_code(job)
            for kind in ('native','reference'):
                deck=(Path(tmp)/('07-'+kind)/'input.cir').read_text()
                self.assertIn('.dc Vavdd 3 6 .01',deck)
                self.assertIn('Vbit3 vtrip_3 0 0',deck)
                for i in range(3):self.assertIn(f'Vbit{i} vtrip_{i} 0 1.8',deck)
            return result

    def test_valid_pair_keeps_code_trip_and_declared_tolerance(self):
        wave=self.wave();other=deepcopy(wave);other['traces']['ovout'][10]=1e-6
        result=self.run_pair(wave,other)
        self.assertEqual(result['code'],7);self.assertEqual(result['trip_voltage'],4.5)
        self.assertEqual(result['max_reference_error'],1e-6)

    def test_changed_axis_or_nonfinite_or_missing_points_are_rejected(self):
        for kind in ('axis','nan','short','kind'):
            bad=self.wave()
            if kind=='axis':bad['x'][100]+=.001
            elif kind=='nan':bad['traces']['ovout'][100]=float('nan')
            elif kind=='short':bad['x'].pop()
            else:bad['plot_kind']='tran'
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_pair(self.wave(),bad)

    def test_mismatch_and_nonswitching_and_tool_diagnostics_are_rejected(self):
        for kind in ('voltage','trip','flat','diagnostic'):
            bad=self.wave()
            if kind=='voltage':bad['traces']['ovout'][100]=.1
            elif kind=='trip':bad['traces']['ovout'][149]=1.8
            elif kind=='flat':bad['traces']['ovout']=[0.]*301
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_pair(self.wave(),bad,'Error: no solution' if kind=='diagnostic' else '')


if __name__=='__main__':unittest.main()
