"""Selected alias identity, raw fidelity and paired model-law controls."""
import copy
import math
from pathlib import Path
import tempfile
import unittest

from scripts import qualify_sky130_mim_mismatch_aliases as probe


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.spec=probe.contract()

    def raw(self, root, *, fault=None):
        names=['frequency']+[v for r in probe.rows() for v in (f'v({r["tag"]})',f'i(v{r["tag"]})')]+[f'v(par_{n})' for n in probe.PARAMETERS]
        coefficients=probe.expected_parameters('tt',self.spec)
        lines=['Title: * test-title','Date: controlled','Plotname: AC Analysis','Flags: complex',
               f'No. Variables: {len(names)}','No. Points: 3','Variables:']
        lines += [f'{i}\t{name}\tfrequency' if name=='frequency' else f'{i}\t{name}\tvoltage' for i,name in enumerate(names)]
        lines += ['Values:']
        for i,f in enumerate((1000,10000,100000)):
            row=[complex(f,math.nan if fault=='frequency-unused' else 0)]
            for item in probe.rows():
                r,c=probe.analytical(item['plate'],coefficients)
                current=-1/(r+1/(2j*math.pi*f*c))
                row.extend([complex(1),current])
            row += [complex(coefficients[n]) for n in probe.PARAMETERS]
            if fault=='nan-current' and i==0: row[2]=complex(math.nan,0)
            if fault=='wrong-source' and i==0: row[1]=complex(.5,0)
            if fault=='wrong-coefficient' and i==0: row[names.index('v(par_camimc)')]*=2
            for j,value in enumerate(row): lines.append(f'{i if j==0 else ""}\t{value.real:.17g},{value.imag:.17g}')
        path=root/'result.raw'; path.write_text('\n'.join(lines)+'\n',encoding='ascii')
        return path

    def test_selection_covers_declared_aliases_controls_without_duplicates(self):
        full=probe.selection(); pilot=probe.selection(True)
        self.assertEqual((len(full),len(pilot)),(45,9))
        self.assertEqual(len({v['name'] for v in full}),45)
        for section in probe.SECTIONS:
            items=[v for v in full if v['section']==section]
            self.assertEqual(len(items),9)
            wrong=next(v for v in items if v['variant']=='wrong-alias')
            self.assertNotEqual(wrong['actual_section'],section+'_mm')

    def test_positive_decks_do_not_override_statistical_switches(self):
        selected=probe.selection()
        staged={s:'.lib pdk-models/test.spice '+s for v in selected for s in (v['actual_section'],)}
        application={m:[f'X_{r["tag"]} {r["tag"]} 0 {r["model"]} w=2 l=10 mf={m} m={m}' for r in probe.rows()] for m in (1,4)}
        for case in selected:
            text=probe.deck(case,staged,application,dict(root='/exact',nonce='a'*32))
            self.assertNotIn('.param',text)
            self.assertIn('.lib pdk-models/test.spice '+case['actual_section'],text)
            self.assertEqual(sum(line.startswith('X_') for line in text.splitlines()),8)
            self.assertIn('AC {mc_mm_switch}',text)
            if case['variant']=='missing-m':
                self.assertTrue(all(' m=' not in line and ' mf=4' in line for line in text.splitlines() if line.startswith('X_')))

    def test_base_and_other_aliases_cannot_claim_selected_mismatch(self):
        for actual in ('tt','ll_mm','hh_mm','hl_mm','lh_mm'):
            with self.assertRaises(ValueError):
                probe.check_parameters(probe.expected_parameters(actual,self.spec),'tt_mm',self.spec)
        probe.check_parameters(probe.expected_parameters('tt_mm',self.spec),'tt_mm',self.spec)

    def test_raw_physical_and_title_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            good=probe.raw_values(self.raw(root),'* test-title','tt',self.spec,1)
            self.assertEqual(len(good['capacitances_F']),8)
            with self.assertRaisesRegex(ValueError,'execution/case'):
                probe.raw_values(root/'result.raw','* other-case','tt',self.spec,1)
            path=root/'result.raw'; path.write_text(path.read_text().replace('AC Analysis','Transient Analysis'))
            with self.assertRaisesRegex(ValueError,'complex AC'):
                probe.raw_values(path,'* test-title','tt',self.spec,1)
            for fault in ('nan-current','wrong-source','wrong-coefficient'):
                with self.subTest(fault=fault),self.assertRaises(ValueError):
                    probe.raw_values(self.raw(root,fault=fault),'* test-title','tt',self.spec,1)
            probe.raw_values(self.raw(root,fault='frequency-unused'),'* test-title','tt',self.spec,1)

    def synthetic(self):
        result={}
        deltas={r['tag']:.001*(i+1) for i,r in enumerate(probe.rows())}
        for case in probe.selection(True):
            params=probe.expected_parameters(case['actual_section'],self.spec)
            values={}
            for row in probe.rows():
                _,base=probe.analytical(row['plate'],params)
                mf=1 if case['variant']=='wrong-mf' else case['multiplier']
                m=1 if case['variant']=='missing-m' else case['multiplier']
                values[row['tag']]=m*base*(1+(deltas[row['tag']]/math.sqrt(mf) if case['actual_section'].endswith('_mm') else 0))
            result[case['name']]={'raw':dict(coefficients=params,capacitances_F=values)}
        return result

    def test_model_law_and_controls_reject_silent_fallback(self):
        good=self.synthetic()
        self.assertEqual(len(probe.comparisons(good,('tt',),self.spec)[0]['detected_controls']),4)
        for kind in ('disabled','wrong-scaling','escaped-fault'):
            bad=copy.deepcopy(good)
            if kind=='disabled': bad['tt-m1-application-alias']['raw']['capacitances_F']=bad['tt-m1-application-base']['raw']['capacitances_F']
            elif kind=='wrong-scaling': bad['tt-m4-application-alias']['raw']['capacitances_F']['p1t0']*=1.001
            else: bad['tt-m4-wrong-mf']['raw']['capacitances_F']=bad['tt-m4-application-alias']['raw']['capacitances_F']
            with self.subTest(kind=kind),self.assertRaises(ValueError): probe.comparisons(bad,('tt',),self.spec)

    def test_scope_cannot_be_promoted(self):
        fields=('qualified','installed_acceptance','full_mim_installed','chunk_complete','release_ready','signoff')
        row=dict(mode='source-integration',**dict.fromkeys(fields,False))
        probe.scope_check(row)
        for field in fields:
            with self.subTest(field=field),self.assertRaises(ValueError): probe.scope_check({**row,field:True})
        with self.assertRaises(ValueError): probe.scope_check({**row,'mode':'installed'})


if __name__=='__main__': unittest.main()
