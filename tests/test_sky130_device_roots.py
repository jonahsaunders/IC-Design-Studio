import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_device_roots as checks
from scripts import sky130_device_root_review as review
from scripts import check_sky130_filled_replay as fixture
from scripts import sky130_floating_connectivity as block_check

ROOT=Path(__file__).resolve().parents[1]


class DeviceRootTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'layout.gds'
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')

    def shapes(self,name,cell=None):
        pair=checks.LAYERS[name] if isinstance(name,str) else name
        return (cell or self.top).shapes(self.layout.layer(*pair))

    def box(self,name,bounds=(0,0,1000,1000),cell=None):self.shapes(name,cell).insert(k.Box(*bounds))

    def stack(self,cell=None):
        for name in checks.CONDUCTORS:self.box(name,cell=cell)
        self.box('diff',cell=cell)

    def audit(self):
        self.layout.write(str(self.path));return checks.audit(self.path)

    def test_empty_seven_absences_do_not_claim_qualification(self):
        r=self.audit();self.assertEqual(len(r['rows']),7)
        self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);checks.validate_saved(r,self.path)

    def test_every_isolated_wire_is_unreviewed(self):
        for name in checks.WIRES:
            self.box(name);r=self.audit()
            self.assertEqual(r['unreviewed'],1)
            self.assertEqual(next(x for x in r['rows'] if x['layer']==name)['disposition'],'unreviewed')
            self.assertEqual(r['measurements']['graph']['unrooted'][0]['layers'],[name])
            self.assertNotIn('violations',r);checks.evaluate(r,r['gds_sha256'],'control');self.shapes(name).clear()

    def test_complete_stack_reaches_gate_without_pin_roots(self):
        self.stack();r=self.audit();g=r['measurements']['graph']
        self.assertEqual((g['nets'],g['rooted_nets'],g['contact_only_nets']),(1,1,0))
        self.assertFalse(r['pin_roots_used']);self.assertEqual(g['area_nm2'],g['covered_area_nm2'])
        self.assertTrue(all(x['disposition']=='executed-reviewed' for x in r['rows']))

    def test_each_missing_contact_disconnects_all_upper_wires(self):
        self.stack();ordered=list(checks.CONDUCTORS)
        for contact in ('licon','mcon','via','via2','via3','via4'):
            self.shapes(contact).clear();r=self.audit()
            expected=[n for n in ordered[ordered.index(contact)+1:] if n in checks.WIRES]
            self.assertEqual(sorted(x['layer'] for x in r['rows'] if x['disposition']=='unreviewed'),sorted(expected))
            self.box(contact)

    def test_diffusion_and_tap_roots_require_licon(self):
        for root in ('diff','tap'):
            self.box(root);self.box('li1');self.assertEqual(self.audit()['unreviewed'],1)
            self.box('licon');self.assertEqual(self.audit()['unreviewed'],0)
            for name in (root,'li1','licon'):self.shapes(name).clear()

    def test_one_nm_gap_and_disconnected_same_layer_islands(self):
        self.box('diff');self.box('poly');self.box('poly',(1001,0,2001,1000))
        r=self.audit();self.assertEqual(r['unreviewed'],1);self.assertEqual(r['measurements']['graph']['nets'],2)
        self.box('poly',(1000,0,1001,1000));self.assertEqual(self.audit()['unreviewed'],0)

    def test_pin_only_feedthrough_remains_unreviewed_but_block_profile_accepts_it(self):
        self.box('m1');self.box((68,16));r=self.audit()
        self.assertEqual(r['unreviewed'],1);self.assertFalse(r['pin_roots_used'])
        # A legal IP endpoint need not terminate at an internal transistor.
        old=block_check.audit(self.path);self.assertEqual(old['status'],'PASS');self.assertEqual(old['anchored_nets'],1)

    def test_pin_annotations_cannot_bridge_islands_or_connect_metal_levels(self):
        self.box('diff');self.box('licon');self.box('li1');self.box('mcon');self.box('m1')
        self.box('m1',(1001,0,2001,1000));self.box((68,16),(0,0,2001,1000))
        self.box('m2');self.box((69,16));r=self.audit()
        self.assertEqual(sorted(x['layer'] for x in r['rows'] if x['disposition']=='unreviewed'),['m1','m2'])

    def test_text_and_standard_cell_markers_are_not_roots(self):
        self.box('m1');self.box((81,4));self.shapes((68,5)).insert(k.Text('VDD',k.Trans()))
        self.shapes('m1').insert(k.Text('annotation',k.Trans()));r=self.audit()
        self.assertEqual(r['unreviewed'],1);self.assertEqual(r['measurements']['layers']['m1']['texts'],1)

    def test_all_exception_labels_are_conservative_guards_on_any_purpose(self):
        self.stack()
        for label in checks.LABELS:
            self.shapes((90,99)).clear();self.shapes((90,99)).insert(k.Text('prefix '+label.upper().replace('_',' _ ')+' suffix',k.Trans()))
            r=self.audit();self.assertEqual(r['unreviewed'],7);self.assertIsNone(r['measurements']['graph'])

    def test_all_unsupported_purposes_count_all_raw_shape_types(self):
        self.stack()
        for pair in checks.ABSENT:
            for shape in (k.Box(0,0,100,100),k.Text('guard',k.Trans()),k.Path([k.Point(0,0),k.Point(100,0)],1)):
                self.shapes(pair).clear();self.shapes(pair).insert(shape);r=self.audit()
                self.assertEqual(r['measurements']['unsupported']['%s:%s'%pair],1)
                self.assertEqual(r['unreviewed'],7);self.assertIsNone(r['measurements']['graph'])
            self.shapes(pair).clear()

    def test_poly_short_can_annotate_existing_poly_but_cannot_bridge_a_gap(self):
        self.box('poly');self.box('diff');self.box('poly_short');self.assertEqual(self.audit()['unreviewed'],0)
        self.box('poly',(1001,0,2001,1000));self.box('poly_short',(0,0,2001,1000))
        r=self.audit();self.assertEqual(r['unreviewed'],7);self.assertEqual(r['measurements']['poly_short_outside'],1)

    def test_holes_fragments_arrays_and_reflections_preserve_geometry(self):
        child=self.layout.create_cell('child');self.stack(child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,10000,20000),k.Vector(5000,0),k.Vector(0,5000),2,3))
        r=self.audit();self.assertEqual(r['measurements']['graph']['rooted_nets'],6)
        ring=k.Polygon(k.Box(0,0,3000,3000));ring.insert_hole([k.Point(500,500),k.Point(500,2500),k.Point(2500,2500),k.Point(2500,500)])
        self.shapes('poly').insert(ring);self.box('poly',(1000,1000,2000,2000));self.box('diff',(1000,1000,2000,2000))
        r=self.audit();self.assertEqual(r['measurements']['graph']['rooted_nets'],7);self.assertEqual(r['unreviewed'],1)
        self.box('poly',(0,1000,1000,2000));self.assertEqual(self.audit()['unreviewed'],0)

    def test_paths_have_exact_polygon_equivalence(self):
        self.box('diff',(-1000,-1000,2000,1000));path=k.Path([k.Point(0,0),k.Point(1000,0)],200)
        self.shapes('poly').insert(path);a=self.audit()['measurements']
        self.shapes('poly').clear();self.shapes('poly').insert(path.polygon());self.assertEqual(a,self.audit()['measurements'])

    def test_contact_only_net_is_counted_without_becoming_a_wire_pass(self):
        self.box('via');r=self.audit();self.assertEqual(r['measurements']['graph']['contact_only_nets'],1)
        self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))

    def test_unsupported_shapes_units_and_transforms_fail(self):
        for shape in (k.Text('unexpected',k.Trans()),k.Path([k.Point(0,0),k.Point(1000,0)],199),
                      k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)])):
            self.shapes('licon').clear();self.shapes('licon').insert(shape)
            with self.assertRaises(ValueError):self.audit()
        self.shapes('licon').clear();self.layout.dbu=.005
        with self.assertRaisesRegex(ValueError,'1 nm'):self.audit()
        self.layout.dbu=.001;child=self.layout.create_cell('extra_top');self.box('poly',cell=child)
        with self.assertRaisesRegex(ValueError,'one top'):self.audit()
        self.top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(2,0,False,0,0)))
        with self.assertRaisesRegex(ValueError,'transform'):self.audit()

    def test_missing_altered_or_inconsistent_reports_fail(self):
        self.stack();r=self.audit()
        for key in ('rows','source','measurements','scope','pin_roots_used'):
            bad=copy.deepcopy(r);bad.pop(key)
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        for change in (lambda m:m['graph'].update(nets=False),lambda m:m['graph'].update(rooted_nets=0),
                       lambda m:m['graph']['covered_area_nm2'].update(m1=0),lambda m:m['layers']['m1'].update(area_nm2=False)):
            bad=copy.deepcopy(r);change(bad['measurements'])
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        self.shapes('via').clear();broken=self.audit();broken['measurements']['graph']['unrooted']=[]
        with self.assertRaisesRegex(ValueError,'accounting'):checks.evaluate(broken,broken['gds_sha256'],'control')

    def test_rehashed_cut_layout_cannot_retain_a_saved_pass(self):
        self.stack();r=self.audit();self.shapes('via4').clear();self.layout.write(str(self.path))
        r['gds_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'actual layout'):checks.validate_saved(r,self.path)

    def test_source_binding_authenticates_exact_endpoint_and_layer_definitions(self):
        folder=Path(self.temp.name)/'fixture';fixture.unpack(fixture.BUNDLE,folder)
        catalog=json.loads((ROOT/'docs/qualification/sky130-error-rule-inventory.json').read_bytes())
        proof=review.source_proof(folder/'sources',catalog);self.assertEqual(len(proof['bindings']),7)
        modified=copy.deepcopy(catalog);next(r for r in modified['rows'] if r['id']=='s11')['description']='other endpoint'
        with self.assertRaises(ValueError):review.source_proof(folder/'sources',modified)
        path=folder/'sources/docs/rules/layers/table-c3-device-lvs-other.csv';path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Changed'):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
