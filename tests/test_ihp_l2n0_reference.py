import hashlib
import json
import shutil
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import klayout.db as k

from scripts import audit_ihp_l2n0_reference as reference
from scripts import ci_feedback


class L2n0ReferenceTests(unittest.TestCase):
    def test_two_dies_and_both_layouts_preserve_their_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'exchange'
            result = reference.audit(exchange_output=output)
            self.assertEqual(len(result['measurements']), 2)
            self.assertEqual(len(result['layouts']), 2)
            self.assertFalse(result['qualified'])
            self.assertFalse(result['catalog_binding_resolved'])
            self.assertFalse(result['fresh_solver_execution'])
            for row in result['measurements'].values():
                self.assertFalse(row['one_port_comparison']['equivalence_established'])
            damaged = output/'L_2n0.gds'
            layout = k.Layout()
            layout.read(str(damaged))
            via = layout.find_layer(133, 0)
            shape = next(shape for shape in layout.top_cell().shapes(via).each() if not shape.is_text())
            shape.delete()
            layout.write(str(damaged))
            with self.assertRaisesRegex(ValueError, 'physical mask changed'):
                reference.compare_geometry(reference.FIXTURE/'L_2n0.gds', damaged)

    def test_modified_missing_and_rebound_sources_fail(self):
        self.assertIn('test_ihp_l2n0_reference', ci_feedback.UNIT_MODULES)
        identities = ci_feedback.source_identity()
        for source in reference.FIXTURE.iterdir():
            self.assertEqual(identities[source.relative_to(reference.ROOT).as_posix()], reference.sha(source))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'fixture'
            shutil.copytree(reference.FIXTURE, root)
            path = next(root.glob('meas_*.S2P'))
            original = path.read_bytes()
            path.write_bytes(original.replace(b'R 50', b'R 75', 1))
            with self.assertRaisesRegex(ValueError, 'Changed L2n0 source:'):
                reference.verify_sources(root)
            path.write_bytes(original)
            license_bytes = (root/'LICENSE').read_bytes()
            (root/'LICENSE').unlink()
            with self.assertRaisesRegex(ValueError, 'file set'):
                reference.verify_sources(root)
            (root/'LICENSE').write_bytes(license_bytes)
            manifest = root/'SOURCE.json'
            changed = original.replace(b'R 50', b'R 75', 1)
            path.write_bytes(changed)
            rebound = json.loads(manifest.read_bytes())
            row = next(row for row in rebound['files'] if row['file'] == path.name)
            row['sha256'] = hashlib.sha256(changed).hexdigest()
            row['git_blob'] = hashlib.sha1(b'blob '+str(len(changed)).encode()+b'\0'+changed).hexdigest()
            manifest.write_bytes((json.dumps(rebound, indent=2)+'\n').encode())
            with self.assertRaisesRegex(ValueError, 'inventory'):
                reference.verify_sources(root)

    def test_phase_only_parser_fault_fails_independent_matrix_check(self):
        real_parser = reference.touchstone

        def wrong_phase(text, ports):
            result = real_parser(text, ports)
            result['z_imag_ohm'] = [-value for value in result['z_imag_ohm']]
            return result

        with patch.object(reference, 'touchstone', wrong_phase):
            with self.assertRaises(AssertionError):
                reference.audit()


if __name__ == '__main__':
    unittest.main()
