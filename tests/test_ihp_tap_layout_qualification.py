from pathlib import Path
import tempfile,unittest
from scripts.qualify_ihp_tap_layouts import audit_native,detected


class TapLayoutAcceptanceTests(unittest.TestCase):
    def test_exact_extracted_geometry_and_terminal_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.cir';good='.subckt coupon TIE well\nR1 TIE well ntap1 A=4p P=8u\n.ends coupon\n'
            path.write_text(good);audit_native(path,'ntap1',2000,2000,'well','R')
            for bad in (good.replace('R1 TIE well','R1 well TIE'),good.replace('ntap1','ptap1'),good.replace('A=4p','A=4.1p'),good.replace('P=8u','P=8.1u'),good.replace('R1 TIE well ntap1 A=4p P=8u','')):
                path.write_text(bad)
                with self.assertRaises(ValueError):audit_native(path,'ntap1',2000,2000,'well','R')

    def test_pin_matching_failure_is_detected_without_accepting_engine_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'lvs').mkdir();log=root/'lvs/lvs.log'
            result=dict(status='failed',stages=[dict(name=n,status='passed' if n!='lvs' else 'failed') for n in ('preflight','layout_export','lvs')])
            log.write_text('Netlists match uniquely.\nFinal result: Top level cell failed pin matching.\n')
            self.assertTrue(detected(result,root,'terminal-swap'))
            for text in ('Tool executable missing.','Netlists match uniquely.\nCell pin lists are equivalent.'):
                log.write_text(text);self.assertFalse(detected(result,root,'terminal-swap'))
            result['status']='blocked';self.assertFalse(detected(result,root,'terminal-swap'))


if __name__=='__main__':unittest.main()
