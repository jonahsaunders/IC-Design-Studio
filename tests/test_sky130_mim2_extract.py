"""Actual native extraction regression inputs and destructive fault controls."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

import klayout.db as db
from icstudio.model import file_digest
from icstudio.sky130_mim2_extract import normalize, required, electrodes, MARKER

FIXTURES=Path(__file__).parent/'fixtures/sky130-mim2-orientation-v1'


class MimOrientationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.tech=self.root/'sky130A.tech';self.tech.write_text('technology fixture')
        self.tech.with_suffix('.tcl').write_text('pcell fixture')
        self.enterContext(patch('icstudio.sky130_mim2_extract.TECH',file_digest(self.tech)))
        self.enterContext(patch('icstudio.sky130_mim2_extract.PCELL',file_digest(self.tech.with_suffix('.tcl'))))

    def input(self,name='1-90',suffix=''):
        dest=self.root/(name+suffix);shutil.copytree(FIXTURES/name,dest)
        return dest

    def normalize(self,dest,scale=10):
        return normalize(dest/'layout.gds','device_coupon',self.tech,dest,f'STUDIO_MIM_SCALE {scale/1000}\n')

    def fail_without_changes(self,dest,pattern,scale=10):
        original=(dest/'device_coupon.ext').read_bytes()
        with self.assertRaisesRegex(ValueError,pattern):self.normalize(dest,scale)
        self.assertEqual((dest/'device_coupon.ext').read_bytes(),original)
        self.assertFalse((dest/'native-original.ext').exists())
        self.assertFalse((dest/'mim-orientation.json').exists())

    def test_actual_native_records_preserve_everything_except_axis_tokens(self):
        provenance=json.loads((FIXTURES/'provenance.json').read_bytes())
        for case in provenance['cases']:
            with self.subTest(case=case['name']):
                dest=self.input(case['name']);original=(dest/'device_coupon.ext').read_bytes()
                for name,sha in case['files'].items():self.assertEqual(file_digest(dest/name),sha)
                self.assertTrue(required(dest/'layout.gds','device_coupon'))
                proof=self.normalize(dest,case['coordinate_nm']);text=(dest/'device_coupon.ext').read_text()
                w,l=map(float,re.search(r'^device csubckt \S+ .*? w=(\S+) l=(\S+)',text,re.M).groups())
                self.assertEqual([w*case['coordinate_nm']/1000,l*case['coordinate_nm']/1000],case['dimensions_um'])
                self.assertEqual((dest/'native-original.ext').read_bytes(),original)
                self.assertEqual(len(proof['changes']),int(case['angle']==90))
                expected=original.decode()
                for change in proof['changes']:expected=expected.replace(change['before'],change['after'])
                self.assertEqual(text,expected)
                self.assertEqual(file_digest(dest/'device_coupon.ext'),proof['corrected_sha256'])
                with self.assertRaisesRegex(ValueError,'already normalized|dimensions disagree'):self.normalize(dest,case['coordinate_nm'])
                self.assertEqual((dest/'native-original.ext').read_bytes(),original)

    def test_incorrect_missing_duplicate_and_hierarchical_native_records_are_rejected(self):
        mutations=[('w=1000 l=200','w=999 l=200','dimensions disagree'),
                   ('-1000 0 -999 1 w=','-9000 0 -8999 1 w=','location'),
                   ('device csubckt','device unknown','every electrode')]
        for i,(old,new,message) in enumerate(mutations):
            dest=self.input(suffix=str(i));p=dest/'device_coupon.ext';text=p.read_text()
            self.assertIn(old,text);p.write_text(text.replace(old,new));self.fail_without_changes(dest,message)
        dest=self.input(suffix='duplicate');p=dest/'device_coupon.ext'
        line=next(s for s in p.read_text().splitlines() if s.startswith('device csubckt'))
        p.write_text(p.read_text()+line+'\n');self.fail_without_changes(dest,'unused electrode')
        dest=self.input(suffix='hierarchy');p=dest/'device_coupon.ext';p.write_text(p.read_text()+'use child id 1 0 0 0 1 0\n')
        self.fail_without_changes(dest,'flattened')

    def test_unreviewed_sources_and_scale_fail_before_output(self):
        for i,scale in enumerate((0,1,20,float('nan'),float('inf'))):
            self.fail_without_changes(self.input(suffix=str(i)),'scale',scale)
        for i,path in enumerate((self.tech,self.tech.with_suffix('.tcl'))):
            original=path.read_bytes();path.write_bytes(original+b'changed')
            self.fail_without_changes(self.input(suffix='source'+str(i)),'reviewed SKY130');path.write_bytes(original)

    def test_missing_and_ambiguous_actual_bottom_contacts_are_rejected(self):
        for kind in ('missing','ambiguous','shared'):
            dest=self.input('1-0',kind);ly=db.Layout();ly.read(str(dest/'layout.gds'));cell=ly.top_cell()
            cap=db.Region(cell.shapes(ly.layer(97,44)))
            cuts=cell.shapes(ly.layer(71,44));regions=db.Region(cuts);cuts.clear()
            cuts.insert(regions & cap)
            if kind!='missing':cuts.insert(regions-cap)
            if kind=='ambiguous':
                cell.shapes(ly.layer(71,20)).insert(db.Box(0,10000,2000,14000))
                cuts.insert(db.Box(600,12000,1400,12800))
            if kind=='shared':
                cell.shapes(ly.layer(97,44)).insert(db.Box(10000,0,12000,10000))
                cell.shapes(ly.layer(71,20)).insert(db.Box(0,-500,15000,10500))
            ly.write(str(dest/'layout.gds'))
            self.fail_without_changes(dest,'exactly one axis|Shared MiM')

    def test_electrode_direction_survives_all_orthogonal_transforms_and_parallel_units(self):
        from tests.test_sky130_mim2 import fixture
        from icstudio.interchange import export_layout
        p,_,_=fixture(3.005,5.005,3);original=self.root/'generated.gds';export_layout(p,original)
        for mirror in (False,True):
            for angle in range(4):
                ly=db.Layout();ly.read(str(original));ly.top_cell().transform(db.Trans(angle,mirror,123000,-456000))
                path=self.root/f'{mirror}-{angle}.gds';ly.write(str(path))
                dbu,rows=electrodes(path,ly.top_cell().name)
                self.assertEqual(len(rows),3)
                for row in rows:
                    x1,y1,x2,y2=row['box'];sizes=[(x2-x1)*dbu,(y2-y1)*dbu]
                    if row['axis']=='y':sizes.reverse()
                    self.assertEqual(sizes,[3.005,5.005])

    def test_fresh_magic_export_cannot_overwrite_corrected_extraction(self):
        from icstudio.silicon_flow import magic_script
        from icstudio.external_tools import extraction_commands
        dest=self.input();calls=[]
        def engine(command,cwd,**kwargs):
            script=kwargs['input_text'];calls.append(script)
            if len(calls)==1:
                self.assertIn('extract all',script);self.assertNotIn('ext2spice -o',script)
                return 'STUDIO_MIM_SCALE 0.01\nSTUDIO_MAGIC_COMPLETE\n'
            self.assertNotIn('extract all',script);self.assertIn('ext2spice scale off',script)
            self.assertIn('w=200 l=1000',(dest/'device_coupon.ext').read_text())
            return 'STUDIO_MAGIC_COMPLETE\n'
        commands,_=extraction_commands()
        with patch('icstudio.silicon_flow.execute',side_effect=engine):
            magic_script('magic',self.tech,dest/'layout.gds','device_coupon',['P','N'],dest,commands+'ext2spice -o extracted.spice')
        self.assertEqual(len(calls),2)

    def test_unqualified_rc_cannot_silently_bypass_orientation(self):
        from icstudio.silicon_flow import magic_script
        from icstudio.external_tools import extraction_commands
        dest=self.input();commands,_=extraction_commands('rc')
        with patch('icstudio.silicon_flow.execute') as execute:
            with self.assertRaisesRegex(ValueError,'distributed RC'):
                magic_script('magic',self.tech,dest/'layout.gds','device_coupon',['P','N'],dest,commands)
            execute.assert_not_called()


class MimDispatchShapeTests(unittest.TestCase):
    """Dispatch guards only; synthetic masks do not establish DRC/signoff validity."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def layout(self, entries, hierarchy=False):
        ly = db.Layout(); ly.dbu = .001; top = ly.create_cell('coupon')
        cell = ly.create_cell('child') if hierarchy else top
        for index, (plate, kind, side) in enumerate(entries):
            region = db.Region(db.Box(0, 0, side, side))
            if kind == 'l': region -= db.Region(db.Box(side//2, side//2, side, side))
            elif kind == 'hole': region -= db.Region(db.Box(side//3, side//3, 2*side//3, 2*side//3))
            elif kind == 'rectangle': region = db.Region(db.Box(0, 0, side, 2*side))
            cell.shapes(ly.layer(89 if plate == 1 else 97, 44)).insert(
                region.transformed(db.Trans(index*100000, 0)))
        if hierarchy:
            top.insert(db.CellInstArray(cell.cell_index(), db.Trans(1, True, 50000, 70000)))
        path = self.root/'layout.gds'; ly.write(str(path)); return path

    def reject_before_engine(self, entries, hierarchy=False):
        from icstudio.external_tools import extraction_commands
        from icstudio.silicon_flow import magic_script
        path = self.layout(entries, hierarchy)
        with self.assertRaisesRegex(ValueError, 'separate rectangular electrodes'):
            required(path, 'coupon')
        for mode in ('lvs', 'rc'):
            commands, _ = extraction_commands(mode)
            with patch('icstudio.silicon_flow.execute') as engine:
                with self.assertRaisesRegex(ValueError, 'separate rectangular electrodes'):
                    magic_script('magic', self.root/'sky130A.tech', path, 'coupon', [],
                                 self.root/'dispatch', commands)
                engine.assert_not_called()

    def test_square_bounding_box_l_and_hole_are_rejected_before_native_dispatch(self):
        for plate in (1, 2):
            for kind in ('l', 'hole'):
                with self.subTest(plate=plate, kind=kind):
                    self.reject_before_engine([(plate, kind, 6000)])

    def test_all_models_and_polygons_are_checked_after_a_nonsquare_is_seen(self):
        for first, second in ((1, 2), (2, 1), (1, 1), (2, 2)):
            for reverse in (False, True):
                entries = [(first, 'rectangle', 2000), (second, 'l', 6000)]
                with self.subTest(models=(first, second), reverse=reverse):
                    self.reject_before_engine(entries[::-1] if reverse else entries)

    def test_recursive_transformed_shape_cannot_bypass_dispatch(self):
        for plate in (1, 2):
            self.reject_before_engine([(plate, 'hole', 6000)], hierarchy=True)

    def test_true_squares_keep_native_lvs_and_rc_dispatch_without_new_size_limits(self):
        from icstudio.external_tools import extraction_commands
        from icstudio.silicon_flow import magic_script
        # These include shapes outside the generator domain. Native dispatch is
        # preserved, not asserted to qualify those shapes electrically/physically.
        for plate in (1, 2):
            for side in (1995, 2000, 2001, 30005, 31000):
                path = self.layout([(plate, 'square', side)])
                self.assertFalse(required(path, 'coupon'))
                rows = electrodes(path, 'coupon', f'sky130_fd_pr__cap_mim_m3_{plate}')[1]
                self.assertIsNone(rows[0]['axis'])
                for mode in ('lvs', 'rc'):
                    commands, _ = extraction_commands(mode)
                    with self.subTest(plate=plate, side=side, mode=mode):
                        with patch('icstudio.silicon_flow.execute', side_effect=RuntimeError('intercepted native')) as engine:
                            with self.assertRaisesRegex(RuntimeError, 'intercepted native'):
                                magic_script('magic', self.root/'sky130A.tech', path, 'coupon', [],
                                             self.root/f'dispatch-{plate}-{side}-{mode}', commands)
                            self.assertEqual(engine.call_count, 1)
                            self.assertNotIn(MARKER, engine.call_args.kwargs['input_text'])


if __name__=='__main__':unittest.main()
