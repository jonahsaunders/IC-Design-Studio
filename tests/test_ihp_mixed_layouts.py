import tempfile
import unittest
from pathlib import Path

from scripts.qualify_ihp_mixed_layouts import PAIRS, PORTS, audit, build, detected, selected
from scripts.qualify_ihp_resistor_layouts import rotated, same_masks
from scripts.qualify_standard_mos import load_technology
from icstudio.model import save_project, load_project


class MixedIHPTests(unittest.TestCase):
    def test_all_three_source_pairs_save_and_rotate_without_losing_masks(self):
        tech, _ = load_technology('ihp-sg13g2')
        with tempfile.TemporaryDirectory() as temp:
            for i, pair in enumerate(PAIRS):
                root = Path(temp)/str(i); p = build(tech, pair, root)
                save_project(p, root/'saved.icproj'); q = load_project(root/'saved.icproj')
                same_masks(p, q)
                for _ in range(4): q = rotated(q)
                same_masks(p, q)
                self.assertEqual(q['cells'][0]['ports'], PORTS)
                self.assertEqual(selected(pair)['ports'], PORTS)

    def test_mixed_netlist_requires_both_devices_geometry_and_terminal_roles(self):
        good = ('.subckt mixed_coupon C B E S G1 W G2\n'
                'XQ C B E S npn13G2l we=70n le=1u Nx=1 m=1\n'
                'C0 G1 W G2 S sg13_hv_svaricap w=3.74u l=.3u Nx=1\n.ends\n')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'native.cir'; path.write_text(good)
            self.assertEqual(audit(path, PAIRS[0])['devices'], 2)
            path.write_text(good.replace('G1 W G2 S sg13', 'G2 W G1 S sg13'))
            self.assertEqual(audit(path, PAIRS[0])['devices'], 2)
            for text in (good.replace('C B E S npn', 'E B C S npn'),
                         good.replace('G1 W G2 S sg13', 'G1 W G2 W sg13'),
                         good.replace('Nx=1', 'Nx=2'), good.replace('we=70n', 'we=80n'),
                         good.replace('w=3.74u', 'w=4u'),
                         good.replace('C0 G1 W G2 S sg13_hv_svaricap w=3.74u l=.3u Nx=1\n', ''),
                         good + 'Xextra C B E S npn13G2l we=70n le=1u Nx=1 m=1\n'):
                path.write_text(text)
                with self.assertRaises(ValueError): audit(path, PAIRS[0])

    def test_missing_varactor_control_cannot_pass_an_empty_or_unrelated_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'lvs-extraction').mkdir(); path = root/'lvs-extraction/native.cir'
            result = dict(status='failed', stages=[dict(name=n, status='passed') for n in ('preflight', 'layout_export')]
                          + [dict(name='lvs_extraction', status='failed', error='IHP extracted port names differ from the schematic.')])
            path.write_text('')
            self.assertFalse(detected(result, root, 'var-missing-recognition'))
            path.write_text('XQ C B E S npn13G2l we=70n le=1u Nx=1 m=1\n')
            self.assertTrue(detected(result, root, 'var-missing-recognition'))
            result['stages'][-1]['error'] = 'Process timed out.'
            self.assertFalse(detected(result, root, 'var-missing-recognition'))


if __name__ == '__main__': unittest.main()
