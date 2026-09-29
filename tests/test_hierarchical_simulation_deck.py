import tempfile
import unittest
from pathlib import Path
from icstudio.hierarchical_flow import simulation_deck
from icstudio.rc_islands import prune


class SimulationDeckTests(unittest.TestCase):
    def fixture(self, directory):
        source=Path(directory)/'extracted.spice'
        source.write_text('.subckt DUT IN OUT\nR1 IN OUT 20\nC1 OUT 0 1p\nR2 orphan_a orphan_b 50\n.ends DUT\n')
        prune(source,Path(directory)/'electrical.spice')
        return source

    def test_prefers_evidenced_observable_deck_only_for_rc(self):
        with tempfile.TemporaryDirectory() as directory:
            source=self.fixture(directory);selected,evidence=simulation_deck(directory,'rc')
            self.assertEqual(selected.name,'electrical.spice')
            self.assertIn('R1 IN OUT 20',selected.read_text());self.assertNotIn('R2 ',selected.read_text())
            self.assertEqual(evidence['removed_resistors'],['r2'])
            self.assertEqual(simulation_deck(directory,'capacitance'),(source,None))

    def test_missing_or_tampered_pruning_evidence_fails_closed(self):
        for fault in ('missing','source','electrical'):
            with tempfile.TemporaryDirectory() as directory:
                source=self.fixture(directory)
                if fault=='missing':(Path(directory)/'electrical.spice.islands.json').unlink()
                else:
                    target=source if fault=='source' else Path(directory)/'electrical.spice'
                    target.write_text(target.read_text()+'* changed\n')
                with self.assertRaisesRegex(ValueError,'missing|changed'):simulation_deck(directory,'rc')


if __name__=='__main__':unittest.main()
