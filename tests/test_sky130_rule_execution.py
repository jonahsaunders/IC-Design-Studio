from copy import deepcopy
import unittest
from scripts.sky130_rule_execution import bind, bind_geometry, bind_interconnect, bind_wide
from scripts.sky130_low_voltage_geometry import check as geometry_check
from scripts.sky130_interconnect_geometry import check as interconnect_check
from scripts.sky130_wide_metal import check as wide_check


def reports():
    # The independent fixture enumerates every published n/psd and HVTP row,
    # including the manual-merge requirement and an unrelated open rule.
    rules=['n/ psd.'+s for s in ('1','2','3','5a','5b','6','7','8','9','10a','10b','11')]+['hvtp.'+str(i) for i in range(1,7)]
    checks=['n/psd.'+s+'.'+t for s in ('1','2','5a','5b','6','7','8','9','11') for t in ('n','p')]
    checks+=['n/psd.10a','n/psd.10b']+['hvtp.'+str(i) for i in range(1,7)]
    checks+=['profile.'+str(pair) for pair in ((64,18),(19,44),(124,20),(124,21),(18,20),(11,44),
             (75,20),(80,20),(125,44),(125,20),(86,20),(79,20),(81,2),(74,22),(81,57),(81,63))]
    checks+=['profile.active_overlap','profile.active_well_straddle']
    review=dict(gds_sha256='a'*64,checker_sha256='b'*64,rows=[dict(rule=r,disposition='execution-review-required') for r in rules+['poly.1a']])
    raw=dict(gds_sha256='a'*64,checker_sha256='c'*64,status='PASS',violations=0,checks=[dict(rule=r,violations=0) for r in checks])
    return review,raw


class RuleExecutionTests(unittest.TestCase):
    def test_only_reviewed_requirements_are_bound(self):
        review,raw=reports();original=deepcopy(review);result=bind(review,raw)
        self.assertEqual(review,original)
        self.assertEqual(result['counts'],{'executed-reviewed':18,'execution-review-required':1})
        self.assertFalse(result['qualified']);self.assertFalse(result['chunk_complete'])

    def test_failed_profile_and_hidden_marker_are_rejected(self):
        for rule in ('n/psd.5a.n','n/psd.6.p','hvtp.3','profile.active_overlap'):
            review,raw=reports();next(r for r in raw['checks'] if r['rule']==rule)['violations']=1
            with self.subTest(rule=rule),self.assertRaisesRegex(ValueError,'profile'):bind(review,raw)

    def test_omitted_or_duplicated_checks_are_rejected(self):
        for duplicate in (False,True):
            review,raw=reports()
            if duplicate:raw['checks'].append(deepcopy(raw['checks'][0]))
            else:raw['checks'].pop(0)
            with self.subTest(duplicate=duplicate),self.assertRaises(ValueError):bind(review,raw)

    def test_layout_change_cannot_reuse_pass(self):
        review,raw=reports();raw['gds_sha256']='d'*64
        with self.assertRaisesRegex(ValueError,'different submitted'):bind(review,raw)

    def test_omitted_profile_guard_cannot_reuse_pass(self):
        review,raw=reports();raw['checks']=[r for r in raw['checks'] if r['rule']!='profile.(75, 20)']
        with self.assertRaisesRegex(ValueError,'profile guard'):bind(review,raw)

    def test_changed_manual_inventory_requires_review(self):
        for change in ('remove','duplicate','disposition'):
            review,raw=reports()
            if change=='remove':review['rows'].pop(0)
            elif change=='duplicate':review['rows'].append(deepcopy(review['rows'][0]))
            else:review['rows'][0]['disposition']='advisory'
            with self.subTest(change=change),self.assertRaises(ValueError):bind(review,raw)


def geometry_reports():
    review,raw=reports();review=bind(review,raw)
    # Enumerate the reviewed manual rows independently of the binding map.
    rules=['nwell.'+s for s in ('1','2a','2b','4')]
    rules+=['difftap.'+s for s in ('1','2','2b','3','8','9','10','11')]
    rules+=['poly.'+s for s in ('2','4','5','6','7','8','10','11','12')]
    rules+=['npc.'+s for s in ('1','2','3','4')]
    rules+=['licon.'+s for s in ('1','2','3','4','5a','6','8','9','11','11a','11b','13','14','15','16','17','18')]
    review['rows'] += [dict(rule=r,disposition='execution-review-required') for r in rules+['x.20']]
    geometry=geometry_check({});geometry.update(gds_sha256='a'*64,checker_sha256='e'*64)
    return review,geometry


class GeometryExecutionTests(unittest.TestCase):
    def test_extends_ledger_without_mutating_or_losing_prior_checks(self):
        review,geometry=geometry_reports();old=deepcopy(review);result=bind_geometry(review,geometry)
        self.assertEqual(review,old)
        self.assertEqual(result['counts'],{'executed-reviewed':61,'execution-review-required':1})
        self.assertEqual(result['raw_geometry'],review['raw_geometry'])
        self.assertFalse(result['qualified']);self.assertFalse(result['chunk_complete'])

    def test_hidden_failure_and_boolean_counts_are_rejected(self):
        for name,value in (('poly.8',1),('nwell.4',1),('licon.16',True),('profile.crossing_gate',1)):
            review,g=geometry_reports();next(c for c in g['checks'] if c['rule']==name)['violations']=value
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'profile'):bind_geometry(review,g)

    def test_missing_and_duplicate_check_or_guard_are_rejected(self):
        for name in ('difftap.2b','profile.absent.(75, 20)','profile.sc_straddle'):
            for duplicate in (False,True):
                review,g=geometry_reports();row=next(c for c in g['checks'] if c['rule']==name)
                if duplicate:g['checks'].append(deepcopy(row))
                else:g['checks'].remove(row)
                with self.subTest(name=name,duplicate=duplicate),self.assertRaises(ValueError):bind_geometry(review,g)

    def test_companion_implant_report_is_required_and_rechecked(self):
        for mode in ('missing','failure','layout','guard'):
            review,g=geometry_reports()
            if mode=='missing':del review['raw_geometry']
            elif mode=='failure':review['raw_geometry']['checks'][0]['violations']=1
            elif mode=='layout':review['raw_geometry']['gds_sha256']='f'*64
            else:review['raw_geometry']['checks'].pop()
            with self.subTest(mode=mode),self.assertRaises((KeyError,ValueError)):bind_geometry(review,g)

    def test_changed_layout_or_manual_inventory_requires_new_review(self):
        for mode in ('layout','remove','duplicate','disposition'):
            review,g=geometry_reports();row=next(r for r in review['rows'] if r['rule']=='nwell.4')
            if mode=='layout':g['gds_sha256']='f'*64
            elif mode=='remove':review['rows'].remove(row)
            elif mode=='duplicate':review['rows'].append(deepcopy(row))
            else:row['disposition']='absent-operand'
            with self.subTest(mode=mode),self.assertRaises(ValueError):bind_geometry(review,g)


def interconnect_reports():
    review,g=geometry_reports();review=bind_geometry(review,g)
    rules=['li.'+s+'.-' for s in ('1','3','5','6')]
    for name,suffixes in (('m1',('1','2','4','5','6','7')),('m2',('1','2','4','5','6','7')),
            ('m3',('1','2','4','6')),('m4',('1','2','3','4a')),('m5',('1','2','3','4')),
            ('ct',('1','2','3','4')),('via',('1a','2','3','4a','5a')),
            ('via2',('1a','2','3','4','5','X.1')),('via3',('1','2','3','4','5')),
            ('via4',('1','2','3','4')),('licon',('5b','5c','7','8a'))):
        rules += [name+'.'+s for s in suffixes]
    review['rows'] += [dict(rule=r,disposition='execution-review-required') for r in rules]
    geometry=interconnect_check({});geometry.update(gds_sha256='a'*64,checker_sha256='f'*64)
    return review,geometry


class InterconnectExecutionTests(unittest.TestCase):
    def test_extends_ledger_and_preserves_companion_reports(self):
        review,g=interconnect_reports();old=deepcopy(review);result=bind_interconnect(review,g)
        self.assertEqual(review,old)
        self.assertEqual(result['counts'],{'executed-reviewed':117,'execution-review-required':1})
        self.assertEqual(result['low_voltage_geometry'],old['low_voltage_geometry'])
        self.assertFalse(result['qualified']);self.assertFalse(result['chunk_complete'])

    def test_failed_omitted_duplicate_or_mismatched_report_is_rejected(self):
        for which in ('raw_geometry','low_voltage_geometry','interconnect'):
            for mode in ('marker','boolean','missing','duplicate','layout'):
                review,g=interconnect_reports();target=g if which=='interconnect' else review[which]
                if mode=='marker':target['checks'][-1]['violations']=1
                elif mode=='boolean':target['checks'][-1]['violations']=True
                elif mode=='missing':target['checks'].pop()
                elif mode=='duplicate':target['checks'].append(deepcopy(target['checks'][-1]))
                else:target['gds_sha256']='0'*64
                with self.subTest(which=which,mode=mode),self.assertRaises(ValueError):bind_interconnect(review,g)

    def test_changed_manual_inventory_requires_review(self):
        for mode in ('missing','duplicate','disposition'):
            review,g=interconnect_reports();row=next(r for r in review['rows'] if r['rule']=='li.5.-')
            if mode=='missing':review['rows'].remove(row)
            elif mode=='duplicate':review['rows'].append(deepcopy(row))
            else:row['disposition']='absent-operand'
            with self.subTest(mode=mode),self.assertRaises(ValueError):bind_interconnect(review,g)


def wide_reports():
    review,g=interconnect_reports();review=bind_interconnect(review,g)
    rules=['m1.3a','m1.3b','m2.3a','m2.3b','m3.3c','m3.3d','m4.5a','m4.5b']
    review['rows'] += [dict(rule=r,disposition='execution-review-required') for r in rules]
    wide=wide_check({});wide.update(gds_sha256='a'*64,checker_sha256='9'*64)
    return review,wide


class WideExecutionTests(unittest.TestCase):
    def test_extends_complete_companion_ledger(self):
        review,w=wide_reports();old=deepcopy(review);result=bind_wide(review,w)
        self.assertEqual(review,old)
        self.assertEqual(result['counts'],{'executed-reviewed':125,'execution-review-required':1})
        self.assertEqual(result['interconnect_geometry'],old['interconnect_geometry'])
        self.assertFalse(result['qualified']);self.assertFalse(result['chunk_complete'])

    def test_failed_missing_duplicate_and_mismatched_reports_rejected(self):
        for which in ('raw_geometry','low_voltage_geometry','interconnect_geometry','wide'):
            for mode in ('marker','boolean','missing','duplicate','layout'):
                review,w=wide_reports();target=w if which=='wide' else review[which]
                if mode=='marker':target['checks'][-1]['violations']=1
                elif mode=='boolean':target['checks'][-1]['violations']=True
                elif mode=='missing':target['checks'].pop()
                elif mode=='duplicate':target['checks'].append(deepcopy(target['checks'][-1]))
                else:target['gds_sha256']='0'*64
                with self.subTest(which=which,mode=mode),self.assertRaises(ValueError):bind_wide(review,w)

    def test_changed_manual_inventory_requires_review(self):
        for mode in ('missing','duplicate','disposition'):
            review,w=wide_reports();row=next(r for r in review['rows'] if r['rule']=='m3.3c')
            if mode=='missing':review['rows'].remove(row)
            elif mode=='duplicate':review['rows'].append(deepcopy(row))
            else:row['disposition']='absent-operand'
            with self.subTest(mode=mode),self.assertRaises(ValueError):bind_wide(review,w)


if __name__=='__main__':unittest.main()
