"""Keep historical RF corner inputs usable without weakening source checks."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.prepare_sky130_rf_qualification import BASE, ROOT, corner_sources
from scripts.sky130_mim_source import previous_mim
from scripts.sky130_rf_source import PROMOTED


class RFCornerSourceTests(unittest.TestCase):
    def test_current_and_original_packages_capture_identical_corner_bytes(self):
        source = ROOT/'icstudio/assets/pdks/sky130A'
        proof, current = corner_sources(source)
        with previous_mim(source) as old:
            old_proof, original = corner_sources(old)
            manifest = json.loads((old/'package.json').read_bytes())
            for name in ('tt', 'ss', 'ff'):
                row = current[name]
                raw = (old/row['path']).read_bytes()
                self.assertEqual(row['text'].encode('utf-8'), raw)
                self.assertEqual(row['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(row['sha256'], manifest['files'][row['path']])
        # The original temporary source is gone; captured data remains usable.
        self.assertEqual(current, original)
        self.assertEqual(proof['selected_manifest_sha256'], PROMOTED)
        self.assertEqual(old_proof['selected_manifest_sha256'], BASE)
        self.assertEqual(proof['historical_manifest_sha256'], BASE)
        self.assertEqual(proof['files'], old_proof['files'])
        self.assertEqual(len(proof['files']), 3)

    def test_unknown_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source/'package.json').write_bytes(b'{"files":{}}\n')
            with self.assertRaisesRegex(ValueError, 'Changed RF corner source package'):
                corner_sources(source)

    def test_changed_or_missing_historical_corner_cannot_be_accepted(self):
        with previous_mim(ROOT/'icstudio/assets/pdks/sky130A') as old:
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp)
                shutil.copyfile(old/'package.json', source/'package.json')
                for name in ('tt', 'ss', 'ff'):
                    relative = f'libs.tech/ngspice/corners/{name}/nonfet.spice'
                    target = source/relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(old/relative, target)
                for name in ('tt', 'ss', 'ff'):
                    target = source/f'libs.tech/ngspice/corners/{name}/nonfet.spice'
                    original = target.read_bytes()
                    with self.subTest(corner=name, fault='changed'):
                        target.write_bytes(original+b'\n* unreviewed edit\n')
                        with self.assertRaisesRegex(ValueError, 'Changed RF corner parameters'):
                            corner_sources(source)
                    target.unlink()
                    with self.subTest(corner=name, fault='missing'):
                        with self.assertRaises(FileNotFoundError):
                            corner_sources(source)
                    target.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
