import unittest,tempfile,random
from pathlib import Path
from unittest.mock import patch
from icstudio.model import clone,validate,digest,History,device,uid,example,save_project,load_project
from icstudio import interface_update as migration,capture_ops as ops,wiring,electrical_rules as erc,cross_probe
from icstudio.symbol_io import default_symbol,symbol_text,import_symbol
from icstudio.symbol_geometry import enriched
from icstudio.physical_cells import instance_pins,place
from icstudio.layout import rect
from icstudio.testbenches import create
from test_capture import amplifier

def fixture():
    p,c=amplifier();cid,did=ops.make_cell(p,c['id'],[d['id'] for d in c['devices'] if d['kind'] in ('R','NMOS')],'amplifier');child=ops.cell(p,cid)
    child['layout_ports']=[{'name':n,'layer':'metal1','point':[i*2000,0]} for i,n in enumerate(child['ports'])];child['shapes']=[rect('metal1',i*2000-100,-100,200,200,net=n) for i,n in enumerate(child['ports'])];child['layout_texts']=[{'text':n,'layer':'metal1','x':i*2000,'y':0,'rotation':0} for i,n in enumerate(child['ports'])]
    place(p,c['id'],did,10000,20000,90,True);p['testbenches']=[create(p,c['id'],'amplifier_ac')];p['testbenches'][0]['analysis'].update(type='ac',start='10',end='10meg',points=20);validate(p);return p,c['id'],cid,did

def rename(s,old,new):
    s=clone(s);s['pins'][new]=s['pins'].pop(old);s['pin_meta'][new]=s['pin_meta'].pop(old);s['pin_order']=[new if n==old else n for n in s['pin_order']];return s

class ConsistencyTests(unittest.TestCase):
    def test_public_erc_and_cli_policy_entry_point_agree(self):
        from icstudio.model import erc as public_erc
        p=example('empty');p['electrical_rules']={'rules':{'ERC.EMPTY':'off','ERC.GROUND':'off'}};self.assertEqual(public_erc(p),[]);self.assertEqual(public_erc(p),erc.check(p,p['top']))
    def test_float_tolerance_matches_electrical_segment_predicate(self):
        p=example('empty');c=p['cells'][0];d=device('R','R1',50,50+1e-10);c['devices']=[d];wire={'id':uid(),'points':[[0,0],[100,0]]};c['wires']=[wire];g=wiring.graph(c,p);self.assertEqual(g[d['id'],'p'],g['wire',wire['id']]);d['y']=50+1e-5;g=wiring.graph(c,p);self.assertNotEqual(g[d['id'],'p'],g['wire',wire['id']])
    def test_multiple_parent_instances_keep_independent_nets_when_pins_move(self):
        p,root,cid,did=fixture();p.pop('testbenches');parent=ops.cell(p,root);other=device('X','X2',900,900,cell=cid,nets={'out':'second_out','vin':'second_in','vdd':'vdd'});other['net_labels']=clone(other['nets']);parent['devices'].append(other);validate(p);s=rename(ops.cell(p,cid)['symbol'],'vin','input');s['pins']['input']=[-80,120];q=migration.plan(p,cid,s)['candidate'];users=[d for d in ops.cell(q,root)['devices'] if d['kind']=='X'];self.assertEqual([d['nets']['input'] for d in users],['vin','second_in']);self.assertTrue(all(d['symbol']['pins']['input']==[-80,120] for d in users))
    def test_review_rename_all_views_parent_nets_benches_and_one_undo(self):
        p,root,cid,did=fixture();base=ops.cell(p,cid)['symbol'];s=rename(base,'out','output');s['pins']['output'][0]+=20;before=clone(p);review=migration.plan(p,cid,s,base);self.assertEqual(p,before);self.assertEqual(len(review['impact']['testbenches']),1)
        h=History(p);h.commit(lambda q:migration.apply(q,review),'interface');q=h.project;c=ops.cell(q,cid);inst=next(d for d in ops.cell(q,root)['devices'] if d['id']==did)
        self.assertEqual(inst['nets']['output'],'out');self.assertEqual(c['symbol']['pin_meta']['output']['id'],base['pin_meta']['out']['id']);self.assertIn('output',{s['net'] for s in c['shapes']});self.assertNotIn('out',{t['text'] for t in c['layout_texts']});self.assertIn('output',{t['pin'] for t in instance_pins(q,root)});self.assertEqual(q['testbenches'],p['testbenches']);self.assertEqual(c['interface_history'][-1]['mapping']['out'],'output')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'interface.icproj';save_project(q,path);self.assertEqual(load_project(path)['cells'],q['cells'])
        h.undo();self.assertEqual(h.project['cells'],before['cells']);self.assertEqual(h.project['testbenches'],before['testbenches'])
    def test_added_terminal_explicit_net_or_unconnected_and_physical_assignment(self):
        p,root,cid,did=fixture();s=clone(ops.cell(p,cid)['symbol']);s['pins']['sense']=[100,100];s['pin_order'].append('sense');s=enriched(s)
        review=migration.plan(p,cid,s);inst=next(d for d in ops.cell(review['candidate'],root)['devices'] if d['id']==did);self.assertTrue(inst['nets']['sense'].startswith('N_'));self.assertIn('sense',review['impact']['unassigned_physical'])
        review=migration.plan(p,cid,s,connections={did:{'sense':'out'}},physical={'sense':{'layer':'metal1','point':[6000,0]}});q=review['candidate'];inst=next(d for d in ops.cell(q,root)['devices'] if d['id']==did);self.assertEqual(inst['nets']['sense'],'out');self.assertNotIn('sense',review['impact']['unassigned_physical']);self.assertIn('sense',{t['pin'] for t in instance_pins(q,root)})
    def test_removed_port_keeps_internal_net_and_parent_wire_stubs(self):
        p,root,cid,did=fixture();c=ops.cell(p,cid);s=clone(c['symbol']);s['pin_order'].remove('vin');s['pins'].pop('vin');s['pin_meta'].pop('vin');oldpos=wiring.pins(ops.cell(p,root),p)[did,'vin'];review=migration.plan(p,cid,s);q=review['candidate'];parent=ops.cell(q,root)
        self.assertNotIn('vin',next(d for d in parent['devices'] if d['id']==did)['nets']);self.assertTrue(any(l['anchor'].get('point')==oldpos and l['name']=='vin' for l in parent.get('labels',[])));self.assertIn('vin',{n for d in ops.cell(q,cid)['devices'] for n in d['nets'].values()});self.assertNotIn('vin',{t['pin'] for t in instance_pins(q,root)});self.assertEqual(review['impact']['disconnected'][0]['pin'],'vin')
    def test_removed_probe_requires_review_and_dependents_are_listed(self):
        p,root,cid,did=fixture();parent=ops.cell(p,root);parent['devices']=[d for d in parent['devices'] if d['kind']!='C'];p['testbenches'][0]['measurements']=[{'kind':'voltage','name':'output_voltage','node':'out'}];validate(p);s=clone(ops.cell(p,cid)['symbol']);s['pins'].pop('out');s['pin_meta'].pop('out');s['pin_order'].remove('out')
        with self.assertRaisesRegex(ValueError,'missing probe'):migration.plan(p,cid,s)
        review=migration.plan(p,cid,s,drop_invalid_probes=True);self.assertEqual(review['impact']['bench_changes'][0]['removed_measurements'],['output_voltage']);self.assertNotIn('out',review['candidate']['testbenches'][0]['probes'])
    def test_stale_review_and_candidate_tamper_never_commit(self):
        p,root,cid,_=fixture();review=migration.plan(p,cid,rename(ops.cell(p,cid)['symbol'],'vin','input'));before=clone(p);p['revision']+=1
        with self.assertRaisesRegex(ValueError,'project changed'):migration.apply(p,review)
        p=before;review['candidate']['name']='tampered'
        with self.assertRaisesRegex(ValueError,'candidate changed'):migration.apply(p,review)
        self.assertEqual(p,before)
    def test_mapping_rejects_merge_unknown_connection_and_grid_error(self):
        p,root,cid,did=fixture();s=ops.cell(p,cid)['symbol']
        with self.assertRaisesRegex(ValueError,'distinct'):migration.plan(p,cid,s,mapping={n:'out' for n in s['pins']})
        with self.assertRaisesRegex(ValueError,'missing use'):migration.plan(p,cid,s,connections={'missing':{}})
        changed=clone(s);changed['pins']['sense']=[100,100];changed['pin_order'].append('sense');changed=enriched(changed)
        with self.assertRaisesRegex(ValueError,'grid'):migration.plan(p,cid,changed,physical={'sense':{'layer':'metal1','point':[1,0]}})
    def test_simultaneous_port_swap_preserves_distinct_internal_and_parent_nets(self):
        p,root,cid,did=fixture();base=ops.cell(p,cid)['symbol'];s=rename(rename(rename(base,'vin','temp'),'out','vin'),'temp','out');q=migration.plan(p,cid,s,base)['candidate'];d=next(d for d in ops.cell(q,root)['devices'] if d['id']==did);self.assertEqual((d['nets']['vin'],d['nets']['out']),('out','vin'));mos=next(d for d in ops.cell(q,cid)['devices'] if d['kind']=='NMOS');self.assertEqual((mos['nets']['g'],mos['nets']['d']),('out','vin'))
    def test_cross_probe_distinguishes_reused_cells_and_root_net_mapping(self):
        p,root,cid,did=fixture();p.pop('testbenches');parent=ops.cell(p,root);other=device('X','X2',900,900,cell=cid,nets={'out':'other_out','vin':'other_in','vdd':'vdd'});other['symbol']=clone(ops.cell(p,cid)['symbol']);other['net_labels']=clone(other['nets']);parent['devices'].append(other);validate(p)
        rows=cross_probe.occurrences(p,root);self.assertEqual(next(r for r in rows if r['object']==other['id'])['status'],'Missing placement');leaf=ops.cell(p,cid)['devices'][0]['id'];self.assertEqual({tuple(r['path']) for r in rows if r['object']==leaf},{(did,),(other['id'],)})
        nets=cross_probe.net_occurrences(p,root,'out');self.assertEqual([r['path'] for r in nets if r['cell']==cid],[[did]]);self.assertEqual(len([r for r in cross_probe.net_occurrences(p,root,'vdd') if r['cell']==cid]),2)
    def test_electrical_policy_severity_scope_occurrences_and_optional_pin(self):
        p,root,cid,did=fixture();p['electrical_rules']={'scope':'hierarchy','rules':{'SYMBOL.OVERLAP':'error','ERC.GROUND':'off'}};child=ops.cell(p,cid);child['symbol']['pins']['vin']=clone(child['symbol']['pins']['out']);rows=erc.check(p,root);issue=next(i for i in rows if i['code']=='SYMBOL.OVERLAP');self.assertEqual(issue['path'],[did]);self.assertEqual(issue['severity'],'error')
        extra={'id':uid(),'name':'isolated','ports':[],'devices':[device('R','R1',nets={'p':'lonely','n':'0'})],'shapes':[]};extra['devices'][0]['symbol']=enriched(default_symbol(['p','n']));extra['devices'][0]['symbol']['pin_meta']['p']['required']=False;p['cells'].append(extra);self.assertFalse(any(i['cell']==extra['id'] for i in erc.check(p,root)));p['electrical_rules']['scope']='project';rows=erc.check(p,root);self.assertFalse(any(i['code']=='ERC.DANGLING' and i['cell']==extra['id'] and i['pin']=='p' for i in rows))
        with self.assertRaises(ValueError):erc.validate_policy({'rules':{'unknown':'error'}})
    def test_bus_direction_rules_and_required_metadata_exchange(self):
        p=example('empty');root=p['top'];s=enriched(default_symbol(['data[0]','out']));s['pin_meta']['data[0]'].update(bus='data[1:0]',direction='in',required=False);s['pin_meta']['out']['direction']='out';child={'id':uid(),'name':'unit','ports':s['pin_order'],'symbol':s,'devices':[],'shapes':[]};p['cells'].append(child);p['cells'][0]['devices']=[device('X','X'+str(i),i*200,0,cell=child['id'],nets={'data[0]':'input','out':'result'}) for i in range(2)]
        rows=erc.check(p,root);self.assertIn('ERC.DRIVERS',{i['code'] for i in rows});self.assertEqual(len([i for i in rows if i['code']=='ERC.BUS.WIDTH']),2);self.assertNotIn('ERC.UNDRIVEN',{i['code'] for i in rows})
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'unit.sym';path.write_text(symbol_text(s));restored,_,_=import_symbol(path,True);self.assertFalse(restored['pin_meta']['data[0]']['required'])
    def test_indexed_graph_matches_exhaustive_queries_on_crossings_and_t_junctions(self):
        rng=random.Random(13);p=example('empty');c=p['cells'][0];c['devices']=[device('R','R'+str(i),rng.randrange(10)*20,rng.randrange(10)*20) for i in range(12)];c['wires']=[{'id':uid(),'points':[[rng.randrange(10)*20,y],[rng.randrange(10)*20+200,y]]} for y in range(0,200,20)]+[{'id':uid(),'points':[[x,0],[x,200]]} for x in range(0,200,20)];c['junctions']=[[40,40],[120,100]];c['labels']=[]
        actual=wiring.graph(c,p);original=wiring.segment_index
        class Exhaustive:
            def __init__(self,count):self.count=count
            def query(self,box):return list(range(self.count))
        def brute(cell):segments,_=original(cell);return segments,Exhaustive(len(segments))
        with patch('icstudio.wiring.segment_index',brute):expected=wiring.graph(c,p)
        keys=list(actual)
        for a in keys:
            for b in keys:self.assertEqual(actual[a]==actual[b],expected[a]==expected[b])

if __name__=='__main__':unittest.main()
