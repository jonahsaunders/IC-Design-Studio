"""Extraction orchestration fixtures; these do not qualify an external engine."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from icstudio.external_tools import extraction_commands
from icstudio.hierarchical_flow import run as physical_run, verify_integrity
from icstudio.model import clone, device, example, file_digest, uid, validate
from icstudio.silicon_flow import magic_script
from icstudio.testbenches import create as create_bench
from tests.test_magic_rc import ORIGINAL, RESISTANCE


EXTRACTED = '''.subckt top IN VSS
R1 IN IN.t0 20
R2 N.n0 N.t0 10
C1 IN VSS 50e-18
C2 IN.t0 VSS 150e-18
C3 N.n0 VSS 90e-18
C4 N.t0 VSS 30e-18
C5 IN N.n0 15e-18
C6 IN N.t0 5e-18
C7 IN.t0 N.n0 45e-18
C8 IN.t0 N.t0 15e-18
.ends top
'''


class MagicRCFlowTests(unittest.TestCase):
    def test_conserved_rc_rejects_a_capacitance_threshold_it_cannot_honor(self):
        for threshold in (1, 'infinite'):
            with self.subTest(threshold=threshold), self.assertRaisesRegex(ValueError, 'zero capacitance threshold'):
                extraction_commands('rc', {'capacitance_threshold': threshold})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def raw(self, directory, original=ORIGINAL):
        (directory / 'top.ext').write_text(original)
        (directory / 'top.res.ext').write_text(RESISTANCE)

    def script(self, profile='rc', directory=None):
        commands, _ = extraction_commands(profile)
        return magic_script(sys.executable, self.root / 'test.tech', self.root / 'layout.gds',
                            'top', ['IN', 'VSS'], directory or self.root / 'extraction',
                            commands + 'ext2spice -o extracted.spice')

    def test_rc_normalizes_between_fresh_processes_and_replays_export_settings(self):
        scripts = []
        def execute(command, cwd, **kwargs):
            scripts.append(kwargs['input_text'])
            self.assertEqual(command[1:3], ['-dnull', '-noconsole'])
            if len(scripts) == 1:
                self.assertIn('extresist all', scripts[-1])
                self.assertNotIn('ext2spice -o', scripts[-1])
                self.assertFalse((cwd / 'rc-normalization.json').exists())
                self.raw(cwd)
            else:
                self.assertNotIn('extract all', scripts[-1])
                self.assertNotIn('extresist all', scripts[-1])
                self.assertIn('ext2spice extresist on', scripts[-1])
                report = json.loads((cwd / 'rc-normalization.json').read_text())
                self.assertEqual(report['conservation']['status'], 'passed')
                for name, checksum in report['files'].items():
                    self.assertEqual(file_digest(cwd / name), checksum)
                self.assertNotEqual((cwd / 'top.res.ext').read_text(), RESISTANCE)
                (cwd / 'extracted.spice').write_text(EXTRACTED)
            return 'STUDIO_MAGIC_COMPLETE\n'
        with patch('icstudio.silicon_flow.execute', side_effect=execute):
            self.script()
        self.assertEqual(len(scripts), 2)
        for command in ('ext2spice lvs', 'ext2spice hierarchy on', 'ext2spice rthresh 0',
                        'ext2spice cthresh 0.0', 'ext2spice renumber off', 'ext2spice scale off'):
            self.assertIn(command, scripts[0]); self.assertIn(command, scripts[1])
        output = self.root / 'extraction'
        for name in ('resistance-run.tcl', 'resistance-console.log', 'run.tcl', 'console.log',
                     'top.raw.ext', 'top.raw.res.ext', 'rc-normalization.json', 'raw-export.spice', 'extracted.spice'):
            self.assertTrue((output / name).is_file(), name)
        report = json.loads((output / 'rc-normalization.json').read_text())
        self.assertEqual(report['export']['status'], 'passed')
        self.assertEqual((output / 'raw-export.spice').read_text(), EXTRACTED)
        for name, checksum in report['files'].items():
            self.assertEqual(file_digest(output / name), checksum)

    def test_raw_extraction_failure_stops_before_normalization_and_export(self):
        for log in ('STUDIO_MAGIC_ERROR raw extraction failed\n',
                    'exttospice: integer value expected\nSTUDIO_MAGIC_COMPLETE\n'):
            with self.subTest(log=log):
                out = self.root / str(len(list(self.root.iterdir())))
                with patch('icstudio.silicon_flow.execute', return_value=log) as execute, \
                     patch('icstudio.magic_rc.normalize') as normalize, \
                     self.assertRaisesRegex(ValueError, 'Magic could not complete'):
                    self.script(directory=out)
                self.assertEqual(execute.call_count, 1); normalize.assert_not_called()
                self.assertFalse((out / 'extracted.spice').exists())
                self.assertEqual((out / 'resistance-console.log').read_text(), log)

    def test_unsupported_normalization_stops_before_export_and_preserves_raw_input(self):
        original = ORIGINAL + 'use child instance 0 0 0 0\n'
        def execute(command, cwd, **kwargs):
            self.raw(cwd, original)
            return 'STUDIO_MAGIC_COMPLETE\n'
        with patch('icstudio.silicon_flow.execute', side_effect=execute) as engine, \
             self.assertRaisesRegex(ValueError, 'Only flat unaliased'):
            self.script()
        self.assertEqual(engine.call_count, 1)
        out = self.root / 'extraction'
        self.assertEqual((out / 'top.ext').read_text(), original)
        self.assertEqual((out / 'top.res.ext').read_text(), RESISTANCE)
        self.assertFalse((out / 'extracted.spice').exists())
        self.assertFalse((out / 'rc-normalization.json').exists())

    def test_export_error_is_not_accepted_even_after_successful_normalization(self):
        calls = []
        def execute(command, cwd, **kwargs):
            calls.append(kwargs['input_text'])
            if len(calls) == 1:
                self.raw(cwd)
                return 'STUDIO_MAGIC_COMPLETE\n'
            return 'exttospice: numeric value expected\nSTUDIO_MAGIC_COMPLETE\n'
        with patch('icstudio.silicon_flow.execute', side_effect=execute), \
             patch('icstudio.magic_rc.finalize') as finalize, \
             self.assertRaisesRegex(ValueError, 'Magic could not complete'):
            self.script()
        finalize.assert_not_called()
        self.assertEqual(len(calls), 2)
        self.assertTrue((self.root / 'extraction/rc-normalization.json').is_file())
        self.assertFalse((self.root / 'extraction/extracted.spice').exists())

    def test_changed_export_topology_fails_finalization_after_both_engine_phases(self):
        calls = []
        def execute(command, cwd, **kwargs):
            calls.append(kwargs['input_text'])
            if len(calls) == 1:self.raw(cwd)
            else:(cwd / 'extracted.spice').write_text(EXTRACTED.replace('R2 N.n0 N.t0 10\n', ''))
            return 'STUDIO_MAGIC_COMPLETE\n'
        with patch('icstudio.silicon_flow.execute', side_effect=execute), \
             self.assertRaisesRegex(ValueError, 'resistance graph'):
            self.script()
        self.assertEqual(len(calls), 2)
        output = self.root / 'extraction'
        self.assertNotIn('export', json.loads((output / 'rc-normalization.json').read_text()))
        self.assertFalse((output / 'raw-export.spice').exists())

    def test_lvs_and_capacitance_profiles_keep_single_process_and_no_normalization(self):
        for profile in ('lvs', 'capacitance'):
            with self.subTest(profile=profile), \
                 patch('icstudio.silicon_flow.execute', return_value='STUDIO_MAGIC_COMPLETE\n') as execute, \
                 patch('icstudio.magic_rc.normalize') as normalize:
                self.script(profile, self.root / profile)
            self.assertEqual(execute.call_count, 1); normalize.assert_not_called()
            script = execute.call_args.kwargs['input_text']
            self.assertIn('extract all', script)
            self.assertIn('ext2spice extresist off', script)
            self.assertIn('ext2spice -o extracted.spice', script)
            self.assertNotIn('extresist all', script)

    def design(self):
        p = example('empty'); c = p['cells'][0]
        c.update(name='top', ports=['IN', 'VSS'], devices=[device('R', 'RDUT', value='1k', nets={'p': 'IN', 'n': 'VSS'})])
        bench = dict(id=uid(), name='fixture', ports=[], shapes=[], devices=[
            device('V', 'VIN', value='1', nets={'p': 'input', 'n': '0'}),
            device('X', 'XDUT', cell=c['id'], nets={'IN': 'input', 'VSS': '0'})])
        p['cells'].append(bench); p['top'] = bench['id']; p['analysis']['type'] = 'op'
        t = create_bench(p, bench['id']); t['physical_extraction'] = {'mode': 'rc'}
        p['testbenches'] = [t]
        p['pdk']['interoperability'] = {'tools': {'magic': {'drc_style': 'fixture'}}}
        return validate(p), t

    def physical(self, output, mutate=None):
        p, bench = self.design()
        tech = self.root / 'test.tech'; tech.write_text('Test fixture only\n')
        setup = self.root / 'setup.tcl'; setup.write_text('# Test fixture only\n')
        process = SimpleNamespace(id='fixture', engine_assets=lambda _: {'technology': tech, 'setup': setup})
        def execute(command, cwd, **kwargs):
            script = kwargs['input_text']
            if 'STUDIO_DRC_COUNT' in script:
                return 'STUDIO_DRC_COUNT 0\nSTUDIO_DRC_STYLE fixture\nSTUDIO_MAGIC_COMPLETE\n'
            if 'extresist all' in script:
                self.raw(cwd)
            elif 'ext2spice extresist on' in script:
                (cwd / 'extracted.spice').write_text(EXTRACTED)
            else:
                (cwd / 'extracted.spice').write_text('.subckt top IN VSS\nR1 IN VSS 1000\n.ends top\n')
            return 'STUDIO_MAGIC_COMPLETE\n'
        def simulate(project, testbench, executable, directory, source, interface):
            directory.mkdir(parents=True)
            result = {'settings': clone(testbench['analysis']), 'measurements': {'status': 'passed', 'measurements': []}}
            (directory / 'result.json').write_text(json.dumps(result))
            if directory.name == 'post-layout' and mutate:
                with (directory.parent / 'parasitics' / mutate).open('a') as stream:
                    stream.write('\nchanged after numerical result\n')
            return result
        with patch('icstudio.process_adapters.physical_adapter', return_value=process), \
             patch('icstudio.hierarchical_flow.audit', return_value=[]), \
             patch('icstudio.physical.connectivity', return_value={'issues': []}), \
             patch('icstudio.interchange.export_layout', side_effect=lambda _, path: path.write_bytes(b'layout fixture')), \
             patch('icstudio.hierarchical_flow.execute', return_value='Engine fixture version'), \
             patch('icstudio.silicon_flow.execute', side_effect=execute), \
             patch('icstudio.hierarchical_flow.simulate', side_effect=simulate), \
             patch('icstudio.hierarchical_flow.netgen_lvs', return_value='Cell pin lists are equivalent.\nCircuits match uniquely.\n'):
            return physical_run(p, bench['id'], output, dict.fromkeys(('magic', 'netgen', 'ngspice'), sys.executable))

    def test_saved_bench_integrity_binds_original_normalized_and_exported_files(self):
        output = self.root / 'physical'
        report = self.physical(output)
        self.assertEqual(report['status'], 'passed', report.get('error'))
        integrity = next(row for row in report['stages'] if row['name'] == 'integrity')['evidence']
        for name in ('top.raw.ext', 'top.raw.res.ext', 'top.ext', 'top.res.ext',
                     'rc-normalization.json', 'raw-export.spice', 'extracted.spice', 'profile.json'):
            relative = 'parasitics/' + name
            self.assertEqual(integrity['files'][relative], file_digest(output / relative))
        profile = json.loads((output / 'parasitics/profile.json').read_text())
        self.assertEqual(profile['capacitance_normalization']['conservation']['status'], 'passed')
        self.assertEqual(profile['capacitance_normalization']['export']['status'], 'passed')
        for name in ('top.raw.ext', 'top.raw.res.ext', 'top.ext', 'top.res.ext', 'rc-normalization.json', 'raw-export.spice'):
            path = output / 'parasitics' / name; original = path.read_bytes()
            path.write_bytes(original + b'\nchanged\n')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'evidence changed'):
                verify_integrity(output, integrity['files'], integrity['assets'], integrity['tools'])
            path.write_bytes(original)

    def test_post_layout_mutation_of_raw_or_normalized_evidence_fails_final_stage(self):
        for name in ('top.raw.ext', 'top.res.ext', 'rc-normalization.json'):
            with self.subTest(name=name):
                report = self.physical(self.root / ('mutated-' + name), mutate=name)
                stages = {row['name']: row for row in report['stages']}
                self.assertEqual(stages['post_layout_simulation']['status'], 'passed', report.get('error'))
                self.assertEqual(stages['integrity']['status'], 'failed')
                self.assertEqual(report['status'], 'failed')
                self.assertIn('evidence changed', stages['integrity']['error'])


if __name__ == '__main__':
    unittest.main()
