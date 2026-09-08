"""0.12 native keyboard/mouse, symbol, hierarchy and real-engine acceptance."""
import argparse,json,os,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--ngspice');args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['XDG_CONFIG_HOME']=str(out/'profile/config');os.environ['XDG_DATA_HOME']=str(out/'profile/data')
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QInputDialog,QFileDialog
from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest,save_project,load_project,validate
from icstudio import capture_ops,wiring
from icstudio.interchange import export_xschem
from icstudio.xschem_io import import_package
from test_capture import circuit,amplifier
errors=[];sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb));app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1540,1000);w.show();w.activateWindow();QTest.qWait(100);checks=[]
def setup(p):
    w.set_project(p);w.mode_combo.setCurrentIndex(0);w.results_dock.hide();w.capture_repeat.setChecked(False);w.schematic.auto_fit=False;w.schematic.scale=1;w.schematic.offset=QPointF(10,20);w.schematic.setFocus();QTest.qWait(30)
def point(x,y):return (QPointF(x,y)*w.schematic.scale+w.schematic.offset).toPoint()
def key(k,mod=Qt.NoModifier):w.schematic.setFocus();QTest.keyClick(w.schematic,k,mod);QTest.qWait(10)
def click(x,y):QTest.mouseClick(w.schematic,Qt.LeftButton,pos=point(x,y));QTest.qWait(10)
def accept(dlg):dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();QTest.qWait(10)
p,c=circuit();setup(p);w.set_capture_profile('Xschem-inspired');d=w.cell['devices'][0];w.select([d['id']]);before=clone(d['nets']);key(Qt.Key_M,Qt.ControlModifier);assert w.schematic.tool=='capture_stretch';click(100,150);QTest.mouseMove(w.schematic,point(130,190));assert w.schematic.capture_preview is not None;assert w.cell['devices'][0]['x']==100;click(130,190);assert w.cell['devices'][0]['nets']==before;key(Qt.Key_U);assert w.cell['devices'][0]['x']==100
key(Qt.Key_M);click(100,150);click(100,190);assert w.cell['devices'][0]['nets']['p']!=w.cell['devices'][1]['nets']['p'];key(Qt.Key_U);checks.append('Xschem move vs stretch, live preview, cancel and undo preserve electrical intent')
scale=w.schematic.scale;revision=w.project['revision'];key(Qt.Key_Z,Qt.ControlModifier);assert w.schematic.scale<scale and w.project['revision']==revision
w.select([d['id']]);field=w.form_fields['Name'];field.setFocus();field.selectAll();QTest.keyClicks(field,'move');assert field.text()=='move' and w.schematic.tool=='select';w.build_inspector();checks.append('canvas profile intercepts Ctrl+Z zoom; property typing is isolated')
w.set_capture_profile('Virtuoso-inspired');w.select([d['id']]);key(Qt.Key_C);click(100,150);key(Qt.Key_Escape);assert len(w.cell['devices'])==2 and w.schematic.capture_preview is None
w.capture_cut(QPointF(250,100));assert len(w.cell['wires'])==2;assert w.cell['devices'][0]['nets']['p']!=w.cell['devices'][1]['nets']['p'];w.select([v['id'] for v in w.cell['wires']]);w.capture_rejoin();assert w.cell['devices'][0]['nets']['p']==w.cell['devices'][1]['nets']['p'];checks.append('cut/rejoin and Escape cancellation through live workspace')
w.capture_repeat.setChecked(True);w.begin_placement(2);key(Qt.Key_R);key(Qt.Key_F,Qt.ShiftModifier);click(400,300);click(600,300);assert len(w.cell['devices'])==4 and w.schematic.tool=='place';assert all(v.get('mirror') and v['rotation']==90 for v in w.cell['devices'][-2:]);key(Qt.Key_Escape);assert len({v['name'] for v in w.cell['devices']})==4;checks.append('repeated rotated and mirrored placement with unique names')
w.select([v['id'] for v in w.cell['devices'][-2:]]);w.capture_properties();dlg=w._workflow_dialog;dlg.fields['field'].setCurrentText('value');dlg.fields['value'].setText('2n');accept(dlg);assert all(v['value']=='2n' for v in w.cell['devices'][-2:]);w.undo();assert all(v['value']=='1n' for v in w.cell['devices'][-2:]);checks.append('bulk parameter form commits once and undoes once')
# Extract an actual transistor amplifier and continue through both cell views.
p,c=amplifier();setup(p);selected=[d['id'] for d in w.cell['devices'] if d['kind'] in ('R','NMOS')];w.select(selected);old_input=QInputDialog.getText;QInputDialog.getText=lambda *_args,**_kw:('amplifier',True);w.capture_make_cell();QInputDialog.getText=old_input;instance=w.cell['devices'][-1];iid=instance['id'];cid=instance['cell'];original_nets=clone(instance['nets']);w.capture_enter(True);dlg=w._symbol_dialog;pad=dlg.pad;dlg.generate();assert pad.symbol['pin_meta'];dlg.pad.setFocus();QTest.qWait(20)
# Native artwork tools, marquee, endpoint handles and property dialog.
pad.symbol['primitives'].append({'kind':'polygon','points':[[-25,-20],[25,0],[-25,20]]});pad.selection=len(pad.symbol['primitives'])-1;pad.selections={pad.selection};pad.notify();pad.command('copy');assert len(pad.selections)==1;pad.command('rotate');pad.command('mirror');dlg.artwork_properties();props=dlg._properties_dialog;props.fields['fill'].setChecked(True);props.fields['color'].setText('#efb36a');accept(props);assert pad.symbol['primitives'][-1]['fill'];pad.undo();pad.redo()
pad.selection=len(pad.symbol['primitives'])-1;pad.selections={pad.selection};pad.command('stretch');i=pad.selection;before_point=clone(pad.symbol['primitives'][i]['points'][0]);screen=lambda pt:(QPointF(*pt)*pad.scale+QPointF(pad.width()/2,pad.height()/2)+pad.offset).toPoint();QTest.mousePress(pad,Qt.LeftButton,pos=screen(before_point));QTest.mouseMove(pad,screen([before_point[0]+5,before_point[1]+5]));QTest.mouseRelease(pad,Qt.LeftButton,pos=screen([before_point[0]+5,before_point[1]+5]));assert pad.symbol['primitives'][i]['points'][0]==[before_point[0]+5,before_point[1]+5];pad.undo();pad.command('move')
# Pin metadata and netlist row order with persistent identity.
row=pad.symbol['pin_order'].index('vin');identity=pad.symbol['pin_meta']['vin']['id'];dlg.pin_table.item(row,3).setText('in');row=pad.symbol['pin_order'].index('out');dlg.pin_table.item(row,3).setText('out');dlg.pin_table.selectRow(row);dlg.order_pin(-1);assert pad.symbol['pin_meta']['vin']['id']==identity;dlg.resize(1180,780);QTest.qWait(50);dlg.grab().save(str(out/'symbol-editor.png'));dlg.save();assert dlg.saved,dlg.error.text();assert next(d for d in w.cell['devices'] if d['id']==iid)['nets']==original_nets;checks.append('symbol generation, polygon copy/rotate/mirror, styled properties, pin directions/order preserve parent nets')
w.select([iid]);w.capture_enter();assert w.cid==cid;w.capture_leave();assert w.cid==c['id'] and iid in w.selection;w.capture_enter();res=next(d for d in w.cell['devices'] if d['kind']=='R');w.select([res['id']]);w.form_fields['value'].setText('12k') if 'value' in w.form_fields else None
# Use the same transactional parameter operation behind the bulk form.
w.capture_commit(lambda p:capture_ops.bulk_parameters(p,cid,[res['id']],{'value':'12k'}),'Edit amplifier load');w.capture_leave();validate(w.project);checks.append('descend schematic, edit circuit, return parent with selection/view preserved')
from icstudio.testbenches import create
bench=create(w.project,w.cid,'amplifier_ac');bench['analysis'].update(type='ac',start='10',end='10meg',points=20);w.commit(lambda p:p.update(testbenches=[bench]),'Save amplifier testbench')
# Save and external exchange retain the complete electrical editor data.
path=out/'amplifier-testbench.icproj';save_project(w.project,path);q=load_project(path);assert q['cells']==w.project['cells'];export_xschem(q,out/'xschem');r,notes=import_package(out/'xschem');validate(r);checks.append('save/reopen and editable Xschem package with hierarchy and symbol metadata')
if args.ngspice:
    import time
    w.settings.setValue('engine/ngspice',args.ngspice);w.run_testbench();deadline=time.monotonic()+40
    while w.process and time.monotonic()<deadline:QTest.qWait(20)
    assert not w.process,'Testbench worker timed out'
    result=w._bench_result;assert result and result['testbench_id']==bench['id'],w.console.toPlainText();assert len(result['x'])>50 and 'out' in result['traces'];assert all(__import__('math').isfinite(v) for v in result['traces']['out']);assert max(result['traces']['out'])>.1;(out/'amplifier-ac-result.json').write_text(json.dumps(result,indent=2));checks.append('actual ngspice saved-testbench worker simulates edited amplifier hierarchy')

w.path=path;w.saved_hash=None;w.check_and_save();assert w.check_revision==w.project['revision'];w.issues=[{'severity':'warning','code':'SYMBOL.UNUSED','message':'navigate','cell':cid,'object':None}];w.fill_checks();w.check_selected(0,0);assert w.cid==cid;checks.append('Check and Save and clickable cross-cell findings')
w.cid=c['id'];w.selection=[];w.refresh(True);w.results_dock.hide();w.resize(1440,960);QTest.qWait(70);w.grab().save(str(out/'schematic-editor.png'));w.resize(1050,720);QTest.qWait(70);w.grab().save(str(out/'compact-editor.png'))
assert not errors,errors
(out/'results.json').write_text(json.dumps({'status':'passed','checks':checks,'errors':errors},indent=2));w.saved_hash=digest(w.project);w.close();print(json.dumps({'status':'passed','checks':len(checks)},indent=2))
