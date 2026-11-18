"""Check that the lessons use actual devices, layouts and fixed bench conditions."""

import unittest

from icstudio.model import validate
from icstudio.student_analog import _cell, _get_bench, _named
from icstudio.student_bandgap import NAMES
from icstudio.student_bandgap_lab import _cases, core_cell, verify_fixture
from icstudio.student_bandgap_layout import check, generate
from icstudio.student_bandgap_pex import compare_devices
from icstudio.student_projects import create


class BandgapLabs(unittest.TestCase):
    def test_each_lab_has_device_models_and_a_checked_layout(self):
        for kind in NAMES:
            with self.subTest(kind=kind):
                p = create('bandgap-lab-'+kind)
                core = core_cell(p)
                self.assertEqual(core['ports'], ['VDD','VSS','VREF'])
                self.assertTrue(all(d.get('model_ref') for d in core['devices']))
                self.assertGreaterEqual(sum(d['model_ref']['device'].startswith(('symbols/npn_','symbols/pnp_'))
                                            for d in core['devices']), 2)
                verify_fixture(p)
                if kind != 'banba':
                    generate(p)
                validate(p)
                self.assertEqual(check(p)['devices'],len(core['devices']))
                adjustable = next(d for d in core['devices'] if d['name']=='R2' or d['name']=='ROUT')
                adjustable['model_params']['l'] = '9u'
                with self.assertRaisesRegex(ValueError,'current component dimensions'):
                    check(p)

    def test_startup_conditions_and_fixture_are_fixed(self):
        for kind in NAMES:
            points = _cases(kind,'startup')
            self.assertEqual(len(points),22)
            self.assertEqual(len(set(points)),22)
            self.assertEqual({p[1] for p in points},{'nominal','ss','ff'})
            self.assertEqual({p[2] for p in points},{-40,27,125})
        project = create('bandgap-lab-widlar')
        bench = _get_bench(project,'bandgap_fast_startup')
        _named(_cell(project,bench['bench_cell']),'CL')['value'] = '1p'
        with self.assertRaisesRegex(ValueError,'5 pF load'):
            verify_fixture(project)

    def test_extract_rejects_changed_device_terminal_and_foreign_cap_node(self):
        body = '.subckt bg VREF VSS VDD\nXQ VDD VREF VSS VSS npn_05p00x05p00\n'
        end = '.ends bg\n'
        actual = body+'C1 VREF VSS 2f\n'+end
        self.assertEqual(compare_devices(body+end,actual,'bg')[1]['capacitors'],1)
        with self.assertRaisesRegex(ValueError, 'terminals|ports'):
            compare_devices(body+end,actual.replace('XQ VDD VREF','XQ VREF VDD'),'bg')
        with self.assertRaisesRegex(ValueError, 'unknown circuit nets'):
            compare_devices(body+end,actual.replace('C1 VREF','C1 stray'),'bg')

    def test_open_routing_via_fails_before_extraction(self):
        from icstudio.layout import polygon

        p = create('bandgap-lab-widlar')
        generate(p)
        cell = core_cell(p)
        transistor = _named(cell,'Q3')
        pin = next(pin for pin in cell['layout_pins']
                   if pin['device_id']==transistor['id'] and pin['pin']=='c')
        x,y = pin['point']
        via1 = next(layer['name'] for layer in p['pdk']['layers'] if (layer['gds'],layer['datatype'])==(35,0))
        cut = next(shape for shape in cell['shapes']
                   if shape['layer']==via1 and (center:=polygon(shape).bbox().center()).x==x and center.y==y)
        cell['shapes'].remove(cut)
        with self.assertRaisesRegex(ValueError,'layout findings'):
            check(p)
