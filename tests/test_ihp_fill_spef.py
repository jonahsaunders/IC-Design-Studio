import json
from pathlib import Path
import tempfile
import unittest
from tests.test_digital_gf180_fill import SPEF
from icstudio.digital_fill_spef import parse
from scripts.ihp_fill_spef import collapse, run


class IHPFillSpefTests(unittest.TestCase):
    def test_native_dialect_reduction_preserves_signal_terminals_and_resistance(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'input.spef';source.write_text(SPEF)
            represented=root/'represented.json'
            represented.write_text(json.dumps(dict(added=[dict(net='ICSTUDIO_FLOAT_0000')])))
            result=run(source,represented,root/'out');before=parse(source);after=parse(root/'out/timing.spef')
            self.assertFalse(result['qualified'])
            self.assertEqual(after['nets'].keys(),before['nets'].keys()-{'ICSTUDIO_FLOAT_0000'})
            for name,item in after['nets'].items():
                self.assertEqual(item['res'],before['nets'][name]['res'])
                self.assertEqual(item['conn'],before['nets'][name]['conn'])
            self.assertLess(result['maximum_relative_solve_residual'],1e-11)

    def test_missing_or_connected_float_cannot_be_reduced(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'input.spef';source.write_text(SPEF);data=parse(source)
            with self.assertRaisesRegex(ValueError,'Missing'):collapse(data,{'missing'})
            data['nets']['ICSTUDIO_FLOAT_0000']['conn'][0][0]='*P'
            with self.assertRaisesRegex(ValueError,'connected'):collapse(data,{'ICSTUDIO_FLOAT_0000'})
