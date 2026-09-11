"""Convergence hints must solve the actual start and preserve circuit semantics."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from icstudio.dc_startup import seed_deck
from icstudio.engines import execute, parse_raw

ENGINE = os.environ.get('ICSTUDIO_TEST_NGSPICE') or shutil.which('ngspice')
DECK = '''Diode sweep with a different nominal source value
V1 in 0 5
R1 in out 1k
D1 out 0 diode
.model diode D(Is=1e-12)
.temp 85
.nodeset v(in)=0.1
.dc V1 .1 .4 .1
.save v(out)
.end
'''


class DCStartupTests(unittest.TestCase):
    def test_unknown_technology_is_rejected_without_writing_an_overlay(self):
        from scripts.prepare_open_project_technology import prepare
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'input.tech'; source.write_text('unknown revision')
            with self.assertRaisesRegex(ValueError, 'Unknown technology'):
                prepare(source, root / 'overlay')
            self.assertEqual(source.read_text(), 'unknown revision')
            self.assertFalse((root / 'overlay').exists())

    def test_incomplete_or_wrong_start_is_not_used_as_a_hint(self):
        with tempfile.TemporaryDirectory() as folder:
            for rows in ([], [[float('nan'), 0]], [[5., .5]], [[.1, .1], [.2, .2]]):
                with self.subTest(rows=rows), patch('icstudio.engines.execute', return_value='done'), \
                        patch('icstudio.engines.parse_raw', return_value=(['v(v-sweep)', 'v(out)'], rows, False)):
                    with self.assertRaises(ValueError): seed_deck(DECK, lambda *args: [], folder)
                    self.assertFalse((Path(folder) / 'dc-startup.nodeset').exists())

    def test_simulator_internal_nodes_are_not_emitted_as_unresolvable_hints(self):
        with tempfile.TemporaryDirectory() as folder, patch('icstudio.engines.execute', return_value='done'), \
                patch('icstudio.engines.parse_raw', return_value=(['v(v-sweep)', 'v(out)', 'v(m.x1#body)'], [[.1, .09, .08]], False)):
            seeded = seed_deck(DECK, lambda *args: [], folder)
            self.assertIn('.nodeset v(out)=', seeded)
            self.assertNotIn('#body', seeded)

    @unittest.skipUnless(ENGINE, 'A real ngspice is required')
    def test_real_hsa_startup_retains_temperature_and_releases_voltage_guesses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            command = lambda raw, deck: [ENGINE, '-n', '-D', 'ngbehavior=hsa', '-D', 'filetype=ascii', '-b', '-r', str(raw), str(deck)]
            seeded = seed_deck(DECK, command, root)
            first = (root / 'dc-startup.cir').read_text()
            self.assertIn('.temp 85', first)
            self.assertIn('V1 in 0 5', first)
            self.assertEqual(seeded.count('.nodeset v(in)='), 1)
            self.assertIn('.nodeset v(in)=0.1', seeded)
            self.assertNotIn('.ic ', seeded)
            results = []
            for name, deck in [('original', DECK), ('seeded', seeded)]:
                path = root / (name + '.cir'); path.write_text(deck)
                raw = root / (name + '.raw'); execute(command(raw, path), root)
                results.append(parse_raw(raw)[1])
            self.assertEqual(len(results[1]), 4)
            for a, b in zip(*results):
                for x, y in zip(a, b): self.assertAlmostEqual(x, y, delta=1e-6)
            # The output rises substantially after the initial guess was released.
            self.assertGreater(results[1][-1][1], results[1][0][1] + .2)
