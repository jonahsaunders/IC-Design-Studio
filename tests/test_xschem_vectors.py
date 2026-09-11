"""Electrical contracts for real-project arrays and crossing diagonal wires."""
import tempfile
import unittest
from pathlib import Path
from icstudio.model import clone, load_project, save_project
from icstudio.native_migration import review_path
from icstudio.native_spice import netlist
from icstudio.xschem_vectors import signals, instance_names


def fixture(root, name='R[2:0]', positive='node[2:0]', negative='node[3:1]'):
    path = root/'array.sch'
    path.write_text('v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n'
        f'C {{devices/res.sym}} 0 0 0 0 {{name={name} value=1k m=1}}\n'
        f'C {{devices/lab_pin.sym}} 0 -30 0 0 {{name=p1 lab={positive}}}\n'
        f'C {{devices/lab_pin.sym}} 0 30 0 0 {{name=p2 lab={negative}}}\n')
    return path


class VectorImportTests(unittest.TestCase):
    def test_series_ladder_is_expanded_in_declared_order_and_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=fixture(root);original=source.read_bytes()
            record=review_path(source)
            self.assertEqual(record['status'],'Complete',record['items'])
            p=record['candidate'];rows=[d for d in p['cells'][0]['devices'] if d['name'].startswith('R__')]
            self.assertEqual([(d['name'],list(d['nets'].values())) for d in rows],
                [('R__2',['node[2]','node[3]']),('R__1',['node[1]','node[2]']),('R__0',['node[0]','node[1]'])])
            self.assertEqual(source.read_bytes(),original)
            save_project(p,root/'saved.icproj');q=load_project(root/'saved.icproj')
            self.assertEqual(p['cells'],q['cells'])
            source.unlink();q['native_migration'].pop('archive')
            emitted=netlist(q,root/'relocated',mode='lvs')
            self.assertIn('R__2 node[2] node[3]',emitted)
            self.assertNotIn('vector_',emitted)

    def test_scalar_terminal_broadcast_and_disjoint_array_placement(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=review_path(fixture(Path(tmp),name='R[0:2]',positive='supply',negative='0'))
            self.assertIsNotNone(r['candidate'],r['items'])
            rows=[d for d in r['candidate']['cells'][0]['devices'] if d['name'].startswith('R__')]
            self.assertEqual(len(rows),3)
            self.assertEqual(len({(d['x'],d['y']) for d in rows}),3)
            self.assertTrue(all(list(d['nets'].values())==['supply','0'] for d in rows))

    def test_width_mismatch_and_name_collision_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            r=review_path(fixture(root,positive='node[3:0]'))
            self.assertIsNone(r['candidate'])
            self.assertIn('width',str(r['items']))
            path=fixture(root)
            path.write_text(path.read_text()+'C {devices/res.sym} 200 0 0 0 {name=R__2 value=1k m=1}\n')
            r=review_path(path);self.assertIsNone(r['candidate']);self.assertIn('collides',str(r['items']))

    def test_expression_limits(self):
        self.assertEqual(signals('a[0:2]'),['a[0]','a[1]','a[2]'])
        self.assertEqual(instance_names('M5[0:1]'),['M5__0','M5__1'])
        for value in ('a[0:128]','a[0:3:2]','2*a[3:0]','a,b'):
            with self.assertRaises(ValueError):signals(value)

    def test_diagonal_crossing_remains_two_nets_and_can_move_with_undo(self):
        from icstudio.model import example, History, uid, validate
        from icstudio.wiring import graph, segment_drag
        p=example('empty');c=p['cells'][0]
        c['wires']=[{'id':uid(),'points':[[0,0],[100,100]]},{'id':uid(),'points':[[0,100],[100,0]]}]
        c['labels']=[];c['junctions']=[]
        validate(p);groups=graph(c,p)
        self.assertNotEqual(groups[('wire',c['wires'][0]['id'])],groups[('wire',c['wires'][1]['id'])])
        history=History(p);before=clone(history.project['cells'])
        history.commit(lambda q:q['cells'][0]['wires'][0].update(points=segment_drag([[0,0],[100,100]],0,10,20)))
        history.undo();self.assertEqual(history.project['cells'],before)
