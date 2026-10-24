"""Reject ambiguous port mappings and physically disconnected pin annotations."""
import copy
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

import klayout.db as k

from scripts.check_sky130_lvs import port_groups_match
from scripts.sky130_lvs_reference import label_copy, prepare_reference, strict_deck


class PortTests(unittest.TestCase):
    def setUp(self):
        self.ports = ['N0000000', 'N0000001', 'N0000002']
        self.pairs = [dict(layout='N0000000,N0000002', reference='N0000002,N0000000', status='Match'),
                      dict(layout='N0000001', reference='N0000001', status='Match')]

    def test_tied_ports_keep_all_names(self):
        self.assertTrue(port_groups_match(self.pairs, self.ports))

    def test_mismatched_pin_group(self):
        self.pairs[0]['reference'] = 'N0000000'
        self.assertFalse(port_groups_match(self.pairs, self.ports))

    def test_duplicate_alias(self):
        self.pairs[0]['layout'] = self.pairs[0]['reference'] = 'N0000000,N0000000,N0000002'
        self.assertFalse(port_groups_match(self.pairs, self.ports))

    def test_unknown_alias(self):
        self.pairs[0]['layout'] = self.pairs[0]['reference'] = 'N0000000,VDD'
        self.assertFalse(port_groups_match(self.pairs, self.ports))

    def test_unpaired_and_failed_native_pins(self):
        for field, value in [('layout', None), ('reference', None), ('status', 'Mismatch')]:
            pairs = copy.deepcopy(self.pairs); pairs[0][field] = value
            self.assertFalse(port_groups_match(pairs, self.ports))

    def test_missing_port(self):
        self.assertFalse(port_groups_match(self.pairs[:1], self.ports))

    def test_extra_port(self):
        self.pairs.append(dict(layout='N9999999', reference='N9999999', status='Match'))
        self.assertFalse(port_groups_match(self.pairs, self.ports))

    def test_no_ports_and_invalid_contract(self):
        for ports in ([], ['VDD'], ['N0000000','N0000000']):
            self.assertFalse(port_groups_match(self.pairs, ports))


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.layout = k.Layout(); self.layout.dbu = .001
        self.top = self.layout.create_cell('test')
        self.metal = self.layout.layer(70,20)
        self.pin = self.layout.layer(70,16)
        self.label = self.layout.layer(70,5)
        self.top.shapes(self.metal).insert(k.Box(460,0,2000,300))
        self.top.shapes(self.pin).insert(k.Box(0,0,800,300))
        self.top.shapes(self.label).insert(k.Text('clk',k.Trans(400,150)))
        self.mapping = dict(top='test',ports={'clk':'N0000000'})

    def run_copy(self):
        source = self.directory/'source.gds'; target = self.directory/'target.gds'
        self.layout.write(str(source))
        return label_copy(source,target,self.mapping)

    def test_label_moves_to_existing_metal_without_adding_material(self):
        result = self.run_copy()
        self.assertTrue(result['mask_preservation'])
        self.assertFalse(result['pin_markers_are_conductors'])
        placed = result['placements'][0]
        self.assertEqual(placed['metal_islands'],1)
        self.assertGreater(placed['new_point'][0],460)
        self.assertLess(placed['pin_metal_area_dbu2'],placed['pin_area_dbu2'])

    def test_pin_spans_disconnected_metal(self):
        self.top.shapes(self.metal).insert(k.Box(0,0,100,300))
        with self.assertRaisesRegex(ValueError,'disconnected conductors'):self.run_copy()

    def test_pin_has_no_metal(self):
        self.top.shapes(self.metal).clear()
        with self.assertRaisesRegex(ValueError,'no metal'):self.run_copy()

    def test_missing_label(self):
        self.top.shapes(self.label).clear()
        with self.assertRaisesRegex(ValueError,'Missing or repeated'):self.run_copy()

    def test_duplicate_label(self):
        self.top.shapes(self.label).insert(k.Text('clk',k.Trans(450,150)))
        with self.assertRaisesRegex(ValueError,'Missing or repeated'):self.run_copy()

    def test_missing_pin(self):
        self.top.shapes(self.pin).clear()
        with self.assertRaisesRegex(ValueError,'pin annotation'):self.run_copy()

    def test_foreign_top(self):
        self.mapping['top']='other'
        with self.assertRaisesRegex(ValueError,'layout top'):self.run_copy()


class IdentityTests(unittest.TestCase):
    def test_unreviewed_master_library_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unreviewed SKY130 master'):
            prepare_reference('',b'.SUBCKT mystery a b\n.ENDS\n',{})

    def test_unreviewed_native_recipe_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unreviewed SKY130 LVS'):
            strict_deck(b'<macro><text>puts "pass"</text></macro>','test')


if __name__ == '__main__':
    unittest.main()
