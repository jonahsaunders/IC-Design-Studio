import unittest
from types import SimpleNamespace
from icstudio.grid import GridMixin
from icstudio.grid_settings import spacing_nm


class Grid(GridMixin):
    def __init__(self):
        self.mode='layout';self.tech={'grid':5};self.scale=.08
        self.view_changed=SimpleNamespace(emit=lambda:None)


class DrawingGridTests(unittest.TestCase):
    def test_visible_grid_is_default_snap_at_all_scales(self):
        c=Grid()
        for grid in (5,7,10):
            c.tech['grid']=grid
            for scale in (.0001,.003,.08,.73,1,5,20):
                c.scale=scale
                self.assertEqual(c.snap_interval(),c.grid_interval())
                self.assertEqual(c.snap_interval()%grid,0)

    def test_fixed_spacing_and_display_thinning_are_separate(self):
        c=Grid();c.grid_snap_mode='fixed';c.grid_snap_step=50
        for scale in (.001,.08,.9,20):
            c.scale=scale;self.assertEqual(c.snap_interval(),50)
            self.assertEqual(c.grid_interval()%50,0)

    def test_grid_visibility_does_not_change_snapping(self):
        c=Grid();spacing=c.snap_interval();c.grid_style='off'
        self.assertEqual(c.snap_interval(),spacing);self.assertTrue(c.grid_snap_active())

    def test_active_draft_freezes_zoom_and_pending_setting_changes(self):
        c=Grid();c.begin_drawing_grid();before=(c.grid_snap_active(),c.snap_interval(),c.grid_interval())
        c.scale*=4;c.grid_snap_enabled=False;c.grid_snap_mode='fixed';c.grid_snap_step=50
        self.assertEqual(before,(c.grid_snap_active(),c.snap_interval(),c.grid_interval()))
        c.end_drawing_grid();self.assertFalse(c.grid_snap_active());self.assertEqual(c.snap_interval(),50)

    def test_spacing_is_exact_and_invalid_values_are_rejected(self):
        self.assertEqual(spacing_nm('0.050',5),50);self.assertEqual(spacing_nm('1e-2',5),10)
        for value in ('0','-1','nan','Infinity','0.003','0.0005','abc','1000001'):
            with self.subTest(value=value),self.assertRaises(ValueError):spacing_nm(value,5)

    def test_changed_technology_keeps_a_valid_fixed_step(self):
        c=Grid();c.grid_snap_mode='fixed';c.grid_snap_step=50;c.tech['grid']=7
        self.assertEqual(c.snap_interval()%7,0)


if __name__=='__main__':unittest.main()
