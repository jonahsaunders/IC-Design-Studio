"""A public baseline pass needs every validated component and explicit context."""
from pathlib import Path
import tempfile
import unittest
from icstudio.digital_sky130_public_baseline import PROFILE, REQUIRED, summarize
from icstudio.digital_macro import export
from tests import test_digital_macro as macro


class PublicBaselineTests(unittest.TestCase):
    def fixture(self, full=9):
        verified={key:dict(status='PASS') for key in REQUIRED}
        verified['sky130_rules']['status']='reviewed-profiles-pass'
        verified['sky130_isolation']['status']='NOT_REQUESTED'
        verified['sky130_density']=dict(status='sampled-full-windows-pass' if full else 'surrounding-layout-required',
            full_windows=full,full_window_findings=0)
        data=dict(platform=dict(name='sky130hd',fingerprint='b'*64),
            artifacts={key:dict(sha256='a'*64) for key in (*REQUIRED,'gds','checkpoint')})
        return data,verified,dict(top='arbitrary_top',physical={})

    def test_full_window_baseline_has_no_foundry_or_complete_rule_claim(self):
        result=summarize(*self.fixture())
        self.assertEqual(result['status'],'public-checks-passed')
        self.assertTrue(result['baseline_checks_passed']);self.assertTrue(result['density_context_complete'])
        self.assertFalse(result['foundry_signoff']);self.assertFalse(result['complete_rule_coverage'])
        self.assertEqual(result['top'],'arbitrary_top');self.assertEqual(len(result['evidence']),len(REQUIRED))
        result['profile']['exclusions'].clear()
        self.assertTrue(PROFILE['exclusions'])

    def test_small_block_keeps_its_surrounding_layout_obligation(self):
        result=summarize(*self.fixture(full=0))
        self.assertEqual(result['status'],'surrounding-layout-required')
        self.assertTrue(result['baseline_checks_passed']);self.assertFalse(result['density_context_complete'])

    def test_every_missing_check_prevents_baseline_pass(self):
        for key in REQUIRED:
            data,verified,config=self.fixture();verified[key]=None
            result=summarize(data,verified,config)
            with self.subTest(key=key):
                self.assertEqual(result['status'],'incomplete');self.assertEqual(result['missing_checks'],[key])
                self.assertFalse(result['baseline_checks_passed'])

    def test_failed_and_unbound_checks_cannot_be_summarized_as_passed(self):
        for key in REQUIRED:
            for fault in ('failed','missing-artifact'):
                data,verified,config=self.fixture()
                if fault=='failed':verified[key]['status']='FAIL'
                else:del data['artifacts'][key]
                with self.subTest(key=key,fault=fault),self.assertRaises(ValueError):summarize(data,verified,config)

    def test_requested_fill_requires_independent_fill_evidence(self):
        data,verified,config=self.fixture();config['physical']['sky130_fill']=True
        self.assertEqual(summarize(data,verified,config)['missing_checks'],['sky130_fill'])
        verified['sky130_fill']=dict(status='generated-and-checked');data['artifacts']['sky130_fill']=dict(sha256='c'*64)
        self.assertEqual(summarize(data,verified,config)['status'],'public-checks-passed')

    def test_inconsistent_density_counts_are_rejected(self):
        for changes in (dict(full_windows=0),dict(full_windows=True),dict(full_windows=-1),dict(full_window_findings=1)):
            data,verified,config=self.fixture();verified['sky130_density'].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):summarize(data,verified,config)

    def test_other_pdks_have_no_sky130_claim(self):
        data,verified,config=self.fixture();data['platform']['name']='gf180mcuD'
        self.assertIsNone(summarize(data,verified,config))

    def test_historical_export_cannot_inherit_baseline_qualification(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result=macro.DigitalMacroTests().fixture(root,name='sky130hd')
            contract=export(result,root,root/'macro.zip')
            baseline=contract['qualification']['sky130_public_baseline']
            self.assertEqual(baseline['status'],'incomplete')
            self.assertEqual(baseline['missing_checks'],list(REQUIRED))


if __name__=='__main__':unittest.main()
