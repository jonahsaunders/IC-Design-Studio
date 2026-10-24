"""Electrical passes must bind the final layout's exact circuit and constraints."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from icstudio.digital import counter_project
from icstudio.digital_implementation import logic_identity
from scripts.check_sky130_filled_electrical import electrical_binding, replay_electrical


class FilledElectricalBindingsTests(unittest.TestCase):
    def fixture(self, stage='timing'):
        project = counter_project(); cfg = project['digital']; cfg['timing_corners'] = ['typical']
        sdc = next(f['text'] for f in cfg['files'] if f['role'] == 'constraint')
        files = {key: dict(path=key, sha256=key+'-digest') for key in ('netlist', 'spef', 'gds', 'checkpoint')}
        original = dict(logic_hash=logic_identity(cfg), platform={'name': 'unit'}, artifacts=files)
        finish = dict(project_id=project['id'], cell_id=project['top'], digital_result=original)
        settings = dict(stage=stage, upstream=dict(result_sha256='finish-digest', artifacts=deepcopy(files), stage='finish'))
        data = dict(stage=stage, logic_hash=original['logic_hash'], platform=original['platform'],
                    artifacts=deepcopy(files), verdict='PASS', **{stage: dict(status='PASS')})
        result = dict(project_id=project['id'], cell_id=project['top'], settings=settings, digital_result=data)
        job = dict(project=project, cell=project['top'], settings=deepcopy(settings))
        return finish, result, job, 'finish-digest', hashlib.sha256(sdc.encode()).hexdigest()

    def test_both_passes_bind_final_inputs(self):
        for stage in ('timing', 'equivalence'):
            with self.subTest(stage=stage):electrical_binding(*self.fixture(stage))

    def test_wrong_upstream_result_stage_or_any_artifact_is_rejected(self):
        for field in ('result_sha256', 'stage', 'artifacts'):
            args = list(self.fixture()); upstream = args[1]['settings']['upstream']
            upstream[field] = {} if field == 'artifacts' else 'different'
            args[2]['settings'] = deepcopy(args[1]['settings'])
            with self.subTest(field=field), self.assertRaises(ValueError):electrical_binding(*args)

    def test_wrong_design_or_technology_is_rejected(self):
        for field in ('project_id', 'cell_id', 'logic_hash', 'platform'):
            args = list(self.fixture()); target = args[1] if field.endswith('_id') else args[1]['digital_result']
            target[field] = 'different'
            with self.subTest(field=field), self.assertRaises(ValueError):electrical_binding(*args)

    def test_changed_rtl_cannot_keep_the_old_pass(self):
        args = list(self.fixture()); args[2]['project']['digital']['files'][0]['text'] += '\n// changed RTL input\n'
        with self.assertRaises(ValueError):electrical_binding(*args)

    def test_old_netlist_or_missing_final_parasitics_cannot_pass(self):
        for key in ('netlist', 'spef'):
            args = list(self.fixture()); args[1]['digital_result']['artifacts'][key]['sha256'] = 'stale'
            with self.subTest(key=key), self.assertRaises(ValueError):electrical_binding(*args)

    def test_incomplete_failed_or_only_summary_pass_is_rejected(self):
        for stage in ('timing', 'equivalence'):
            for field in ('status', 'verdict'):
                for status in ('FAIL', 'UNKNOWN', 'INCOMPLETE', None):
                    args = list(self.fixture(stage)); data = args[1]['digital_result']
                    (data[stage] if field == 'status' else data)[field] = status
                    with self.subTest(stage=stage, field=field, status=status), self.assertRaises(ValueError):
                        electrical_binding(*args)

    def test_pre_layout_constraints_or_additional_unexecuted_corners_are_rejected(self):
        for fault in ('constraint', 'missing', 'duplicate', 'corners'):
            args = list(self.fixture()); cfg = args[2]['project']['digital']
            if fault == 'corners':cfg['timing_corners'] = ['typical', 'slow']
            else:
                sdc = next(f for f in cfg['files'] if f['role'] == 'constraint')
                if fault == 'constraint':sdc['text'] += '\nset_false_path -from [all_inputs]\n'
                elif fault == 'missing':cfg['files'].remove(sdc)
                else:cfg['files'].append(deepcopy(sdc))
            with self.subTest(fault=fault), self.assertRaises(ValueError):electrical_binding(*args)

    def test_settings_cannot_be_replaced_after_execution(self):
        args = list(self.fixture()); args[2]['settings']['upstream']['root'] = 'different'
        with self.assertRaises(ValueError):electrical_binding(*args)


class NativeElectricalReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        bundle = Path(__file__).parent/'fixtures/sky130-filled-electrical-reports-v1.zip'
        self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(),
                         'c3e924cc05cb8063c1c1023a069edd8d9b6f9def75e8224d266e04e9b517bef2')
        with zipfile.ZipFile(bundle) as archive:archive.extractall(self.root)
        manifest = json.loads((self.root/'manifest.json').read_bytes())
        for name, digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((self.root/name).read_bytes()).hexdigest(), digest)
        self.expected = json.loads((self.root/'expected.json').read_bytes())

    def test_actual_native_reports_reproduce_both_passes(self):
        for stage in ('timing', 'equivalence'):
            self.assertEqual(replay_electrical(self.root/stage, self.expected[stage])['status'], 'PASS')

    def test_positive_summary_cannot_hide_a_failing_or_missing_path(self):
        path = self.root/'timing/timing-corners/typical/timing_paths.tsv'; original = path.read_bytes()
        rows = path.read_text().splitlines(); fields = rows[0].split('\t'); fields[3] = '-0.000001'
        rows[0] = '\t'.join(fields); path.write_text('\n'.join(rows)+'\n')
        with self.assertRaises(ValueError):replay_electrical(self.root/'timing', self.expected['timing'])
        path.write_bytes(original); path.unlink()
        with self.assertRaises(ValueError):replay_electrical(self.root/'timing', self.expected['timing'])

    def test_positive_slack_does_not_hide_missing_extracted_interconnect(self):
        path = self.root/'timing/timing-corners/typical/parasitic_annotation.txt'
        path.write_text('Found 1 unannotated drivers.\n_16_/Q\nFound 0 partially unannotated drivers.\n')
        with self.assertRaises(ValueError):replay_electrical(self.root/'timing', self.expected['timing'])

    def test_cached_or_failed_strategy_cannot_supply_a_proof(self):
        path = self.root/'equivalence/proof/strategies/counter.count/smtbmc/status'
        for text in ('PASS (cached)', 'FAIL', 'UNKNOWN', 'ERROR'):
            path.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                replay_electrical(self.root/'equivalence', self.expected['equivalence'])

    def test_missing_proof_completion_or_new_counterexample_is_rejected(self):
        path = self.root/'equivalence/proof/PASS'; original = path.read_bytes(); path.unlink()
        with self.assertRaises(ValueError):replay_electrical(self.root/'equivalence', self.expected['equivalence'])
        path.write_bytes(original); (path.parent/'unexpected.vcd').write_text('unexpected trace')
        with self.assertRaises(ValueError):replay_electrical(self.root/'equivalence', self.expected['equivalence'])

    def test_induction_unknown_retains_trace_when_pdr_proves_the_partition(self):
        root = self.root/'equivalence/proof'
        (root/'strategies/counter.count/smtbmc/status').write_text('UNKNOWN')
        (root/'strategies/counter.count/pdr/status').write_text('PASS')
        trace = 'strategies/counter.count/smtbmc/trace_induct.vcd'; (root/trace).write_text('induction trace')
        expected = deepcopy(self.expected['equivalence'])
        row = expected['equivalence']['partitions'][0]
        row['strategies'] = [{'strategy': 'pdr', 'status': 'PASS'}, {'strategy': 'smtbmc', 'status': 'UNKNOWN'}]
        expected['equivalence']['counterexamples'] = [trace]
        result = replay_electrical(self.root/'equivalence', expected)
        self.assertEqual(result['status'], 'PASS'); self.assertEqual(result['retained_strategy_traces'], [trace])
        (root/'strategies/counter.count/smtbmc/status').write_text('FAIL')
        with self.assertRaises(ValueError):replay_electrical(self.root/'equivalence', expected)


if __name__ == '__main__':
    unittest.main()
