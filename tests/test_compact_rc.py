"""Independent endpoint equations, provenance faults and compact export tests."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.compact_rc import build, audit, records, CURRENT_SUM, SERIES_VOLTAGE
from icstudio.magic_rc import normalize, finalize, contract
from icstudio.rc_islands import prune
from tests.test_magic_rc import ORIGINAL, RESISTANCE


def solve_helpers(helpers, driven):
    """Generic DC modified nodal analysis, independent of the sum construction."""
    known = {'0': 0., **driven}
    nodes = sorted({n for t in helpers for n in t[1:(3 if t[0][0]=='R' else 5)]} - known.keys())
    branches = ['@'+t[0] for t in helpers if t[0][0]=='E']
    unknown = nodes + branches; ix = {n: i for i, n in enumerate(unknown)}
    size = len(unknown); matrix = [[0.] * (size+1) for _ in unknown]
    def stamp(row, col, value):
        if row in known:return
        if col in known:matrix[ix[row]][size] -= value * known[col]
        else:matrix[ix[row]][ix[col]] += value
    for t in helpers:
        kind=t[0][0];p,n=t[1:3]
        if kind=='R':
            g=1./float(t[3])
            for row, col, val in ((p,p,g),(n,n,g),(p,n,-g),(n,p,-g)):stamp(row,col,val)
        elif kind=='G':
            cp,cn=t[3:5];g=float(t[5])
            for row,col,val in ((p,cp,g),(p,cn,-g),(n,cp,-g),(n,cn,g)):stamp(row,col,val)
        else:
            cp,cn=t[3:5];g=float(t[5]);branch='@'+t[0]
            for row,col,val in ((p,branch,1.),(n,branch,-1.),(branch,p,1.),
                                (branch,n,-1.),(branch,cp,-g),(branch,cn,g)):stamp(row,col,val)
    for col in range(size):
        pivot=max(range(col,size),key=lambda row:abs(matrix[row][col]))
        assert abs(matrix[pivot][col])>1e-15
        matrix[col],matrix[pivot]=matrix[pivot],matrix[col]
        scale=matrix[col][col];matrix[col]=[v/scale for v in matrix[col]]
        for row in range(size):
            if row==col:continue
            scale=matrix[row][col]
            matrix[row]=[a-scale*b for a,b in zip(matrix[row],matrix[col])]
    return {**known,**{n:matrix[i][-1] for i,n in enumerate(unknown)}}


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
        for encoding in (SERIES_VOLTAGE,CURRENT_SUM):
            model = build(ground, coupling, weights, 'VSS', physical_nodes=owner,
                          max_capacitors=20,encoding=encoding)
            sources, caps = records(model['text'], owner)
            for driven in owner:
                with self.subTest(encoding=encoding,driven=driven):
                    potentials=solve_helpers(sources,{n:float(n==driven) for n in owner})
                    actual = {n: 0. for n in owner}
                    for _, pos, neg, value in caps:
                        actual[pos] += float(value) * 1e18 * (potentials[pos] - potentials[neg])
                    for n in owner:
                        self.assertAlmostEqual(actual[n], expected[n][driven], delta=1e-13)
                    self.assertAlmostEqual(math.fsum(actual.values()), 0., delta=1e-13)
            self.assertEqual(audit(model['text'], owner, ground, coupling, 'VSS')['status'], 'passed')
        self.assertEqual(audit(model['text'], owner, ground, coupling, 'VSS')['status'], 'passed')
        corrupted = model['text'].replace(' 0 0.20000000000000001\n', ' 0 0.21\n', 1)
        self.assertNotEqual(corrupted, model['text'])
        with self.assertRaisesRegex(ValueError, 'conserve'):
            audit(corrupted, owner, ground, coupling, 'VSS')
        physical_return = [list(t) for t in sources]
        physical_return[0][1] = 'A.t0'
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
            self.assertEqual(retained['preserved_compact_resistors'],report['export']['internal_sum_resistors'])
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

    def test_auxiliary_source_budget_counts_output_buffers_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('icstudio.compact_rc.MAX_SOURCES',1):
                with self.assertRaisesRegex(ValueError,'budget'):self.fixture(root)
            self.assertEqual((root/'top.ext').read_text(),ORIGINAL)
            self.assertFalse((root/'top.raw.ext').exists())
        inputs=({'A':1.,'VSS':0.},{},{'A':{'A':1.},'VSS':{'VSS':1.}},'VSS')
        with patch('icstudio.compact_rc.MAX_SOURCES',4):
            self.assertEqual(build(*inputs,physical_nodes=['A','VSS'],max_capacitors=2,
                                   encoding=SERIES_VOLTAGE)['sources'],4)
            with self.assertRaisesRegex(ValueError,'budget'):
                build(*inputs,physical_nodes=['A','VSS'],max_capacitors=2)

    def test_rehashed_model_and_weight_tampering_fail_before_export_changes(self):
        for changed in ('weights','model','drive','termination','buffer'):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); report=self.fixture(root)
                before=(root/'extracted.spice').read_bytes()
                if changed=='weights':report['nets']['IN']['weights']={'IN':.5,'IN.t0':.5}
                else:
                    path=root/'compact-capacitance.spice';model=path.read_text()
                    if changed=='model':model=model.replace(' 0 0.25\n',' 0 0.3\n',1)
                    elif changed=='drive':model=model.replace('STUDIO_RC_INTERNAL_W0','IN')
                    elif changed=='termination':model=model.replace(' 0 1\n',' 0 2\n',1)
                    else:model='\n'.join(line for line in model.splitlines() if not line.startswith('E_STUDIO_BUFFER_0 '))+'\n'
                    path.write_text(model,newline='\n')
                    report['files'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
                (root/'rc-normalization.json').write_text(json.dumps(report),newline='\n')
                with self.assertRaisesRegex(ValueError,'differs|differ'):finalize(root,'top')
                self.assertEqual((root/'extracted.spice').read_bytes(),before)
                self.assertFalse((root/'raw-export.spice').exists())

    def test_auxiliary_nodes_cannot_alias_physical_nodes_case_insensitively(self):
        for name in ('STUDIO_RC_INTERNAL_w0','studio_rc_internal_current_2','studio_rc_internal_u0'):
            with self.subTest(name=name):
                physical=[name,'GND']
                with self.assertRaisesRegex(ValueError,'collides'):
                    build({'A':1.,'GND':0.},{},{'A':{physical[0]:1.},'GND':{'GND':1.}},
                          'GND',physical_nodes=physical,max_capacitors=10)

    def test_current_sum_grammar_rejects_leaks_cycles_and_unbuffered_loads(self):
        model=build({'A':1.,'VSS':0.},{},{'A':{'A':1.},'VSS':{'VSS':1.}},
                    'VSS',physical_nodes=['A','VSS'],max_capacitors=2)['text']
        original=[line.split() for line in model.splitlines()]
        def changed(prefix,index,value):
            rows=[t[:] for t in original]
            next(t for t in rows if t[0].startswith(prefix))[index]=value
            return rows
        faults={
            'leak':changed('R_',1,'A'),
            'wrong_termination':changed('R_',3,'2'),
            'reversed_current':changed('G_',1,'A'),
            'self_cycle':changed('G_',3,'STUDIO_RC_INTERNAL_W0'),
            'future_dependency':changed('G_',3,'STUDIO_RC_INTERNAL_U0'),
            'negative_gain':changed('G_',5,'-1'),
            'nonfinite_gain':changed('G_',5,'nan'),
            'altered_buffer':changed('E_',5,'1.01'),
            'physical_buffer_return':changed('E_',2,'VSS'),
            'unbuffered_load':changed('C_',2,'STUDIO_RC_INTERNAL_W0'),
            'external_drive':original+[['VEXTRA','A','0','1']],
            'duplicate':original+[original[0]],
            'missing_buffer':[t for t in original if not t[0].startswith('E_STUDIO_BUFFER_0')],
            'missing_current':[t for t in original if t[0]!='G_STUDIO_SUM_0'],
            'unused_average':[['R_STUDIO_SUM_999','STUDIO_RC_INTERNAL_EXTRA','0','1'],
                              ['G_STUDIO_SUM_999','0','STUDIO_RC_INTERNAL_EXTRA','A','0','1']]+original,
        }
        for fault,rows in faults.items():
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                records('\n'.join(' '.join(t) for t in rows),{'A','VSS'})

    def test_legacy_finalized_exports_remain_authenticated_and_usable(self):
        def legacy(*args,**kwargs):return build(*args,**kwargs,encoding=SERIES_VOLTAGE)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('icstudio.compact_rc.build',legacy):report=self.fixture(root)
            # Historical normalization predates the explicit encoding field.
            report['compact_model'].pop('encoding')
            (root/'rc-normalization.json').write_text(json.dumps(report),newline='\n')
            report=finalize(root,'top')
            text=(root/'extracted.spice').read_text()
            self.assertEqual(contract(text,report),'.subckt top IN VSS\n.ends\n')
            retained=prune(root/'extracted.spice',root/'electrical.spice',normalization=report)
            self.assertEqual(retained['preserved_compact_resistors'],0)

    def test_helper_element_name_collision_cannot_replace_a_physical_wire(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            path=root/'extracted.spice'
            original=path.read_text().replace('R0 ','R_STUDIO_SUM_0 ',1)
            path.write_text(original,newline='\n')
            with self.assertRaisesRegex(ValueError,'collides'):finalize(root,'top')
            self.assertEqual(path.read_text(),original)
            self.assertFalse((root/'raw-export.spice').exists())

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
