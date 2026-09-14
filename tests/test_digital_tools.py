"""Regression checks for explicit backend choice and incomplete installations."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from icstudio import digital, digital_flow, digital_runtime, digital_tools


class DigitalToolSelectionTests(unittest.TestCase):
    def test_old_paths_do_not_disable_included_tools(self):
        values={'engine/yosys':'/old/yosys', 'digital/orfs':'/old/orfs'}
        settings=Mock(); settings.value.side_effect=lambda key,default='':values.get(key,default)
        self.assertEqual(digital_tools.selection(settings), {'toolchain':'included','tools':{},'orfs':''})
        values['digital/toolchain']='custom'
        selection=digital_tools.selection(settings)
        self.assertEqual(selection['tools']['yosys'],'/old/yosys')
        self.assertEqual(selection['orfs'],'/old/orfs')
        values['digital/toolchain']='included'
        self.assertEqual(digital_tools.selection(settings)['tools'],{})
        self.assertEqual(values['engine/yosys'],'/old/yosys')

    def test_included_dispatch_ignores_saved_executable_overrides(self):
        runtime={'kind':'linux','root':'/included','sha256':'fixture'}
        with patch.object(digital_runtime,'installed',return_value=runtime), \
             patch.object(digital_flow,'environment',return_value={}), \
             patch.object(digital_flow.shutil,'which',side_effect=AssertionError('Must not search PATH')):
            job=digital_flow.prepare(digital.counter_project(), tools={'iverilog':'/old/iverilog'},toolchain='included')
        self.assertEqual(job['settings']['runtime'],runtime)
        self.assertEqual(job['settings']['tools']['iverilog'],'opt/icstudio/bin/iverilog')

    def test_custom_mode_with_empty_paths_never_uses_included_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            executable=Path(td)/'yosys'; executable.write_text('fixture')
            with patch.object(digital_runtime,'installed',side_effect=AssertionError('Must remain custom')), \
                 patch.object(digital_flow.shutil,'which',return_value=str(executable)):
                job=digital_flow.prepare(digital.counter_project(),'synth',toolchain='custom')
            self.assertNotIn('runtime',job['settings'])

    def test_missing_included_payload_does_not_fall_back_to_host_tools(self):
        with patch.object(digital_runtime,'installed',return_value=None), \
             patch.object(digital_runtime,'status',return_value={'state':'unavailable','message':'Get the desktop package.'}), \
             patch.object(digital_flow.shutil,'which',side_effect=AssertionError('Must not search PATH')):
            with self.assertRaisesRegex(ValueError,'desktop package'):
                digital_flow.prepare(digital.counter_project(),toolchain='included')

    def test_missing_frozen_payload_is_a_broken_installation(self):
        with patch.object(digital_runtime,'manifest',return_value=None), \
             patch.object(digital_runtime.sys,'frozen',True,create=True):
            info=digital_runtime.status()
            self.assertEqual(info['state'],'error')
            self.assertEqual(info['reason'],'package_missing')
            self.assertNotIn('source checkout',info['message'])
            with patch.object(digital_flow.shutil,'which',side_effect=AssertionError('Must not search PATH')):
                with self.assertRaisesRegex(ValueError,'complete desktop package'):
                    digital_flow.prepare(digital.counter_project())

    def test_invalid_manifest_is_reported_without_crashing(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{'ICSTUDIO_DIGITAL_PAYLOAD':td}):
            for data in ('[]','{"schema":1,"system":"ubuntu-24.04-x86_64","archive":"runtime.tar.gz","sha256":42}'):
                (Path(td)/'manifest.json').write_text(data)
                self.assertEqual(digital_runtime.status()['state'],'error')


if __name__=='__main__': unittest.main()
