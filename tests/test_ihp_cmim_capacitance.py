"""Exercise the bounded graph check against retained native Magic output."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from icstudio.catalog import create_device
from icstudio.catalog_migration import emit
from icstudio.ihp_cmim_capacitance import DEVICE, MAGIC_FILES, PACKAGE_SHA256, Unit, applicable, compare
from icstudio.model import digest, file_digest
from icstudio.physical_backend import stage
from scripts.qualify_standard_mos import load_technology


FIXTURE = Path(__file__).parent / 'fixtures/ihp-cmim-capacitance-v1'
SCALE = 'STUDIO_CMIM_CIF_SCALE 0.009999999776482582\n'
COUPON = Unit('coupon', ('C1', 'C2'), ('C1', 'C2'), Decimal('7e-6'), Decimal('7e-6'))


class CmimCapacitanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((FIXTURE / 'SOURCE.json').read_text(encoding='utf-8'))
        for name, expected in manifest['members'].items():
            if file_digest(FIXTURE / name) != expected:
                raise ValueError('Retained fixture changed: ' + name)
        cls.raw, cls.original, cls.flat = (
            (FIXTURE / name).read_text(encoding='utf-8')
            for name in ('coupon.ext', 'hierarchical.spice', 'flat.spice')
        )
        cls.technology = load_technology('ihp-sg13g2')[0]

    def check(self, raw=None, original=None, flat=None, scale=SCALE):
        return compare(self.raw if raw is None else raw,
                       self.original if original is None else original,
                       self.flat if flat is None else flat, scale, COUPON)

    def test_native_flat_preserves_three_edges_and_records_original_corruption(self):
        proof = self.check()
        self.assertEqual(proof['substrate'], 'floating internal SUB')
        values = {tuple(row['nodes']): (row['raw'], row['hierarchical'], row['flat'])
                  for row in proof['edges_af']}
        self.assertEqual(values, {
            ('C1', 'C2'): ('476.219', '476.22', '476.22'),
            ('C1', 'SUB'): ('944.474', None, '944.47'),
            ('C2', 'SUB'): ('1382.71', '2327.18', '1382.71'),
        })
        with self.assertRaisesRegex(ValueError, 'edges differ'):
            self.check(flat=self.original)

    def test_flat_wrong_values_and_extra_declarations_fail(self):
        for before, after in (
            ('0.94447f', '0.94448f'),
            ('C1 C1 SUB', 'C1 C1 0'),
            ('C1 C1 SUB', 'C1 C2 SUB'),
            ('.ends', 'C99 C1 C2 1f\n.ends'),
            ('.ends', 'R99 SUB 0 1t\n.ends'),
            ('.ends', '.global SUB\n.ends'),
            ('X0 C1 C2', 'X0 C2 C1'),
            ('w=7u', 'w=7.00000000000000000000000000001u'),
            ('w=7u', 'w=7u m=2'),
            ('w=7u', 'w=7u m=1 m=1'),
            ('w=7u', 'w=7u\nX9 C1 C2 cap_cmim w=7u l=7u'),
            ('.subckt coupon C1 C2', '.subckt coupon C2 C1'),
        ):
            with self.subTest(after=after), self.assertRaises(ValueError):
                self.check(flat=self.flat.replace(before, after))

    def test_original_must_also_retain_intrinsic_unit_and_interface(self):
        for old, new in (('w=7u', 'w=8u'), ('X0 C1 C2', 'X0 C2 C1'),
                         ('C0 C2 C1', 'C0 C2 VSS'), ('.ends', '.global SUB\n.ends')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.check(original=self.original.replace(old, new))

    def test_raw_alias_hierarchy_foreign_device_and_geometry_fail(self):
        for record in ('use foo foo 1 0 0 0 1 0', 'equiv "C1" "C2"',
                       'mystery C1 C2', self.raw.splitlines()[-1],
                       'device csubckt unrelated'):
            with self.subTest(record=record), self.assertRaises(ValueError):
                self.check(raw=self.raw + record + '\n')
        for old, new in (('scale 1000 1 1', 'scale 1000 1 2'),
                         ('w=700', 'w=701'), ('"C2" 2', '"C2" 1'),
                         ('"None" "C1"', '"None" "C2"'),
                         ('944.474', '940.474'), ('476.219', '477.219')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.check(raw=self.raw.replace(old, new))
        for scale in ('', SCALE + SCALE, SCALE.replace('0.009999999776482582', '0.02')):
            with self.subTest(scale=scale), self.assertRaisesRegex(ValueError, '10 nm grid'):
                self.check(scale=scale)

    def test_arbitrary_source_names_order_and_dimensions_are_bound(self):
        tech = deepcopy(self.technology)
        device = create_device(tech, DEVICE, 'MimUnit')
        device['nets'] = {'c0': 'UPPER', 'c1': 'lower_plate'}
        device['model_params'].update(w='8.2u', l='9u')
        cell = {'id': 'dut', 'name': 'test_cell', 'ports': ['lower_plate', 'UPPER'],
                'devices': [device], 'layout_instances': []}
        project = {'pdk': tech, 'cells': [cell]}
        source = ('.subckt test_cell lower_plate UPPER\n' + emit(device, tech, 'simulation')
                  + '\n.ends test_cell\n')
        tech_file = Path(tech['package_root']) / MAGIC_FILES[0]
        unit, assets = applicable(project, cell, source, tech_file)
        self.assertEqual(unit, Unit('test_cell', ('lower_plate', 'UPPER'),
                                   ('UPPER', 'lower_plate'), Decimal('8.2e-6'), Decimal('9e-6')))
        self.assertEqual(len(assets), 7)
        for altered in (source.replace('m=1', 'm=2'), source.replace('cap_cmim', 'unlocked')):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                applicable(project, cell, altered, tech_file)
        cell['devices'].append(deepcopy(device))
        with self.assertRaisesRegex(ValueError, 'one ordinary catalog unit'):
            applicable(project, cell, source, tech_file)
        cell['devices'].pop()
        cell['layout_instances'].append({'cell': 'foreign'})
        with self.assertRaisesRegex(ValueError, 'flat two-port DUT'):
            applicable(project, cell, source, tech_file)
        cell['layout_instances'].clear()
        tech['simulation']['catalog'][DEVICE]['model_source'] = 'unlocked'
        with self.assertRaisesRegex(ValueError, 'pinned catalog'):
            applicable(project, cell, source, tech_file)

    def test_managed_backend_stages_exact_pdk_without_package_json(self):
        technology = self.technology
        manifest = Path(technology['package_root']) / 'package.json'
        self.assertEqual(digest(json.loads(manifest.read_bytes())), PACKAGE_SHA256)
        device = create_device(technology, DEVICE, 'MimUnit')
        device['nets'] = {'c0': 'C1', 'c1': 'C2'}
        cell = {'id': 'dut', 'name': 'coupon', 'ports': ['C1', 'C2'], 'devices': [device]}
        source = ('.subckt coupon C1 C2\n' + emit(device, technology, 'simulation')
                  + '\n.ends coupon\n')
        job = {'project': {'pdk': technology, 'cells': [cell]}, 'settings': {}}
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            staged = stage(job, work, work.as_posix(), '/native-runtime')['project']
            package = work / 'pdk'
            self.assertFalse((package / 'package.json').exists())
            unit, assets = applicable(staged, staged['cells'][0], source, package / MAGIC_FILES[0])
            self.assertEqual(unit, COUPON)
            self.assertEqual(len(assets), 7)
            for owner, key, altered in (
                ('technology', 'unexpected', 'injected'),
                ('package_lock', 'revision', 'changed'),
            ):
                tampered = deepcopy(staged)
                pdk = tampered['pdk']
                fields = pdk if owner == 'technology' else pdk['package_lock']
                fields[key] = altered
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'pinned catalog'):
                    applicable(tampered, tampered['cells'][0], source, package / MAGIC_FILES[0])
            deck = package / MAGIC_FILES[-1]
            deck.write_bytes(deck.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'capacitance source changed'):
                applicable(staged, staged['cells'][0], source, package / MAGIC_FILES[0])

    def test_source_native_cmim_fails_closed_while_other_devices_are_untouched(self):
        cell = {'id': 'dut', 'name': 'test_cell', 'devices': []}
        project = {'pdk': self.technology, 'cells': [cell]}
        source = '.subckt test_cell A B\nXfoo A B cap_cmim w=7u l=7u\n.ends'
        with self.assertRaisesRegex(ValueError, 'ordinary catalog unit'):
            applicable(project, cell, source, None)
        self.assertEqual(applicable(project, cell, source.replace('cap_cmim', 'other'), None),
                         (None, {}))
