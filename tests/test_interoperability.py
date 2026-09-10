"""External exchange regressions using real KLayout geometry and LVS objects."""
import json
import tempfile
import unittest
from pathlib import Path
from icstudio.model import example,clone,uid,device,digest,validate,History,file_digest,flatten
from icstudio.layout import kdb,rect,polygon
from icstudio.interchange import export_layout,import_layout,spice,export_handoff
from icstudio.layout_exchange import review,apply
from icstudio.interoperability import technology_contract,export_technology,tool_asset,compare_interfaces


class InteroperabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.p=example();self.c=self.p['cells'][0]
        self.c['shapes']=[{**rect('metal1',0,0,1000,1000),'device_id':self.c['devices'][1]['id']}]
        self.path=self.root/'layout.gds';export_layout(self.p,self.path)

    def edit(self,operation):
        ly=kdb().Layout();ly.read(str(self.path));operation(ly);ly.write(str(self.path))

    def move(self,dx=100):
        self.edit(lambda ly:next(ly.top_cell().shapes(ly.layer(4,0)).each()).transform(kdb().Trans(dx,0)))

    def test_three_way_independent_edits_preserve_link_and_undo(self):
        self.move();p=clone(self.p);p['cells'][0]['devices'][1]['value']='2k'
        record=review(p,self.path);self.assertFalse(record['errors']);self.assertFalse(record['conflicts'])
        h=History(p);h.commit(lambda q:apply(q,record));shape=h.project['cells'][0]['shapes'][0]
        self.assertEqual(shape['id'],self.c['shapes'][0]['id']);self.assertEqual(shape['device_id'],self.c['devices'][1]['id'])
        self.assertEqual(polygon(shape).bbox().left,100);self.assertEqual(h.project['cells'][0]['devices'][1]['value'],'2k')
        h.undo();self.assertEqual(h.project['cells'][0]['shapes'],self.c['shapes']);h.redo();self.assertTrue(h.project['cells'][0]['shapes'][0]['external_modified'])

    def test_conflict_requires_choice_and_stale_review_rejected(self):
        self.move();p=clone(self.p);p['cells'][0]['shapes'][0]['points']=[[300,0],[1300,1000]]
        record=review(p,self.path);self.assertTrue(record['conflicts'])
        with self.assertRaisesRegex(ValueError,'Resolve'):apply(p,record)
        chosen={row['path']:'external' for row in record['conflicts']};record=review(p,self.path,chosen)
        self.assertFalse(record['conflicts']);apply(p,record);self.assertEqual(polygon(p['cells'][0]['shapes'][0]).bbox().left,100)
        record=review(p,self.path);p['name']='changed'
        with self.assertRaisesRegex(ValueError,'project changed'):apply(p,record)
        record=review(p,self.path);self.move(20)
        with self.assertRaisesRegex(ValueError,'exchange file changed'):apply(p,record)

    def test_copy_keeps_original_only_and_is_idempotent(self):
        def copy(ly):
            shape=next(ly.top_cell().shapes(ly.layer(4,0)).each())
            new=ly.top_cell().shapes(ly.layer(4,0)).insert(shape.polygon.transformed(kdb().Trans(2000,0)))
            new.set_property(127,shape.property(127))
        self.edit(copy);record=review(self.p,self.path);self.assertFalse(record['errors']);q=record['candidate'];shapes=q['cells'][0]['shapes']
        self.assertEqual(len(shapes),2);self.assertEqual(sum(bool(s.get('device_id')) for s in shapes),1)
        again=review(q,self.path);self.assertFalse(again['conflicts']);self.assertEqual(again['candidate']['cells'],q['cells'])

    def test_property_only_and_cell_name_edits_survive(self):
        self.path=self.root/'layout.oas';export_layout(self.p,self.path)
        def edit(ly):
            ly.top_cell().name='renamed';ly.top_cell().set_property(10,'classification')
            next(ly.top_cell().shapes(ly.layer(4,0)).each()).set_property(11,'measurement')
        self.edit(edit);q=review(self.p,self.path)['candidate'];c=q['cells'][0]
        self.assertEqual(c['id'],self.c['id']);self.assertEqual(c['name'],'renamed');self.assertIn([10,'classification'],c['external_properties'])
        self.assertIn([11,'measurement'],c['shapes'][0]['external_properties'])
        export_layout(q,self.root/'again.oas');ly=kdb().Layout();ly.read(str(self.root/'again.oas'));self.assertEqual(ly.cell('renamed').property(10),'classification')

    def test_text_properties_survive_review_and_export(self):
        self.c['layout_texts']=[{'layer':'metal1','text':'A','x':0,'y':0}];self.c['layout_label_mode']='explicit'
        export_layout(self.p,self.path)
        def edit(ly):
            next(s for s in ly.top_cell().shapes(ly.layer(4,0)).each() if s.is_text()).set_property(11,'pin-purpose')
        self.edit(edit);q=review(self.p,self.path)['candidate']
        self.assertIn([11,'pin-purpose'],q['cells'][0]['layout_texts'][0]['external_properties'])
        export_layout(q,self.root/'again.gds');ly=kdb().Layout();ly.read(str(self.root/'again.gds'))
        self.assertEqual(next(s for s in ly.top_cell().shapes(ly.layer(4,0)).each() if s.is_text()).property(11),'pin-purpose')

    def test_baseline_tamper_and_pdk_revision_are_rejected(self):
        p=clone(self.p);p['pdk']['revision']='different'
        with self.assertRaisesRegex(ValueError,'technology changed'):review(p,self.path)
        Path(str(self.path)+'.icstudio.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'baseline'):review(self.p,self.path)

    def test_instance_move_with_magic_identity_property(self):
        child={'id':uid(),'name':'child','ports':[],'devices':[],'shapes':[rect('metal1',0,0,100,100)]};self.p['cells'].append(child)
        ident=uid();self.c['layout_instances']=[{'id':ident,'name':'placed','cell':child['id'],'x':2000,'y':0,'rotation':0}]
        export_layout(self.p,self.path)
        def move(ly):
            i=next(ly.cell('top').each_inst());i.delete_property(126);i.set_property(61,'studio_'+ident);i.transform(kdb().Trans(500,0))
        self.edit(move);record=review(self.p,self.path);self.assertFalse(record['errors']);inst=record['candidate']['cells'][0]['layout_instances'][0]
        self.assertEqual(inst['id'],ident);self.assertEqual(inst['name'],'placed');self.assertEqual(inst['x'],2500)

    def test_contract_aliases_units_and_locked_decks(self):
        tech=clone(self.p['pdk']);tech['interoperability']={'version':1,'net_aliases':{'VSS':'0'},'global_nets':['0','VDD!'],'tools':{'magic':{'technology':'process.tech'}}}
        (self.root/'process.tech').write_text('technology fixture');tech['package_root']=str(self.root);tech['package_lock']={'id':'fourth_pdk','revision':'r1','files':{'process.tech':file_digest(self.root/'process.tech')}}
        contract=technology_contract(tech);self.assertEqual(contract['pdk']['id'],'fourth_pdk');self.assertEqual(tool_asset(tech,'magic','technology'),(self.root/'process.tech').resolve())
        self.assertTrue(compare_interfaces(['VSS','A'],['0','A'],contract['net_aliases'])['equal'])
        self.assertFalse(compare_interfaces(['A','Y'],['Y','A'])['equal'])
        tech['interoperability']['net_aliases']={'A':'B','B':'A'}
        with self.assertRaisesRegex(ValueError,'Cyclic'):technology_contract(tech)
        (self.root/'process.tech').write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed locked'):tool_asset(tech,'magic','technology')

    def instance_fixture(self):
        child={'id':uid(),'name':'child','ports':[],'devices':[],'shapes':[rect('metal1',0,0,100,100)]};self.p['cells'].append(child)
        original={'id':uid(),'name':'placed','cell':child['id'],'x':2000,'y':0,'rotation':0}
        self.c['layout_instances']=[original];export_layout(self.p,self.path)
        return original

    def test_instance_copy_keeps_only_unchanged_identity(self):
        original=self.instance_fixture()
        def copy(ly):
            instance=next(ly.cell('top').each_inst())
            duplicate=ly.cell('top').insert(instance.cell_inst.transformed(kdb().Trans(-1000,0)))
            duplicate.set_property(126,instance.property(126))
        self.edit(copy);record=review(self.p,self.path);self.assertFalse(record['errors'])
        q=record['candidate'];instances=q['cells'][0]['layout_instances'];self.assertEqual(len(instances),2)
        retained=next(i for i in instances if i['id']==original['id'])
        self.assertEqual(retained['x'],2000);self.assertEqual(retained['name'],'placed')
        duplicate=next(i for i in instances if i['id']!=original['id'])
        self.assertEqual(duplicate['x'],1000);self.assertNotEqual(duplicate['name'],'placed')
        again=review(q,self.path);self.assertFalse(again['conflicts']);self.assertEqual(again['candidate']['cells'],q['cells'])
        self.edit(lambda ly:[i.transform(kdb().Trans(100,0)) for i in ly.cell('top').each_inst()])
        with self.assertRaisesRegex(ValueError,'copied instance identity is ambiguous'):review(self.p,self.path)

    def test_instance_property_only_edit_without_marker(self):
        original=self.instance_fixture()
        def edit(ly):
            instance=next(ly.cell('top').each_inst());instance.delete_property(126);instance.set_property(11,'measurement')
        self.edit(edit);record=review(self.p,self.path);self.assertFalse(record['errors'])
        instance=record['candidate']['cells'][0]['layout_instances'][0]
        self.assertEqual(instance['id'],original['id']);self.assertIn([11,'measurement'],instance['external_properties'])

    def test_klayout_technology_loads_and_original_conversion_restores_bytes(self):
        export_technology(self.p['pdk'],self.root/'tech');technology=kdb().Technology();technology.load(str(self.root/'tech/technology.lyt'))
        self.assertEqual(technology.layer_properties_file,'layers.lyp');self.assertEqual(technology.dbu,.001)
        from icstudio.layout_source import inspect,convert,restore
        ly=kdb().Layout();ly.dbu=.0005;top=ly.create_cell('top');child=ly.create_cell('child');idx=ly.layer(8,2);child.shapes(idx).insert(kdb().Box(1,1,999,999));top.insert(kdb().CellInstArray(child.cell_index(),kdb().ICplxTrans(1.5,45,False,10,10)))
        source=self.root/'source.oas';ly.write(str(source));self.assertTrue(inspect(source)['issues'])
        with self.assertRaisesRegex(ValueError,'flattening'):convert(source,'top')
        q,notes=convert(source,'top',flatten=True,round_to_nm=True);validate(q);self.assertEqual(len(q['cells']),1)
        restore(q,self.root/'restored.oas');self.assertEqual(source.read_bytes(),(self.root/'restored.oas').read_bytes())

    def test_global_nets_stay_global_through_flatten_and_cross_probe(self):
        from icstudio.cross_probe import net_occurrences
        p=example('empty');child={'id':uid(),'name':'child','ports':['A'],'devices':[device('R','R1',nets={'p':'A','n':'VDD!'})],'shapes':[]}
        p['cells'].append(child);p['cells'][0]['devices']=[device('X','X1',cell=child['id'],nets={'A':'in'}),device('X','X2',cell=child['id'],nets={'A':'out'})];p['global_nets']=['VDD!'];validate(p)
        self.assertEqual([d['nets']['n'] for d in flatten(p)],['VDD!','VDD!']);self.assertEqual(len(net_occurrences(p,p['top'],'VDD!')),2);self.assertIn('.global VDD!',spice(p))


class XschemSemanticTests(unittest.TestCase):
    def test_lvs_format_global_scope_and_external_roundtrip(self):
        from tests.test_native_migration import divider
        from icstudio.native_migration import review_path
        from icstudio.native_spice import netlist
        from icstudio.native_exchange import export_project,review_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=divider(root/'source')
            sym=path.parent/'res.sym';original=Path(__file__).parents[1]/'icstudio/assets/exchange/xschem/devices/res.sym'
            sym.write_text(original.read_text().replace('K {','K {lvs_format="@name @pinlist @value" ',1))
            path.write_text(path.read_text().replace('S {}','S {.global VDD!}',1))
            result=review_path(path);self.assertEqual(result['status'],'Complete',result['items']);p=result['candidate']
            text=netlist(p,root/'lvs',mode='lvs');self.assertIn('.global VDD!',text);self.assertNotIn('.control',text);self.assertIn('.subckt',text)
            self.assertNotIn(' m=1',text);self.assertIn(' m=1',netlist(p,root/'sim'))
            exported=export_project(p,root/'export');reviewed=review_project(root/'export'/exported['top']);self.assertFalse(reviewed['errors'],reviewed)
            self.assertEqual(reviewed['candidate']['global_nets'],['VDD!'])
            self.assertNotIn(' m=1',netlist(reviewed['candidate'],root/'again',mode='lvs'))

    def test_embedded_subcircuit_overrides_drawn_pin_order_and_bad_ports_fail(self):
        from icstudio.xschem_compat import CaptureReader
        from icstudio.native_migration import review_path
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'models.inc').write_text('.subckt custom B A\nR1 B A 1k\n.ends\n')
            (root/'custom.sym').write_text('v {xschem version=3.4.7 file_version=1.2}\nK {type=primitive format="@name @pinlist @symname" template="name=X1" spice_sym_def=".include models.inc"}\nB 5 -2 -32 2 -28 {name=A dir=inout}\nB 5 -2 28 2 32 {name=B dir=inout}\n')
            top=root/'top.sch';top.write_text('v {xschem version=3.4.7 file_version=1.2}\nC {custom.sym} 0 0 0 0 {name=X1}\n')
            reader=CaptureReader(top,[root],None,{});p=reader.capture();self.assertEqual(p['cells'][0]['devices'][0]['symbol']['pin_order'],['B','A'])
            result=review_path(top);self.assertIsNotNone(result['candidate'],result['items'])
            (root/'models.inc').write_text('.subckt custom C A\nR1 C A 1k\n.ends\n')
            result=review_path(top);self.assertIsNone(result['candidate']);self.assertTrue(any('disagree' in row['detail'] for row in result['items']))

    def test_extracted_port_order_and_profiles(self):
        from icstudio.external_tools import extraction_commands,check_extracted_interface,snapshot
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);deck=root/'layout.spice';deck.write_text('.subckt inv Y A VDD VSS\n.ends\n')
            with self.assertRaisesRegex(ValueError,'port order'):check_extracted_interface(deck,'inv',['A','Y','VDD','VSS'],example()['pdk'])
            for profile in ('lvs','capacitance','rc'):
                commands,settings=extraction_commands(profile);self.assertIn('ext2spice merge none',commands);self.assertEqual(settings['distributed_resistance'],profile=='rc')
            with self.assertRaisesRegex(ValueError,'capture|outside'):snapshot(root,root/'nested')


if __name__=='__main__':unittest.main()
