import copy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.mos_grouping import (MODELS, Unchecked, circuit, geometry, intent,
                                    native_channels, raw_channels, run, signature, remap, authenticate)


def source(first='ng=3', second='ng=1'):
    return ('.subckt DUT D G S B H\n'
            f'X1 D G S B sg13_hv_nmos w=3u l=1u {first} m=1\n'
            f'X2 D H S B sg13_hv_nmos w=1u l=1u {second} m=1\n.ends DUT\n')


def raw():
    header = 'version 8.3\ntech ihp-sg13g2\nstyle ngspice()\nscale 1000 1 1\n'
    return header + ''.join(
        f'device msubckt sg13_hv_nmos {x} {y} {x+1} {y+1} l=100 w=100 "B" "{g}" 200 0 "S" 100 1,1 "D" 100 1,1\n'
        for x, y, g in [(0, 0, 'G'), (220, 0, 'G'), (440, 0, 'G'), (0, 900, 'H')])


def stream(path):
    import klayout.db as db
    layout = db.Layout(); layout.dbu = .001
    cell = layout.create_cell('DUT')
    active, poly = layout.layer(1, 0), layout.layer(5, 0)
    cell.shapes(active).insert(db.Box(-100, 0, 5500, 1000))
    cell.shapes(active).insert(db.Box(-100, 9000, 1100, 10000))
    for x, y in [(0, 0), (2200, 0), (4400, 0), (0, 9000)]:
        cell.shapes(poly).insert(db.Box(x, y-100, x+1000, y+1100))
    layout.write(str(path))


class MosGroupingTests(unittest.TestCase):
    def test_reviewed_package_and_source_identity_cannot_be_rebound(self):
        from scripts.qualify_standard_mos import load_technology
        from icstudio.model import file_digest
        for target in MODELS:
            technology = load_technology(target)[0]
            self.assertTrue(authenticate(technology))
            for mutation in ('revision', 'layers', 'lock'):
                changed = copy.deepcopy(technology)
                if mutation == 'revision':changed['package_lock']['revision'] = 'other'
                elif mutation == 'layers':changed['layers'][0]['gds'] += 1
                else:changed['package_lock']['files'][next(iter(changed['package_lock']['files']))] = '0'*64
                with self.subTest(target=target, mutation=mutation), self.assertRaises(Unchecked):authenticate(changed)
            def changed_file(path):
                return '0'*64 if str(path).endswith('_setup.tcl') else file_digest(path)
            with self.subTest(target=target), patch('icstudio.mos_grouping.file_digest', side_effect=changed_file), self.assertRaises(Unchecked):
                authenticate(technology)

    def test_literal_intent_keeps_terminal_association_and_count(self):
        ports, expected = intent(source(), 'DUT', 'ihp-sg13g2')
        self.assertEqual(ports, ['D', 'G', 'S', 'B', 'H'])
        self.assertEqual(sum(expected.values()), 2)
        self.assertEqual({(key[1], key[-1]) for key in expected}, {('g', 3), ('h', 1)})
        swapped = source().replace('D G S B', 'S G D B')
        self.assertEqual(expected, intent(swapped, 'dut', 'ihp-sg13g2')[1])
        self.assertIsNone(intent('.subckt a P N\nR1 P N 10\n.ends\n', 'a', 'ihp-sg13g2'))

    def test_malformed_and_unsupported_intent_does_not_pass(self):
        changes = [source('ng=3 ng=4'), source('ng={fingers}'), source('ng=0'), source('ng=9'),
                   source('ng=2.5'), source('nf=3'), source().replace('m=1', 'm=1.5', 1),
                   source().replace('w=3u', 'w=nan'), source('ng=1e999999'), source('ng='+'9'*200),
                   source().replace('X2', 'x1'), source() + '.subckt child A B\nR1 A B 1\n.ends\n',
                   source().replace('X1', 'C1', 1), source().replace('ng=3', 'ng=3 rfmode=1')]
        for changed in changes:
            with self.subTest(changed=changed), self.assertRaises(Unchecked):
                intent(changed, 'DUT', 'ihp-sg13g2')

    def test_internal_names_are_allowed_and_only_explicit_correspondence_remaps(self):
        internal = source().replace('D G S B H\n', 'D S B H\n')
        expected = intent(internal, 'DUT', 'ihp-sg13g2')[1]
        renamed = intent(internal.replace('D G S B sg13', 'D a_1_2 S B sg13'), 'DUT', 'ihp-sg13g2')[1]
        self.assertNotEqual(expected, renamed)
        self.assertEqual(remap(expected, {'g':'a_1_2', 'd':'d', 's':'s', 'b':'b', 'h':'h'}), renamed)
        with self.assertRaises(Unchecked):remap(expected, {'d':'d', 's':'s', 'b':'b', 'h':'h'})

    def test_masks_bind_groups_to_native_terminal_class(self):
        records = raw_channels(raw(), MODELS['ihp-sg13g2'], Decimal('.01'))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'layout.gds'; stream(path)
            actual, count = geometry(path, 'DUT', 'ihp-sg13g2', records, Decimal('.01'))
            self.assertEqual(count, 2)
            self.assertEqual(actual, intent(source(), 'DUT', 'ihp-sg13g2')[1])
            # Same global channel dimensions/count and diffusion-group sizes;
            # only which gate net owns each group has changed.
            swapped = copy.deepcopy(records)
            for record in swapped:
                key = list(record['key']); key[1] = 'h' if key[1] == 'g' else 'g'; record['key'] = tuple(key)
            wrong, _ = geometry(path, 'DUT', 'ihp-sg13g2', swapped, Decimal('.01'))
            self.assertNotEqual(wrong, actual)
            # Keeping total width and all individual channels does not preserve
            # three shared fingers versus three separately contacted copies.
            wrong_source = source().replace('w=3u l=1u ng=3 m=1', 'w=1u l=1u ng=1 m=3')
            self.assertNotEqual(actual, intent(wrong_source, 'DUT', 'ihp-sg13g2')[1])

    def test_raw_alias_locations_missing_metadata_and_hierarchy_reject(self):
        text = raw(); device = text.splitlines()[4]
        for changed in [text + device.replace(' 0 0 1 1 ', ' -0 00 01 1 ') + '\n',
                        text.replace('scale 1000 1 1\n', ''), text + 'use child child_0 0 0\n',
                        text.replace('scale 1000 1 1', 'scale 1000 1 5'),
                        text.replace('tech ihp-sg13g2', 'tech other'), text.replace('version 8.3', 'version 7.0'),
                        text.replace('style ngspice()', 'style bogus')]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                raw_channels(changed, MODELS['ihp-sg13g2'], Decimal('.01'))

    def test_equal_per_net_channel_totals_cannot_hide_swapped_groups(self):
        import klayout.db as db
        layout=db.Layout();layout.dbu=.001;cell=layout.create_cell('DUT')
        active,poly=layout.layer(1,0),layout.layer(5,0);records=[]
        for group,(gate,count) in enumerate([('A',3),('A',3),('H',2),('H',2),('H',2)]):
            y=group*4000
            cell.shapes(active).insert(db.Box(-100,y,(count-1)*2200+1100,y+2000))
            for finger in range(count):
                x=finger*2200;cell.shapes(poly).insert(db.Box(x,y-100,x+1000,y+2100))
                records.append(dict(key=signature('sg13_hv_nmos',['D',gate,'S','B']),width=Decimal('2e-6'),
                                    length=Decimal('1e-6'),location=(x//10,y//10,x//10+1,y//10+1)))
        text=('.subckt DUT D A H S B\nX1 D A S B sg13_hv_nmos w=6u l=1u ng=3 m=2\n'
              'X2 D H S B sg13_hv_nmos w=4u l=1u ng=2 m=3\n.ends\n')
        swapped=text.replace('w=6u l=1u ng=3 m=2','PLACEHOLDER').replace('w=4u l=1u ng=2 m=3','w=6u l=1u ng=3 m=2').replace('PLACEHOLDER','w=4u l=1u ng=2 m=3')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'groups.gds';layout.write(str(path))
            observed,_=geometry(path,'DUT','ihp-sg13g2',records,Decimal('.01'))
            expected=intent(text,'DUT','ihp-sg13g2')[1];wrong=intent(swapped,'DUT','ihp-sg13g2')[1]
            self.assertEqual(observed,expected);self.assertNotEqual(observed,wrong)
            self.assertEqual(sorted((k[-1],v) for k,v in expected.items()),sorted((k[-1],v) for k,v in wrong.items()))
            self.assertEqual({k[1]:k[-1]*v for k,v in expected.items()},{k[1]:k[-1]*v for k,v in wrong.items()})

    def test_native_channels_do_not_accept_merged_m_or_finger_counts(self):
        native = '.subckt DUT D G S B\nX1 D G S B sg13_hv_nmos w=1u l=1u\n.ends\n'
        self.assertEqual(sum(native_channels(native, 'DUT', MODELS['ihp-sg13g2']).values()), 1)
        for suffix in [' m=2', ' ng=2', ' w=2u', ' rfmode=1']:
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                native_channels(native.replace('l=1u', 'l=1u' + suffix), 'DUT', MODELS['ihp-sg13g2'])

    def test_changed_channel_dimension_or_location_cannot_match_masks(self):
        records = raw_channels(raw(), MODELS['ihp-sg13g2'], Decimal('.01'))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'layout.gds'; stream(path)
            for key, value in [('width', Decimal('2e-6')), ('location', (10000, 0, 10001, 1)),
                               ('location', (-1, 0, 1, 1)), ('location', (99, 0, 101, 1))]:
                changed = copy.deepcopy(records); changed[0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    geometry(path, 'DUT', 'ihp-sg13g2', changed, Decimal('.01'))

    def test_unchecked_context_is_retained_without_launching_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); ref = folder/'source.spice'
            ref.write_text(source('ng={n}'), encoding='utf-8')
            proof, files = run(folder/'proof', {'package_lock': {'id': 'ihp-sg13g2'}}, ref,
                               'DUT', folder/'absent.gds', folder/'absent.spice', '', '')
            self.assertEqual(proof['status'], 'NOT_CHECKED')
            self.assertIn('proof/proof.json', files)
            self.assertFalse((folder/'proof/run.tcl').exists())


if __name__ == '__main__':
    unittest.main()
