"""First-MiM native failure regression and cross-family mask controls."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch
import klayout.db as db
from icstudio.model import file_digest
from icstudio.sky130_mim2_extract import electrodes, masks, normalize, required

FIXTURES=Path(__file__).parent/'fixtures/sky130-mim1-orientation-v1'
MODEL='sky130_fd_pr__cap_mim_m3_1'


class FirstMimOrientationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.tech=self.root/'sky130A.tech';self.tech.write_text('test technology')
        self.tech.with_suffix('.tcl').write_text('test pcell')
        self.enterContext(patch('icstudio.sky130_mim2_extract.TECH',file_digest(self.tech)))
        self.enterContext(patch('icstudio.sky130_mim2_extract.PCELL',file_digest(self.tech.with_suffix('.tcl'))))

    def fixture(self,angle=90,suffix=''):
        dest=self.root/(str(angle)+suffix);shutil.copytree(FIXTURES/str(angle),dest);return dest

    def normalize(self,dest):
        return normalize(dest/'layout.gds','device_coupon',self.tech,dest,'STUDIO_MIM_SCALE 0.01\n')

    def test_actual_first_plate_native_records_and_original_failure(self):
        provenance=json.loads((FIXTURES/'provenance.json').read_bytes())
        for case in provenance['cases']:
            dest=self.fixture(case['angle'])
            for name,sha in case['files'].items():self.assertEqual(file_digest(dest/name),sha)
            self.assertTrue(required(dest/'layout.gds','device_coupon'))
            old=(dest/'device_coupon.ext').read_bytes();proof=self.normalize(dest)
            self.assertEqual(proof['models'],[MODEL]);self.assertEqual(proof['model'],MODEL)
            self.assertEqual((dest/'native-original.ext').read_bytes(),old)
            self.assertEqual(len(proof['changes']),int(case['angle']==90))
            expected=old.decode()
            for change in proof['changes']:expected=expected.replace(change['before'],change['after'])
            self.assertEqual((dest/'device_coupon.ext').read_text(),expected)
            self.assertRegex(expected,r'device csubckt '+MODEL+r'.* w=200 l=1000 ')
            self.assertIn('STUDIO_DRC_COUNT 0',(dest/'console.log').read_text())
            if case['angle']==90:self.assertIn('Property errors were found',(dest/'lvs.log').read_text())

    def test_all_transforms_and_parallel_first_plate_electrodes(self):
        from tests.test_sky130_devices import technology
        from scripts.qualify_sky130_mim2 import fixture
        from icstudio.interchange import export_layout
        p=fixture(technology(),(3.005,5.005,3),plate=1)
        original=self.root/'original.gds';export_layout(p,original)
        for mirror in (False,True):
            for angle in range(4):
                ly=db.Layout();ly.read(str(original));ly.top_cell().transform(db.Trans(angle,mirror,123000,-456000))
                path=self.root/f'{mirror}-{angle}.gds';ly.write(str(path))
                dbu,rows=electrodes(path,'device_coupon',MODEL);self.assertEqual(len(rows),3)
                for row in rows:
                    x1,y1,x2,y2=row['box'];sizes=[(x2-x1)*dbu,(y2-y1)*dbu]
                    if row['axis']=='y':sizes.reverse()
                    self.assertEqual(sizes,[3.005,5.005]);self.assertEqual(row['model'],MODEL)

    def test_wrong_native_model_and_wrong_layer_contacts_fail_without_mutation(self):
        for fault in ('model','contacts','size','duplicate'):
            dest=self.fixture(suffix=fault);native=dest/'device_coupon.ext'
            if fault=='model':native.write_text(native.read_text().replace(MODEL,MODEL[:-1]+'2'))
            elif fault=='size':native.write_text(native.read_text().replace('w=1000 l=200','w=1001 l=200'))
            elif fault=='duplicate':
                text=native.read_text();native.write_text(text+next(s for s in text.splitlines() if s.startswith('device csubckt'))+'\n')
            else:
                ly=db.Layout();ly.read(str(dest/'layout.gds'));cell=ly.top_cell()
                caps=db.Region(cell.shapes(ly.layer(89,44)));cuts=db.Region(cell.shapes(ly.layer(70,44)))
                cell.shapes(ly.layer(70,44)).clear();cell.shapes(ly.layer(70,44)).insert(cuts&caps)
                cell.shapes(ly.layer(71,44)).insert(cuts-caps);ly.write(str(dest/'layout.gds'))
            original=native.read_bytes()
            with self.assertRaisesRegex(ValueError,'unused electrode|dimensions disagree|exactly one axis'):self.normalize(dest)
            self.assertEqual(native.read_bytes(),original);self.assertFalse((dest/'native-original.ext').exists())

    def test_first_plate_distributed_rc_cannot_bypass_orientation(self):
        from icstudio.silicon_flow import magic_script
        from icstudio.external_tools import extraction_commands
        dest=self.fixture();commands,_=extraction_commands('rc')
        with patch('icstudio.silicon_flow.execute') as execute:
            with self.assertRaisesRegex(ValueError,'distributed RC'):
                magic_script('magic',self.tech,dest/'layout.gds','device_coupon',['P','N'],dest,commands)
            execute.assert_not_called()

    def test_top_cuts_keep_full_edge_margin_at_every_pitch_residue(self):
        from tests.test_sky130_devices import technology
        from icstudio.catalog import create_device
        from icstudio.sky130_devices import geometry
        tech=technology();device=create_device(tech,'sky130_fd_pr/cap_mim_m3_1.sym','C1')
        # All eighty 5 nm residues of the 400 nm contact pitch, plus bounds.
        for w in [2000,30000,*range(2800,3200,5)]:
            l=6005 if w==30000 else 5005;device['model_params'].update(w=w/1000,l=l/1000)
            cuts=[s for s in geometry(tech,device)['shapes'] if s.get('generator_role','').startswith('passive:top_via_')]
            self.assertTrue(cuts)
            for cut in cuts:
                xs,ys=zip(*cut['points'])
                self.assertEqual([max(xs)-min(xs),max(ys)-min(ys)],[200,200])
                self.assertTrue(min(xs)>=300 and max(xs)<=w-300 and min(ys)>=300 and max(ys)<=l-300)


if __name__=='__main__':unittest.main()
