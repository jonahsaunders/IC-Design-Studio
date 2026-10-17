import copy
import unittest
from scripts.ihp_cell_capacitance import compare, protected_floating


class IHPCellCapacitanceTests(unittest.TestCase):
    def fixture(self):
        return dict(ground='vss',nodes=['vss','pin','internal','poly1','poly2'],
                    edges_af=[('internal','vss',2.),('internal','poly1',3.),
                              ('poly1','poly2',4.),('poly2','pin',5.),('poly2','vss',6.)])

    def test_complete_indirect_component_is_protected(self):
        graph=self.fixture()
        self.assertEqual(protected_floating(graph,{'internal'},{'poly1','poly2'}),{'poly1','poly2'})
        self.assertEqual(compare(graph,copy.deepcopy(graph),{'internal'},{'poly1','poly2'})['compared_pairs'],5)

    def test_remote_poly_change_fails_despite_unchanged_internal_incident_caps(self):
        before=self.fixture();after=copy.deepcopy(before)
        after['edges_af'][-1]=('poly2','vss',6.000000001)
        with self.assertRaisesRegex(ValueError,'Cell environment changed'):
            compare(before,after,{'internal'},{'poly1','poly2'})

    def test_new_floating_fill_attachment_is_not_discarded(self):
        before=self.fixture();after=copy.deepcopy(before)
        after['nodes'].append('fill');after['edges_af'].append(('poly2','fill',.1))
        with self.assertRaisesRegex(ValueError,'Cell environment changed'):
            compare(before,after,{'internal'},{'poly1','poly2'})

    def test_external_wire_only_changes_leave_cell_subnetwork_invariant(self):
        before=self.fixture();after=copy.deepcopy(before)
        after['nodes'].append('fill');after['edges_af'].extend([('pin','fill',.1),('fill','vss',1.)])
        self.assertEqual(compare(before,after,{'internal'},{'poly1','poly2'})['status'],'cell-capacitance-subnetwork-identical')

    def test_inventory_and_ground_corruption_fail(self):
        before=self.fixture()
        for mutation in ('ground','missing','self','negative','unknown','duplicate'):
            after=copy.deepcopy(before)
            if mutation=='ground':after['ground']='pin'
            elif mutation=='missing':after['nodes'].remove('poly1')
            elif mutation=='self':after['edges_af'].append(('pin','pin',1.))
            elif mutation=='negative':after['edges_af'].append(('pin','vss',-1.))
            elif mutation=='unknown':after['edges_af'].append(('missing','pin',1.))
            else:after['nodes'].append('pin')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                compare(before,after,{'internal'},{'poly1','poly2'})

    def test_device_nodes_cannot_be_classified_as_floating(self):
        before=self.fixture()
        for internal,floating in [([],['poly1']),(['internal'],['internal']),(['internal'],['vss']),(['vss'],[])]:
            with self.assertRaises(ValueError):compare(before,before,internal,floating)

    def test_subtraction_residue_is_recorded_without_changing_the_model(self):
        before=self.fixture();after=copy.deepcopy(before)
        after['edges_af'].append(('internal','pin',3.76802e-17))
        saved=copy.deepcopy(after)
        result=compare(before,after,{'internal'},{'poly1','poly2'})
        self.assertEqual(after,saved)
        self.assertEqual(result['status'],'cell-capacitance-subnetwork-preserved')
        self.assertEqual(result['total_native_residue_change_af'],3.76802e-17)
        after['edges_af'][-1]=('internal','pin',1e-10)
        with self.assertRaises(ValueError):compare(before,after,{'internal'},{'poly1','poly2'})

    def test_tiny_error_in_an_ordinary_capacitor_is_not_a_residue(self):
        before=self.fixture();after=copy.deepcopy(before)
        after['edges_af'][-1]=('poly2','vss',6.000000000000001)
        with self.assertRaises(ValueError):compare(before,after,{'internal'},{'poly1','poly2'})

    def test_cumulative_residue_bound_cannot_be_evaded_with_many_small_caps(self):
        before=self.fixture();after=copy.deepcopy(before)
        for i in range(2001):
            name=f'outside{i}';after['nodes'].append(name)
            after['edges_af'].append(('internal',name,5e-11))
        with self.assertRaises(ValueError):compare(before,after,{'internal'},{'poly1','poly2'})
