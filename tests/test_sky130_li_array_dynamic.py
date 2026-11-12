import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import sys
import unittest
from scripts import audit_sky130_li_array_dynamic as a
from scripts import qualify_sky130_li_array_dynamic as q


class DynamicContractTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for name,(case,analysis,kind,fault) in a.expected_selection().items():
            row=dict(name=name,case=case,analysis=analysis,kind=kind,fault=fault,count=int(case.split('-')[1][1:]))
            row.update({k:f'runs/{name}/{v}' for k,v in [('raw','result.raw'),('deck','input.cir'),('circuit','circuit.spice'),('log','console.log')]})
            rows.append(row)
        return rows

    def test_frozen_contract_and_unqualified_scope(self):
        p=a.ROOT/q.CONTRACT;self.assertEqual(a.sha(p),q.CONTRACT_SHA)
        d=json.loads(p.read_text());self.assertFalse(d['qualified'])
        self.assertEqual(d['selection']['positive_processes'],24)
        self.assertEqual(d['selection']['fault_processes'],6)
        self.assertIn('Unchanged',d['runtime']['old42_contracts'])

    def test_independent_runner_selection_equals_exact_cartesian_product(self):
        expected=set(a.expected_selection().values());self.assertEqual(set(q.jobs()),expected)
        self.assertEqual(len(list(q.jobs())),30)
        self.assertEqual(len(a.validate_rows(self.rows())),30)

    def test_missing_duplicate_and_wrong_case_count_route_fault_rejected(self):
        rows=self.rows()
        with self.assertRaises(ValueError):a.validate_rows(rows[:-1])
        with self.assertRaises(ValueError):a.validate_rows(rows[:-1]+[rows[0]])
        for key,value in [('case','l1-m2-r0'),('count',2),('kind','native'),('analysis','ac'),('fault','unknown')]:
            bad=copy.deepcopy(rows);bad[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.validate_rows(bad)

    def test_aliased_and_escaping_output_paths_rejected(self):
        for key in ('raw','deck','circuit','log'):
            for value in ('../escape','/tmp/other',self.rows()[1][key]):
                rows=self.rows();rows[0][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):a.validate_rows(rows)
        for name in ('../x','/x','x/../y','x//y','C:/x','x\\y','./x',''):
            with self.subTest(name=name),self.assertRaises(ValueError):a.safe(name)

    def test_inventory_rejects_changed_missing_and_extra_data(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'raw';p.write_text('original');files={'raw':a.sha(p)};a.verify_inventory(root,files)
            p.write_text('changed')
            with self.assertRaises(ValueError):a.verify_inventory(root,files)
            p.unlink()
            with self.assertRaises(ValueError):a.verify_inventory(root,files)
            p.write_text('original');extra=root/'extra';extra.write_text('x')
            with self.assertRaises(ValueError):a.verify_inventory(root,files)

    def test_inventory_rejects_symbolic_link_when_host_can_create_one(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'raw';p.write_text('original');files={'raw':a.sha(p)}
            try:(root/'alias').symlink_to(p)
            except OSError as exc:
                if sys.platform=='win32':self.skipTest('Host cannot create a symlink: '+str(exc))
                raise
            with self.assertRaises(ValueError):a.verify_inventory(root,files)

    def native(self):return '.subckt coupon R1 R2\n'+''.join(f'R{i} R2 R1 sky130_fd_pr__res_generic_l1 w=2 l=5\n' for i in range(3))+'.ends\n'

    def test_native_count_graph_width_and_multiplicity_fail_closed(self):
        text=self.native();self.assertEqual(len(a.primitive_rows(text,3)),3)
        for bad in (text.replace('R0 R2 R1','R0 floating R1'),text.replace('w=2','w=3',1),text.replace('w=2','w=2 m=1',1),text.replace('R2 R2 R1','R0 R2 R1')):
            with self.assertRaises(ValueError):a.primitive_rows(bad,3)
        with self.assertRaises(ValueError):a.primitive_rows(text,16)

    def test_faults_are_explicit_netlist_perturbations_not_native_extractions(self):
        text=self.native()
        removed=q.circuit_text(text,'remove-one-unit');self.assertEqual(len([s for s in removed.splitlines() if s.startswith('R')]),2)
        width=q.circuit_text(text,'one-unit-width-3um');self.assertEqual(width.count('w=3'),1);self.assertEqual(width.count('w=2'),2)
        self.assertEqual(q.circuit_text(text,'load-capacitance-2nF'),text)
        for data in (removed,width):
            with self.assertRaises(ValueError):a.primitive_rows(data,3)

    def test_analytic_resistance_and_ramp_limits(self):
        # Independent elementary decimal arithmetic for source law.
        from decimal import Decimal as D
        unit=D('12.2')*D('0.000005')/(D('0.000002')+D('0.000000017'))*(1-D('.0006045')*3-D('.0000003693')*9)
        for n in (3,16):
            r=a.resistance(n);self.assertAlmostEqual(r,float(unit/n),places=13)
            self.assertEqual(a.transient_expected(0,r),0)
            self.assertAlmostEqual(a.transient_expected(1,r),.001*10/(10+r),places=15)
            self.assertAlmostEqual(a.transient_expected(1e-9,r),a.transient_expected(math.nextafter(1e-9,math.inf),r),places=15)

    def test_raw_truncation_and_nonfinite_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'output.raw'
            for text in ('', 'Title: x\nPlotname: Transient Analysis\n', 'Title: x\nFlags: real\nNo. Variables: 2\nNo. Points: 1\nVariables:\n0 time time\n1 v(output) voltage\nValues:\n0 0\nnan\n'):
                p.write_text(text)
                with self.assertRaises((ValueError,KeyError)):a.observe(p,'tran',3)


if __name__=='__main__':unittest.main()
