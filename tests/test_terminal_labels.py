import unittest
from icstudio.catalog import create_device
from icstudio.catalog_migration import symbol_context
from icstudio.model import device
from icstudio.symbol_geometry import visible_text
from icstudio.terminal_labels import connection_label
from scripts.qualify_standard_mos import load_technology


class TerminalLabelTests(unittest.TestCase):
    def test_bipolar_and_thermal_labels_follow_the_model_family(self):
        tech, _ = load_technology('ihp-sg13g2')
        for model in ('npn13G2_5t', 'npn13G2l_5t', 'npn13G2v_5t'):
            d = create_device(tech, 'sg13g2_pr/' + model + '.sym', 'Q1')
            self.assertEqual({p: connection_label(tech, d, p) for p in d['nets']},
                             dict(c='Collector', b='Base', e='Emitter', s='Substrate', t='Temperature rise'))

    def test_mos_and_two_terminal_components_keep_their_labels(self):
        mos = device('NMOS', 'M1', model_mode='generic')
        self.assertEqual(connection_label({}, mos, 'b'), 'Bulk')
        self.assertEqual(connection_label({}, mos, 's'), 'Source')
        self.assertEqual(connection_label({}, device('V', 'V1'), 'p'), 'Positive (+)')

    def test_arbitrary_cell_ports_are_not_reinterpreted_as_mos_terminals(self):
        d = device('X', 'X1', nets={'s': 'n1', 'b': 'n2', 'd': 'n3', 'g': 'n4'})
        self.assertEqual([connection_label({}, d, pin) for pin in d['nets']], ['s', 'b', 'd', 'g'])

    def test_mixed_case_artwork_tracks_live_emitter_parameters(self):
        tech, _ = load_technology('ihp-sg13g2')
        d = create_device(tech, 'sg13g2_pr/npn13G2l_5t.sym', 'Q1')
        d['model_params'].update(nx=4, el=2.5)
        context = symbol_context(d, tech)
        self.assertEqual(visible_text({'text': 'Nx=@Nx El=@El unknown=@Extra'}, context),
                         'Nx=4 El=2.5 unknown=@Extra')
        d['model_params'].update(nx=2, el=1)
        context = symbol_context(d, tech)
        self.assertEqual(visible_text({'text': 'Nx=@Nx El=@El'}, context), 'Nx=2 El=1')


if __name__ == '__main__':
    unittest.main()
