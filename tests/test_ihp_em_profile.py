import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from pathlib import Path

from icstudio import em_technology, ihp_em_profile, inductor, inductor_em, openems_backend
from icstudio.model import example, load_project, save_project
from scripts.qualify_standard_mos import load_technology


def project():
    p = example('empty')
    p['pdk'] = load_technology('ihp-sg13g2')[0]
    return p


class PublicIHPProfileTests(unittest.TestCase):
    def test_cli_stops_before_refinement_for_an_impossible_base_pair(self):
        # External process fixture: exercises the CLI lifecycle, not EM physics.
        from scripts.qualify_ihp_em_profile import main
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'run'
            argv = ['qualify', '--python', sys.executable, '--output', str(root), '--mesh-um', '.5', '--max-cells', '3000000']
            with patch.object(sys, 'argv', argv), patch.dict(os.environ, ICSTUDIO_TEST_EM_MODE='negative-base'), \
                    patch.object(openems_backend, 'DRIVER', Path(__file__).parent/'fixtures/openems_fake_driver.py'):
                with self.assertRaisesRegex(ValueError, 'base mesh has negative resistance'):
                    main()
            self.assertTrue((root/'base-2.json').exists())
            self.assertEqual(json.loads((root/'model.json').read_text())['settings']['mesh_um'], .5)
            self.assertEqual(json.loads((root/'model.json').read_text())['settings']['max_cells'], 3000000)
            self.assertTrue((root/'base-feasibility.json').exists())
            self.assertFalse((root/'fine-1.log').exists())
            self.assertFalse((root/'qualification.json').exists())
            self.assertFalse((root/'characterized.icproj').exists())

    def test_topvia_receipt_requires_both_decks_and_the_specific_fault(self):
        from scripts.qualify_ihp_topvia import accept
        result = dict(violations=1, decks=[dict(name='main', categories=["'TV2.a'"]),
                                         dict(name='maximal', categories=[])])
        accept('cut-width', 'TV2.a', result)
        with self.assertRaisesRegex(ValueError, 'expected native rule'):
            accept('cut-spacing', 'TV2.b', result)
        with self.assertRaisesRegex(ValueError, 'geometry findings remain'):
            accept('single', None, result)
        with self.assertRaisesRegex(ValueError, 'both public decks'):
            accept('cut-width', 'TV2.a', dict(result, decks=result['decks'][:1]))

    def test_public_topmetal_via_also_satisfies_minimum_metal_width(self):
        from icstudio.layout_routing import via_recipes
        tech = project()['pdk']
        recipe = next(r for r in via_recipes(tech) if r['name'] == 'TopMetal1 to TopMetal2')
        self.assertEqual((recipe['size'], recipe['spacing'], recipe['enclosure'], recipe['pad']), (900, 1060, 550, 2000))
        explicit = copy.deepcopy(tech); explicit['routing_vias'] = [via_recipes(tech)[0]]
        self.assertEqual([r['name'] for r in via_recipes(explicit)], ['M1 to M2'])

    def test_exact_public_material_values_and_substrate_coordinate_translation(self):
        tech = project()['pdk']
        for bulk in (280, 180):
            stack = ihp_em_profile.profile(tech, bulk)
            rows = {row['name']: row for row in stack['layers']}
            self.assertEqual(len(rows), 8)
            for name, z, thickness, sigma in [('TopMetal1', 6.4303, 2., 27800000.),
                                             ('TopVia2', 8.4303, 2.8, 3143000.),
                                             ('TopMetal2', 11.2303, 3., 30300000.)]:
                self.assertAlmostEqual(rows[name]['z_um'], z)
                self.assertAlmostEqual(rows[name]['thickness_um'], thickness)
                self.assertEqual(rows[name]['conductivity_s_m'], sigma)
            self.assertEqual(rows['Substrate']['z_um'], -bulk - 3.75)
            self.assertEqual(rows['Substrate']['thickness_um'], bulk)
            self.assertEqual(rows['Substrate']['epsilon_r'], 11.9)
            self.assertEqual(rows['Substrate']['conductivity_s_m'], 2.)
            self.assertEqual(rows['EPI']['z_um'], -3.75)
            self.assertEqual(rows['EPI']['conductivity_s_m'], 5.)
            self.assertEqual(rows['SiO2']['z_um'], 0.)
            self.assertAlmostEqual(rows['Passive']['z_um'], 15.7303)
            self.assertAlmostEqual(rows['AIR']['z_um'], 16.1303)
            self.assertEqual(rows['AIR']['thickness_um'], 300.)
            self.assertEqual(set(stack['layout_map']), {'TopMetal1.drawing', 'TopVia2.drawing', 'TopMetal2.drawing'})
            self.assertEqual(stack['excluded_layers'], {})
            self.assertIn('SHA256 ', stack['source'])
        with self.assertRaisesRegex(ValueError, '280 or 180'):
            ihp_em_profile.profile(tech, 200)

    def test_other_process_fake_name_changed_source_and_mask_mapping_rejected(self):
        for target in ('sky130A', 'gf180mcuC', 'gf180mcuD'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'pinned SG13G2'):
                tech = load_technology(target)[0]; tech['name'] = 'IHP SG13G2'
                ihp_em_profile.profile(tech)
        for fault in ('identity', 'source', 'mask', 'purpose', 'missing'):
            tech = project()['pdk']
            if fault == 'identity': tech['package_lock']['id'] = 'custom'
            if fault == 'source': tech['package_lock']['files']['UPSTREAM-LOCK.json'] = '0' * 64
            row = next(r for r in tech['layers'] if r['name'] == 'TopVia2.drawing')
            if fault == 'mask': row['gds'] = 9
            if fault == 'purpose': row['datatype'] = 22
            if fault == 'missing': tech['layers'].remove(row)
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'pinned SG13G2'):
                ihp_em_profile.profile(tech)

    def test_modified_public_inputs_or_lock_rejected(self):
        tech = project()['pdk']
        for name in ('SOURCE.json', 'SG13G2.xml', 'SG13G2_200um.xml', 'LICENSE', 'UPSTREAM-README.md'):
            with tempfile.TemporaryDirectory() as tmp:
                assets = Path(tmp) / 'source'; shutil.copytree(ihp_em_profile.ASSETS, assets)
                path = assets / name; path.write_bytes(path.read_bytes() + b'changed')
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Changed public'):
                    ihp_em_profile.profile(tech, assets=assets)

    def test_profile_reuse_has_exact_revision_and_preserves_catalog_unavailability(self):
        p = project(); before = copy.deepcopy(p['pdk'])
        p['pdk']['em_stackup'] = ihp_em_profile.profile(p['pdk'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'profile.icproj'; save_project(p, path); restored = load_project(path)
            self.assertEqual(restored['pdk']['em_stackup'], p['pdk']['em_stackup'])
        for key in ('simulation', 'physical', 'package_lock'):
            self.assertEqual(before[key], p['pdk'][key])
        for name in ('inductor', 'inductor3'):
            self.assertTrue(p['pdk']['simulation']['catalog']['sg13g2_pr/' + name + '.sym']['unavailable'])
        changed = copy.deepcopy(p['pdk']); changed['package_lock']['revision'] = 'different'
        with self.assertRaisesRegex(ValueError, 'different PDK'):
            em_technology.bind_stackup(changed, p['pdk']['em_stackup'])

    def test_all_selected_masks_prepare_and_export_without_losing_dielectric_slabs(self):
        for bulk in (280, 180):
            p = project(); p['pdk']['em_stackup'] = ihp_em_profile.profile(p['pdk'], bulk)
            spec = dict(inductor.defaults(p), turns=1, width=8000, spacing=3000,
                        inner=16000, lead=10000, via_rows=1, via_columns=1)
            self.assertEqual(spec['metal'], 'TopMetal2.drawing')
            proposal = inductor.plan(p, p['top'], spec); inductor.install(p, proposal)
            data = inductor_em.manifest(p, p['top'], proposal['device_id'])
            self.assertTrue(data['solver_stackup_complete'], data['solver_missing'])
            prepared = openems_backend.model(data, {})
            self.assertEqual(prepared['layers'], p['pdk']['em_stackup']['layers'])
            self.assertEqual({s['layer'] for s in prepared['solids']}, set(ihp_em_profile.LAYERS))
            xml, numbers = em_technology.solver_stackup(data['stackup'], data['physical_layer_map'])
            tree = ET.fromstring(xml)
            self.assertEqual(len(tree.findall('ELayers/Dielectrics/Dielectric')), 5)
            self.assertEqual(set(numbers), set(ihp_em_profile.LAYERS))

    def test_context_cannot_silently_drop_lower_metal_fill_or_unmodelled_layers(self):
        tech = project()['pdk']; stack = ihp_em_profile.profile(tech)
        for name in ('Metal1.drawing', 'TopMetal2.filler', 'TopMetal2.slit', 'Activ.drawing'):
            issues = em_technology.readiness(tech, stack, [name])
            self.assertTrue(issues, name)
            self.assertIn(name, '; '.join(issues))


if __name__ == '__main__':
    unittest.main()
