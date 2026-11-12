"""A zero-exit reader must not hide a discarded physical mask."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from icstudio.magic_diagnostics import require_readable_stream
from icstudio.silicon_flow import magic_script
from icstudio.engines import magic_convert,magic_import

LOST_MASK = ('Error while reading cell "coupon" (byte position 694): '
             'Unknown layer/datatype in boundary, layer=210 type=0\n'
             'Total of 1 warning.\nSTUDIO_DRC_COUNT 0\nSTUDIO_MAGIC_COMPLETE\n')
BROKEN_RULE = ('/pdk/ihp-sg13g2-drc.tech: line 295: section drc:\n'
               '\tUnrecognized layer (type) name "missing_contact"\n'
               'STUDIO_DRC_COUNT 0\nSTUDIO_MAGIC_COMPLETE\n')


class MagicInputDiagnosticsTests(unittest.TestCase):
    def test_zero_count_and_completion_do_not_override_an_invalid_native_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with patch('icstudio.silicon_flow.execute',return_value=BROKEN_RULE), \
                    self.assertRaisesRegex(ValueError,'complete technology rules'):
                magic_script('magic','pdk.tech','layout.gds','coupon',[],out,'drc check')
            self.assertEqual((out/'console.log').read_text(),BROKEN_RULE)

    def test_conversion_rejects_invalid_technology_even_if_it_writes_a_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            def execute(*args,**kwargs):
                (out/'coupon.mag').write_text('cell from incomplete technology')
                return BROKEN_RULE
            with patch('icstudio.engines.execute',side_effect=execute), \
                    self.assertRaisesRegex(ValueError,'complete technology rules'):
                magic_convert('magic','layout.gds','pdk.tech',out,'coupon')
            self.assertEqual((out/'conversion.log').read_text(),BROKEN_RULE)

    def test_technology_diagnostics_cover_missing_sections_includes_and_truncation(self):
        for path,section,body in (
                ('C:/a path/pdk.tech','cifinput','Must define layer before specifying operations.'),
                ('/pdk/entry','(none)','Unrecognized section name: broken'),
                ('/pdk/input.tech','cifinput',"Warning: Couldn't find include file required.tech"),
                ('/pdk/output.tech','cifoutput','long line truncated')):
            with self.subTest(body=body),self.assertRaisesRegex(ValueError,'complete technology rules'):
                require_readable_stream(f'{path}: line 13: section {section}:\r\n\t{body}\r\n'
                                        'STUDIO_MAGIC_COMPLETE\r\n','retained.log')

    def test_native_cell_import_rejects_a_broken_technology_before_stream_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'coupon.mag';source.write_text('magic\ntech sample\n<< end >>\n')
            tech=root/'pdk.tech';tech.write_text('invalid technology')
            out=root/'converted';log=BROKEN_RULE+'STUDIO_IMPORT_COMPLETE\n'
            def execute(*args,**kwargs):
                (out/'magic-raw.gds').write_bytes(b'partial stream')
                return log
            with patch('icstudio.engines.execute',side_effect=execute), \
                    self.assertRaisesRegex(ValueError,'complete technology rules'):
                magic_import('magic',source,tech,out)
            self.assertEqual((out/'conversion.log').read_text(),log)
            self.assertFalse((out/'imported.gds').exists())

    def test_workspace_export_does_not_offer_a_review_after_a_native_rule_error(self):
        from icstudio.external_tools import magic_workspace_export
        from icstudio.model import file_digest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);workspace=root/'workspace';workspace.mkdir()
            (workspace/'native').mkdir();(workspace/'native/coupon.mag').write_text('native cell')
            (workspace/'technology').mkdir();tech=workspace/'technology/pdk.tech';tech.write_text('bad rules')
            report=dict(version=1,status='complete',top='coupon',technology_file='technology/pdk.tech',
                        files={'technology/pdk.tech':file_digest(tech)})
            (workspace/'workspace.json').write_text(json.dumps(report));out=root/'export'
            def execute(*args,**kwargs):
                (out/'edited.gds').write_bytes(b'partial stream')
                return BROKEN_RULE
            with patch('icstudio.external_tools.execute',side_effect=execute), \
                    patch('icstudio.external_tools.executable_info',return_value={'path':'magic'}), \
                    self.assertRaisesRegex(ValueError,'complete technology rules'):
                magic_workspace_export(workspace,out)
            self.assertEqual((out/'engine.log').read_text(),BROKEN_RULE)
            self.assertFalse((out/'review-source.json').exists())

    def test_runtime_probe_rejects_an_invalid_deck_even_with_a_legal_count(self):
        from icstudio.physical_runtime_probe import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);log=BROKEN_RULE+'PROBE_DRC 0\n'
            job={'project':{'pdk':{'package_root':str(root)}},'settings':{'tools':{'magic':'magic'}}}
            with patch('icstudio.engines.execute',return_value=log), \
                    self.assertRaisesRegex(ValueError,'complete technology rules'):
                run(job,root,lambda *_:None)
            self.assertEqual((root/'physical-flow/legal.log').read_text(),log)
            self.assertFalse((root/'physical-flow/report.json').exists())

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
