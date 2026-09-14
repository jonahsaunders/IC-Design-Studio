"""Cross-PDK EM contracts using synthetic materials, never process qualification."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from icstudio import em_technology as profiles, inductor, inductor_em as em
from icstudio.model import example, clone, save_project, load_project
from icstudio.layout import kdb, polygon, rect, drc
from test_inductor_em import results


def fixture(identifier='custom-rdl', names=('RDL_A', 'Cut_AB', 'RDL_B'), grid=10):
    p = example('empty'); tech = p['pdk']; lower, cut, upper = names
    tech.update(name=identifier, revision='synthetic-1', grid=grid)
    # Deliberately share a GDS number with different datatypes: a layer-number
    # only XML writer would silently merge distinct conductors and the via.
    tech['layers'] = [dict(name=name, gds=120, datatype=i+1, color='#68a6f4', width=200, space=200)
                      for i, name in enumerate(names)]
    tech['routing_vias'] = [dict(name='Upper connection', lower=lower, cut=cut, upper=upper,
                                size=200, enclosure=100, spacing=200)]
    tech['connectivity'] = dict(conductors=[lower, upper], vias=[[lower, cut, upper]])
    tech['package_lock'] = dict(id=identifier, revision='synthetic-1', files={})
    stack = dict(schema=2, source='Synthetic cross-PDK acceptance; not foundry data',
                 layout_map=dict(zip(names, ('Bottom copper', 'Copper cuts', 'Top copper'))), layers=[
        dict(name='Bottom copper', kind='conductor', z_um=1, thickness_um=.5, conductivity_s_m=2e7),
        dict(name='Copper cuts', kind='via', z_um=1.5, thickness_um=.5, conductivity_s_m=3e7),
        dict(name='Top copper', kind='conductor', z_um=2, thickness_um=1, conductivity_s_m=4e7),
        dict(name='Insulator', kind='dielectric', z_um=0, thickness_um=10, epsilon_r=4.1, loss_tangent=.001),
        dict(name='Bulk', kind='substrate', z_um=-100, thickness_um=100, epsilon_r=11.9, conductivity_s_m=2)])
    tech['em_stackup'] = profiles.bind_stackup(tech, stack)
    return p


class PDKEMTests(unittest.TestCase):
    def create(self, p, shape='octagon'):
        proposal = inductor.plan(p, p['top'], {**inductor.defaults(p), 'shape': shape})
        inductor.install(p, proposal)
        return proposal['device_id']

    def test_five_shapes_across_named_and_future_process_contracts(self):
        cases = [('sky130A', ('met4', 'via4', 'met5'), 5),
                 ('gf180mcuC', ('Metal4', 'Via4', 'Metal5'), 10),
                 ('gf180mcuD', ('M5', 'V5', 'M6'), 20),
                 ('ihp-sg13g2', ('TopMetal1', 'TopVia2', 'TopMetal2'), 5),
                 ('unlisted-custom-process', ('RDL1', 'RDLcut', 'RDL2'), 50)]
        for identifier, names, grid in cases:
            for shape in inductor.SHAPES:
                with self.subTest(pdk=identifier, shape=shape):
                    p = fixture(identifier, names, grid); did = self.create(p, shape)
                    self.assertFalse(drc(p, p['top']))
                    manifest = em.manifest(p, p['top'], did)
                    self.assertTrue(manifest['solver_stackup_complete'], manifest['solver_missing'])
                    self.assertEqual(set(manifest['physical_layer_map']), set(names))
                    self.assertTrue(profiles.capabilities(p['pdk'])['profile_ready'])
                    characterized = em.install_results(p, p['top'], did, results(manifest))
                    self.assertTrue(characterized['rows'])

    def test_solver_bundle_preserves_datatypes_masks_materials_and_units(self):
        p = fixture(); did = self.create(p)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'em.zip'; data = em.export_bundle(p, p['top'], did, path)
            with zipfile.ZipFile(path) as archive:
                xml = ET.fromstring(archive.read('stackup.xml'))
                self.assertEqual(xml.find('ELayers').get('LengthUnit'), 'um')
                layers = xml.findall('ELayers/Layers/Layer'); materials = {m.get('Name'): m for m in xml.findall('Materials/Material')}
                expected = {l['name']: l for l in p['pdk']['em_stackup']['layers']}
                self.assertEqual(len({layer.get('Layer') for layer in layers}), 3)
                for layer in layers:
                    source = expected[layer.get('Name')]
                    self.assertEqual(float(layer.get('Zmin')), source['z_um'])
                    self.assertEqual(float(layer.get('Zmax')), source['z_um']+source['thickness_um'])
                    self.assertEqual(float(materials[layer.get('Material')].get('Conductivity')), source['conductivity_s_m'])
                table = json.loads(archive.read('solver-layers.json'))['layers']
                self.assertEqual({row['datatype'] for row in table}, {1, 2, 3})
                gds = Path(directory)/'solver.gds'; gds.write_bytes(archive.read('solver-geometry.gds'))
                layout = kdb().Layout(); layout.read(str(gds)); self.assertEqual(layout.dbu, .001)
                self.assertEqual([c.name for c in layout.top_cells()], ['EM_MODEL'])
                for row in table:
                    wanted = kdb().Region()
                    for shape in data['context_geometry']:
                        if shape['layer'] == row['name']: wanted.insert(polygon(shape))
                    actual = kdb().Region(layout.top_cell().begin_shapes_rec(layout.find_layer(row['solver_gds'], 0)))
                    self.assertTrue((actual ^ wanted).is_empty(), row['name'])

    def test_profile_reuse_persistence_and_revision_binding(self):
        p = fixture(); did = self.create(p); stack = p['pdk']['em_stackup']; before = clone(stack)
        changed = clone(p['pdk']); changed['package_root'] = '/another/installation'; changed['layers'][0]['color'] = '#abcdef'
        self.assertEqual(profiles.bind_stackup(changed, stack), stack)
        for change in ('process', 'revision', 'mask', 'rules'):
            q = clone(p['pdk'])
            if change == 'process': q['package_lock']['id'] = 'another-process'
            elif change == 'revision': q['package_lock']['revision'] = 'next-revision'
            elif change == 'mask': q['layers'][0]['datatype'] = 50
            else: q['routing_vias'][0]['size'] = 400
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'different PDK'):
                profiles.bind_stackup(q, stack)
        self.assertEqual(before, stack)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'coil.icproj'; save_project(p, path); q = load_project(path)
            self.assertEqual(q['pdk']['em_stackup'], stack)
            self.assertTrue(em.manifest(q, q['top'], did)['stackup_complete'])

    def test_context_requires_all_layers_and_scope_is_bound_to_results(self):
        p = fixture(); did = self.create(p)
        # The mapping is known to the PDK but has no physical material data.
        p['pdk']['layers'].append(dict(name='Neighbor', gds=200, datatype=0, color='#abcdef', width=200, space=200))
        p['pdk']['connectivity']['conductors'].append('Neighbor')
        p['pdk']['em_stackup'].pop('technology')
        p['pdk']['em_stackup'] = profiles.bind_stackup(p['pdk'], p['pdk']['em_stackup'])
        # Layer changes invalidate the winding rules too: regenerate first.
        inductor.install(p, inductor.plan(p, p['top'], inductor.defaults(p), did=did))
        p['cells'][0]['shapes'].append(rect('Neighbor', 400000, 0, 1000, 1000))
        context = em.manifest(p, p['top'], did)
        self.assertFalse(context['stackup_complete']); self.assertIn('Neighbor', ' '.join(context['missing']))
        with self.assertRaisesRegex(ValueError, 'Neighbor'): em.install_results(p, p['top'], did, results(context))
        isolated = em.manifest(p, p['top'], did, 'isolated'); self.assertTrue(isolated['stackup_complete'])
        data = {**results(isolated), 'scope': 'isolated'}; em.install_results(p, p['top'], did, data)
        self.assertIsNotNone(em.result_status(p, p['top'], did)[0])
        with self.assertRaises(ValueError): em.install_results(p, p['top'], did, {**data, 'scope': 'context'})

    def test_explicit_marker_exclusion_cannot_remove_known_conductors(self):
        p = fixture(); tech = p['pdk']; tech['layers'].append(dict(name='Annotation', gds=120, datatype=99, color='#abcdef', width=0, space=0))
        tech['em_stackup'].pop('technology'); tech['em_stackup']['excluded_layers'] = {'Annotation': 'Text outline only'}
        tech['em_stackup'] = profiles.bind_stackup(tech, tech['em_stackup']); did = self.create(p)
        p['cells'][0]['shapes'].append(rect('Annotation', 400000, 0, 1000, 1000))
        self.assertTrue(em.manifest(p, p['top'], did)['stackup_complete'])
        for name in ('RDL_A', 'Cut_AB'):
            stack = clone(tech['em_stackup']); stack['layout_map'].pop(name); stack['excluded_layers'][name] = 'Do not simulate'
            self.assertIn('cannot be excluded', ' '.join(profiles.readiness(tech, stack, [name])))
        stack = clone(tech['em_stackup']); stack['layout_map']['Cut_AB'] = 'Top copper'
        self.assertIn('expected physical via', ' '.join(profiles.readiness(tech, stack, ['Cut_AB'])))

    def test_missing_values_remain_unknown_and_material_models_are_explicit(self):
        tech = fixture()['pdk']; tech.pop('em_stackup'); tech['stack_3d'] = {'RDL_A': {'z_um': 999}}
        draft = profiles.template(tech)
        self.assertTrue(all(layer['z_um'] is None and layer['conductivity_s_m'] is None for layer in draft['layers']))
        self.assertFalse(profiles.capabilities(tech)['profile_ready'])
        with self.assertRaises(ValueError): profiles.bind_stackup(tech, draft)
        tech['routing_vias'] = []; self.assertFalse(profiles.capabilities(tech)['geometry'])
        stack = fixture()['pdk']['em_stackup']; stack['layers'][0]['dispersion'] = 'unknown model'
        with self.assertRaisesRegex(ValueError, 'unsupported'): profiles.validate_stackup(stack)
        for bad in ([], {'source': 'x', 'layers': []}, {**stack, 'layout_map': []}):
            with self.assertRaises(ValueError): profiles.validate_stackup(bad)

    def test_generic_profile_can_be_set_up_before_first_coil(self):
        from test_inductor_em import stackup
        p = example('empty'); p['pdk']['em_stackup'] = profiles.bind_stackup(p['pdk'], stackup())
        identity = clone(p['pdk']['em_stackup']['technology']); did = self.create(p)
        self.assertEqual(profiles.technology_identity(p['pdk']), identity)
        self.assertTrue(em.manifest(p, p['top'], did)['stackup_complete'])

    def test_xml_rejects_slab_gaps_and_reserved_material_names_are_escaped(self):
        p = fixture(); stack = p['pdk']['em_stackup']; stack['layers'][0]['name'] = 'PEC'
        stack['layout_map']['RDL_A'] = 'PEC'
        xml, _ = profiles.solver_stackup(stack, stack['layout_map']); root = ET.fromstring(xml)
        self.assertNotEqual(root.find("ELayers/Layers/Layer[@Name='PEC']").get('Material'), 'PEC')
        stack['layers'][-1]['thickness_um'] = 99
        with self.assertRaisesRegex(ValueError, 'contiguous'): profiles.solver_stackup(stack, stack['layout_map'])
        did = self.create(p)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'em.zip'; data = em.export_bundle(p, p['top'], did, path)
            self.assertTrue(data['stackup_complete']); self.assertFalse(data['solver_stackup_complete'])
            with zipfile.ZipFile(path) as archive:
                self.assertNotIn('solver-geometry.gds', archive.namelist())
                self.assertIn('contiguous', archive.read('solver-setup-missing.txt').decode())


if __name__ == '__main__': unittest.main()
