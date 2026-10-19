"""A zero-exit reader must not hide a discarded physical mask."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from icstudio.magic_diagnostics import require_readable_stream
from icstudio.silicon_flow import magic_script
from icstudio.engines import magic_convert

LOST_MASK = ('Error while reading cell "coupon" (byte position 694): '
             'Unknown layer/datatype in boundary, layer=210 type=0\n'
             'Total of 1 warning.\nSTUDIO_DRC_COUNT 0\nSTUDIO_MAGIC_COMPLETE\n')


class MagicInputDiagnosticsTests(unittest.TestCase):
    def test_zero_violation_count_does_not_override_a_dropped_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with patch('icstudio.silicon_flow.execute',return_value=LOST_MASK), \
                    self.assertRaisesRegex(ValueError,'complete layout'):
                magic_script('magic','pdk.tech','layout.gds','coupon',[],out,'drc check')
            self.assertEqual((out/'console.log').read_text(),LOST_MASK)

    def test_conversion_keeps_failure_log_even_if_native_cell_was_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            def execute(*args,**kwargs):
                (out/'coupon.mag').write_text('partial native cell')
                return LOST_MASK
            with patch('icstudio.engines.execute',side_effect=execute), \
                    self.assertRaisesRegex(ValueError,'complete layout'):
                magic_convert('magic','layout.gds','pdk.tech',out,'coupon')
            self.assertEqual((out/'conversion.log').read_text(),LOST_MASK)

    def test_unmapped_text_and_malformed_cells_are_not_silently_accepted(self):
        for log in ('Unknown layer/datatype in text, layer=34 type=11',
                    'Error while reading cell "coupon": malformed boundary'):
            with self.subTest(log=log),self.assertRaises(ValueError):
                require_readable_stream(log,'retained.log')

    def test_unrelated_informational_warnings_remain_visible_and_nonfatal(self):
        require_readable_stream('WARNING: RLIMIT_NOFILE is above 1024\n'
                                'Warning: Calma reading is not undoable!\n','retained.log')

    def test_repeated_fixed_boundary_does_not_hide_other_reader_errors(self):
        warning=('Error while reading cell "adc_vcm_generator" (byte position 38763380): '
                 'Warning:  Cell adc_vcm_generator boundary was redefined.')
        require_readable_stream((warning+'\n')*8+'STUDIO_DRC_COUNT 0\n','retained.log')
        for log in (warning+'\n'+LOST_MASK, LOST_MASK+warning,
                    warning+' Unknown layer/datatype in boundary',
                    warning.replace('Cell adc_vcm_generator','Cell other'),
                    warning.replace('was redefined','could not be read')):
            with self.subTest(log=log),self.assertRaises(ValueError):
                require_readable_stream(log,'retained.log')


if __name__=='__main__':unittest.main()
