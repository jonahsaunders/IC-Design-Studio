"""Detect partial or invalid output even when an external process exits zero."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from icstudio.external_tools import xschem_netlist


class XschemOutputTests(unittest.TestCase):
    def test_empty_or_unresolved_netlists_are_failed_runs(self):
        for content,reason in (('', 'empty'),('**.subckt top\n?\n.end\n','unresolved Tcl')):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);source=root/'source';source.mkdir()
                schematic=source/'top.sch';schematic.write_text('v {xschem version=3.4.4 file_version=1.2}\n')
                output=root/'run'
                def execute(command,cwd,timeout,env):
                    # Windows TEMP may use an 8.3 alias; the wrapper resolves it.
                    self.assertEqual(env['TMPDIR'],str((output/'tmp').resolve()))
                    self.assertTrue(Path(env['TMPDIR']).is_dir())
                    (output/'netlists/top.spice').write_text(content)
                    return 'engine console output\n'
                with patch('icstudio.external_tools.execute',side_effect=execute),self.assertRaisesRegex(ValueError,reason):
                    xschem_netlist(schematic,output,sys.executable)
                report=json.loads((output/'report.json').read_text())
                self.assertEqual(report['status'],'failed')
                self.assertEqual(report['environment']['TMPDIR'],str((output/'tmp').resolve()))
                self.assertEqual((output/'engine.log').read_text(),'engine console output\n')

    def test_tcl_failure_includes_diagnostic_and_retains_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir()
            schematic=source/'top.sch';schematic.write_text('v {xschem version=3.4.4 file_version=1.2}\n')
            log='tcleval(): evaluation of script: netlist failed\n : could not run postprocessor\n'
            with patch('icstudio.external_tools.execute',return_value=log),self.assertRaisesRegex(ValueError,'netlist failed'):
                xschem_netlist(schematic,root/'run',sys.executable)
            self.assertEqual((root/'run/engine.log').read_text(),log)
            self.assertEqual(json.loads((root/'run/report.json').read_text())['status'],'failed')


if __name__=='__main__':unittest.main()
