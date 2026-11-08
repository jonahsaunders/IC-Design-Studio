"""Source-bound description/voltage controls; no simulator acceptance claimed."""
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get('ICSTUDIO_REVIEW_SOURCE', Path(__file__).resolve().parents[1]))
DRAFT = Path(__file__).resolve().parents[1]
CONTRACT = Path(os.environ.get('ICSTUDIO_VPP_CONTRACT', ROOT/'docs/qualification/sky130-vpp-voltage-v1'))
PACKAGE = ROOT/'icstudio/assets/pdks/sky130A'


def load(name):
    spec = importlib.util.spec_from_file_location(name, DRAFT/'scripts'/f'{name}.py')
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


description = load('prepare_sky130_vpp_descriptions')
voltage = load('qualification_sky130_vpp_voltage')


class VppDescriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_raw = (PACKAGE/'package.json').read_bytes()
        cls.original = json.loads(cls.original_raw)
        cls.changed_raw, cls.note_raw = description.corrected(cls.original_raw)
        cls.changed = json.loads(cls.changed_raw)

    def test_small_geometry_choice_loses_wrong_default_size(self):
        key = description.PARENT[:-4]+'__sky130_fd_pr__cap_vpp_04p4x04p6_m1m2m3_shieldl1m5_floatm4.sym'
        before = self.original['technology']['simulation']['catalog'][key]
        after = self.changed['technology']['simulation']['catalog'][key]
        self.assertIn(description.INHERITED, before['notes'])
        self.assertNotIn(description.INHERITED, after['notes'])
        self.assertEqual(after['model'], before['model'])
        self.assertTrue(any('M5 shield' in note for note in after['notes']))

    def test_m4_shield_choice_loses_contradictory_m5_note(self):
        key = description.PARENT[:-4]+'__sky130_fd_pr__cap_vpp_06p8x06p1_l1m1m2m3_shieldpom4.sym'
        after = self.changed['technology']['simulation']['catalog'][key]
        self.assertTrue(any('M4 shield' in note for note in after['notes']))
        self.assertFalse(any('M5 shield' in note for note in after['notes']))

    def test_only_nine_derived_descriptions_change(self):
        old = self.original['technology']['simulation']['catalog']
        new = self.changed['technology']['simulation']['catalog']
        self.assertEqual(old.keys(), new.keys())
        changed = []
        for key, value in old.items():
            if value != new[key]:
                changed.append(key)
                a, b = copy.deepcopy(value), copy.deepcopy(new[key])
                self.assertEqual(a.pop('notes').count(description.INHERITED), 1)
                b.pop('notes'); self.assertEqual(a, b)
        self.assertEqual(len(changed), 9)
        self.assertEqual(old[description.PARENT], new[description.PARENT])
        self.assertEqual({k: v for k, v in self.changed['files'].items() if k != description.NOTE}, self.original['files'])
        self.assertNotEqual(self.changed['revision'], self.original['revision'])

    def test_missing_unsuffixed_identity_still_rejects_device_creation(self):
        from icstudio.catalog import create_device
        tech = copy.deepcopy(self.changed['technology'])
        tech['package_lock'] = {key: self.changed[key] for key in ('id', 'revision')}
        choices = [row for row in json.loads(self.note_raw)['changes'] if not row['available']]
        self.assertEqual(len(choices), 1)
        with self.assertRaisesRegex(ValueError, 'definition is absent'):
            create_device(tech, choices[0]['catalog_key'], 'DUT')

    def test_changed_input_and_repeat_correction_reject(self):
        for raw in (self.original_raw+b' ', self.changed_raw):
            with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                description.corrected(raw)

    def test_late_output_asset_change_cannot_report_success(self):
        real_copy = shutil.copyfile
        first = []
        calls = []
        total = len(self.original['files'])
        def late_change(source, destination):
            result = real_copy(source, destination)
            calls.append(str(destination))
            if not first:
                first.append(Path(destination))
            if len(calls) == total:
                first[0].write_bytes(first[0].read_bytes()+b'\nchanged output\n')
            return result
        with tempfile.TemporaryDirectory() as folder, patch.object(description.shutil, 'copyfile', side_effect=late_change):
            with self.assertRaisesRegex(ValueError, 'asset changed in prepared'):
                description.prepare(PACKAGE, Path(folder)/'package')
        self.assertEqual(len(calls), total)

    def test_current_package_preparation_automatically_corrects_derived_notes(self):
        from scripts.prepare_alternate_models import prepare
        from scripts.alternate_model_source import PROMOTED
        from icstudio.catalog import create_device
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'package'
            report = prepare(PACKAGE, root)
            package = json.loads((root/'package.json').read_bytes())
            self.assertNotEqual(report['manifest_sha256'], PROMOTED['sky130A'])
            catalog = package['technology']['simulation']['catalog']
            derived = {key: row for key, row in catalog.items() if row.get('alternate_of') == description.PARENT}
            self.assertEqual(len(derived), 9)
            self.assertTrue(all(description.INHERITED not in row['notes'] for row in derived.values()))
            self.assertIn(description.INHERITED, catalog[description.PARENT]['notes'])
            missing = [key for key, row in derived.items() if row['unavailable']]
            self.assertEqual(len(missing), 1)
            tech = copy.deepcopy(package['technology'])
            tech['package_lock'] = {key: package[key] for key in ('id', 'revision')}
            with self.assertRaisesRegex(ValueError, 'definition is absent'):
                create_device(tech, missing[0], 'DUT')


class VppVoltageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = voltage.VppVoltageContract(CONTRACT, PACKAGE)
        cls.key = description.PARENT

    def point(self, **changes):
        point = dict(catalog_key=self.key, vc0=0.0, vc1=0.0)
        point.update(changes)
        return self.contract.screen(point)

    def test_all_nine_models_signed_boundaries_and_one_ulp_controls(self):
        self.assertEqual(len(self.contract.contract['bindings']), 9)
        for key in self.contract.contract['bindings']:
            for bound in (-5.5, 0, 5.5):
                with self.subTest(key=key, bound=bound):
                    self.assertEqual(self.point(catalog_key=key, vc0=bound)['plate_voltage_status'], 'WITHIN_DOCUMENTED_LIMITS')
            for sign in (-1, 1):
                self.assertEqual(self.point(catalog_key=key, vc0=sign*math.nextafter(5.5, math.inf))['plate_voltage_status'], 'OUTSIDE_DOCUMENTED_LIMITS')

    def test_difference_not_two_absolute_voltages(self):
        for first, second in ((10, 4.5), (-4.5, -10), (103, 100), (-100, -103)):
            self.assertEqual(self.point(vc0=first, vc1=second)['plate_voltage_status'], 'WITHIN_DOCUMENTED_LIMITS')
        self.assertEqual(self.point(vc0=3, vc1=-3)['plate_voltage_status'], 'OUTSIDE_DOCUMENTED_LIMITS')

    def test_second_terminal_boundary_and_plate_reversal(self):
        for first, second in ((0, 5.5), (0, -5.5), (5.5, 0), (-5.5, 0)):
            self.assertEqual(self.point(vc0=first, vc1=second)['plate_voltage_status'], 'WITHIN_DOCUMENTED_LIMITS')
        self.assertEqual(self.point(vc1=math.nextafter(5.5, math.inf))['plate_voltage_status'], 'OUTSIDE_DOCUMENTED_LIMITS')

    def test_common_mode_and_all_other_validities_remain_unknown(self):
        row = self.point(vc0=1e200, vc1=1e200)
        self.assertEqual(row['plate_voltage_status'], 'WITHIN_DOCUMENTED_LIMITS')
        for key in ('body_voltage_status', 'shield_voltage_status', 'common_mode_status', 'temperature_status',
                    'reliability_status', 'absolute_ratings_status', 'full_operating_envelope_status', 'capacitance_accuracy_status'):
            self.assertEqual(row[key], 'NOT_ESTABLISHED')
        self.assertFalse(row['qualified']); self.assertFalse(row['chunk_complete'])
        self.assertFalse(row['native_execution']); self.assertFalse(row['simulator_restriction'])

    def test_exact_identity_and_unavailable_choice_controls(self):
        missing = next(iter(self.contract.contract['unavailable'].items()))
        for field, identifier in (('catalog_key', missing[0]), ('model', missing[1]['model'])):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                self.contract.screen({field: identifier, 'vc0': 0, 'vc1': 0})
        for identifier in (missing[1]['model']+'_nhv', self.key.upper(), 'sky130_fd_pr__cap_vpp_fake'):
            with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                self.contract.screen({'model': identifier, 'vc0': 0, 'vc1': 0})
        model = self.contract.contract['bindings'][self.key]['model']
        self.assertEqual(self.contract.screen(dict(model=model, vc0=1, vc1=0))['catalog_key'], self.key)

    def test_no_inferred_body_shield_temperature_or_assurance_fields(self):
        for key in ('body', 'top', 'temperature_c', 'qualified', 'model'):
            with self.assertRaisesRegex(ValueError, 'Require exactly'):
                self.point(**{key: 0})

    def test_nonfinite_boolean_strings_and_large_integer_reject(self):
        for value in (True, False, '5.5', '5.5V', math.nan, math.inf, -math.inf, 10**1000):
            with self.assertRaises(ValueError):
                self.point(vc0=value)

    def test_float_subtraction_overflow_cannot_hide_out_of_bounds(self):
        self.assertEqual(self.point(vc0=1.7e308, vc1=-1.7e308)['plate_voltage_status'], 'OUTSIDE_DOCUMENTED_LIMITS')

    def test_source_changed_after_construction_rejects(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'contract'; shutil.copytree(CONTRACT, root)
            reader = voltage.VppVoltageContract(root, PACKAGE)
            source = root/'sources/docs/rules/device-details/cap_vpp/index.rst'
            source.write_bytes(source.read_bytes().replace(b'5.5V', b'6.0V'))
            with self.assertRaisesRegex(ValueError, 'Changed VPP resource'):
                reader.screen(dict(catalog_key=self.key, vc0=0, vc1=0))

    def test_changed_contract_limit_cannot_relax_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'contract'; shutil.copytree(CONTRACT, root)
            source = root/'contract.json'; data = json.loads(source.read_bytes()); data['quantity']['upper'] = '6'
            source.write_bytes(description.json_bytes(data))
            with self.assertRaisesRegex(ValueError, 'Changed VPP resource'):
                voltage.VppVoltageContract(root, PACKAGE)

    def test_corrected_package_full_asset_copy_and_changed_model_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'package'
            report = description.prepare(PACKAGE, root)
            self.assertEqual(report['available_choices'], 8); self.assertEqual(report['unavailable_choices'], 1)
            source_manifest = json.loads((PACKAGE/'package.json').read_bytes())
            self.assertEqual(report['original_assets'], len(source_manifest['files']))
            for relative, expected in source_manifest['files'].items():
                self.assertEqual(hashlib.sha256((root/relative).read_bytes()).hexdigest(), expected)
            reader = voltage.VppVoltageContract(CONTRACT, root)
            self.assertEqual(reader.screen(dict(catalog_key=self.key, vc0=5.5, vc1=0))['plate_voltage_status'], 'WITHIN_DOCUMENTED_LIMITS')
            relative = reader.contract['bindings'][self.key]['model_source']
            path = root/relative; path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError, 'Changed VPP resource'):
                reader.screen(dict(catalog_key=self.key, vc0=0, vc1=0))
            with self.assertRaisesRegex(ValueError, 'new VPP-description'):
                description.prepare(PACKAGE, root)


if __name__ == '__main__':
    unittest.main()
