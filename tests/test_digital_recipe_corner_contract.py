"""Process-changing corner overrides must not bypass the GF180 recipe contract."""
from pathlib import Path
import tempfile
import unittest
from icstudio import digital_recipes
from icstudio.digital_platform import implementation_options, validate
from icstudio.model import clone, digest
from tests import test_digital_platforms as platform_fixtures

REPO = Path(__file__).resolve().parents[1]


def fixture(name):
    # The existing public fixture captures actual files and supplies all corners.
    temp = tempfile.TemporaryDirectory()
    platform, _ = platform_fixtures.DigitalPlatformTests().fixture(Path(temp.name), name)
    platform['orfs']['geometry_recipe'] = digital_recipes.GF180_RECIPES[name][0]
    # Independent pre-existing fixture bytes, checked by the real validator.
    for entry in digital_recipes.PATCHES:
        source = REPO / 'tests/fixtures/gf180-recipes' / ('pdn.cfg' if entry['name'] == 'pdn' else 'tapcell.tcl')
        target = Path(temp.name) / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        from icstudio.model import file_digest
        platform['files'].append({'path': entry['path'], 'bytes': target.stat().st_size,
                                  'sha256': file_digest(target)})
    platform['fingerprint'] = digest(platform['files'])
    validate(platform)
    return temp, platform


class CornerContractTests(unittest.TestCase):
    def test_valid_profiles_and_all_selected_corners_remain_valid(self):
        for name, kval in [('gf180', '9'), ('gf180d', '11')]:
            temp, platform = fixture(name)
            with temp:
                for corner in ['typical', 'slow', 'fast']:
                    with self.subTest(name=name, corner=corner):
                        platform['corner'] = corner
                        self.assertEqual(implementation_options(platform)['KVALUE'], kval)

    def test_each_process_override_is_rejected_even_on_unselected_corner(self):
        mutations = {'KVALUE': '99', 'METAL_OPTION': '4LM_1TM',
                     'TRACK_OPTION': '7t', 'POWER_OPTION': '3v3'}
        for name in ['gf180', 'gf180d']:
            temp, platform = fixture(name)
            with temp:
                for corner in ['typical', 'slow', 'fast']:
                    for key, value in mutations.items():
                        changed = clone(platform)
                        changed['orfs']['corners'][corner][key] = value
                        with self.subTest(name=name, corner=corner, key=key):
                            with self.assertRaisesRegex(ValueError, 'matching GF180'):
                                validate(changed)

    def test_c_and_d_stack_swap_is_rejected(self):
        for name, other in [('gf180', '11'), ('gf180d', '9')]:
            temp, platform = fixture(name)
            with temp:
                platform['orfs']['corners']['typical']['KVALUE'] = other
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, 'matching GF180'):
                        implementation_options(platform)

    def test_redundant_matching_override_keeps_corner_voltage_and_rc_files(self):
        temp, platform = fixture('gf180d')
        with temp:
            for corner in ['typical', 'slow', 'fast']:
                platform['orfs']['corners'][corner].update(platform['orfs']['variables'])
                platform['corner'] = corner
                self.assertEqual(implementation_options(platform)['KVALUE'], '11')
                self.assertIn('PWR_NETS_VOLTAGES', implementation_options(platform))
                self.assertIn('11k', platform['orfs']['corner_file_options'][corner]['RCX_RULES'])

    def test_custom_manifest_without_geometry_recipe_keeps_existing_scope(self):
        temp, platform = fixture('gf180d')
        with temp:
            del platform['orfs']['geometry_recipe']
            platform['orfs']['corners']['typical']['KVALUE'] = '9'
            self.assertEqual(implementation_options(platform)['KVALUE'], '9')


