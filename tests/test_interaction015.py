"""Topology and numerical measurement regressions for direct editing."""
import unittest
from icstudio.model import example,device,uid,clone,validate
from icstudio import wiring,capture_ops
from icstudio.measurements import sample_at,evaluate


def circuit():
    p=example('empty');c=p['cells'][0];c.update(wires=[],junctions=[],labels=[])
    c['devices']=[device('R','R1',0,50),device('C','C1',200,50)]
    for d in c['devices']:d['net_labels']={}
    wiring.add_wire(c,[[0,0],[0,-50],[200,-50],[200,0]],p)
    return p,c


class ConnectedMovement(unittest.TestCase):
    def test_repeated_segment_slide_does_not_accumulate_corners(self):
        p,c=circuit();wire=c['wires'][0];original=clone(wire['points'])
        for dy in [-10,-10,20]*20:
            wiring.reshape_segment(c,wire['id'],1,0,dy,p);validate(p)
            self.assertEqual(len(wire['points']),4)
            self.assertEqual(c['devices'][0]['nets']['p'],c['devices'][1]['nets']['p'])
        self.assertEqual(wire['points'],original);self.assertEqual(len(c['wires']),1)

    def test_free_wire_slides_without_artificial_endpoint_stubs(self):
        p=example('empty');c=p['cells'][0];c.update(wires=[{'id':uid(),'points':[[0,0],[100,0]]}],junctions=[])
        wiring.reshape_segment(c,c['wires'][0]['id'],0,0,40,p)
        self.assertEqual(c['wires'][0]['points'],[[0,40],[100,40]])

    def test_pin_move_and_return_keeps_route_size_bounded(self):
        p,c=circuit();original=clone(c['wires'][0]['points']);d=c['devices'][0]
        for dx,dy in [(10,10),(10,-10),(-20,0)]*20:
            old=wiring.pins(c,p);d['x']+=dx;d['y']+=dy;wiring.keep_connections(c,old,p);validate(p)
            self.assertLessEqual(len(c['wires'][0]['points']),4)
            self.assertEqual(c['devices'][0]['nets']['p'],c['devices'][1]['nets']['p'])
        self.assertEqual(c['wires'][0]['points'],original)

    def test_group_translation_preserves_simple_direct_wire(self):
        p,c=circuit();c['wires'][0]['points']=[[0,0],[200,0]]
        ids=[d['id'] for d in c['devices']]
        for dx,dy in [(200,10),(-200,-10)]*10:
            capture_ops.transform(p,c['id'],ids,dx,dy,stretch=True);validate(p)
            self.assertEqual(len(c['wires'][0]['points']),2)
        self.assertEqual(c['wires'][0]['points'],[[0,0],[200,0]])

    def test_branch_lead_stretches_without_new_wire_per_drag(self):
        p,c=circuit();c['devices'].append(device('L','L1',100,-150));c['devices'][-1]['net_labels']={}
        wiring.add_wire(c,[[100,-100],[100,-50]],p)
        for dy in [-10,-10,20]*15:
            wiring.reshape_segment(c,c['wires'][0]['id'],1,0,dy,p);validate(p)
            self.assertEqual(len(c['wires']),2)
            self.assertEqual(c['devices'][0]['nets']['p'],c['devices'][2]['nets']['n'])
            self.assertLessEqual(sum(len(w['points']) for w in c['wires']),7)

    def test_shared_pin_moves_to_distinct_destinations_keep_branches(self):
        p,c=circuit();a=c['devices'][0];b=device('L','L1',0,50);b['net_labels']={};c['devices'].append(b)
        old=wiring.pins(c,p);a['x']=20;b['x']=-20;wiring.keep_connections(c,old,p);validate(p)
        self.assertEqual(len({d['nets']['p'] for d in c['devices']}),1)

    def test_stationary_pin_on_dragged_segment_remains_connected(self):
        p,c=circuit();c['devices'].append(device('L','L1',100,0));c['devices'][-1]['net_labels']={};wiring.rebuild(c,p)
        for dy in [-10,-10,20]*10:
            # Interior run remains horizontal; find it by its long horizontal span.
            w=c['wires'][0];index=next(i for i,(a,b) in enumerate(zip(w['points'],w['points'][1:])) if abs(a[0]-b[0])==200)
            wiring.reshape_segment(c,w['id'],index,0,dy,p);validate(p)
            self.assertEqual(len({d['nets']['p'] for d in c['devices']}),1)
            self.assertLessEqual(len(c['wires']),2)


class Measurements(unittest.TestCase):
    def result(self,x=None,values=None,kind='tran'):
        return {'x':x or [0,1,2], 'traces':{'out':values or [0,2,0]},'settings':{'type':kind}}

    def test_exact_interpolation_nearest_and_out_of_range(self):
        r=self.result();self.assertEqual(sample_at(r,'out',.25),.5);self.assertEqual(sample_at(r,'out',.25,True),0)
        self.assertIsNone(sample_at(r,'out',3));self.assertEqual(sample_at(r,'out',2),0)

    def test_descending_dc_and_logarithmic_frequency(self):
        self.assertEqual(sample_at(self.result([2,1,0],[0,2,0],'dc'),'out',.25),.5)
        self.assertAlmostEqual(sample_at(self.result([1,100],[0,2],'ac'),'out',10),1)

    def test_limit_at_any_xy_and_whole_trace(self):
        r=self.result();m={'kind':'XY','x':.25,'y':.5,'trace':'out','rule':'<='}
        self.assertEqual(evaluate(r,m)['verdict'],'PASS');m['y']=.49;self.assertEqual(evaluate(r,m)['verdict'],'FAIL')
        m['kind']='Y';m['y']=1;self.assertEqual(evaluate(r,m),{'value':2,'verdict':'FAIL','crossings':2})
        m['rule']='>=';m['y']=0;self.assertEqual(evaluate(r,m)['verdict'],'PASS')

    def test_missing_trace_and_out_of_domain_cannot_pass(self):
        m={'kind':'XY','x':3,'y':100,'trace':'out','rule':'<='}
        self.assertEqual(evaluate(self.result(),m)['verdict'],'Out of range');m['trace']='missing';self.assertEqual(evaluate(self.result(),m)['verdict'],'No trace')
