import os
import tempfile
import unittest
from pathlib import Path
from icstudio.model import example, device, clone, validate, design_digest, uid
from icstudio import analog_optimizer as opt
from icstudio import variation_runs
from icstudio.simulation import run


def mos_project(polarity='NMOS'):
    p = example('empty'); c = p['cells'][0]; sign = 1 if polarity == 'NMOS' else -1
    c['devices'] = [device(polarity, 'M1', nets={'d': 'd', 'g': 'g', 's': '0', 'b': '0'}),
                    device('V', 'VG', value=str(sign * .8), nets={'p': 'g', 'n': '0'}),
                    device('V', 'VD', value=str(sign * 1.8), nets={'p': 'd', 'n': '0'})]
    p['analysis']['type'] = 'op'; validate(p)
    return p


def setup(p):
    return dict(id='op', name='Bias', cell=p['top'], engine='builtin', settings=clone(p['analysis']))


def prepare_job(settings, engine, project, cid):
    return dict(settings=clone(settings), engine=engine, project=clone(project), cell=cid)


def search_spec(**kw):
    return dict(kind='analog_optimizer', axes=[dict(target='VG.value', lower='.6', upper='1', count=3)], budget=100,
                objective=dict(entry_id='op', expression='final(V("g"))', unit='V', goal='target', target='.8'), **kw)


def completed(manifest):
    return [dict(id=str(j['case']['index']), job=clone(j), state='Complete', result=clone(run(j['project'], j['cell'], j['settings']))) for j in manifest['jobs']]


class AnalogOptimizerTests(unittest.TestCase):
    def setUp(self):
        self.p = mos_project(); self.plan = opt.source_plan(setup(self.p)); self.spec = search_spec()

    def prepare(self, spec=None, plan=None):
        return opt.prepare(self.p, self.p['top'], plan or self.plan, spec or self.spec, prepare_job)

    def test_real_teaching_search_applies_expected_candidate_atomically(self):
        before = clone(self.p); m = self.prepare(); rows = completed(m); report = opt.evaluate(m, rows)
        self.assertEqual(self.p, before); self.assertEqual(report['best']['candidate'], 2)
        self.assertTrue(report['complete']); opt.apply_candidate(self.p, m, rows, 2)
        self.assertAlmostEqual(opt.get_target(self.p, self.p['top'], 'VG.value'), .8)

    def test_budget_counts_every_test_and_pvt_condition_before_preparing_jobs(self):
        self.plan['temperatures'] = [0, 27, 80]; self.spec['budget'] = 8; calls = []
        with self.assertRaisesRegex(ValueError, '9 simulations'):
            opt.prepare(self.p, self.p['top'], self.plan, self.spec, lambda *a: calls.append(a))
        self.assertEqual(calls, [])

    def test_ratio_links_are_exact_and_disjoint(self):
        self.p['cells'][0]['devices'].append(device('NMOS', 'M2'))
        self.spec['axes'] = [dict(target='M1.params.w', lower='1u', upper='4u', count=4,
                                  links=[dict(target='M2.params.w', ratio=2)])]
        for j in self.prepare()['jobs']:
            self.assertAlmostEqual(opt.get_target(j['project'], j['cell'], 'M2.params.w'), 2 * opt.get_target(j['project'], j['cell'], 'M1.params.w'))
        self.spec['axes'].append(dict(target='M2.params.w', lower='1u', upper='2u', count=2))
        with self.assertRaisesRegex(ValueError, 'occur once'): self.prepare()

    def test_invalid_bounds_counts_and_duplicate_links(self):
        for update in ({'count': 2.5}, {'count': 0}, {'lower': 'nan'}, {'upper': '.1'},
                       {'links': [dict(target='VG.value', ratio=1)]}):
            spec = clone(self.spec); spec['axes'][0].update(update)
            with self.assertRaises((ValueError, TypeError)): self.prepare(spec)

    def test_project_variables_work_and_plan_override_cannot_cancel_search(self):
        self.p['parameters'] = {'bias': '.8'}; self.p['cells'][0]['devices'][1]['value'] = '{bias}'
        self.spec['axes'][0]['target'] = '@bias'
        self.assertEqual([j['project']['parameters']['bias'] for j in self.prepare()['jobs']], ['0.6', '0.8', '1.0'])
        self.plan['variables'] = {'bias': '.9'}
        with self.assertRaisesRegex(ValueError, 'overrides adjustable'): self.prepare()

    def test_supply_override_overlap_rejected(self):
        self.plan['entries'][0]['supply'] = 'VG.value'; self.plan['voltages'] = [.8, .9]
        with self.assertRaisesRegex(ValueError, 'overrides adjustable'): self.prepare()

    def test_worst_condition_and_matching_objective_entry(self):
        self.p['cells'][0]['devices'].pop(0)  # Ideal sources support teaching temperature sweeps.
        self.plan['temperatures'] = [0, 80]
        other = {**clone(self.plan['entries'][0]), 'id': 'other', 'name': 'Other test'}; self.plan['entries'].append(other)
        self.spec['objective']['goal'] = 'maximize'
        m = self.prepare(); rows = completed(m)
        for row in rows:
            case = row['job']['case']; candidate = case['candidate']; temp = case['labels']['temperature']
            # Candidate 3 looks best nominally but fails at the hot condition.
            value = 99 if case['entry_id'] == 'other' else {1: 1., 2: 2., 3: 3. if temp == 0 else .5}[candidate]
            row['result']['traces']['g'] = [value]
        report = opt.evaluate(m, rows)
        self.assertEqual(report['best']['candidate'], 2); self.assertEqual(report['best']['worst_value'], 2)

    def test_saved_limits_are_recomputed_and_failed_candidates_never_applied(self):
        self.p['cells'][0]['specifications'] = [dict(name='Gate safety', expression='final(V("g"))', max='.7', unit='V')]
        m = self.prepare(); rows = completed(m)
        rows[-1]['result']['specifications'] = [dict(name='Gate safety', status='PASS')]
        report = opt.evaluate(m, rows)
        self.assertEqual(report['best']['candidate'], 1)
        before = clone(self.p)
        with self.assertRaisesRegex(ValueError, 'passes every'): opt.apply_candidate(self.p, m, rows, 3)
        self.assertEqual(self.p, before)

    def test_incomplete_or_wrong_identity_evidence_cannot_be_applied(self):
        m = self.prepare(); rows = completed(m)
        with self.assertRaisesRegex(ValueError, 'Finish'): opt.apply_candidate(self.p, m, rows[:-1], 2)
        rows[1]['result']['design_hash'] = 'wrong'
        report = opt.evaluate(m, rows); self.assertEqual(report['candidates'][1]['state'], 'Failed')
        rows[0]['job']['settings']['temperature'] = 999
        self.assertEqual(opt.evaluate(m, rows)['candidates'][0]['state'], 'Pending')
        rows[2]['result']['settings']['type']='tran'
        self.assertEqual(opt.evaluate(m, rows)['candidates'][2]['state'],'Failed')

    def test_stale_revision_prevents_apply(self):
        m = self.prepare(); rows = completed(m); self.p['revision'] += 1
        with self.assertRaisesRegex(ValueError, 'circuit changed'): opt.apply_candidate(self.p, m, rows, 2)

    def test_objective_units_missing_trace_and_non_scalar_report_failure(self):
        for expression, unit in [('V("g")', 'V'), ('final(V("missing"))', 'V'), ('final(V("g"))', 'A')]:
            spec = clone(self.spec); spec['objective'].update(expression=expression, unit=unit)
            m = self.prepare(spec); report = opt.evaluate(m, completed(m))
            self.assertIsNone(report['best']); self.assertTrue(all(c['state'] == 'Failed' for c in report['candidates']))

    def test_gmid_constraints_require_op_and_all_conditions(self):
        self.spec['gmid'] = dict(entry_id='op', device='M1', min=5, max=7, headroom=.1)
        m = self.prepare(); report = opt.evaluate(m, completed(m))
        self.assertEqual(report['best']['candidate'], 2)
        self.plan['entries'][0]['settings']['type'] = 'tran'
        with self.assertRaisesRegex(ValueError, 'operating-point'): self.prepare()

    def test_restart_manifest_and_resume_only_unfinished_jobs(self):
        m = self.prepare(); rows = completed(m); rows[1]['state'] = 'Cancelled'; rows[2]['state'] = 'Interrupted'
        with tempfile.TemporaryDirectory() as root:
            variation_runs.save(m, root); restored = variation_runs.load(root, self.p['id'])[0]
        self.assertEqual(len(variation_runs.pending(restored, rows)), 2)
        retry = clone(rows[1]); retry['state'] = 'Complete'; retry['id'] = 'retry'; rows.append(retry)
        self.assertEqual(len(variation_runs.pending(restored, rows)), 1)

    def test_native_or_model_width_not_invented(self):
        p = mos_project(); d = p['cells'][0]['devices'][0]
        d['native_spice'] = {'type': 'device', 'parameters': {'w': '5u'}}
        result = dict(device_operating_point={'M1': dict(id=-1e-5, gm=1e-4)})
        point = opt.read_gmid(dict(project=p, cell=p['top']), result, 'M1')
        self.assertEqual(point['gmid'], 10); self.assertIsNone(point['current_density'])
        with self.assertRaisesRegex(ValueError, 'normalization'): opt.width_estimate(point, '10u')

    def test_nmospmos_gmid_density_and_sizing_at_actual_bias(self):
        for polarity in ('NMOS', 'PMOS'):
            p = mos_project(polarity); r = run(p, p['top'], p['analysis']); point = opt.read_gmid(dict(project=p, cell=p['top']), r, 'M1')
            self.assertAlmostEqual(point['gmid'], 2 / (.8 - .45), places=5)
            self.assertAlmostEqual(opt.width_estimate(point, abs(point['id']) * 2), point['width'] * 2)
            self.assertAlmostEqual(abs(point['vgs']), .8)

    def test_zero_current_and_missing_model_vectors_are_explicit(self):
        for values in ({}, {'id': 0, 'gm': 1e-6}, {'id': 1e-30, 'gm': 1e-6}, {'id': 1e-5, 'gm': float('nan')}):
            with self.assertRaises(ValueError): opt.read_gmid(dict(project=self.p, cell=self.p['top']), {'device_operating_point': {'M1': values}}, 'M1')

    def test_hierarchical_width_uses_selected_instance_overrides(self):
        p=example('empty');child=dict(id=uid(),name='unit',ports=['g','d'],parameters={'width':'1u'},
            devices=[device('NMOS','M1',nets={'d':'d','g':'g','s':'0','b':'0'})],shapes=[])
        child['devices'][0]['params']['w']='{width}';p['cells'].append(child)
        p['cells'][0]['devices']=[device('X','X1',cell=child['id'],parameters={'width':'2u'},nets={'d':'d','g':'g'}),
            device('X','X2',cell=child['id'],parameters={'width':'6u'},nets={'d':'d','g':'g'})]
        validate(p)
        self.assertAlmostEqual(opt.device_geometry(p,p['top'],'X1/M1')['width'],2e-6)
        self.assertAlmostEqual(opt.device_geometry(p,p['top'],'X2/M1')['width'],6e-6)

    def test_gmid_experiment_is_not_directly_applicable(self):
        spec = dict(kind='analog_gmid', axes=self.spec['axes'], gmid=dict(entry_id='op', device='M1'))
        m = self.prepare(spec); rows = completed(m); report = opt.evaluate(m, rows)
        self.assertEqual(len(report['candidates'][1]['points']), 1)
        with self.assertRaisesRegex(ValueError, 'circuit search'): opt.apply_candidate(self.p, m, rows, 2)

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'), 'Set ICSTUDIO_TEST_NGSPICE for real ngspice qualification.')
    def test_real_ngspice_gmid_matches_direct_saved_ratio(self):
        from icstudio.engines import run_ngspice
        executable = os.environ['ICSTUDIO_TEST_NGSPICE']; self.p['spice'] = {'version': 1, 'assets': {}}
        with tempfile.TemporaryDirectory() as directory:
            result = run_ngspice(self.p, self.p['top'], self.p['analysis'], executable, Path(directory))
        point = opt.read_gmid(dict(project=self.p, cell=self.p['top']), result, 'M1')
        saved = result['device_operating_point']['M1']
        self.assertAlmostEqual(point['gmid'], abs(saved['gm'] / saved['id']))
        self.assertGreater(point['gmid'], 0)


if __name__ == '__main__': unittest.main()
