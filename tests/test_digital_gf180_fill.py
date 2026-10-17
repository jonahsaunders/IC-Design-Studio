"""Fill must preserve circuit masks and signal RC, and reject stale evidence."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from icstudio import digital_fill_spef as spef, digital_gf180_fill as fill
from icstudio.digital_physical import DEFAULTS, validate_settings
from icstudio import digital_identity, digital_rc

SPEF = '''*SPEF "IEEE 1481-1998"
*DESIGN "block"
*R_UNIT 1 OHM
*C_UNIT 1 PF
*NAME_MAP
*1 out
*2 ICSTUDIO_FLOAT_0000
*PORTS
*1 O
*D_NET *1 4
*CONN
*P *1 O
*CAP
1 *1 1
2 *1:1 1
3 *1 *2:1 2
*RES
1 *1 *1:1 3
*END
*D_NET *2 4
*CONN
*N *2:1 *C 1 1
*CAP
1 *2:1 1
2 *2:2 1
3 *1 *2:1 2
*RES
1 *2:1 *2:2 .79
*END
'''


class FloatingSpefTests(unittest.TestCase):
    def test_reduction_preserves_signal_records_and_analytical_capacitance(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'raw.spef';target=Path(td)/'timing.spef';source.write_text(SPEF)
            before=spef.parse(source)
            spef.reduce(source,target,{'ICSTUDIO_FLOAT_0000'})
            after=spef.parse(target)
            self.assertEqual(set(after['nets']),{'out'})
            self.assertEqual(after['nets']['out']['conn'],before['nets']['out']['conn'])
            self.assertEqual(after['nets']['out']['res'],before['nets']['out']['res'])
            self.assertAlmostEqual(float(after['nets']['out']['ground']['out']),2.)
            self.assertNotIn('ICSTUDIO_FLOAT_',target.read_text())

    def test_incomplete_or_inconsistent_extraction_is_rejected(self):
        mutations=[SPEF.rsplit('*END',1)[0], SPEF.replace('*R_UNIT 1 OHM','*R_UNIT 1 KOHM'),
            SPEF.replace('3 *1 *2:1 2\n*RES\n1 *2','*RES\n1 *2'),
            SPEF.replace('1 *2:1 *2:2 .79','1 *2:1 *2:2 NaN'),
            SPEF.replace('*D_NET *1 4','*D_NET *1 400'),
            SPEF.replace('*2 ICSTUDIO_FLOAT_0000','*1 ICSTUDIO_FLOAT_0000'),
            SPEF.replace('3 *1 *2:1 2','3 *1 *9:1 2')]
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bad.spef'
            for text in mutations:
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ValueError):spef.parse(path)

    def test_a_floating_square_cannot_have_a_circuit_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bad.spef';path.write_text(SPEF.replace('*N *2:1 *C 1 1','*I *2:1 I'))
            with self.assertRaisesRegex(ValueError,'isolated'):spef.reduce(path,Path(td)/'out.spef',{'ICSTUDIO_FLOAT_0000'})


class FillIntegrationTests(unittest.TestCase):
    def test_setting_validation_and_checkpoint_invalidation(self):
        validate_settings({'gf180_fill':True})
        for value in (1,'yes',None):
            with self.assertRaises(ValueError):validate_settings({'gf180_fill':value})
        with self.assertRaises(ValueError):validate_settings({'gf180_fill':True,'pdn_tcl':'custom'})
        cfg=dict(top='top',files=[],physical={})
        old=digital_identity.stage_key(cfg,'floorplan');cfg['physical']['gf180_fill']=True
        self.assertNotEqual(old,digital_identity.stage_key(cfg,'floorplan'))

    def test_timing_rejects_a_prefill_job(self):
        r=SimpleNamespace(settings={'upstream':{'artifacts':{'spef':{}}}},config={'physical':{'gf180_fill':True}})
        with self.assertRaisesRegex(ValueError,'finish'):digital_rc.timing_sources(r)

    def test_native_roundtrip_preserves_masks_and_marker_clearance(self):
        import klayout.db as k
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'before.gds';target=Path(td)/'after.gds'
            layout=k.Layout();layout.dbu=.001;top=layout.create_cell('block')
            top.shapes(layout.layer(63,0)).insert(k.Box(0,0,100000,100000))
            top.shapes(layout.layer(34,0)).insert(k.Box(5000,2000,6000,98000))
            top.shapes(layout.layer(75,0)).insert(k.Box(85000,2000,90000,5000))
            layout.write(str(source));before=source.read_bytes()
            boxes=fill.write_fill(source,target,'block',DEFAULTS)
            self.assertTrue(boxes);self.assertEqual(source.read_bytes(),before)
            after=k.Layout();after.read(str(target));cell=after.top_cell()
            for number in (34,75):
                a=k.Region(top.begin_shapes_rec(layout.layer(number,0)))
                b=k.Region(cell.begin_shapes_rec(after.layer(number,0)))
                self.assertTrue((a^b).is_empty())
            with self.assertRaisesRegex(ValueError,'unfilled'):fill.write_fill(target,Path(td)/'twice.gds','block',DEFAULTS)

    def test_timing_bindings_reject_old_spef_and_settings(self):
        with tempfile.TemporaryDirectory() as td:
            artifacts={'fill':{'path':'fill.json'},'gds':{'sha256':'filled'},'spef':{'sha256':'after'},
                       'netlist':{'sha256':'logic'},'fill_represented_odb':{'sha256':'geometry'}}
            cfg={'platform':{'fingerprint':'p'},'physical':{'gf180_fill':True}}
            report=dict(schema=1,recipe=fill.RECIPE,status='generated_and_extracted',settings={**DEFAULTS,**cfg['physical']},
                platform_fingerprint='p',gds=artifacts['gds'],spef=artifacts['spef'],source={'netlist':artifacts['netlist']},
                model_artifacts={'fill_represented_odb':artifacts['fill_represented_odb']})
            path=Path(td)/'fill.json';path.write_text(json.dumps(report));up={'root':td,'artifacts':artifacts}
            fill.verify(up,cfg)
            artifacts['spef']={'sha256':'before'}
            with self.assertRaisesRegex(ValueError,'parasitics'):fill.verify(up,cfg)
            artifacts['spef']=report['spef'];cfg['physical']['die_area']=[0,0,200,200]
            with self.assertRaisesRegex(ValueError,'settings'):fill.verify(up,cfg)


if __name__=='__main__':unittest.main()
