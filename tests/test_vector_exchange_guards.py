"""Exchange must never silently reduce a native electrical array to one device."""
import tempfile
import unittest
from pathlib import Path

from icstudio.model import example, device, clone, validate
from icstudio.interchange import export_xschem, export_handoff
from icstudio.native_exchange import export_project
from icstudio.native_migration import review_path
from tests.test_native_migration import divider


class VectorExchangeGuardTests(unittest.TestCase):
    def test_generic_array_is_rejected_before_writing_output(self):
        p = example('empty'); c = p['cells'][0]
        c['devices'] = [device('R', 'R1', nets={'p': 'in', 'n': '0'})]
        c['devices'][0]['array'] = {'start': 1, 'end': 0}
        validate(p); before = clone(p)
        with tempfile.TemporaryDirectory() as folder:
            for index, export in enumerate((export_xschem, export_handoff)):
                out = Path(folder)/('exchange'+str(index))
                with self.assertRaisesRegex(ValueError, 'Materialize.*SPICE'):
                    export(p, out)
                self.assertFalse(out.exists())
        self.assertEqual(p, before)

    def test_native_array_rejected_by_both_public_export_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record = review_path(divider(root/'source'))
            self.assertEqual(record['status'], 'Complete', record['items'])
            p = record['candidate']
            resistor = next(d for c in p['cells'] for d in c['devices'] if d['name'] == 'R1')
            resistor['array'] = {'start': 0, 'end': 2}
            validate(p)
            for index, export in enumerate((export_project, export_xschem)):
                out = root/('exchange'+str(index))
                with self.assertRaisesRegex(ValueError, 'compact native instance array'):
                    export(p, out)
                self.assertFalse(out.exists())

    def test_bus_interface_and_global_bus_fail_closed(self):
        for scope in ('ports', 'globals'):
            p = example('empty')
            if scope == 'ports': p['cells'][0]['ports'] = ['data[1:0]']
            else: p['global_nets'] = ['supply[1:0]']
            validate(p)
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as folder:
                out = Path(folder)/'exchange'
                with self.assertRaisesRegex(ValueError, 'explicit scalar terminals.*SPICE'):
                    export_xschem(p, out)
                self.assertFalse(out.exists())

    def test_existing_indexed_scalar_devices_keep_export_support(self):
        p = example('empty')
        p['cells'][0]['devices'] = [device('R', 'R1', nets={'p': 'data[2]', 'n': '0'})]
        validate(p)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)/'exchange'; export_xschem(p, out)
            self.assertIn('data[2]', (out/'simulation.cir').read_text())

    def test_compatible_xschem_capture_rejects_native_array_metadata(self):
        from icstudio.xschem_compat import review_project, export_capture
        from tests.test_xschem_compatible import fixture
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); record = review_project(fixture(root/'source'))
            self.assertFalse(record['errors'], record['errors'])
            p = record['candidate']
            next(d for c in p['cells'] for d in c['devices'] if d['name']=='R1')['array'] = {'start':0,'end':1}
            out = root/'exchange'
            with self.assertRaisesRegex(ValueError, 'compact native instance array'):
                export_capture(p, out)
            self.assertFalse(out.exists())


if __name__ == '__main__': unittest.main()
