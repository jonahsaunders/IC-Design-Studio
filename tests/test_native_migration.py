"""Migration contracts: independence, electrical edits, hierarchy and failures."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_xschem_compatible import fixture
from icstudio.model import clone, digest, load_project, save_project, validate, History
from icstudio.native_migration import review_path, review
from icstudio.native_spice import netlist, run, render
from icstudio.electrical_identity import partition
from icstudio import wiring


def divider(root, hierarchical=False, include=False):
    program = ('.include "models with spaces/value.spice"\n' if include else '') + '.control\nop\ntran 10u 100u\nac dec 3 1 1000\n.endc'
    path = fixture(root, program)
    text = path.read_text().replace('{capa.sym}', '{res.sym}').replace('name="C1"', 'name="R2"').replace('value="1u"', 'value="1k"')
    if include:
        folder = path.parent/'models with spaces'; folder.mkdir(); (folder/'value.spice').write_text('.param supply=1\n')
    if hierarchical:
        (path.parent/'child.sym').write_text('v {xschem version=3.4.7 file_version=1.2}\nK {type=subcircuit format="@name @pinlist @symname r=@r" template="name=X1 r=1k"}\nB 5 -2 -32 2 -28 {name=p dir=inout}\nB 5 -2 28 2 32 {name=n dir=inout}\nB 4 -10 -20 10 20 {}\n')
        (path.parent/'child.sch').write_text('v {xschem version=3.4.7 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\nC {res.sym} 0 0 0 0 {name=R1 value={r} m=1}\nC {lab_wire.sym} 0 -30 0 0 {name=p1 lab=p}\nC {lab_wire.sym} 0 30 0 0 {name=p2 lab=n}\n')
        text = text.replace('C {res.sym} 100 -30 1 0 {name="R1" value="1k" m="1"}', 'C {child.sym} 100 -30 1 0 {name=X1 r=1k}')
    path.write_text(text); return path


class NativeMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def migrate(self, **kwargs):
        self.path = divider(self.root/'original source', **kwargs)
        result = review_path(self.path)
        self.assertEqual(result['status'], 'Complete', result['items'])
        self.assertIsNotNone(result['candidate']); return result['candidate']

    def test_native_document_runs_without_exchange_records_or_original_files(self):
        p = self.migrate(include=True); original = clone(p)
        p['native_migration'].pop('archive'); shutil.rmtree(self.path.parent)
        with patch('icstudio.xschem_runtime.netlist', side_effect=AssertionError('Native generation called the compatibility netlister')), patch('urllib.request.urlopen', side_effect=AssertionError('Native generation accessed the network')):
            text = netlist(p, self.root/'relocated project café')
        self.assertNotIn('xschem_exchange', p)
        self.assertTrue(all('xschem' not in d for c in p['cells'] for d in c['devices']))
        self.assertIn('R1', text); self.assertIn('models/', text)
        self.assertEqual(original['cells'], p['cells'])

    def test_review_does_not_mutate_capture(self):
        from icstudio.xschem_compat import review_project
        path = divider(self.root/'source'); capture = review_project(path)['candidate']; before = digest(capture)
        review(capture); self.assertEqual(digest(capture), before)

    def test_edit_value_and_designator_updates_emission(self):
        p = self.migrate(); d = next(d for d in p['cells'][0]['devices'] if d['name']=='R1')
        d['native_spice']['parameters']['value'] = '3k'; d['name'] = 'Rchanged'
        text = netlist(p, self.root/'run'); self.assertIn('Rchanged', text); self.assertIn('3k', text)

    def test_parameterized_hierarchy_remains_editable(self):
        p = self.migrate(hierarchical=True); self.assertEqual(len(p['cells']), 2)
        d = next(d for d in p['cells'][0]['devices'] if d['kind']=='X')
        d['native_spice']['parameters']['r'] = '3k'; text = netlist(p, self.root/'run')
        self.assertIn('child r=3k', text); self.assertIn('.subckt child p n r=1k', text); self.assertIn('{r}', text)

    def test_save_reopen_keeps_terminal_and_net_ids(self):
        p = self.migrate(); save_project(p, self.root/'native.icproj'); q = load_project(self.root/'native.icproj')
        self.assertEqual(p['cells'], q['cells'])
        for d in q['cells'][0]['devices']:
            self.assertEqual(set(d['terminal_ids']), set(d['nets'])); self.assertEqual(set(d['net_ids']), set(d['nets']))

    def test_device_and_wire_moves_keep_net_identity(self):
        p = self.migrate(); c = p['cells'][0]; before = clone(c)
        d = next(d for d in c['devices'] if d['name']=='R1'); old = wiring.pins(c, p); d['y'] -= 20
        wiring.keep_connections(c, old, p); wiring.rebuild(c, p)
        self.assertEqual(partition(c), partition(before))
        self.assertEqual(d['net_ids'], next(x for x in before['devices'] if x['id']==d['id'])['net_ids'])
        wire = c['wires'][0]; identity = wire['net_id']; wiring.reshape_segment(c, wire['id'], 0, 0, -10, p)
        self.assertEqual(wire['net_id'], identity); self.assertEqual(partition(c), partition(before))

    def test_accidental_merge_during_move_rejects_transaction(self):
        p = self.migrate(); h = History(p); before = digest(h.project)
        def move(q):
            c=q['cells'][0]; old=wiring.pins(c,q); d=next(d for d in c['devices'] if d['name']=='R1')
            d['x']=0; d['y']=30; wiring.keep_connections(c,old,q)
        with self.assertRaises(ValueError): h.commit(move)
        self.assertEqual(digest(h.project), before)

    def test_net_label_rename_retains_identity(self):
        p = self.migrate(); c = p['cells'][0]; d = next(d for d in c['devices'] if d['name']=='R2'); pin = next(pin for pin,n in d['nets'].items() if n=='out'); ident=d['net_ids'][pin]
        wiring.set_label(c,d['id'],pin,'renamed_output',p)
        self.assertEqual(d['net_ids'][pin],ident); self.assertEqual(d['nets'][pin],'renamed_output')

    def test_duplicate_allocates_distinct_terminal_ids(self):
        from icstudio.model import uid
        p = self.migrate(); c = p['cells'][0]; d=clone(c['devices'][0]); d.update(id=uid(),name='V2',x=500,y=500); d['net_labels']={};c['devices'].append(d);validate(p)
        terminal_ids=[v for d in c['devices'] for v in d['terminal_ids'].values()]
        self.assertEqual(len(terminal_ids),len(set(terminal_ids)))

    def test_hierarchical_pin_rename_preserves_terminal_identity(self):
        from icstudio.capture_ops import apply_symbol
        p=self.migrate(hierarchical=True);parent=p['cells'][0];d=next(d for d in parent['devices'] if d['kind']=='X');child=next(c for c in p['cells'] if c['id']==d['cell'])
        terminal=d['terminal_ids']['p'];net=d['net_ids']['p'];base=clone(child['symbol']);symbol=clone(base)
        symbol['pins']['input']=symbol['pins'].pop('p');symbol['pin_meta']['input']=symbol['pin_meta'].pop('p');symbol['pin_order']=['input' if pin=='p' else pin for pin in symbol['pin_order']]
        apply_symbol(p,child['id'],symbol,base);validate(p)
        self.assertEqual(d['terminal_ids']['input'],terminal);self.assertEqual(d['net_ids']['input'],net)
        self.assertIn('.subckt child input n',netlist(p,self.root/'renamed interface'))

    def test_missing_symbols_do_not_produce_complete_migration(self):
        path=divider(self.root/'source');path.write_text(path.read_text().replace('{res.sym}','{private.sym}',1));r=review_path(path)
        self.assertIsNone(r['candidate']);self.assertEqual(r['status'],'Needs attention')

    def test_tcl_behavior_requires_translation(self):
        from icstudio.xschem_compat import review_project
        path=fixture(self.root/'source');p=review_project(path)['candidate'];d=next(d for d in p['cells'][0]['devices'] if d['name']=='R1');d['xschem']['properties']['format']='tcleval(custom_script)';r=review(p)
        self.assertIsNone(r['candidate']);self.assertTrue(any('executable' in row['detail'] for row in r['items']))

    def test_unmapped_graph_is_explicitly_reported(self):
        from icstudio.xschem_compat import review_project
        path=fixture(self.root/'source');p=review_project(path)['candidate'];p['cells'][0]['xschem']['components'].append({'kind':'graph','reference':'graph.sym'});r=review(p)
        self.assertEqual(r['status'],'Needs attention');self.assertTrue(any('graph' in row['detail'] for row in r['items']))

    def test_model_tampering_blocks_execution(self):
        p=self.migrate(include=True);next(iter(p['spice']['assets'].values()))['text']+='\n.param changed=1\n'
        with self.assertRaisesRegex(ValueError,'checksum'): netlist(p,self.root/'run')

    def test_model_include_in_schematic_header_is_packaged(self):
        path=divider(self.root/'header project');(path.parent/'header.spice').write_text('.param header_value=2\n')
        path.write_text(path.read_text().replace('S {}','S {.include "header.spice"}'))
        r=review_path(path);self.assertEqual(r['status'],'Complete',r['items']);p=r['candidate']
        self.assertEqual(len(p['spice']['assets']),1);shutil.rmtree(path.parent)
        self.assertIn('.include models/',netlist(p,self.root/'header run'))

    def test_scalar_bus_names_survive_native_conversion(self):
        from icstudio.spice_program import prepare_program
        path=divider(self.root/'bus project');path.write_text(path.read_text().replace('lab="out"','lab="data[0]"'))
        r=review_path(path);self.assertEqual(r['status'],'Complete',r['items']);p=r['candidate'];text=netlist(p,self.root/'bus run')
        self.assertIn('data[0]',text);prepare_program(text,self.root/'bus run',{'probes':'v(data[0])'})

    def test_vector_bus_reports_conversion_requirement(self):
        path=divider(self.root/'vector project');path.write_text(path.read_text().replace('lab="out"','lab="data[7:0]"'))
        r=review_path(path);self.assertIsNone(r['candidate']);self.assertEqual(r['status'],'Needs attention')

    def test_circuit_without_program_gets_editable_operating_point_setup(self):
        from icstudio.xschem_io import records
        from icstudio.xschem_project import record_text
        path=divider(self.root/'DUT');path.write_text('\n'.join(record_text(r) for r in records(path.read_text()) if not (r[0]=='C' and r[1]=='code_shown.sym'))+'\n')
        result=review_path(path);self.assertEqual(result['status'],'Complete',result['items'])
        programs=[d for d in result['candidate']['cells'][0]['devices'] if d.get('native_spice',{}).get('type')=='program']
        self.assertEqual(len(programs),1);self.assertIn('\nop\n',programs[0]['native_spice']['text'])

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Set ICSTUDIO_TEST_NGSPICE for real simulator tests')
    def test_actual_simulation_after_source_removal_and_hierarchy_edit(self):
        p=self.migrate(hierarchical=True,include=True);d=next(d for d in p['cells'][0]['devices'] if d['kind']=='X');d['native_spice']['parameters']['r']='3k'
        p['native_migration'].pop('archive');shutil.rmtree(self.path.parent)
        save_project(p,self.root/'native.icproj');q=load_project(self.root/'native.icproj')
        r=run(q,q['top'],{'type':'program','probes':'v(out)','timeout':60},os.environ['ICSTUDIO_TEST_NGSPICE'],self.root/'Moved project café')
        self.assertEqual(r['program_status'],'Complete',r['warnings']);self.assertEqual(len(r['analysis_cases']),3);self.assertAlmostEqual(r['traces']['out'][-1],.25,places=8)


if __name__=='__main__': unittest.main()
