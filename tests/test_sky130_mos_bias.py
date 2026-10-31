"""Boundary coverage, actual terminal voltages and independent fault detection."""
import re
import unittest

from icstudio.model import clone
from scripts.qualify_sky130_mos_bias import AXES, LIMITS, PINS, SOURCES, STEPS, compare, rows, sources


def response(axis):
    grid=[i/STEPS for i in range(STEPS+1)]
    result=dict(x=grid,currents={},traces={})
    for row in rows(axis):
        for pin in PINS:
            key=row['tag']+pin
            result['currents']['v'+key]=[(1 if pin=='d' else -1 if pin=='s' else 0)*g*1e-3 for g in grid]
            result['traces'][key]=[row['span'][0]+(row['span'][1]-row['span'][0])*g for g in grid] if pin==row['driven'] else [row['bias'][pin]]*len(grid)
    return result


class Sky130MOSBiasTests(unittest.TestCase):
    def test_each_numeric_range_agrees_with_its_exact_public_source_lines(self):
        lines=(SOURCES/'device-details.rst').read_text(encoding='utf-8').splitlines()
        for model,(drain,gate,body,(start,end)) in LIMITS.items():
            block='\n'.join(lines[start-1:end]); found={}
            for axis,low,high in re.findall(r'V_\{(DS|GS|BS)\} = ([+-]?[\d.]+)` to ([+-]?[\d.]+)V',block):
                found.setdefault(axis,[]).append(tuple(sorted((float(low),float(high)))))
            with self.subTest(model=model):
                self.assertEqual(found['DS'][-1],drain)
                self.assertEqual(found['GS'],[gate]); self.assertEqual(found['BS'],[body])
                if model.endswith('g5v0d16v0'):
                    self.assertEqual(max(map(abs,found['DS'][0])),16)
                    self.assertIn('V_{GS} = 0',block)

    def test_all_reviewed_variants_and_conditional_off_state_are_explicit(self):
        self.assertEqual(len(LIMITS),11)
        sources()
        for axis in AXES:
            probes=list(rows(axis)); names={r['key'] for r in probes}
            self.assertEqual(len(names),6 if axis=='off-drain' else 33)
            self.assertEqual(len(probes),4*len(names))
            self.assertEqual(len({r['tag'] for r in probes}),len(probes))
            for row in probes:
                if axis=='off-drain':
                    self.assertEqual(row['bias']['g'],0)
                    self.assertEqual(max(map(abs,row['span'])),16)
                elif row['model'].endswith('g5v0d16v0'):
                    maximum=10 if row['pm'] else 11
                    self.assertLessEqual(abs(row['bias']['d']),maximum)
                    if axis=='drain': self.assertEqual(max(map(abs,row['span'])),maximum)
        with self.assertRaises(ValueError): list(rows('unreviewed'))

    def test_current_mismatch_and_every_required_terminal_are_checked(self):
        reference=response('gate'); key=next(iter(reference['currents']))
        self.assertEqual(compare(reference,reference,'gate')['status'],'PASS')
        measured=clone(reference); measured['currents'][key][20]*=2
        self.assertEqual(compare(measured,reference,'gate')['status'],'MISMATCH')
        for mutation in ('missing','short','nonfinite','grid','flat','conservation'):
            bad=clone(reference)
            if mutation=='missing': del bad['currents'][key]
            elif mutation=='short': bad['currents'][key].pop()
            elif mutation=='nonfinite': bad['currents'][key][10]=float('nan')
            elif mutation=='grid': bad['x'][-1]=.99
            elif mutation=='flat': bad['currents']={k:[0]*len(v) for k,v in bad['currents'].items()}
            else: bad['currents'][key][20]*=2
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): compare(reference,bad,'gate')

    def test_actual_terminal_voltages_must_reach_both_published_endpoints(self):
        for axis in AXES:
            reference=response(axis); row=next(rows(axis)); key=row['tag']+row['driven']
            for index in (0,STEPS):
                bad=clone(reference); bad['traces'][key][index]+=.01
                with self.subTest(axis=axis,index=index),self.assertRaisesRegex(ValueError,'declared voltage'):
                    compare(bad,reference,axis)
                with self.assertRaisesRegex(ValueError,'declared voltage'): compare(reference,bad,axis,fault=True)

    def test_fault_mode_does_not_waive_current_or_reference_checks(self):
        reference=response('body'); measured=clone(reference)
        for row in rows('body'):
            measured['traces'][row['tag']+'b']=[0]*(STEPS+1)
            for pin in PINS:
                key='v'+row['tag']+pin
                measured['currents'][key]=[2*v for v in measured['currents'][key]]
        result=compare(measured,reference,'body',fault=True)
        self.assertTrue(all(error>1 for error in result['device_errors'].values()))
        self.assertEqual(compare(reference,reference,'body',fault=True)['status'],'PASS')


if __name__=='__main__': unittest.main()
