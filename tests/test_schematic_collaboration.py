"""Real HTTP schematic transactions, electrical races, hierarchy and recovery."""
from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import unittest
from pathlib import Path

from test_live_collaboration import KEY, post
from icstudio import wiring
from icstudio.capture_ops import transform, apply_symbol
from icstudio.electrical_identity import partition, terminal_id
from icstudio.layout import rect
from icstudio.layout_collaboration import Session
from icstudio.live_protocol import changes
from icstudio.live_server import Server
from icstudio.live_store import Store
from icstudio.model import clone, device, example, uid, validate


def circuit():
    p = example('empty'); c = p['cells'][0]
    c.update(devices=[device('R', 'R1', 0, 0), device('R', 'R2', 500, 0)],
             wires=[], labels=[], junctions=[], electrical={})
    c['shapes'] = [rect('metal1', 2000, 0, 600, 600)]
    return validate(p)


class SchematicCollaboration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'server.sqlite3'
        self.start()
        self.p = circuit()
        status, self.a = post(self.url, '/v2/workspaces', dict(project=self.p, name='Alice'), KEY)
        self.assertEqual(status, 200, self.a)
        self.wid = self.a['workspace']; self.base = '/v2/workspaces/' + self.wid
        _, invite = self.api('invite', dict(role='edit'), self.a)
        _, self.b = self.api('join', dict(invite=invite['invite'], name='Bob'))

    def start(self):
        self.store = Store(self.path, KEY)
        self.server = Server(('127.0.0.1', 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(5); self.store.close()

    def tearDown(self):
        self.stop(); self.temp.cleanup()

    def api(self, action, data, actor=None):
        return post(self.url, self.base + '/' + action, data, actor['token'] if actor else '')

    def request(self, snapshot, fn):
        q = clone(snapshot['project']); fn(q); validate(q)
        return dict(id=uid(), revision=snapshot['revision'], action='edit',
                    label='Schematic edit', changes=changes(snapshot['project'], q))

    def state(self, actor=None):
        status, result = self.api('sync', {}, actor or self.a)
        self.assertEqual(status, 200, result)
        return result

    def accept(self, request, actor=None):
        status, result = self.api('edit', request, actor or self.a)
        self.assertEqual(status, 200, result)
        return result

    def test_parallel_component_moves_and_personal_undo_preserve_other_editor(self):
        before = partition(self.p['cells'][0]); barrier = threading.Barrier(2)
        def move(actor, index):
            d = actor['project']['cells'][0]['devices'][index]
            req = self.request(actor, lambda p: transform(p, p['top'], [d['id']], dx=50))
            barrier.wait(); return self.api('edit', req, actor)
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(move, self.a, 0), pool.submit(move, self.b, 1)]
            for future in futures:
                status, result = future.result(); self.assertEqual(status, 200, result)
        state = self.state(); self.assertEqual([d['x'] for d in state['project']['cells'][0]['devices']], [50, 550])
        self.assertEqual(partition(state['project']['cells'][0]), before)
        state = self.accept(dict(id=uid(), action='undo'))
        self.assertEqual([d['x'] for d in state['project']['cells'][0]['devices']], [0, 550])
        state = self.accept(dict(id=uid(), action='redo'))
        self.assertEqual([d['x'] for d in state['project']['cells'][0]['devices']], [50, 550])

    def test_layout_and_schematic_changes_merge_in_one_revision_history(self):
        self.accept(self.request(self.a, lambda p: p['cells'][0]['devices'][0].update(value='12k')))
        state = self.accept(self.request(self.b, lambda p: p['cells'][0]['shapes'][0].update(points=[[2100, 0], [2700, 600]])), self.b)
        self.assertEqual(state['project']['cells'][0]['devices'][0]['value'], '12k')
        self.assertEqual(state['revision'], 2)

    def test_new_touching_wires_conflict_even_without_common_object_ids(self):
        first = self.request(self.a, lambda p: wiring.add_wire(p['cells'][0], [[100, 200], [200, 200]], p))
        second = self.request(self.b, lambda p: wiring.add_wire(p['cells'][0], [[200, 200], [300, 200]], p))
        self.accept(first)
        status, _ = self.api('edit', second, self.b)
        self.assertEqual(status, 409); self.assertEqual(len(self.state()['project']['cells'][0]['wires']), 1)

    def test_new_disjoint_wires_merge_and_server_assigns_distinct_nets(self):
        self.accept(self.request(self.a, lambda p: wiring.add_wire(p['cells'][0], [[100, 200], [200, 200]], p)))
        state = self.accept(self.request(self.b, lambda p: wiring.add_wire(p['cells'][0], [[800, 200], [900, 200]], p)), self.b)
        self.assertEqual(len({w['net'] for w in state['project']['cells'][0]['wires']}), 2)

    def test_wire_connection_and_stretch_are_atomic_and_keep_terminal_identity(self):
        state = self.accept(self.request(self.a, lambda p: wiring.add_wire(p['cells'][0], [[0, 50], [500, 50]], p)))
        before = state['project']['cells'][0]; identity = before['devices'][0]['terminal_ids']; group = partition(before)
        moved = self.accept(self.request(state, lambda p: transform(p, p['top'], [p['cells'][0]['devices'][0]['id']], dx=100)))
        cell = moved['project']['cells'][0]
        self.assertEqual(cell['devices'][0]['terminal_ids'], identity); self.assertEqual(partition(cell), group)
        self.assertIn([100, 50], cell['wires'][0]['points'])
        self.assertEqual(self.accept(dict(id=uid(), action='undo'))['project']['cells'][0]['wires'], before['wires'])

    def test_same_device_changes_and_stale_undo_are_rejected(self):
        original = self.request(self.a, lambda p: p['cells'][0]['devices'][0].update(value='12k'))
        self.accept(original)
        self.assertEqual(self.api('edit', self.request(self.b, lambda p: p['cells'][0]['devices'][0].update(value='20k')), self.b)[0], 409)
        state = self.state(self.b)
        self.accept(self.request(state, lambda p: p['cells'][0]['devices'][0].update(value='30k')), self.b)
        self.assertEqual(self.api('edit', dict(id=uid(), action='undo'), self.a)[0], 409)

    def test_duplicate_component_names_and_bad_wires_do_not_publish(self):
        def add(p): p['cells'][0]['devices'].append(device('C', 'C1', 1000, 0))
        first, second = self.request(self.a, add), self.request(self.b, add)
        self.accept(first); self.assertEqual(self.api('edit', second, self.b)[0], 409)
        state = self.state(); req = self.request(state, lambda p: wiring.add_wire(p['cells'][0], [[100, 200], [200, 200]], p))
        next(r for r in req['changes'] if r['field'] == 'wires')['after']['points'] = [[0, 0], [10, 10]]
        self.assertEqual(self.api('edit', req, self.a)[0], 409); self.assertEqual(self.state()['revision'], 1)

    def test_server_rebuilds_forged_derived_connectivity(self):
        req = self.request(self.a, lambda p: wiring.add_wire(p['cells'][0], [[0, 50], [500, 50]], p))
        next(r for r in req['changes'] if r['field'] == 'wires')['after']['net'] = 'FORGED'
        state = self.accept(req); c = state['project']['cells'][0]
        self.assertEqual(c['devices'][0]['nets']['n'], c['devices'][1]['nets']['n'])
        self.assertNotEqual(c['wires'][0]['net'], 'FORGED')

    def test_hierarchy_creation_symbol_interface_update_and_undo(self):
        from icstudio.symbol_io import default_symbol
        child = dict(id=uid(), name='child', ports=['a', 'b'], devices=[device('R', 'Rchild', nets={'p':'a','n':'b'})], shapes=[])
        child['symbol'] = default_symbol(child['ports'])
        def add(p):
            p['cells'].append(clone(child))
            p['cells'][0]['devices'].append(device('X','X1',1000,0,cell=child['id'],nets={'a':'a','b':'b'}))
        state = self.accept(self.request(self.a, add)); self.assertEqual(len(state['project']['cells']), 2)
        # Existing symbol API applies one consistent interface to all instances.
        symbol = clone(child['symbol']); symbol['primitives'].append({'kind':'line','points':[[-20,0],[20,0]]})
        state = self.accept(self.request(state, lambda p: apply_symbol(p, child['id'], symbol)))
        self.assertEqual(state['project']['cells'][1]['symbol']['primitives'][-1]['points'], [[-20,0],[20,0]])
        terminal = next(d for d in state['project']['cells'][0]['devices'] if d['name']=='X1')['terminal_ids']['a']
        renamed = clone(state['project']['cells'][1]['symbol'])
        renamed['pins']['input'] = renamed['pins'].pop('a')
        renamed['pin_meta']['input'] = renamed['pin_meta'].pop('a')
        renamed['pin_order'] = ['input' if pin=='a' else pin for pin in renamed['pin_order']]
        request = self.request(state, lambda p: apply_symbol(p, child['id'], renamed))
        partial = dict(request, id=uid(), changes=[r for r in request['changes'] if r['cell']==child['id']])
        self.assertEqual(self.api('edit', partial, self.a)[0],409)
        renamed_state = self.accept(request)
        instance = next(d for d in renamed_state['project']['cells'][0]['devices'] if d['name']=='X1')
        self.assertIn('input', instance['nets']);self.assertNotIn('a', instance['nets'])
        self.assertEqual(instance['terminal_ids']['input'], terminal)
        self.assertEqual(self.api('edit', self.request(self.b, lambda p: p['cells'][0]['devices'][0].update(value='14k')), self.b)[0], 409)
        self.accept(dict(id=uid(), action='undo'))
        self.accept(dict(id=uid(), action='undo')); state = self.accept(dict(id=uid(), action='undo'))
        self.assertEqual(len(state['project']['cells']), 1)

    def test_move_and_delete_connected_wire_require_review(self):
        state=self.accept(self.request(self.a,lambda p:wiring.add_wire(p['cells'][0],[[0,50],[500,50]],p)))
        move=self.request(state,lambda p:transform(p,p['top'],[p['cells'][0]['devices'][0]['id']],dx=100))
        deletion=self.request(state,lambda p:p['cells'][0].update(wires=[]))
        self.accept(deletion,self.b)
        self.assertEqual(self.api('edit',move,self.a)[0],409)
        current=self.state()['project']['cells'][0]
        self.assertEqual(current['devices'][0]['x'],0);self.assertEqual(current['wires'],[])

    def test_net_rename_and_remote_connection_change_conflict(self):
        from icstudio.net_labels import add,rename
        def label(p): add(p['cells'][0],'signal',dict(kind='pin',id=p['cells'][0]['devices'][0]['id'],pin='n'),p)
        state=self.accept(self.request(self.a,label))
        renamed=self.request(state,lambda p:rename(p['cells'][0],p['cells'][0]['labels'][0]['id'],'output',p))
        connect=self.request(state,lambda p:wiring.add_wire(p['cells'][0],[[0,50],[500,50]],p))
        self.accept(renamed)
        self.assertEqual(self.api('edit',connect,self.b)[0],409)
        self.assertEqual(self.state()['project']['cells'][0]['labels'][0]['name'],'output')

    def test_schematic_presence_reservations_and_viewer_permission(self):
        ident = self.p['cells'][0]['devices'][0]['id']
        status, state = self.api('sync', dict(presence=dict(cell=self.p['top'],view='schematic',selection=[ident],cursor=[0,0])), self.a)
        self.assertEqual(status,200);self.assertEqual(state['participants'][0]['view'],'schematic');self.assertTrue(state['leases'])
        self.assertEqual(self.api('edit',self.request(self.b,lambda p:p['cells'][0]['devices'][0].update(value='14k')),self.b)[0],409)
        _, invite = self.api('invite',dict(role='view'),self.a)
        _, viewer = self.api('join',dict(invite=invite['invite'],name='Reviewer'))
        self.assertEqual(self.api('edit',self.request(viewer,lambda p:p['cells'][0]['devices'][1].update(value='14k')),viewer)[0],403)

    def test_retry_after_server_restart_applies_once_and_v1_is_rejected(self):
        req=self.request(self.a,lambda p:p['cells'][0]['devices'][0].update(value='14k'))
        self.accept(req);self.store.db.execute('PRAGMA user_version=1');self.stop();self.start()
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0],2)
        state=self.accept(req);self.assertEqual(state['revision'],1);self.assertEqual(state['acknowledged'],req['id'])
        self.assertEqual(post(self.url,'/v1/workspaces',dict(project=self.p,name='Old client'),KEY)[0],426)

    def test_checkpoint_comments_on_terminals_nets_and_electrical_findings(self):
        from icstudio.review_anchors import targets
        def review(**kw): return self.api('review', dict(id=uid(), **kw), self.a)
        status, cp=review(action='create_checkpoint',revision=0,name='Schematic review');self.assertEqual(status,200)
        choices=targets(self.p,self.p['top'],findings=True)
        for prefix in ('terminal:','net:','finding:'):
            key=next(k for k in choices if k.startswith(prefix))
            status, result=review(action='comment',checkpoint=cp['id'],cell=self.p['top'],object=key,text='Please inspect this connection')
            self.assertEqual(status,200,result)
        self.assertEqual(review(action='comment',checkpoint=cp['id'],cell=self.p['top'],object='terminal:missing',text='Invalid')[0],409)


class SharedFolderSchematic(unittest.TestCase):
    def test_whole_cell_schematic_and_whole_project_hierarchy_claims(self):
        with tempfile.TemporaryDirectory() as root:
            a=Session.create(root,circuit(),'Alice');b=Session.join(root,'Bob');cid=a.base['top']
            a.claim(cid,['metal1']);q=clone(a.base);q['cells'][0]['devices'][0]['value']='22k'
            with self.assertRaisesRegex(ValueError,'whole cell'):a.publish(q)
            a.release();a.claim(cid);a.publish(q);self.assertEqual(b.refresh(b.base)['cells'][0]['devices'][0]['value'],'22k')
            q=clone(a.base);q['cells'].append(dict(id=uid(),name='empty_child',ports=[],devices=[],shapes=[]))
            with self.assertRaisesRegex(ValueError,'whole project'):a.publish(q)
            a.release();a.claim('*');self.assertEqual(len(a.publish(q)['cells']),2)
            with self.assertRaisesRegex(ValueError,'Alice'):b.claim(cid)


if __name__=='__main__': unittest.main()
