"""Missing coverage, failed engines and stale physical evidence cannot pass."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from icstudio import digital_physical_checks as checks
from icstudio.digital_physical_engine import antenna_diode, positive_areas
from icstudio.digital_flow import artifact, validate_result
from icstudio.digital_macro import export
from icstudio.model import clone, file_digest
from tests import test_digital_macro as macro_fixtures


def raw(sha='a'*64, top='counter'):
    return {'schema': 1, 'checkpoint_sha256': sha, 'top': top, 'signal_inputs': 4,
            'missing_gate_models': [], 'unrouted_inputs': [], 'unconnected_power_pins': [],
            'routing_layers': [{'name': 'metal1', 'has_antenna_rule': True}],
            'antenna': {'error': '', 'violating_nets': 0},
            'power': [{'net': net, 'kind': kind, 'terminals': 8, 'special_wires': 2, 'error': ''}
                      for net, kind in [('VDD', 'POWER'), ('VSS', 'GROUND')]]}


class PhysicalCheckTests(unittest.TestCase):
    def test_only_declared_antenna_cells_with_valid_diffusion_are_diodes(self):
        for kind in ('CORE', 'CORE_SPACER', 'CORE_ANTENNACELL'):
            master = SimpleNamespace(getType=lambda: kind, getName=lambda: 'cell')
            for areas in ([], [(0, None)], [(-1, None)], [(float('nan'), None)],
                          [(float('inf'), None)], [(1, None), (-1, None)], [(0.4, None)]):
                pin = SimpleNamespace(getDiffArea=lambda: areas)
                with self.subTest(kind=kind, areas=areas):
                    result = antenna_diode(pin, master, 'u/I')
                    valid = kind == 'CORE_ANTENNACELL' and areas == [(0.4, None)]
                    self.assertEqual(result is not None, valid)
                    if valid:
                        self.assertEqual(result['diffusion_areas'], [{'area': 0.4, 'layer': None}])
        self.assertFalse(positive_areas([(1, None), (float('nan'), None)]))

    def test_diode_evidence_requires_complete_distinct_positive_coverage(self):
        value = raw()
        value.update(schema=2, gate_inputs=3, antenna_diode_inputs=[
            {'pin': 'diode/I', 'master': 'antenna', 'class': 'CORE_ANTENNACELL',
             'diffusion_areas': [{'area': 0.4, 'layer': None}]}])
        self.assertEqual(checks.evaluate(value, 'a'*64, 'counter')['status'], 'PASS')
        changes = {
            'missing-count': lambda r: r.pop('gate_inputs'),
            'missing-list': lambda r: r.pop('antenna_diode_inputs'),
            'bad-count': lambda r: r.update(gate_inputs=4),
            'boolean-count': lambda r: r.update(gate_inputs=True),
            'no-gates': lambda r: r.update(gate_inputs=0, signal_inputs=1),
            'duplicate-pin': lambda r: (r['antenna_diode_inputs'].append(clone(r['antenna_diode_inputs'][0])), r.update(gate_inputs=2)),
            'ordinary-cell': lambda r: r['antenna_diode_inputs'][0].update({'class': 'CORE'}),
            'missing-area': lambda r: r['antenna_diode_inputs'][0].update(diffusion_areas=[]),
            'zero-area': lambda r: r['antenna_diode_inputs'][0]['diffusion_areas'][0].update(area=0),
            'negative-area': lambda r: r['antenna_diode_inputs'][0]['diffusion_areas'][0].update(area=-1),
            'invalid-area': lambda r: r['antenna_diode_inputs'][0]['diffusion_areas'][0].update(area=float('nan')),
            'boolean-area': lambda r: r['antenna_diode_inputs'][0]['diffusion_areas'][0].update(area=True),
            'missing-layer': lambda r: r['antenna_diode_inputs'][0]['diffusion_areas'][0].pop('layer'),
            'missing-master': lambda r: r['antenna_diode_inputs'][0].pop('master'),
            'genuine-missing-gate': lambda r: r['missing_gate_models'].append('logic/A'),
        }
        for label, change in changes.items():
            modified = clone(value); change(modified)
            with self.subTest(label=label):
                self.assertEqual(checks.evaluate(modified, 'a'*64, 'counter')['status'], 'FAIL')
        gates_only = raw(); gates_only.update(schema=2, gate_inputs=4, antenna_diode_inputs=[])
        self.assertEqual(checks.evaluate(gates_only, 'a'*64, 'counter')['status'], 'PASS')

    def test_missing_or_invalid_evidence_never_passes(self):
        self.assertEqual(checks.evaluate(raw(), 'a'*64, 'counter')['status'], 'PASS')
        changes = {
            'no-inputs': lambda r: r.update(signal_inputs=0),
            'boolean-count': lambda r: r.update(signal_inputs=True),
            'unmodeled': lambda r: r['missing_gate_models'].append('u/A'),
            'unrouted': lambda r: r['unrouted_inputs'].append('u/A'),
            'unconnected-power': lambda r: r['unconnected_power_pins'].append('u/VDD'),
            'missing-layer-rule': lambda r: r['routing_layers'][0].update(has_antenna_rule=False),
            'missing-layers': lambda r: r.update(routing_layers=[]),
            'duplicate-layer': lambda r: r['routing_layers'].append(clone(r['routing_layers'][0])),
            'bad-layer': lambda r: r.update(routing_layers=[None]),
            'missing-count': lambda r: r['antenna'].pop('violating_nets'),
            'antenna-violation': lambda r: r['antenna'].update(violating_nets=1),
            'antenna-error': lambda r: r['antenna'].update(error='engine error'),
            'antenna-boolean': lambda r: r['antenna'].update(violating_nets=False),
            'missing-ground': lambda r: r['power'].pop(),
            'duplicate-power': lambda r: r['power'].append(clone(r['power'][0])),
            'grid-error': lambda r: r['power'][-1].update(error='PSM-0069'),
            'no-terminals': lambda r: r['power'][0].update(terminals=0),
            'no-grid': lambda r: r['power'][0].update(special_wires=0),
            'bad-power': lambda r: r.update(power=[None]),
        }
        for label, change in changes.items():
            value = raw(); change(value)
            with self.subTest(label=label):
                self.assertEqual(checks.evaluate(value, 'a'*64, 'counter')['status'], 'FAIL')
        for key in raw():
            value = raw(); value.pop(key)
            with self.subTest(missing=key):
                try:
                    result = checks.evaluate(value, 'a'*64, 'counter')
                except ValueError:
                    continue
                self.assertEqual(result['status'], 'FAIL')

    def test_different_geometry_or_top_rejected(self):
        for sha, top in [('b'*64, 'counter'), ('a'*64, 'another')]:
            with self.assertRaisesRegex(ValueError, 'another checkpoint or design'):
                checks.evaluate(raw(), sha, top)

    def test_production_executor_captures_reports_and_preserves_failure(self):
        for fault in ('none', 'antenna', 'missing-output', 'changed-checkpoint'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as td:
                root = Path(td); checkpoint = root/'final.odb'; checkpoint.write_text('fixture database')
                runner = SimpleNamespace(root=root, artifacts={'checkpoint': artifact(root, checkpoint)},
                    config={'top': 'counter'}, platform={'fingerprint': 'b'*64}, tools={'openroad': 'fixture'})
                runner.add_artifact = lambda key, path: runner.artifacts.update({key: artifact(root, path)})
                def save(key, data, name):
                    path = root/name; path.write_text(json.dumps(data)); runner.add_artifact(key, path)
                runner.save_json = save
                def command(*args, **kwargs):
                    value = raw(file_digest(checkpoint))
                    if fault == 'antenna': value['antenna']['violating_nets'] = 1
                    if fault != 'missing-output':
                        (root/'physical-checks/engine-checks.json').write_text(json.dumps(value))
                    if fault == 'changed-checkpoint': checkpoint.write_text('changed')
                runner.command = command
                stale = root/'physical-checks'; stale.mkdir()
                (stale/'engine-checks.json').write_text(json.dumps(raw(file_digest(checkpoint))))
                if fault == 'none':
                    self.assertEqual(checks.execute(runner)['status'], 'PASS')
                    self.assertIn('physical_check_physical_engine', runner.artifacts)
                else:
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        checks.execute(runner)
                    if fault == 'antenna':
                        self.assertEqual(json.loads((root/'physical_checks.json').read_text())['status'], 'FAIL')

    def test_saved_evidence_and_export_bind_geometry_platform_and_top(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); job, result = macro_fixtures.DigitalMacroTests().fixture(root)
            data = result['digital_result']; files = data['artifacts']
            report = checks.evaluate(raw(files['checkpoint']['sha256']), files['checkpoint']['sha256'], 'counter')
            report['platform_fingerprint'] = data['platform']['fingerprint']
            path = root/'physical_checks.json'; path.write_text(json.dumps(report))
            files['physical_checks'] = artifact(root, path)
            data['physical'] = {'checks': clone(report)}
            validate_result(result, root)
            destination = root/'macro.zip'
            manifest = export(result, root, destination)
            self.assertEqual(manifest['qualification']['physical_checks']['status'], 'PASS')
            self.assertIn('physical_checks', manifest['artifacts'])
            original = destination.read_bytes()
            for fault in ('absent-report', 'absent-declaration', 'changed-geometry', 'changed-platform', 'forged-pass', 'wrong-top'):
                bad = clone(result)
                changed = clone(report)
                if fault == 'absent-report': bad['digital_result']['artifacts'].pop('physical_checks')
                elif fault == 'absent-declaration': bad['digital_result'].pop('physical')
                elif fault == 'changed-geometry': changed['checkpoint_sha256'] = 'c'*64
                elif fault == 'changed-platform': changed['platform_fingerprint'] = 'c'*64
                elif fault == 'forged-pass': changed['checks']['antenna']['violating_nets'] = 1
                else: changed['top'] = changed['checks']['top'] = 'another'
                if fault not in ('absent-report', 'absent-declaration'):
                    bad['digital_result']['physical']['checks'] = clone(changed)
                    path.write_text(json.dumps(changed))
                    bad['digital_result']['artifacts']['physical_checks'] = artifact(root, path)
                with self.subTest(fault=fault), self.assertRaises(ValueError):
                    export(bad, root, destination)
                self.assertEqual(destination.read_bytes(), original)
                path.write_text(json.dumps(report))

    def test_qualifier_records_missing_engine_failure(self):
        from scripts.qualify_digital_physical_checks import qualify
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(FileNotFoundError):
                qualify(root/'absent-evidence', root/'output', root/'absent-openroad')
            self.assertEqual(json.loads((root/'output/report.json').read_text())['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
