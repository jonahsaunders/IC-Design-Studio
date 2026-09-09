"""Geometry expectations and independent finite-lattice snapping oracle."""
import random
import unittest
from icstudio.layout_snap import nearest_target, segment_point


class LayoutSnapTests(unittest.TestCase):
    def target(self, point, shapes, terminals=(), scale=1, visible=('metal1','metal2')):
        return nearest_target(point,shapes,terminals,5,scale,set(visible),'metal1')

    def test_all_rectangle_corners_edges_center_and_midpoints(self):
        shape={'id':'box','kind':'rect','layer':'metal1','points':[[0,0],[100,100]]}
        for pointer, expected, kind in [((98,2),(100,0),'Corner'),((2,98),(0,100),'Corner'),
                ((32,3),(30,0),'Edge'),((98,48),(100,50),'Midpoint'),((48,52),(50,50),'Center')]:
            with self.subTest(pointer=pointer):
                target=self.target(pointer,[shape]);self.assertEqual((target.point,target.kind),(expected,kind))

    def test_path_centerline_and_endpoints(self):
        shape={'id':'route','kind':'path','layer':'metal2','width':40,'points':[[0,0],[100,0],[100,100]]}
        for pointer, expected in [((32,3),(30,0)),((98,67),(100,65)),((102,98),(100,100))]:
            self.assertEqual(self.target(pointer,[shape]).point,expected)

    def test_polygon_hole_and_slanted_lattice(self):
        shape={'id':'poly','kind':'polygon','layer':'metal1','points':[[0,0],[100,75],[0,150]],
               'holes':[[[20,70],[20,100],[40,100],[40,70]]]}
        self.assertEqual(self.target((59,44),[shape]).point,(60,45))
        self.assertEqual(self.target((22,82),[shape]).point,(20,85))

    def test_transformed_path_uses_centerline(self):
        shape={'id':'instance','kind':'rect','layer':'metal1','points':[[80,0],[120,100]],'_snap_path':[(100,0),(100,100)]}
        target=self.target((102,33),[shape]);self.assertEqual((target.point,target.kind),((100,35),'Segment'))

    def test_hidden_targets_and_off_grid_terminals_are_ignored(self):
        terminals=[{'id':'hidden','layer':'metal2','point':[0,0]},{'id':'bad','layer':'metal1','point':[2,2]}]
        self.assertIsNone(self.target((1,1),[],terminals,visible=('metal1',)))

    def test_active_layer_breaks_coincident_ties_and_terminal_wins(self):
        shapes=[{'id':layer,'kind':'rect','layer':layer,'points':[[0,0],[100,100]]} for layer in ('metal2','metal1')]
        terminal={'id':'pin','layer':'metal1','point':[0,0]}
        self.assertEqual(self.target((2,2),shapes).layer,'metal1')
        self.assertEqual(self.target((2,2),shapes,[terminal]).kind,'Terminal')

    def test_screen_tolerance_and_distance_priority(self):
        terminals=[{'id':'a','layer':'metal1','point':[0,0]},{'id':'b','layer':'metal2','point':[100,0]}]
        self.assertIsNone(self.target((9,0),[],terminals))
        self.assertEqual(self.target((90,0),[],terminals,scale=.1).point,(100,0))
        self.assertIsNone(self.target((45,45),[],terminals,scale=1))

    def test_exact_segment_solution_matches_exhaustive_grid_oracle(self):
        rng=random.Random(928)
        for _ in range(600):
            a=tuple(rng.randint(-20,20) for _ in range(2));b=tuple(rng.randint(-20,20) for _ in range(2))
            pointer=tuple(rng.uniform(-30,30) for _ in range(2));grid=rng.choice((1,2,3,5))
            candidates=[(x,y) for x in range(-20,21) for y in range(-20,21)
                if x%grid==y%grid==0 and min(a[0],b[0])<=x<=max(a[0],b[0]) and min(a[1],b[1])<=y<=max(a[1],b[1])
                and (x-a[0])*(b[1]-a[1])==(y-a[1])*(b[0]-a[0])]
            distance=lambda p:sum((p[i]-pointer[i])**2 for i in range(2))
            actual=segment_point(a,b,pointer,grid)
            if not candidates:self.assertIsNone(actual,(a,b,pointer,grid))
            else:self.assertAlmostEqual(distance(actual),min(map(distance,candidates)),msg=str((a,b,pointer,grid)))


if __name__=='__main__':unittest.main()
