"""Development cache protocol and independent LI raw-semantic controls."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import audit_sky130_li_case as independent
from scripts import sky130_li_resume as resume


class SelectionTests(unittest.TestCase):
    def test_complete_unit_only(self):
        self.assertEqual(resume.selection(['l1-w2-l5']), ['l1-w2-l5'])
        for selection in (None, [], [''], ['l1-w2-l5', 'l1-w2-l5'], ['physical-0'], ['m1-w2-l5']):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                resume.selection(selection)

    def test_exhaustive_rejects_reuse_before_output_or_native_tools(self):
        from scripts import qualify_sky130_metal_resistor_layouts as runner
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'must-not-exist'
            arguments = ['runner', '--sky130', temporary, '--output', str(out), '--magic', 'missing', '--netgen', 'missing']
            for addition in (['--resume-from', temporary], ['--select', resume.CASE]):
                with patch('sys.argv', arguments + addition), self.assertRaises(SystemExit):
                    runner.main()
                self.assertFalse(out.exists())

    def test_unknown_development_selection_rejects_before_output(self):
        from scripts import qualify_sky130_metal_resistor_layouts as runner
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'must-not-exist'
            arguments = ['runner', '--sky130', temporary, '--output', str(out), '--magic', 'missing', '--netgen', 'missing',
                         '--development', '--select', 'unknown']
            with patch('sys.argv', arguments), self.assertRaises(ValueError):
                runner.main()
            self.assertFalse(out.exists())


class IdentityTests(unittest.TestCase):
    def test_conservative_sources_detect_helpers_and_fixtures_but_not_documentation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('icstudio', 'scripts', 'tests', 'examples', 'docs'):
                (root / name).mkdir()
            helper = root / 'scripts/helper.py'
            helper.write_text('threshold = 1\n')
            lock = root / 'examples/lock.json'
            lock.write_text('{}')
            before = resume.sources(root)
            (root / 'docs/notes.md').write_text('Unrelated prose.')
            self.assertEqual(before, resume.sources(root))
            helper.write_text('threshold = 2\n')
            self.assertNotEqual(before, resume.sources(root))
            helper.write_text('threshold = 1\n')
            lock.write_text('{"revision":2}')
            self.assertNotEqual(before, resume.sources(root))
            (root / 'tests/new_test.py').write_text('pass\n')
            self.assertIn('tests/new_test.py', resume.sources(root))

    def test_every_reuse_dimension_changes_key(self):
        original = {'sources': {'helper.py': 'a'}, 'contract': copy.deepcopy(resume.CONTRACT),
                    'runtime': {'tool': 'a', 'loaded_library': 'a', 'environment': {'LANG': 'C'}},
                    'pdk': {'asset': 'a'}}
        mutations = [lambda v: v['sources'].update({'helper.py': 'b'}),
                     lambda v: v['contract'].update({'dimension_tolerance_um': .1}),
                     lambda v: v['contract'].update({'width_um': 3}),
                     lambda v: v['runtime'].update({'tool': 'b'}),
                     lambda v: v['runtime'].update({'loaded_library': 'b'}),
                     lambda v: v['runtime']['environment'].update({'LANG': 'en_US'}),
                     lambda v: v['pdk'].update({'asset': 'b'})]
        for mutate in mutations:
            changed = copy.deepcopy(original)
            mutate(changed)
            self.assertNotEqual(resume.key(original), resume.key(changed))

    def test_unsupported_platform_and_launcher_fail_closed(self):
        with patch.object(resume.sys, 'platform', 'win32'), self.assertRaisesRegex(ValueError, 'Linux'):
            resume.runtime({'magic': 'magic', 'netgen': 'netgen'})
        with patch.object(resume.sys, 'platform', 'linux'), patch.object(resume.platform, 'machine', return_value='x86_64'), self.assertRaisesRegex(ValueError, 'launcher paths'):
            resume.runtime({'magic': '/tmp/magic', 'netgen': '/tmp/netgen'})

    def test_project_bytecode_cannot_stand_in_for_recorded_source(self):
        with patch.object(resume.sys, 'platform', 'linux'), patch.object(resume.platform, 'machine', return_value='x86_64'), \
             patch.object(resume.sys, 'version_info', (3, 12)), patch.object(resume.sys, 'dont_write_bytecode', True), \
             patch.object(resume.sys, 'flags', SimpleNamespace(hash_randomization=0, no_user_site=1)), \
             patch.object(resume.sys, 'pycache_prefix', None), self.assertRaisesRegex(ValueError, 'stale project bytecode'):
            resume.runtime({'magic': '/opt/icstudio/bin/magic', 'netgen': '/opt/icstudio/bin/netgen'})


class ReceiptTests(unittest.TestCase):
    """Protocol-only fixtures; native semantic audit is separately tested below."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / resume.CASE).mkdir()
        (self.root / resume.CASE / 'native.txt').write_text('Original native output.')
        self.identity = {'suite': resume.SUITE, 'source': 'original', 'contract': resume.CONTRACT}
        resume.write(self.root / 'inputs.json', self.identity)
        self.execution = {'run_id': 'original-run-id', 'case_id': resume.CASE,
                          'output': str(self.root), 'case_path': str(self.root / resume.CASE),
                          'source_commit': 'a' * 40, 'source_hashes': {'original.py': 'original'},
                          'started': '2026-10-23T00:00:00Z', 'finished': '2026-10-23T00:00:01Z',
                          'native_elapsed_seconds': 1}
        self.mock = patch.object(resume, 'audit', return_value={'status': 'PASS'})
        self.mock.start()
        self.addCleanup(self.mock.stop)
        resume.receipt(self.root / resume.CASE, self.identity, self.execution)
        resume.write(self.root / 'qualification.json', {'mode': 'development', 'status': 'PASS', 'selected': [resume.CASE],
                     'execution': self.execution, 'input_key': resume.key(self.identity)})

    def test_hit_preserves_original_execution_identity(self):
        hit = resume.lookup(self.root, self.identity)
        self.assertTrue(hit['hit'])
        self.assertEqual(hit['execution'], self.execution)
        self.assertEqual(hit['execution']['source_commit'], 'a' * 40)

    def test_json_normalization_does_not_create_false_identity_miss(self):
        # Runtime APIs return tuples; JSON correctly represents them as arrays.
        self.identity['libc'] = ('glibc', '2.39')
        resume.write(self.root / 'inputs.json', self.identity)
        resume.receipt(self.root / resume.CASE, self.identity, self.execution)
        report = json.loads((self.root / 'qualification.json').read_bytes())
        report['input_key'] = resume.key(self.identity)
        resume.write(self.root / 'qualification.json', report)
        self.assertTrue(resume.lookup(self.root, self.identity)['hit'])

    def test_changed_input_misses(self):
        changed = copy.deepcopy(self.identity)
        changed['source'] = 'new'
        self.assertFalse(resume.lookup(self.root, changed)['hit'])

    def test_missing_corrupt_and_added_outputs_miss(self):
        path = self.root / resume.CASE / 'native.txt'
        path.write_text('Corrupt native output.')
        self.assertFalse(resume.lookup(self.root, self.identity)['hit'])
        path.unlink()
        self.assertFalse(resume.lookup(self.root, self.identity)['hit'])
        path.write_text('Original native output.')
        (self.root / resume.CASE / 'unexpected.txt').write_text('Late output.')
        self.assertFalse(resume.lookup(self.root, self.identity)['hit'])

    def test_interrupted_publication_or_failed_run_cannot_hit(self):
        for status in ('RUNNING', 'FAIL'):
            report = json.loads((self.root / 'qualification.json').read_bytes())
            report['status'] = status
            resume.write(self.root / 'qualification.json', report)
            self.assertFalse(resume.lookup(self.root, self.identity)['hit'])
        (self.root / 'receipt.json').unlink()
        self.assertFalse(resume.lookup(self.root, self.identity)['hit'])

    def test_rehashed_semantic_corruption_still_misses(self):
        path = self.root / resume.CASE / 'native.txt'
        path.write_text('Wrong model, but rehashed.')
        resume.write(self.root / 'case-manifest.json', resume.tree(self.root / resume.CASE, evidence=True))
        value = json.loads((self.root / 'receipt.json').read_bytes())
        value['manifest_sha256'] = resume.digest(self.root / 'case-manifest.json')
        resume.write(self.root / 'receipt.json', value)
        with patch.object(resume, 'audit', side_effect=ValueError('Wrong actual extracted model.')):
            miss = resume.lookup(self.root, self.identity)
        self.assertFalse(miss['hit'])
        self.assertIn('extracted model', miss['reason'])

    def test_original_execution_cannot_be_relabelled(self):
        value = json.loads((self.root / 'receipt.json').read_bytes())
        value['execution']['source_commit'] = 'b' * 40
        resume.write(self.root / 'receipt.json', value)
        self.assertFalse(resume.lookup(self.root, self.identity)['hit'])


class IndependentSemanticTests(unittest.TestCase):
    def test_generator_source_substitution_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            pdk = Path('/reviewed/pdk')
            text = independent.generator_script(pdk)
            (folder / 'empty.magicrc').write_bytes(b'')
            (folder / 'generate.tcl').write_text(text, encoding='utf-8')
            independent.check_generator(folder, pdk)
            (folder / 'generate.tcl').write_text(text.replace('sky130A.tcl}', 'unbound-generator.tcl}'), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'generator source'):
                independent.check_generator(folder, pdk)

    def test_native_technology_and_execution_setting_mutations_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            pdk = Path('/reviewed/pdk')
            origin = Path('/retained/run/physical-0')
            for stage in ('drc', 'lvs-extraction'):
                (folder / stage).mkdir()
                (folder / stage / 'run.tcl').write_text(independent.native_script(origin, stage), encoding='utf-8')
                (folder / stage / 'startup.tcl').write_text('tech load ' + independent.tcl_literal(pdk / 'libs.tech/magic/sky130A.tech') + '\ndrc euclidean on\n', encoding='utf-8')
            independent.check_native_scripts(folder, origin, pdk)
            for relative, old, new in [('drc/startup.tcl', 'sky130A.tech', 'wrong.tech'),
                                       ('drc/run.tcl', 'drc ignore none', 'drc ignore all'),
                                       ('lvs-extraction/run.tcl', 'blackbox off', 'blackbox on'),
                                       ('lvs-extraction/run.tcl', 'scale off', 'scale on'),
                                       ('lvs-extraction/run.tcl', 'merge none', 'merge aggressive')]:
                path = folder / relative
                original = path.read_text(encoding='utf-8')
                path.write_text(original.replace(old, new), encoding='utf-8')
                with self.subTest(relative=relative, mutation=new), self.assertRaises(ValueError):
                    independent.check_native_scripts(folder, origin, pdk)
                path.write_text(original, encoding='utf-8')

    def test_netgen_setup_or_input_redirection_rejected(self):
        pdk, origin = Path('/reviewed/pdk'), Path('/retained/run/physical-0')
        text = ('Reading netlist file ' + str(origin / 'schematic-lvs.spice') + '\nReading netlist file ' +
                str(origin / 'lvs-extraction/extracted.spice') + '\nReading setup file ' +
                str(pdk / 'libs.tech/netgen/sky130A_setup.tcl') + '\nComparison output logged to file ' +
                str(origin / 'lvs/lvs.log') + '\nLVS Done.\n')
        independent.check_netgen_inputs(text, origin, pdk)
        for old, new in [('sky130A_setup.tcl', 'wrong_setup.tcl'), ('extracted.spice', 'substitute.spice'),
                         ('schematic-lvs.spice', 'substitute.spice'), ('lvs.log', 'unbound.log')]:
            with self.subTest(mutation=new), self.assertRaises(ValueError):
                independent.check_netgen_inputs(text.replace(old, new), origin, pdk)

    def test_actual_spice_interface_model_dimensions_and_extra_devices(self):
        good = '.subckt coupon R1 R2\nR0 R2 R1 sky130_fd_pr__res_generic_l1 w=2 l=5\n.ends\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'extracted.spice'
            path.write_text(good)
            independent.spice(path)
            for changed in (good.replace('w=2', 'w=2.1'), good.replace('l=5', 'l=nan'),
                            good.replace('res_generic_l1', 'res_generic_m1'), good.replace('R0 R2 R1', 'R0 R2 floating'),
                            good.replace('.ends', 'R2 R1 R2 100\n.ends'), good.replace('coupon R1 R2', 'coupon R2 R1')):
                path.write_text(changed)
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    independent.spice(path)

    def test_short_and_open_need_actual_extracted_fault(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'extracted.spice'
            path.write_text('.subckt coupon R1 R2\nR0 R2 R1 sky130_fd_pr__res_generic_l1 w=2 l=5\n.ends\n')
            for fault in ('terminal-open', 'terminal-short'):
                with self.assertRaises(ValueError):
                    independent.spice(path, fault=fault)

    def test_literal_geometry_and_ports_reject_semantic_corruption(self):
        import klayout.db as db
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'layout.gds'
            target = independent.expected()
            def save(width=2000, terminal='R1'):
                layout = db.Layout()
                layout.dbu = .001
                cell = layout.create_cell('coupon')
                cell.shapes(layout.layer(67, 20)).insert(db.Box(-1000, -2785, 1000, 2785))
                cell.shapes(layout.layer(67, 13)).insert(db.Box(-1000, -2500, -1000 + width, 2500))
                cell.shapes(layout.layer(67, 5)).insert(db.Text(terminal, db.Trans(0, -2643)))
                cell.shapes(layout.layer(67, 5)).insert(db.Text('R2', db.Trans(0, 2642)))
                layout.write(str(path))
            save()
            independent.check_stream(path, target)
            save(width=2100)
            with self.assertRaisesRegex(ValueError, 'geometry'):
                independent.check_stream(path, target)
            save(terminal='wrong')
            with self.assertRaisesRegex(ValueError, 'labels'):
                independent.check_stream(path, target)

    def test_native_launch_failure_or_truncated_log_is_not_a_fault(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'console.log'
            for text in ('', 'STUDIO_MAGIC_COMPLETE\nSTUDIO_MAGIC_ERROR missing input\n',
                         'STUDIO_MAGIC_COMPLETE\nSTUDIO_MAGIC_COMPLETE\n'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    independent.magic_log(path)


if __name__ == '__main__':
    unittest.main()
