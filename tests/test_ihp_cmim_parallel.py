"""Adversarial readback controls for the finite native parallel CMIM evidence."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from icstudio.ihp_cmim_capacitance import Parallel, compare
from scripts.check_ihp_cmim_parallel import currents, inventory, project_contract, read_native, source_files, verify
from tests.test_ihp_cmim_capacitance import SCALE


class ParallelNativeReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root/'job/parasitics'
        self.raw.mkdir(parents=True)
        fixture = Path(__file__).parent/'fixtures/ihp-cmim-parallel-v1'
        for source, target in (('coupon.ext','coupon.ext'),('hierarchical.spice','extracted.spice'),('flat.spice','extracted-flat.spice')):
            shutil.copyfile(fixture/source,self.raw/target)
        unit = Parallel('coupon', ('C1','C2'), ('C1','C2'), ((Decimal('7e-6'),Decimal('7e-6'),2),))
        proof = compare(
            (self.raw/'coupon.ext').read_text(), (self.raw/'extracted.spice').read_text(),
            (self.raw/'extracted-flat.spice').read_text(), SCALE, unit)
        (self.raw/'cmim-capacitance.json').write_text(json.dumps(proof))

    def test_retained_native_graph_is_read_independently(self):
        result = read_native(self.root)
        self.assertEqual(result['intrinsic_units'], 2)
        self.assertEqual(result['raw_edges_af'], [
            {'nodes':['C1','C2'],'value':'928.042'},
            {'nodes':['C1','SUB'],'value':'1487.62'},
            {'nodes':['C2','SUB'],'value':'2245.84'}])

    def test_native_metadata_and_substrate_are_required(self):
        path = self.raw/'coupon.ext'
        original = path.read_text()
        for mutation in ('missing-substrate','missing-ports','wrong-tech','duplicate-index','nonzero-substrate',
                         'wrong-scale','duplicate-metadata','unknown-record'):
            text = original
            if mutation == 'missing-substrate': text = '\n'.join(r for r in text.splitlines() if not r.startswith('substrate '))+'\n'
            elif mutation == 'missing-ports': text = '\n'.join(r for r in text.splitlines() if not r.startswith('port '))+'\n'
            elif mutation == 'wrong-tech': text = text.replace('tech ihp-sg13g2','tech unrelated')
            elif mutation == 'duplicate-index': text = text.replace('port "C2" 2','port "C2" 1')
            elif mutation == 'nonzero-substrate': text = text.replace('substrate "SUB" 0 0','substrate "SUB" 0 1')
            elif mutation == 'wrong-scale': text = text.replace('scale 1000 1 1','scale 1000 1 2')
            elif mutation == 'duplicate-metadata': text += 'tech ihp-sg13g2\n'
            else: text += 'equiv "C1" "C2"\n'
            path.write_text(text)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): read_native(self.root)
        path.write_text(original)

    def test_export_missing_intrinsic_or_edge_and_changed_receipt_are_rejected(self):
        path = self.raw/'extracted-flat.spice'
        original = path.read_text()
        for old,new in (('X1 C1 C2 cap_cmim l=7u w=7u\n',''),('C1 C1 SUB 1.48762f\n',''),
                        ('1.48762f','1.48772f'),('X1 C1 C2','X1 C2 C1')):
            path.write_text(original.replace(old,new))
            with self.subTest(new=new), self.assertRaises(ValueError): read_native(self.root)
        path.write_text(original)
        record = self.raw/'cmim-capacitance.json'
        proof = json.loads(record.read_text());proof['edges_af'][0]['raw'] = '1'
        record.write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError,'application raw receipt'): read_native(self.root)

    def test_incomplete_inventory_bad_status_and_changed_source_fail_before_claims(self):
        base = {'status':'OBSERVED','qualified':False,'installed_acceptance':False,
                'source_files':source_files(),'files':{}}
        for mutation in ('empty-files','wrong-status','empty-sources','wrong-source','changed-file'):
            report = deepcopy(base)
            if mutation == 'wrong-status': report['status'] = 'INVALID'
            elif mutation == 'empty-sources': report['source_files'] = {}
            elif mutation == 'wrong-source': report['source_files']['scripts/check_ihp_cmim_parallel.py'] = '0'*64
            elif mutation == 'changed-file':
                report['files'] = inventory(self.root)
                (self.raw/'coupon.ext').write_text((self.raw/'coupon.ext').read_text()+'\n')
            (self.root/'report.json').write_text(json.dumps(report))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): verify(self.root)

    def test_unlisted_nested_report_is_part_of_complete_inventory(self):
        path = self.root/'job/report.json';path.write_text('{}')
        before = inventory(self.root)
        self.assertIn('job/report.json', before)
        path.write_text('{"changed":true}')
        self.assertNotEqual(inventory(self.root)['job/report.json'], before['job/report.json'])

    def test_actual_native_complex_samples_and_current_faults(self):
        # Values retained from the first 2026-11-07 native m2 saved-bench run;
        # title/date are immaterial to the independent complex-vector reader.
        text = '''Flags: complex
No. Variables: 3
No. Points: 3
Variables:
0 frequency frequency grid=3
1 v(vin) voltage
2 i(vin) current
Values:
0 1.000000000000000e+05,0
1.000000000000000e+00,0
0,-9.491562484105483e-08
1 3.162277660168380e+05,0
1.000000000000000e+00,0
0,-3.001495600357906e-07
2 1.000000000000000e+06,0
1.000000000000000e+00,0
-2.131628207280301e-14,-9.491562484105479e-07
'''
        path = self.root/'job/post-layout/deck.raw'
        path.parent.mkdir();path.write_text(text)
        graph = read_native(self.root)
        result = currents(self.root, graph)
        self.assertLess(result['maximum_relative_current_error'], 1e-8)
        for old,new in (('-9.491562484105479e-07','-9.481562484105479e-07'),
                        ('i(vin)','i(unrelated)'), ('1.000000000000000e+06','1.100000000000000e+06'),
                        ('-9.491562484105483e-08','nan')):
            path.write_text(text.replace(old,new))
            with self.subTest(new=new), self.assertRaises(ValueError): currents(self.root, graph)

    def test_saved_package_and_device_revision_are_bound(self):
        from icstudio.catalog import create_device
        from scripts.qualify_standard_mos import load_technology
        technology = load_technology('ihp-sg13g2')[0]
        project = {'pdk':technology, 'top':'dut', 'cells':[{'id':'dut','name':'coupon','ports':['C1','C2'],
            'devices':[create_device(technology,'sg13g2_pr/cap_cmim.sym','C1')]}]}
        self.assertEqual(project_contract(project),project['cells'][0])
        for kind in ('package-revision','device-revision','device-pdk','catalog-order'):
            changed = deepcopy(project)
            if kind == 'package-revision': changed['pdk']['package_lock']['revision'] = 'UNRELATED'
            elif kind == 'catalog-order': changed['pdk']['simulation']['catalog']['sg13g2_pr/cap_cmim.sym']['pin_order'].reverse()
            else: changed['cells'][0]['devices'][0]['model_ref'][kind.split('-')[1]] = 'UNRELATED'
            with self.subTest(kind=kind), self.assertRaises(ValueError): project_contract(changed)
