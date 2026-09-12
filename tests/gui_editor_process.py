"""0.11 routing transitions against locked process geometry and real engines."""
import argparse,json,os,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--pdks',required=True)
for name in ('magic','netgen','ngspice'):a.add_argument('--'+name,required=True)
args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'profile/config');os.environ['XDG_DATA_HOME']=str(out/'profile/data')
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest,example
from icstudio.analog import reference
from icstudio.analog_layout import generate_mirror
from icstudio.sky130_layout import layers
from icstudio.layout import polygon,kdb
from icstudio.gf180_layout import reference_project,generate_inverter,layers as gf_layers
errors=[];sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.settings.remove('editor/workspaces');w.error=lambda e:errors.append(str(e));w.resize(1660,1100);w.show();w.activateWindow();QTest.qWait(160)
for name in ('magic','netgen','ngspice'):w.settings.setValue('engine/'+name,str(Path(getattr(args,name)).resolve()))
def tech(family):
    root=Path(args.pdks).resolve()/family;m=json.loads((root/'package.json').read_text());t=m['technology'];t.update(package_root=str(root),package_lock={k:m[k] for k in ('id','revision','files')});return t
p,cid,key=reference(tech('sky130A'));generate_mirror(p,cid);w.set_project(p);w.cid=cid;w.mode_combo.setCurrentIndex(1);w.refresh(True);ls=layers(w.project['pdk']);c=w.layout
before=clone(w.cell['shapes']);pins={(v['device_id'],v['pin']):v['point'] for v in w.cell['layout_pins']};first,second=w.cell['devices'];ga=pins[first['id'],'g'];gb=pins[second['id'],'g'];dr=pins[first['id'],'d'];diode=[dr[0],ga[1]]
w.layer_combo.setCurrentText(ls['m1']);w.editor_net.setCurrentText(first['nets']['g']);w.start_layout_tool('path');c.drawing=[QPointF(*dr),QPointF(*diode)];w.layer_combo.setCurrentText(ls['m2'])
assert len(w.cell['shapes'])==len(before)+4 and c.drawing==[QPointF(*diode)] and c.layer==ls['m2'];transition=clone(w.cell['shapes']);c.drawing.append(QPointF(*gb));c.setFocus();QTest.keyClick(c,Qt.Key_Return);assert len(w.cell['shapes'])==len(before)+5;w.cancel_tool()
for layer in ls.values():
    region=lambda rows:kdb().Region([polygon(s) for s in rows if s['layer']==layer]).merged()
    assert (region(before)^region(w.cell['shapes'])).is_empty(),layer
w.check_linked_layout();assert not w.issues,w.issues;w.run_silicon();deadline=time.monotonic()+600
while w.process and time.monotonic()<deadline:QTest.qWait(50)
assert not w.process and w._silicon_result['silicon_report']['status']=='passed',w.console.toPlainText()
w.undo();assert w.cell['shapes']==transition;w.undo();assert w.cell['shapes']==before
checks=['route layer selector commits segment and complete via atomically','continued path preserves exact verified mask regions','actual full DRC, LVS and extracted electrical verification after route edit','two undo operations restore route completion and layer transition']
# A locked cut layer blocks every part of the pending transition.
w.layer_combo.setCurrentText(ls['m1']);w.start_layout_tool('path');c.drawing=[QPointF(*dr),QPointF(*diode)];c.locked_layers.add(ls['via']);before_hash=digest(w.project);n=len(errors);w.layer_combo.setCurrentText(ls['m2']);assert len(errors)==n+1 and 'Unlock' in errors.pop();assert digest(w.project)==before_hash and c.layer==ls['m1'] and len(c.drawing)==2;c.locked_layers.clear();w.cancel_tool();checks.append('locked cut rejects transition without partial geometry or layer change')
# Processes without a via recipe retain the original in-progress layer.
p=example('empty');p['pdk']['routing_vias']=[];w.set_project(p);w.mode_combo.setCurrentIndex(1);w.layer_combo.setCurrentText('metal1');w.start_layout_tool('path');c.drawing=[QPointF(0,0),QPointF(1000,0)];before_hash=digest(w.project);n=len(errors);w.layer_combo.setCurrentText('metal2');assert len(errors)==n+1;errors.pop();assert digest(w.project)==before_hash and c.layer=='metal1' and w.layer_combo.currentText()=='metal1';w.cancel_tool();checks.append('unsupported process retains in-progress path and original layer')
# Native GF180 layers added during generation become selectable immediately.
p,cid=reference_project(tech('gf180mcuC'));w.set_project(p);w.cid=cid;w.commit(lambda p:generate_inverter(p,cid),'Generate GF180');w.mode_combo.setCurrentIndex(1);m1=gf_layers(w.project['pdk'])['m1'];assert w.layer_combo.findText(m1)>=0;w.layer_combo.setCurrentText(m1);assert c.layer==m1;checks.append('GF180 native drawing layers populate the active layer selector')
# Capture a useful release screenshot from actual mirror geometry.
p,cid,key=reference(tech('sky130A'));generate_mirror(p,cid);w.set_project(p);w.cid=cid;w.mode_combo.setCurrentIndex(1);w.refresh(True);w.set_keyboard_profile('Classic analog',{});w.navtabs.setCurrentIndex(2);w.results_dock.hide();w.resizeDocks([w.nav,w.inspector],[360,290],Qt.Horizontal);w.layer_combo.setCurrentText(ls['m1']);w.start_layout_tool('path');w.editor_net.setCurrentText('IREF');w.layout.fit();QTest.qWait(100);w.grab().save(str(out/'mirror-editor.png'));w.cancel_tool();w.resize(1100,760);QTest.qWait(100);w.grab().save(str(out/'compact-editor.png'))
assert not errors,errors;w.saved_hash=digest(w.project);w.close();(out/'report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2));print('PASS',len(checks),'native process editor checks')
