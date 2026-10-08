"""Independent endpoint equations, provenance faults and compact export tests."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from icstudio.compact_rc import build, audit, records
from icstudio.magic_rc import normalize, finalize, contract
from icstudio.rc_islands import prune
from tests.test_magic_rc import ORIGINAL, RESISTANCE


class CompactRCTests(unittest.TestCase):
    def test_every_endpoint_matches_expanded_matrix_with_distributed_substrate(self):
        weights = {'A': {'A': .2, 'A.t0': .8}, 'B#': {'B.n0': .4, 'B.t0': .6},
                   'VSS': {'VSS': .3, 'VSS.t0': .7}}
        ground = {'A': 1.2, 'B#': .7, 'VSS': 0.}
        coupling = {('A', 'B#'): 2.5, ('B#', 'VSS'): 3.2}
        owner = {n: net for net, group in weights.items() for n in group}
        expected = {n: {m: 0. for m in owner} for n in owner}
        def edge(a, b, c):
            expected[a][a] += c; expected[b][b] += c
            expected[a][b] -= c; expected[b][a] -= c
        for net, value in ground.items():
            for n, w in weights[net].items():
                if value: edge(n, 'VSS', value * w)
        for (a, b), c in coupling.items():
            for n, w in weights[a].items():
                for m, v in weights[b].items(): edge(n, m, c * w * v)
        model = build(ground, coupling, weights, 'VSS', physical_nodes=owner, max_capacitors=20)
        sources, caps = records(model['text'], owner)
        for driven in owner:
            potentials = {n: float(n == driven) for n in owner}; potentials['0'] = 0.
            for _, pos, neg, control, _, gain in sources:
                potentials[pos] = potentials[neg] + float(gain) * potentials[control]
            actual = {n: 0. for n in owner}
            for _, pos, neg, value in caps:
                actual[pos] += float(value) * 1e18 * (potentials[pos] - potentials[neg])
            for n in owner:
                self.assertAlmostEqual(actual[n], expected[n][driven], delta=1e-13)
            self.assertAlmostEqual(math.fsum(actual.values()), 0., delta=1e-13)
        self.assertEqual(audit(model['text'], owner, ground, coupling, 'VSS')['status'], 'passed')
        corrupted = model['text'].replace(' 0 0.20000000000000001\n', ' 0 0.21\n', 1)
        self.assertNotEqual(corrupted, model['text'])
        with self.assertRaisesRegex(ValueError, 'conserve'):
            audit(corrupted, owner, ground, coupling, 'VSS')
        physical_return = [list(t) for t in sources]
        physical_return[0][2] = 'A.t0'
        with self.assertRaisesRegex(ValueError, 'physical node'):
            records('\n'.join(' '.join(t) for t in physical_return + caps), owner)

    def fixture(self, root, *, budget=50_000):
        (root/'top.ext').write_text(ORIGINAL, newline='\n')
        (root/'top.res.ext').write_text(RESISTANCE, newline='\n')
        report = normalize(root, 'top', coupling_representation='compact', max_capacitors=budget)
        (root/'extracted.spice').write_text('.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n.ends\n', newline='\n')
        return report

    def test_compact_export_contract_and_island_handling_keep_exact_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); report=self.fixture(root)
            self.assertEqual(report['compact_model']['capacitors'], 5)
            report=finalize(root,'top'); text=(root/'extracted.spice').read_bytes().decode()
            self.assertEqual(report['export']['compact_conservation']['status'],'passed')
            self.assertEqual(contract(text,report),'.subckt top IN VSS\n.ends\n')
            retained=prune(root/'extracted.spice',root/'electrical.spice',normalization=report)
            self.assertEqual(retained['preserved_compact_sources'],report['export']['controlled_sources'])
            self.assertEqual((root/'electrical.spice').read_bytes(),(root/'extracted.spice').read_bytes())
            with self.assertRaisesRegex(ValueError,'Unsupported'):
                prune(root/'extracted.spice',root/'unauthorized.spice')
            with self.assertRaisesRegex(ValueError,'changed'):
                contract(text.replace('R0 N.n0 N.t0 10','R0 N.n0 IN 10'),report)

    def test_compact_budgets_are_enforced_before_inputs_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,'budget'):self.fixture(root,budget=4)
            self.assertEqual((root/'top.ext').read_text(),ORIGINAL)
            self.assertFalse((root/'top.raw.ext').exists())
            self.assertFalse((root/'compact-capacitance.spice').exists())

    def test_rehashed_model_and_weight_tampering_fail_before_export_changes(self):
        for changed in ('weights','model','drive'):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); report=self.fixture(root)
                before=(root/'extracted.spice').read_bytes()
                if changed=='weights':report['nets']['IN']['weights']={'IN':.5,'IN.t0':.5}
                else:
                    path=root/'compact-capacitance.spice';model=path.read_text()
                    if changed=='model':model=model.replace(' 0 0.25\n',' 0 0.3\n',1)
                    else:model=model.replace('STUDIO_RC_INTERNAL_W0_0','IN')
                    path.write_text(model,newline='\n')
                    report['files'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
                (root/'rc-normalization.json').write_text(json.dumps(report),newline='\n')
                with self.assertRaisesRegex(ValueError,'differs|differ'):finalize(root,'top')
                self.assertEqual((root/'extracted.spice').read_bytes(),before)
                self.assertFalse((root/'raw-export.spice').exists())

    def test_auxiliary_nodes_cannot_alias_physical_nodes_case_insensitively(self):
        physical=['STUDIO_RC_INTERNAL_w0','GND']
        with self.assertRaisesRegex(ValueError,'collides'):
            build({'A':1.,'GND':0.},{},{'A':{physical[0]:1.},'GND':{'GND':1.}},
                  'GND',physical_nodes=physical,max_capacitors=10)

    def test_repeated_mutual_records_rebuild_with_compensated_sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=ORIGINAL.replace('"N#" 40','"N#" 10000000000000000')+'cap "IN" "N#" 1\ncap "IN" "N#" 1\n'
            (root/'top.ext').write_text(original,newline='\n')
            (root/'top.res.ext').write_text(RESISTANCE,newline='\n')
            normalize(root,'top',coupling_representation='compact')
            (root/'extracted.spice').write_text('.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n.ends\n',newline='\n')
            self.assertEqual(finalize(root,'top')['export']['status'],'passed')

    def test_omitted_isolated_capacitance_endpoint_is_restored_without_a_drive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=ORIGINAL+'node "FLOAT" 0 0 25 0 m1\ncap "FLOAT" "IN" 12\n'
            resistance=RESISTANCE+'rnode "FLOAT" 0 1 25 0 0\n'
            (root/'top.ext').write_text(original,newline='\n')
            (root/'top.res.ext').write_text(resistance,newline='\n')
            normalize(root,'top',coupling_representation='compact')
            (root/'extracted.spice').write_text('.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n.ends\n',newline='\n')
            report=finalize(root,'top')
            self.assertEqual(report['export']['restored_capacitive_nodes'],['FLOAT'])
            text=(root/'extracted.spice').read_text()
            sources,_=records((root/'compact-capacitance.spice').read_text(),{'IN','IN.t0','N.n0','N.t0','VSS','FLOAT'})
            self.assertFalse(any(t[1]=='FLOAT' or t[2]=='FLOAT' for t in sources))
            self.assertEqual(contract(text,report),'.subckt top IN VSS\n.ends\n')


if __name__=='__main__':unittest.main()
