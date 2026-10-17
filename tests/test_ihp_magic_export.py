import tempfile
from pathlib import Path
import unittest
from scripts.ihp_magic_export import export,export_script,tcl_word


class NativeLayoutGridExportTests(unittest.TestCase):
    def test_native_path_is_literal_and_rejects_brace_or_multiline_injection(self):
        self.assertEqual(tcl_word('C:\\a $b [c]\\d'),'{'+'C:/a $b [c]/d'+'}')
        for value in ('a} ; error BAD','a\nb','a\x00b'):
            with self.subTest(value=value),self.assertRaises(ValueError):tcl_word(value)

    def test_top_identifier_cannot_inject_native_commands(self):
        for name in ('a; quit','../a','a\nb','a [exec bad]',''):
            with self.subTest(name=name),self.assertRaises(ValueError):export_script(name)

    def test_existing_evidence_is_preserved_before_inputs_are_read(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'existing';out.mkdir();marker=out/'marker';marker.write_text('retain')
            with self.assertRaisesRegex(ValueError,'new native export'):
                export('missing','top','missing','missing',out)
            self.assertEqual(marker.read_text(),'retain')


if __name__=='__main__':unittest.main()
