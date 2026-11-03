"""The process comparison independently checks the native raw observable."""
import math
from pathlib import Path
import tempfile
import unittest

from scripts.check_ihp_cmim_process_control import CASES, measurement
from scripts.qualify_ihp_cmim_process_control import deck


def raw_plot(plot, flags, variables, values):
    columns = ''.join(f'\t{i}\t{name}\t{unit}\n' for i, (name, unit) in enumerate(variables))
    body = '\n'.join(values)
    return (f'Plotname: {plot}\nFlags: {flags}\nNo. Variables: {len(variables)}\nNo. Points: 1\n'
            f'Variables:\n{columns}Values:\n 0\t{body}\n')


class CmimProcessControlReaderTests(unittest.TestCase):
    def test_raw_current_and_scope_controls(self):
        spec = CASES['voltage-4']
        probes = [('v(upper)','voltage'), ('v(lower)','voltage'), ('i(vdrive)','current')]
        op = raw_plot('Operating Point', 'real', [probes[1], *probes], ['10', '0', '10', '0'])
        ac = raw_plot('AC Analysis', 'complex', [('frequency','frequency'), *probes],
                      ['1000000,0', '0,0', '1,0', '-1e-14,-4.7e-7'])
        log = 'Doing analysis at TEMP = 26.850000 and TNOM = 27.000000\n'*2
        original = {'input.cir': deck(spec), 'op.raw': op, 'ac.raw': ac, 'engine.log': log}
        controls = (
            ('ac.raw', ac.replace('1000000,0', '100000,0'), 'frequency differs'),
            ('ac.raw', ac.replace('-4.7e-7', '4.7e-7'), 'current sign/passivity'),
            ('ac.raw', ac.replace('-4.7e-7', 'NaN'), 'Nonfinite'),
            ('ac.raw', ac+'\t99\n', 'row shape'),
            ('op.raw', op.replace('0\t10', '0\t11'), 'scale/duplicate'),
            ('input.cir', original['input.cir'].replace('cap_typ','cap_wcs'), 'model section'),
        )
        for statement, anchor in (('Cunreviewed lower 0 1p', '.control'),
                                  ('.param cap_carea=0', '.control'),
                                  ('alter Vdrive 0', 'op\n')):
            injected = original['input.cir'].replace(anchor, statement+'\n'+anchor, 1)
            controls += (('input.cir', injected, 'Unexpected stimulus deck statement'),)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in original.items():
                (root/name).write_text(text, encoding='ascii')
            row = measurement(root, spec)
            self.assertEqual(row['capacitance_f'], 4.7e-7/(2*math.pi*1_000_000))
            self.assertEqual(row['temperature_k'], 300)
            self.assertEqual(row['op']['v(lower)'], 10)
            for name, text, failure in controls:
                with self.subTest(failure=failure):
                    (root/name).write_text(text, encoding='ascii')
                    with self.assertRaisesRegex(ValueError, failure):
                        measurement(root, spec)
                    (root/name).write_text(original[name], encoding='ascii')


if __name__ == '__main__':
    unittest.main()
