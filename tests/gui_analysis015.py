"""Native simulation, marker and wire interaction acceptance, using real workers."""
import argparse,json,os,sys,time,traceback,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
from PySide6.QtCore import Qt,QPoint,QPointF,QSettings,QProcess
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from icstudio.gui import Studio
from icstudio.model import example,clone,digest,design_digest,device,uid
from icstudio import wiring
from icstudio.measurements import evaluate
errors=[];sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear()
w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1540,1040);w.show();QTest.qWait(150);checks=[]
def passed(text):checks.append(text)
def capture(name):QTest.qWait(60);assert w.grab().save(str(out/name))
def finish():
    deadline=time.monotonic()+35
    while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(25)
    assert not w.run_manager.busy,'workers timed out'
    assert not errors,errors

def screen(c,x,y):return (QPointF(x,y)*c.scale+c.offset).toPoint()

w.command_actions['Compatibility matrix'].trigger();QTest.qWait(50)
assert w._compatibility_dialog.isVisible() and w.compatibility_table.rowCount()==8
w.compatibility_search.setText('Xschem');assert w.compatibility_table.rowCount()==1
assert 'Import / export'==w.compatibility_table.item(0,2).text();w.compatibility_search.clear();w._compatibility_dialog.grab().save(str(out/'compatibility.png'));w._compatibility_dialog.close();passed('Help action opens searchable offline compatibility matrix')
# Saved run plan and actual independent QProcess workers.
w.set_project(example('rc'));w.parallel_jobs.setValue(2)
for i,kind in enumerate(('tran','tran','ac')):
    w.analysis_type.setCurrentIndex(w.analysis_type.findData(kind))
    if kind=='tran':w.analysis_fields['stop'].setText('2m');w.analysis_fields['step'].setText('100n')
    w.add_simulation_setup()
assert len(w.project['simulation_setups'])==3
w.run_enabled_setups();rows=list(w.run_manager.rows)
assert len(rows)==3 and [r['state'] for r in rows]==['Running','Running','Queued']
assert w.run_button.isEnabled();snapshot=clone(rows[0]['job']['project'])
deadline=time.monotonic()+10
while sum(p.state()==QProcess.Running for p in w.run_manager.processes)<2 and time.monotonic()<deadline:QTest.qWait(5)
assert len({p.processId() for p in w.run_manager.processes if p.processId()})==2
capture('simulation-running.png');passed('Two real workers run concurrently and the third queues at the configured limit')
w.simulation_runs.selectRow(2);w.stop_selected_runs();assert rows[2]['state']=='Cancelled'
w.simulation_runs.selectRow(1);w.stop_selected_runs();assert rows[1]['state'] in ('Stopping','Cancelled')
finish();assert rows[0]['state']=='Complete';assert rows[1]['state']=='Cancelled';assert len(w.jobs)==1
assert rows[0]['result']['design_hash']==design_digest(snapshot)
assert json.loads((rows[1]['path']/'status.json').read_text())['status']=='cancelled';passed('Selected running and queued jobs cancel independently; cancelled results never publish')
assert w.simulation_runs.rowCount()==3 and w.run_button.isEnabled()
w.open_simulation_explorer();w.simulation_runs.selectRow(0);w.open_selected_run();assert w.result is rows[0]['result'];passed('Completed runs open with their immutable input revision and independent log')
# Free-position markers, exact numeric thresholds, persistence and dragging.
plot=w.plot;w.results_tabs.setCurrentIndex(0);w.resizeDocks([w.results_dock],[490],Qt.Vertical);QTest.qWait(100)
w.waveform_tools.trace.setCurrentText('vout');w.waveform_tools.mode.setCurrentIndex(3)
x=(plot.result['x'][30]+plot.result['x'][31])*.5;y=.6
QTest.mouseClick(plot,Qt.LeftButton,pos=plot.screen(x,y).toPoint());assert len(plot.markers)==1
m=plot.markers[0];assert m['kind']=='XY' and m['trace']=='vout'
# Numeric entry is independent of pixel resolution and the simulator sample grid.
w.waveform_tools.open_manager();ui=w.waveform_tools;ui.x.setText('3.05u');ui.y.setText('1.8');ui.apply_marker(False)
assert math.isclose(m['x'],3.05e-6) and evaluate(plot.result,m)['verdict']=='PASS',(m,evaluate(plot.result,m),ui.error.text())
ui.y.setText('-1');ui.apply_marker(False);assert evaluate(plot.result,m)['verdict']=='FAIL'
assert 'FAIL' in ui.csv_text();ui.dialog.grab().save(str(out/'waveform-markers.png'));ui.dialog.close();passed('Exact X/Y coordinates and engineering suffixes produce numerical PASS/FAIL checks and CSV')
# Place a visible Y line and drag it; switching trace visibility retains markers.
w.waveform_tools.mode.setCurrentIndex(2);QTest.mouseClick(plot,Qt.LeftButton,pos=plot.screen(.001,.7).toPoint());assert len(plot.markers)==2
limit=plot.markers[-1];pos=plot.screen(.001,limit['y']).toPoint();end=pos+QPoint(0,-30)
QTest.mousePress(plot,Qt.LeftButton,pos=pos);QTest.mouseMove(plot,end);QTest.mouseRelease(plot,Qt.LeftButton,pos=end)
assert limit['y']>.7;assert w.waveform_tools.path.exists();before=clone(plot.markers)
w.traces.item(0).setCheckState(Qt.Unchecked);assert plot.markers==before;passed('Mouse placement and dragging retain exact markers across trace visibility changes')
# Test out-of-range status and marker restoration after choosing another result.
plot.add_marker('X',-.01,0,'vout');assert evaluate(plot.result,plot.markers[-1])['verdict']=='Out of range'
plot.markers.pop();plot.markers_changed.emit();saved=clone(plot.markers)
r=clone(w.result);r['created']='another run';w.add_result(r);assert not plot.markers;w.run_combo.setCurrentIndex(0);assert plot.markers==saved;passed('Measurements restore per result; out-of-range coordinates cannot falsely pass')
# Zoom, pan, cancel and focused shortcuts operate on the plot, never the circuit.
plot.fit_plot();QTest.qWait(20);original_bounds=plot.bounds();pos=plot.box.center()
wheel=QWheelEvent(pos,plot.mapToGlobal(pos.toPoint()),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False);app.sendEvent(plot,wheel)
assert plot.bounds()[1]-plot.bounds()[0]<original_bounds[1]-original_bounds[0]
QTest.mousePress(plot,Qt.MiddleButton,pos=pos.toPoint());QTest.mouseMove(plot,(pos+QPointF(25,10)).toPoint());QTest.mouseRelease(plot,Qt.MiddleButton,pos=(pos+QPointF(25,10)).toPoint());assert plot.bounds()!=original_bounds
plot.setFocus();QTest.keyClick(plot,Qt.Key_F);assert plot.bounds()==original_bounds
marker=plot.markers[0];marker.update(x=.0004,y=.8);start=plot.screen(.001,marker['y']).toPoint();old_x=marker['x'];old_y=marker['y'];end=start+QPoint(0,-15)
QTest.mousePress(plot,Qt.LeftButton,pos=start);QTest.mouseMove(plot,end);assert marker['x']==old_x and marker['y']!=old_y
QTest.keyClick(plot,Qt.Key_Escape);QTest.mouseRelease(plot,Qt.LeftButton,pos=end);assert marker['x']==old_x and marker['y']==old_y
cells=clone(w.project['cells']);count=len(plot.markers);QTest.keyClick(plot,Qt.Key_Delete);assert len(plot.markers)==count-1 and w.project['cells']==cells
plot.markers=saved;plot.markers_changed.emit();passed('Plot zoom/pan, single-axis marker dragging, Escape and Delete preserve circuit data')
# Improve screenshot with readable threshold and cursor.
plot.markers[0].update(x=25e-6,y=1.3);plot.markers[1].update(y=1.6);plot.markers_changed.emit();plot.fit_plot();x0,x1,y0,y1=plot.bounds();plot._view_bounds=(0,100e-6,y0,y1);capture('waveforms-dark.png')
w.toggle_theme();QTest.qWait(80);capture('waveforms-light.png');w.toggle_theme()
# Actual wire drag/preview/undo, compared with the committed topology.
p=example('empty');c=p['cells'][0];c.update(wires=[],junctions=[],labels=[]);c['devices']=[device('R','R1',100,150),device('C','C1',400,150)]
for d in c['devices']:d['net_labels']={}
wiring.add_wire(c,[[100,100],[100,40],[400,40],[400,100]],p);w.set_project(p);w.results_dock.hide();w.schematic.fit();QTest.qWait(80);canvas=w.schematic
for i in range(6):
    wire=w.cell['wires'][0];a,b=wire['points'][1:3];pos=screen(canvas,(a[0]+b[0])/2,a[1]);end=pos+QPoint(0,-20 if i%2==0 else 20)
    QTest.mousePress(canvas,Qt.LeftButton,pos=pos);QTest.mouseMove(canvas,end);assert canvas.wire_drag
    QTest.mouseRelease(canvas,Qt.LeftButton,pos=end);assert len(w.cell['wires'][0]['points'])==4
assert w.cell['devices'][0]['nets']['p']==w.cell['devices'][1]['nets']['p']
before=clone(w.cell);w.undo();w.redo();assert w.cell==before;passed('Native repeated wire drags preserve connectivity and four corners; undo/redo is atomic')
# Run history recovery, plan portability and compact workspace.
w.set_project(snapshot);assert len(w.project['simulation_setups'])==3;assert len(w.run_manager.rows)==3
assert [r['state'] for r in w.run_manager.rows].count('Complete')==1;passed('Reopening the project restores run history and its saved analysis plan')
w.open_simulation_explorer();capture('simulation-history.png');w.resize(1100,760);QTest.qWait(100);assert w.width()==1100;capture('simulation-compact.png')
assert not errors,errors;w.saved_hash=digest(w.project);w.close();app.processEvents()
(out/'report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2));print('PASS',len(checks),'native analysis and wiring checks')
