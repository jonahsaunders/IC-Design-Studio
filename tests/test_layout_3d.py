"""Independent area, volume, hierarchy and budget checks for layout extrusion."""
import math
import unittest
from unittest.mock import patch

from icstudio.design_ops import flatten_layout
from icstudio.layout import rect, polygon
from icstudio.layout_3d import build_mesh, extrude, stack_layers
from icstudio.model import clone, digest, example


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cap_area(triangles):
    return sum(abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])) / 2
               for a, b, c, normal in triangles if normal == (0, 0, 1))


def fixture():
    p = example('empty')
    p['cells'][0]['shapes'] = [
        rect('metal1', 0, 0, 10000, 1200),
        dict(id='ring', kind='polygon', layer='metal2', points=[[0,0],[10000,0],[10000,8000],[0,8000]],
             holes=[[[2000,2000],[8000,2000],[8000,6000],[2000,6000]]], net='ring'),
        dict(id='wire', kind='path', layer='poly', points=[[-2000,2000],[-2000,9000],[9000,9000]], width=800),
        rect('via1', 500, 200, 600, 600), rect('via1', 8900, 200, 600, 600)]
    return p


class Layout3DTests(unittest.TestCase):
    def test_units_area_volume_and_outward_winding(self):
        triangles = extrude(polygon(rect('metal1', 2000000000, -2000000000, 2000, 3000)), (2000000, -2000000))
        self.assertEqual(len(triangles), 12)
        self.assertAlmostEqual(cap_area(triangles), 6.)
        self.assertAlmostEqual(sum(dot(a, cross(b, c))/6 for a, b, c, _ in triangles), 6.)
        for a, b, c, normal in triangles:
            ab, ac = tuple(y-x for x, y in zip(a, b)), tuple(y-x for x, y in zip(a, c))
            self.assertGreater(dot(cross(ab, ac), normal), 0)
        self.assertEqual(max(v[0] for t in triangles for v in t[:3]), 2.)

    def test_hole_caps_and_inner_walls_are_exact(self):
        s = fixture()['cells'][0]['shapes'][1]
        triangles = extrude(polygon(s), (0, 0))
        self.assertAlmostEqual(cap_area(triangles), 56.)
        self.assertAlmostEqual(sum(dot(a, cross(b, c))/6 for a, b, c, _ in triangles), 56.)
        for a, b, c, normal in triangles:
            if normal == (0, 0, 1):
                x, y = (a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3
                self.assertFalse(2 < x < 8 and 2 < y < 6)

    def test_paths_concavity_and_project_are_preserved(self):
        p = fixture()
        before = digest(p)
        mesh = build_mesh(p, p['top'])
        for layer in mesh.layers:
            expected = sum(polygon(s).area()/1e6 for s in p['cells'][0]['shapes'] if s['layer'] == layer.name)
            self.assertAlmostEqual(cap_area(layer.triangles), expected)
        mesh.layers[0].z_um = -4
        self.assertEqual(digest(p), before)
        self.assertEqual(mesh.shape_count, 5)

    def test_nested_mirrored_rotated_arrays_match_flat_geometry(self):
        p = fixture()
        tile = p['cells'][0]
        middle = dict(id='middle', name='middle', ports=[], devices=[], shapes=[], layout_instances=[
            dict(id='inner', name='inner', cell=tile['id'], x=1000, y=3000, rotation=90, mirror=True,
                 nx=2, ny=2, a=[14000,2000], b=[-3000,13000])])
        top = dict(id='top3d', name='top3d', ports=[], devices=[], shapes=[], layout_instances=[
            dict(id='outer', name='outer', cell='middle', x=-10000, y=2000, rotation=270, mirror=True)])
        p['cells'].extend([middle, top]);p['top'] = top['id']
        actual = build_mesh(p, p['top'])
        q = clone(p);q['cells'][-1]['shapes'] = flatten_layout(p, p['top']);q['cells'][-1]['layout_instances'] = []
        for i, shape in enumerate(q['cells'][-1]['shapes']):
            shape['id'] = 'flat-' + str(i)
        expected = build_mesh(q, q['top'])
        self.assertEqual(actual.bounds_um, expected.bounds_um)
        self.assertEqual(actual.origin_um, expected.origin_um)
        for a, b in zip(actual.layers, expected.layers):
            self.assertEqual(sorted(a.triangles), sorted(b.triangles))
        self.assertEqual(actual.shape_count, 20)

    def test_crop_clips_material_and_can_cut_through_holes(self):
        p = fixture();p['cells'][0]['shapes'] = [p['cells'][0]['shapes'][1]]
        mesh = build_mesh(p, p['top'], (1000, 1000, 5000, 7000))
        self.assertTrue(mesh.cropped)
        self.assertEqual(mesh.origin_um, (3., 4.))
        self.assertAlmostEqual(cap_area(next(l.triangles for l in mesh.layers if l.name == 'metal2')), 12.)
        for layer in mesh.layers:
            for triangle in layer.triangles:
                for x, y, _ in triangle[:3]:
                    self.assertTrue(-2 <= x <= 2 and -3 <= y <= 3)

    def test_million_instances_refuse_full_view_but_crop_stays_small(self):
        p = example('empty');top = p['cells'][0]
        tile = dict(id='tile', name='tile', ports=[], devices=[], shapes=[rect('metal1', 0, 0, 600, 600)])
        p['cells'].append(tile)
        top['layout_instances'] = [dict(id='array', name='array', cell='tile', x=0, y=0,
                                       nx=1000, ny=1000, a=[2000,0], b=[0,2000])]
        with self.assertRaisesRegex(ValueError, 'No partial geometry'):
            build_mesh(p, p['top'])
        mesh = build_mesh(p, p['top'], (0, 0, 3500, 3500))
        self.assertEqual(mesh.expanded_count, 1000000)
        self.assertEqual(mesh.shape_count, 4)
        self.assertEqual(mesh.triangle_count, 48)

    def test_budget_rejects_instead_of_truncating_and_empty_is_valid(self):
        p = fixture()
        with patch('icstudio.layout_3d.MAX_TRIANGLES', 10):
            with self.assertRaisesRegex(ValueError, 'detail budget'):
                build_mesh(p, p['top'])
        with patch('icstudio.layout_3d.MAX_INPUT_VERTICES', 3):
            with self.assertRaisesRegex(ValueError, 'detail budget'):
                build_mesh(p, p['top'])
        self.assertEqual(build_mesh(p, p['top'], (100000,100000,200000,200000)).triangle_count, 0)
        empty = example('empty')
        self.assertEqual(build_mesh(empty, empty['top']).triangle_count, 0)
        for box in ((0,0,0,1), (0,0,math.inf,1)):
            with self.assertRaises(ValueError):build_mesh(p, p['top'], box)

    def test_stack_metadata_partial_defaults_and_validation(self):
        pdk = fixture()['pdk']
        pdk['stack_3d'] = dict(source='test coupon', layers=[dict(layer='metal1', z_um=-.1, thickness_um=.3)])
        layers, source = stack_layers(pdk)
        metal = next(l for l in layers if l.name == 'metal1')
        self.assertEqual((metal.z_um, metal.thickness_um, metal.illustrative), (-.1, .3, False))
        self.assertEqual(source, 'test coupon')
        self.assertTrue(layers[0].illustrative)
        for thickness in (0, -.1, float('nan'), float('inf'), 100001, 'bad'):
            pdk['stack_3d']['layers'][0]['thickness_um'] = thickness
            with self.assertRaises(ValueError):stack_layers(pdk)
        for entries in ([dict(layer='unknown', z_um=0, thickness_um=1)], [dict(layer='metal1')],
                        [dict(layer='metal1', z_um=0, thickness_um=1)]*2):
            pdk['stack_3d']['layers'] = entries
            with self.assertRaises(ValueError):stack_layers(pdk)


if __name__ == '__main__':
    unittest.main()
