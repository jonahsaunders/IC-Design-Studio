from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_gf180_banba_physical as physical
from scripts.verify_gf180_banba_physical import cdl, check_extracted, fix_pnp_technology, drc_results


REFERENCE = '''.subckt banba_layout VDD VSS VREF
X_M VREF CTRL VSS VSS nfet_03v3 w=4u l=2u m=1 nf=1
X_Q VSS VSS VA pnp_05p00x05p00 m=1
X_R VA VREF VSS ppolyf_u_1k r_width=1u r_length=100u m=1
X_C VREF VSS cap_mim_2f0_m3m4_noshield c_width=90u c_length=90u m=1
.ends banba_layout
'''


class PhysicalReferenceTests(unittest.TestCase):
    def test_reader_keeps_terminal_order_and_geometry(self):
        text = cdl(REFERENCE)
        self.assertIn('Q_Q VSS VSS VA pnp_05p00x05p00', text)
        self.assertIn('R_R VA VREF VSS ppolyf_u_1k w=1e-06 l=0.0001', text)
        self.assertIn('C_C VREF VSS cap_mim_2f0_m3m4_noshield w=9e-05 l=9e-05', text)

    def test_multiplicity_is_never_silently_lost(self):
        for field in ('m=2', 'nf=2'):
            with self.assertRaisesRegex(ValueError, 'multiplicity'):
                cdl(REFERENCE.replace(field.split('=')[0]+'=1', field, 1))

    def test_symmetric_devices_and_extracted_junctions_are_accepted(self):
        extracted = REFERENCE.replace('VREF CTRL VSS VSS nfet', 'VSS CTRL VREF VSS nfet')
        extracted = extracted.replace('VA VREF VSS ppoly', 'VREF VA VSS ppoly')
        extracted = extracted.replace('w=4u l=2u', 'w=4u l=2u ad=3.2p pd=9.6u')
        extracted += 'C0 VREF VSS 0.23p\n'
        result = check_extracted(REFERENCE, extracted)
        self.assertEqual(result['devices'], 4)
        self.assertEqual(result['capacitances'], 1)
        self.assertAlmostEqual(result['total_capacitance_f']/1e-12, .23)

    def test_faults_are_rejected_before_simulation(self):
        faults = [REFERENCE.replace('VREF CTRL', 'VREF VSS'),
                  REFERENCE.replace('r_length=100u', 'r_length=99u'),
                  REFERENCE.replace('pnp_05p00x05p00', 'pnp_10p00x00p42'),
                  REFERENCE.replace('X_Q VSS VSS VA pnp_05p00x05p00 m=1\n', ''),
                  REFERENCE.replace('.subckt banba_layout VDD VSS VREF', '.subckt banba_layout VDD VSS'),
                  REFERENCE+'Cbad VREF VSS -1p\n']
        for faulty in faults:
            with self.subTest(fault=faulty), self.assertRaises(ValueError):
                check_extracted(REFERENCE, faulty)

    def test_pnp_patch_preserves_bounded_model_selection(self):
        text = '\n'.join('device msubcircuit '+name+' pnp pwell,space/w *pdiff error a2>'+lo+' a2<'+hi
            for name, lo, hi in [('pnp_10p00x00p42', '4.1', '4.3'), ('pnp_05p00x00p42', '2.0', '2.2'),
                                 ('pnp_10p00x10p00', '99.0', '101.0'), ('pnp_05p00x05p00', '24.0', '26.0')])
        fixed = fix_pnp_technology(text)
        self.assertIn('pnp_05p00x05p00 pnp *pdiff pwell,space/w a1>24.0 a1<26.0', fixed)
        self.assertEqual(fixed.count('device msubcircuit'), 4)
        with self.assertRaisesRegex(ValueError, 'declarations changed'):
            fix_pnp_technology(fixed)


class PhysicalGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def reports(self, directory, density=False):
        directory.mkdir(parents=True, exist_ok=True)
        for deck in ('main', 'density', 'antenna'):
            item = "<item><category>'M1.4'</category></item>" if density and deck == 'density' else ''
            (directory/f'banba-layout_{deck}.lyrdb').write_text(
                '<report-database><categories/><items>'+item+'</items></report-database>')

    def test_engine_failure_cannot_pass_with_empty_reports(self):
        self.reports(self.root)
        result = drc_results(self.root, 'banba-layout', 1)
        self.assertFalse(result['passed'])
        self.assertIn('engine failed', physical.drc_remaining(result)[0])
        self.assertTrue(drc_results(self.root, 'banba-layout', 0)['passed'])

    def test_density_findings_fail_even_if_wrapper_exits_zero(self):
        self.reports(self.root, density=True)
        result = drc_results(self.root, 'banba-layout', 0)
        self.assertFalse(result['passed'])
        self.assertEqual(physical.drc_remaining(result), ['DRC closure: M1.4.'])

    def test_unrelated_report_cannot_replace_a_missing_deck(self):
        self.reports(self.root)
        (self.root/'banba-layout_antenna.lyrdb').rename(self.root/'other.lyrdb')
        with self.assertRaisesRegex(ValueError, 'missing banba-layout_antenna'):
            drc_results(self.root, 'banba-layout', 0)

    def test_malformed_output_cannot_pass_as_zero_findings(self):
        for text in ['<wrong><categories/><items/></wrong>', '<report-database/>',
                     '<report-database><categories/><items><item/></items></report-database>']:
            with self.subTest(text=text):
                self.reports(self.root)
                (self.root/'banba-layout_main.lyrdb').write_text(text)
                with self.assertRaises(ValueError):
                    drc_results(self.root, 'banba-layout', 0)

    def test_drc_lvs_scope_uses_no_extractor_and_retains_density_failure(self):
        # Use the real saved 103-device comparison. Only external process
        # execution is replaced; reference generation and report parsing run.
        for density, lvs_exit, expected in [(False, 0, 0), (True, 0, 1), (False, 1, 1)]:
            output = self.root/f'run-{density}-{lvs_exit}'
            phases = []
            def command(args, folder, name, env=None):
                phases.append(name)
                folder.mkdir(parents=True, exist_ok=True)
                (folder/(name+'.log')).write_text('test engine\n')
                if name == 'drc':
                    self.reports(output/'drc', density=density)
                elif name == 'lvs':
                    (output/'lvs').mkdir()
                    shutil.copyfile(physical.EXAMPLE/'physical-evidence/comparison.lvsdb',
                                    output/'lvs/banba-layout.lvsdb')
                    return lvs_exit
                return 0
            with self.subTest(density=density, lvs_exit=lvs_exit), \
                    patch.object(physical, 'locked_checkout') as lock, \
                    patch.object(physical, 'command', side_effect=command), \
                    redirect_stdout(io.StringIO()):
                code = physical.main(['--drc-lvs-only', '--pv', str(self.root),
                    '--klayout', sys.executable, '--out', str(output)])
            self.assertEqual(code, expected)
            self.assertEqual(phases, ['klayout-version', 'drc', 'lvs'])
            self.assertEqual(lock.call_count, 1)
            report = json.loads((output/'physical-verification.json').read_text())
            self.assertFalse(report['signoff'])
            self.assertEqual(report['lvs']['pairs']['device'], 103)
            self.assertEqual(report['passed'], expected == 0)
            self.assertEqual(report['scope'], 'drc-lvs')

    def test_full_scope_still_requires_extraction_engines(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            physical.main(['--pv', str(self.root), '--klayout', sys.executable, '--out', str(self.root)])
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
