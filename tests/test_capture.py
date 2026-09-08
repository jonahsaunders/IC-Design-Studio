import unittest,tempfile
from pathlib import Path
from icstudio.model import example,device,uid,clone,validate,History,flatten
from icstudio import capture_ops as ops,wiring
from icstudio.symbol_io import default_symbol,symbol_text,import_symbol,validate_symbol
from icstudio.symbol_geometry import enriched,transform,align,text_value
from icstudio.interchange import pin_positions,export_xschem
from icstudio.xschem_io import import_package

def circuit():
    p=example('empty');c=p['cells'][0];c.update(devices=[device('R','R1',100,150),device('C','C1',400,150)],wires=[],labels=[],junctions=[])
    for d in c['devices']:d['net_labels']={}
    wiring.add_wire(c,[[100,100],[400,100]],p);wiring.rebuild(c,p);return p,c

def amplifier():
    p=example('empty');p['name']='Amplifier capture acceptance';c=p['cells'][0]
    c['devices']=[device('V','VDD',100,100,value='1.8',nets={'p':'vdd','n':'0'}),device('V','VIN',100,350,value='.65',nets={'p':'vin','n':'0'}),device('R','RD',400,100,value='10k',nets={'p':'vdd','n':'out'}),device('NMOS','MN1',400,300,nets={'d':'out','g':'vin','s':'0','b':'0'}),device('C','CL',650,300,value='1p',nets={'p':'out','n':'0'})]
    wiring.migrate(c,p);return p,c

class CaptureTests(unittest.TestCase):
    def test_move_detaches_stretch_preserves_and_undo_atomic(self):
        p,c=circuit();h=History(p);ids=[c['devices'][0]['id']];nets=clone(c['devices'][0]['nets'])
        h.commit(lambda p:ops.transform(p,c['id'],ids,0,40,stretch=True),'stretch');self.assertEqual(h.project['cells'][0]['devices'][0]['nets'],nets);h.undo();self.assertEqual(h.project['cells'],p['cells'])
        h.commit(lambda p:ops.transform(p,c['id'],ids,0,40,stretch=False),'move');ds=h.project['cells'][0]['devices'];self.assertNotEqual(ds[0]['nets']['p'],ds[1]['nets']['p'])
    def test_cut_gap_rejoin_and_remote_bends(self):
        p,c=circuit();ids=ops.cut_wire(p,c['id'],c['wires'][0]['id'],0,[250,100]);self.assertNotEqual(c['devices'][0]['nets']['p'],c['devices'][1]['nets']['p']);ops.rejoin(p,c['id'],ids);self.assertEqual(c['devices'][0]['nets']['p'],c['devices'][1]['nets']['p']);validate(p)
    def test_copy_selection_preserves_internal_wiring_not_original_contacts(self):
        p,c=circuit();ids=[d['id'] for d in c['devices']]+[c['wires'][0]['id']];new=ops.transform(p,c['id'],ids,0,300,copy=True);self.assertEqual(len(new),3);a,b=c['devices'][2:];self.assertEqual(a['nets']['p'],b['nets']['p']);self.assertNotEqual(a['nets']['p'],c['devices'][0]['nets']['p']);validate(p)
    def test_mirror_twice_restores_positions_and_nets(self):
        p=example('inverter');c=p['cells'][0];wiring.migrate(c,p);d=c['devices'][2];before=pin_positions(d);nets=clone(d['nets']);ops.transform(p,c['id'],[d['id']],mirror=True);self.assertNotEqual(pin_positions(d),before);self.assertEqual(d['nets'],nets);ops.transform(p,c['id'],[d['id']],mirror=True);self.assertEqual(pin_positions(d),before)
    def test_bulk_invalid_value_leaves_history_unchanged(self):
        p,c=circuit();h=History(p);ids=[d['id'] for d in c['devices']]
        with self.assertRaises(ValueError):h.commit(lambda p:ops.bulk_parameters(p,c['id'],ids,{'value':'nonsense'}),'bulk')
        self.assertEqual(h.project,p);h.commit(lambda p:ops.bulk_parameters(p,c['id'],ids,{'value':'2u'}),'bulk');self.assertTrue(all(d['value']=='2u' for d in h.project['cells'][0]['devices']))
    def test_extract_amplifier_then_reorder_move_and_rename_symbol(self):
        p,c=amplifier();chosen=[d['id'] for d in c['devices'] if d['kind'] in ('R','NMOS')];cid,iid=ops.make_cell(p,c['id'],chosen,'amplifier');validate(p);child=ops.cell(p,cid);inst=next(d for d in c['devices'] if d['id']==iid);old=clone(inst['nets']);base=clone(child['symbol']);s=clone(base);s['pins']['vin'][0]-=30;s['pin_order'].reverse();ops.apply_symbol(p,cid,s,base);self.assertEqual(inst['nets'],old);self.assertEqual(child['ports'],s['pin_order']);validate(p)
        base=clone(s);s['pins']['input']=s['pins'].pop('vin');s['pin_meta']['input']=s['pin_meta'].pop('vin');s['pin_order']=['input' if n=='vin' else n for n in s['pin_order']];ops.apply_symbol(p,cid,s,base);validate(p);self.assertEqual(inst['nets']['input'],'vin');self.assertEqual(next(d for d in child['devices'] if d['kind']=='NMOS')['nets']['g'],'input')
        self.assertEqual(len(flatten(p,c['id'])),5)
    def test_symbol_styles_arcs_polygons_and_external_edits_roundtrip(self):
        s=enriched(default_symbol(['a','b']));s['primitives']=[{'kind':'polygon','points':[[-20,-20],[20,0],[-20,20]],'fill':True,'color':'#42cbb5'},{'kind':'arc','points':[[-10,-10],[10,10]],'start':20,'sweep':150},{'kind':'text','points':[[0,0],[20,10]],'text':'@name @gain','font_size':10,'bold':True}];s['pin_meta']['a'].update(direction='in',role='analog');s['pin_order']=['b','a']
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'symbol.sym';path.write_text(symbol_text(s));out,_,_=import_symbol(path,True);self.assertEqual(out['primitives'],s['primitives']);self.assertEqual(out['pin_order'],['b','a']);self.assertEqual(out['pin_meta']['a']['id'],s['pin_meta']['a']['id']);path.write_text(path.read_text().replace('@name @gain','@name CHANGED'));out,_,notes=import_symbol(path,True);self.assertTrue(any('CHANGED' in item.get('text','') for item in out['primitives']));self.assertTrue(notes)
        self.assertEqual(text_value('@name @gain',{'name':'X2','gain':10}),'X2 10')
    def test_metadata_rejects_duplicate_ids_invalid_bus_order(self):
        s=enriched(default_symbol(['data[0]','data[1]']));s['pin_meta']['data[0]']['bus']='data[1:0]';validate_symbol(s,s['pins']);s['pin_order']=['data[0]','data[0]']
        with self.assertRaises(ValueError):validate_symbol(s,s['pins'])
    def test_symbol_geometry_group_align_and_identity(self):
        s=enriched(default_symbol(['a']));s['primitives']=[{'kind':'rect','points':[[i*20,i*15],[i*20+10,i*15+10]]} for i in range(3)];before=clone(s['pin_meta']);align(s,[0,1,2],'top');self.assertTrue(all(item['points'][0][1]==0 for item in s['primitives']));transform(s,[0,1,2],angle=90,pins=['a']);self.assertEqual(s['pin_meta'],before);validate_symbol(s,s['pins'])
    def test_used_pin_removal_rejected(self):
        p,c=amplifier();cid,_=ops.make_cell(p,c['id'],[d['id'] for d in c['devices'] if d['kind']=='NMOS'],'amp');s=clone(ops.cell(p,cid)['symbol']);name=s['pin_order'].pop();s['pins'].pop(name);s['pin_meta'].pop(name)
        with self.assertRaisesRegex(ValueError,'electrically used'):ops.apply_symbol(p,cid,s)
    def test_interface_checks_report_unused_and_overlap(self):
        p=example('empty');c=p['cells'][0];c['ports']=['a','b'];c['symbol']=enriched(default_symbol(c['ports']));c['symbol']['pins']['b']=c['symbol']['pins']['a'];codes=[i['code'] for i in ops.findings(p,c['id'])];self.assertIn('SYMBOL.OVERLAP',codes);self.assertIn('SYMBOL.UNUSED',codes)
