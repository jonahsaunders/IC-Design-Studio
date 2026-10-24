"""Focused controls for explicit DC bias and fresh MiM electrical selection."""
import json
import math
from pathlib import Path
import tempfile
import unittest

from scripts import qualify_sky130_mim_bias_boundaries as runner

CONTRACT = json.loads((runner.ROOT / runner.CONTRACT_PATH).read_bytes())


def write_raw(path, analysis, plate=1, section='tt', bias=5, ground=0, change=None):
    coefficients = CONTRACT['passive_sections'][section]['coefficients']
    names = [f'{kind}({prefix}_{key})' for key in runner.PATHS for kind,prefix in (('v','p'),('v','n'),('i','vp'),('i','vn'))]
    names += [f'v(par_{key})' for key in runner.PROBES]
    if analysis == 'ac': names.insert(0,'frequency')
    points = 8 if analysis == 'ac' else 1
    header = f'Title: Independent source-law fixture\nPlotname: {"AC Analysis" if analysis=="ac" else "Operating Point"}\nFlags: {"complex" if analysis=="ac" else "real"}\n'
    header += f'No. Variables: {len(names)}\nNo. Points: {points}\nVariables:\n'
    header += ''.join(f'\t{i}\t{name}\tvoltage\n' for i,name in enumerate(names))
    data = ''
    for index in range(points):
        frequency = 1e3 * 10 ** index
        metal=plate+2; w=2+1e6*(coefficients[f'm{metal}_dw']+coefficients[f'tol_m{metal}']); l=10+1e6*(coefficients[f'm{metal}_dw']+coefficients[f'tol_m{metal}'])
        r=coefficients[f'rm{metal}']*l/w+coefficients[f'rcvia{metal}']*(.56 if plate==1 else .73)**2/(w*l)
        c=coefficients['camimc']*w*l+2*coefficients['cpmimc']*(w+l)
        y=1/complex(r,-1/(2*math.pi*frequency*c))
        values={f'v(par_{key})':complex(coefficients.get(key,0)) for key in runner.PROBES}
        if analysis=='ac': values['frequency']=complex(frequency)
        for key in runner.PATHS:
            values.update({f'v(p_{key})':complex(1 if analysis=='ac' else bias), f'v(n_{key})':complex(0 if analysis=='ac' else ground),
                           f'i(vp_{key})':-y if analysis=='ac' else complex(0),f'i(vn_{key})':y if analysis=='ac' else complex(0)})
        if change: values.update(change)
        for i,name in enumerate(names):
            value=complex(values[name]); token=f'{value.real:.17g},{value.imag:.17g}' if analysis=='ac' else f'{value.real:.17g}'
            data+=(str(index)+'\t' if i==0 else '\t')+token+'\n'
    path.write_text(header+'Values:\n'+data,encoding='utf-8')


class MiMBiasBoundaries(unittest.TestCase):
    def test_sixty_distinct_selected_contexts_and_no_silent_domain_extension(self):
        cases=runner.selected([1,2],list(runner.SECTIONS),[0,90],[-5,0,5])
        self.assertEqual(len(cases),60)
        self.assertEqual(len({runner.case_name(*case) for case in cases}),60)
        for values in (([],['tt'],[0],[5]),([1],['tt'],[0],[5,5]),([1],['nominal'],[0],[5]),([1],['tt'],[45],[5]),([1],['tt'],[0],[4.99])):
            with self.assertRaises(ValueError):runner.selected(*values)
        self.assertEqual(len(runner.domain_controls()),5)
        for value in (-5,0,5): self.assertEqual(runner.checked_bias(value),value)

    def test_actual_op_bias_is_required_even_when_ac_is_unchanged(self):
        coefficients=CONTRACT['passive_sections']['tt']['coefficients']
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.raw'
            write_raw(path,'ac');self.assertEqual(runner.measure_ac(path,1,coefficients)['status'],'PASS')
            for value in (0,-5,4.99):
                write_raw(path,'op',bias=value)
                with self.assertRaisesRegex(ValueError,'signed OP'):runner.measure_op(path,5,coefficients)
            write_raw(path,'op',bias=5,ground=.5)
            with self.assertRaisesRegex(ValueError,'signed OP'):runner.measure_op(path,5,coefficients)

    def test_all_three_biases_both_models_and_passive_sections_match_the_source_law(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.raw'
            for plate in (1,2):
                for section in runner.SECTIONS:
                    coefficients=CONTRACT['passive_sections'][section]['coefficients']
                    for bias in (-5,0,5):
                        write_raw(path,'op',plate,section,bias)
                        self.assertEqual(runner.measure_op(path,bias,coefficients)['paths']['extracted']['differential_V'],bias)
                    write_raw(path,'ac',plate,section)
                    self.assertEqual(len(runner.measure_ac(path,plate,coefficients)['samples']),8)

    def test_nonfinite_sources_currents_and_coefficients_fail_in_both_analyses(self):
        coefficients=CONTRACT['passive_sections']['tt']['coefficients']
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.raw'
            for analysis in ('op','ac'):
                for channel in ('v(p_schematic)','v(n_extracted)','i(vp_independent)','i(vn_extracted)','v(par_camimc)'):
                    for value in (float('nan'),float('inf')):
                        write_raw(path,analysis,change={channel:value})
                        with self.subTest(analysis=analysis,channel=channel), self.assertRaisesRegex(ValueError,'Nonfinite'):
                            runner.measure_op(path,5,coefficients) if analysis=='op' else runner.measure_ac(path,1,coefficients)

    def test_completed_fault_has_the_exact_expected_bias_and_fails_intended_bias(self):
        coefficients=CONTRACT['passive_sections']['tt']['coefficients']
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.raw'
            for bias in (-5,0,5):
                for fault in runner.faults(bias):
                    actual,ground=runner.applied(bias,fault);write_raw(path,'op',bias=actual,ground=ground)
                    self.assertEqual(runner.measure_op(path,actual,coefficients,ground)['status'],'PASS')
                    with self.assertRaisesRegex(ValueError,'signed OP'):runner.measure_op(path,bias,coefficients)

    def test_only_unused_frequency_imaginary_slot_may_be_nonfinite(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.raw'
            for unused in (float('nan'),float('inf')):
                write_raw(path,'ac',change={'frequency':complex(1000,unused)})
                self.assertEqual(runner.raw_values(path,'ac')[0]['frequency'].real,1000)
            write_raw(path,'ac',change={'frequency':complex(float('nan'),0)})
            with self.assertRaisesRegex(ValueError,'Nonfinite'):runner.raw_values(path,'ac')
            write_raw(path,'ac',change={'v(p_extracted)':complex(1,float('nan'))})
            with self.assertRaisesRegex(ValueError,'Nonfinite'):runner.raw_values(path,'ac')

    def test_kcl_and_wrong_coefficients_are_rejected(self):
        coefficients=CONTRACT['passive_sections']['tt']['coefficients']
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.raw'
            write_raw(path,'ac',change={'i(vn_schematic)':0})
            with self.assertRaisesRegex(ValueError,'KCL'):runner.measure_ac(path,1,coefficients)
            write_raw(path,'op',change={'i(vp_schematic)':1e-6})
            with self.assertRaisesRegex(ValueError,'current/KCL'):runner.measure_op(path,5,coefficients)
            write_raw(path,'op',change={'v(par_camimc)':1})
            with self.assertRaisesRegex(ValueError,'coefficient'):runner.measure_op(path,5,coefficients)

    def test_extra_plot_is_not_an_operating_point(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.raw';write_raw(path,'op');path.write_text(path.read_text()+'Plotname: Operating Point\n')
            with self.assertRaisesRegex(ValueError,'exactly one'):runner.raw_values(path,'op')

    def test_actual_schematic_export_retains_native_include_and_explicit_two_terminal_drives(self):
        tech,_=runner.load_technology('sky130A')
        with tempfile.TemporaryDirectory() as temp:
            native=Path(temp)/'native.spice';native.write_text(runner.independent(runner.SIZE,plate=2),encoding='utf-8')
            context=dict(execution_root='/fixed/native',case='p2-lh-r0-bm5')
            _,text=runner.circuit(tech,2,native,'.lib /locked/library.spice lh',-5,'op',**context)
            self.assertIn(f'.include {native.as_posix()}\n',text)
            self.assertIn('VP_extracted p_extracted 0 DC -5 AC 1\nVN_extracted n_extracted 0 DC 0 AC 0\n',text)
            self.assertIn('X_extracted p_extracted n_extracted device_coupon\n',text)
            self.assertIn('mf=1',text)
            _,missing=runner.circuit(tech,2,native,'.lib /locked/library.spice lh',-5,'op','missing-bias',**context)
            self.assertIn('VP_extracted p_extracted 0 AC 1\n',missing)
            with self.assertRaises(ValueError):runner.circuit(tech,2,native,'',5.001,'op',**context)

    def test_raw_title_binds_orientation_analysis_fault_and_execution(self):
        expected=runner.context_title('/fixed/native','p1-tt-r0-bp5','op')
        alternatives=[runner.context_title('/other/native','p1-tt-r0-bp5','op'),
                      runner.context_title('/fixed/native','p1-tt-r90-bp5','op'),
                      runner.context_title('/fixed/native','p1-tt-r0-bp5','ac'),
                      runner.context_title('/fixed/native','p1-tt-r0-bp5','op','missing-bias')]
        self.assertEqual(len(set([expected,*alternatives])),5)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.raw';path.write_text('Title: '+expected+'\n')
            runner.require_raw_title(path,expected)
            for different in alternatives:
                path.write_text('Title: '+different+'\n')
                with self.assertRaisesRegex(ValueError,'context identity'):runner.require_raw_title(path,expected)
            path.write_text('Title: '+expected+'\nTitle: '+expected+'\n')
            with self.assertRaisesRegex(ValueError,'context identity'):runner.require_raw_title(path,expected)


if __name__=='__main__':unittest.main()
