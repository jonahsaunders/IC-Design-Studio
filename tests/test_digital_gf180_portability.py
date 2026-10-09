"""Regression controls for engine-local IDs and omitted required evidence."""
import copy
from pathlib import Path
import unittest
from icstudio import digital_gf180_checks as check

class PortabilityTests(unittest.TestCase):
    def report(self):
        return dict(port_nets={'VDD':312,'A':1997,'VSS':302,'B':1872},failures=[
            dict(kind='power-terminal-disconnected',pin=dict(instance='a',name='VDD'),actual_net=90,expected_net=312),
            dict(kind='power-terminal-disconnected',pin=dict(instance='b',name='VDD'),actual_net=90,expected_net=312),
            dict(kind='power-terminal-disconnected',pin=dict(instance='c',name='VSS'),actual_net=None,expected_net=302)])
    def test_engine_local_renumbering_preserves_full_partition_and_source_report(self):
        a=self.report();original=copy.deepcopy(a);b=copy.deepcopy(a);rename=lambda n:None if n is None else 4000-n
        b['port_nets']={p:rename(n) for p,n in b['port_nets'].items()}
        for f in b['failures']:
            for key in ('actual_net','expected_net'):f[key]=rename(f[key])
        self.assertEqual(check.canonical_metal(a),check.canonical_metal(b))
        self.assertEqual(a,original)
    def test_shorts_island_splits_missing_metal_and_changed_expected_supply_remain_visible(self):
        original=self.report();baseline=check.canonical_metal(original)
        for fault in ('short','split','missing','expected-supply'):
            changed=copy.deepcopy(original)
            if fault=='short':changed['port_nets']['B']=changed['port_nets']['A']
            elif fault=='split':changed['failures'][1]['actual_net']=91
            elif fault=='missing':changed['port_nets']['A']=None
            else:changed['failures'][0]['expected_net']=changed['port_nets']['VSS']
            with self.subTest(fault=fault):self.assertNotEqual(baseline,check.canonical_metal(changed))
    def test_port_findings_preserve_equality_missing_nodes_and_diagnostics(self):
        a=self.report();a['port_nets']['B']=None;a['failures'].append(dict(kind='missing-port-metal',ports=a['port_nets']))
        a['extraction_logs']=['Unresolved native warning'];b=check.canonical_metal(a)
        self.assertEqual(b['failures'][-1]['ports'],b['port_nets'])
        self.assertEqual(b['extraction_logs'],a['extraction_logs'])
        self.assertIsNone(b['failures'][-1]['ports']['B'])
    def test_required_or_partial_evidence_cannot_silently_become_a_historical_job(self):
        for data in [dict(artifacts={},environment=dict(gf180_connectivity=dict(recipe=check.RECIPE))),
                     dict(artifacts={'gf180_check_database':{}})]:
            with self.subTest(data=data),self.assertRaisesRegex(ValueError,'incomplete'):
                check.validate_saved(data,Path('.'))
        self.assertIsNone(check.validate_saved(dict(artifacts={}),Path('.')))

if __name__=='__main__':unittest.main()
