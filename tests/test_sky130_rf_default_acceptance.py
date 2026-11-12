"""The release RF gate must select the current bundle without weakening its lock."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from icstudio.catalog import create_device
from scripts import qualify_sky130_rf_default as gate
from scripts.sky130_rf_source import PROMOTED as HISTORICAL_RF


class CurrentDefaultAcceptance(unittest.TestCase):
    def test_real_empty_profile_selects_current_package_and_both_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, source = gate.fresh_project(Path(tmp))
            self.assertEqual(project['pdk']['revision'], gate.REVISIONS['sky130A'])
            self.assertNotEqual(gate.PROMOTED['sky130A'], HISTORICAL_RF)
            self.assertEqual(source.parent, Path(tmp).resolve() / 'registry')
            for key in ('sky130_fd_pr/diode__sky130_fd_pr__model__parasitic__rf_diode_ps2nw.sym',
                        'sky130_fd_pr/nfet_g5v0d10v5_nvt_esd.sym'):
                create_device(project['pdk'], key, 'D1')

    def test_historical_or_crossed_current_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(gate.PROMOTED, {'sky130A': HISTORICAL_RF}):
                with self.assertRaisesRegex(ValueError, 'Unreviewed current'):
                    gate.fresh_project(Path(tmp) / 'historical')
            self.assertFalse((Path(tmp) / 'historical/registry').exists())
            with patch.dict(gate.REVISIONS, {'sky130A': 'wrong-current-revision'}):
                with self.assertRaisesRegex(ValueError, 'did not select'):
                    gate.fresh_project(Path(tmp) / 'crossed')

    def test_installed_asset_changed_after_hub_selection_is_rejected(self):
        real_build = gate.build_project
        def corrupt(*args, **kwargs):
            result = real_build(*args, **kwargs)
            project = result['project']
            asset = next(iter(project['pdk']['package_lock']['files']))
            path = Path(project['pdk']['package_root']) / asset
            path.write_bytes(path.read_bytes() + b'\n')
            return result
        with tempfile.TemporaryDirectory() as tmp, patch.object(gate, 'build_project', corrupt):
            with self.assertRaisesRegex(ValueError, 'asset missing or changed'):
                gate.fresh_project(Path(tmp))


if __name__ == '__main__':
    unittest.main()
