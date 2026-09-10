"""Native acceptance for saved requirements, individual cases and physical verification."""
import argparse,json,os,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
from PySide6.QtCore import Qt,QPoint,QPointF,QSettings
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QTableWidgetItem,QDialogButtonBox
from icstudio.gui import Studio
from icstudio.model import example,clone,digest,save_project
from icstudio.variation_runs import prepare,pending,summary
from test_professional016 import rc_design
errors=[];sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear();w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1600,1080);w.show();QTest.qWait(120);checks=[]
def passed(text):checks.append(text)
def wait_until(predicate,seconds=30):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:QTest.qWait(20)
    assert predicate(),'Timed out';assert not errors,errors

def capture(name):QTest.qWait(100);assert w.grab().save(str(out/name))

w.set_project(example());w.open_engineering_tab(w.spec_tab);w.add_spec_row({'name':'Settled output','expression':'final(V("vout"))','min':'1','max':'1.81','unit':'V'});w.add_spec_row({'name':'Peak source power','expression':'max(abs(V("vin")*I("V1")))','max':'.001','unit':'W'});w.save_specifications();assert len(w.cell['specifications'])==2
save_project(w.project,out/'goals.icproj');passed('Editable specification table saves expression, units and limits with the cell')
# Review matrix supports deselection and independent jobs.
base=w.prepare_simulation(w.project['analysis'],'builtin');manifest=prepare(base,{'kind':'sweep','name':'RC resistance study','target':'R1.value','values':['5k','10k','20k','30k']});dlg=w.review_case_matrix(manifest);dlg.case_table.item(3,0).setCheckState(Qt.Unchecked);buttons=dlg.findChild(QDialogButtonBox);buttons.button(QDialogButtonBox.Ok).click();QTest.qWait(5);manifest=w.selected_manifest();assert len(manifest['jobs'])==3
queued=[r for r in w.run_manager.rows if r['state']=='Queued'];assert len(w.run_manager.rows)==3
if queued:w.run_manager.cancel(queued[-1:])
wait_until(lambda:not w.run_manager.busy);initial=len(w.run_manager.rows);w.resume_cases();wait_until(lambda:not w.run_manager.busy);assert all(r.get('result',{}).get('specifications') for r in w.run_manager.rows if r['state']=='Complete');assert not pending(manifest,w.run_manager.rows);assert len(w.run_manager.rows)==initial+(1 if queued else 0);w.refresh_cases();assert w.case_histogram.bins;w.open_engineering_tab(w.cases_tab);capture('variation-cases.png');passed('Reviewed matrix runs independent real workers, resumes only cancelled cases and reports yield and histogram')
# Open any old case without following newly completed jobs.
w.case_table.selectRow(0);w.open_case();assert not w.follow_latest.isChecked();assert w.spec_results.rowCount()==2;capture('specifications.png');passed('Case selection opens immutable requirement results and disables follow-latest')
w.annotate_check.setChecked(True);assert w.schematic.simulation_annotations;assert 'case' in w.schematic.simulation_annotation_label;passed('Operating-point annotations follow the selected variation case')
# Calculator UI builds plots with their own units and markers.
dlg=w.wavecalc_dialog();table=dlg.expression_table;table.item(0,1).setText('V("vout")');table.setRowCount(3)
for i,(name,expr) in enumerate([('Output','V("vout")'),('Source power','V("vin")*I("V1")'),('Spectrum','fft(V("vout"))')]):
    table.setItem(i,0,QTableWidgetItem(name));table.setItem(i,1,QTableWidgetItem(expr))
dlg.render_plots();QTest.qWait(80);assert len(dlg.plots)==3;assert dlg.plots[1].result['plot_unit']=='W';assert dlg.plots[2].result['settings']['type']=='fft';a,b=dlg.plots[:2];ab=a.bounds();bb=b.bounds();a._view_bounds=(ab[0],ab[1]/2,ab[2],ab[3]);a.notify_view();assert b.bounds()[:2]==a.bounds()[:2];assert b.bounds()[2:]==bb[2:];assert dlg.grab().save(str(out/'waveform-calculator.png'));dlg.close();passed('Calculator plots differential/derived power and FFT, keeps units separate and links X views')
# Physical model with real extraction and two actual worker simulations.
w.set_project(rc_design());w.mode_combo.setCurrentIndex(2);w.open_engineering_tab(w.physical_assistant_tab);w.start_live_checks();wait_until(lambda:w._live_worker is None);assert w.placement_table.rowCount()==2;assert all(r['state']=='Placed' for r in w._placement_rows);assert not [i for i in w._live_findings if i['code'].startswith('LVS.')];capture('placement-rules.png');passed('Placement checklist and asynchronous revision-bound checks use actual physical terminals')
from icstudio.layout import rect
from icstudio.live_geometry import preview
candidate={'id':'probe','kind':'path','layer':'metal1','points':[[0,500],[0,8000]],'width':50,'net':'vin'};assert not w.can_commit_geometry(candidate);assert 'Blocked' in w.live_note.text();passed('Route commit rejects a declared width violation before adding geometry')
w.start_job({'type':'rc_compare','analysis':clone(w.project['analysis']),'section_nm':5000},'builtin');wait_until(lambda:not w.run_manager.busy);assert w.run_manager.rows[-1]['state']=='Complete',w.run_manager.rows[-1]['log'];assert w._rc_result and w.rc_table.rowCount()==1;w.open_engineering_tab(w.rc_tab);capture('extracted-comparison.png');w.rc_overlay();assert w.plot.overlays;passed('Distributed RC worker compares the same saved requirement before and after and overlays real waveforms')
save_project(w.project,out/'extracted-demo.icproj');(out/'extracted-result.json').write_text(json.dumps(w._rc_result,indent=2))
# Reviewed Xschem roundtrip preserves reusable native additions.
from icstudio.interchange import export_xschem
exchange=out/'xschem';export_xschem(w.project,exchange);dlg=w.show_xschem_review(exchange/'top.sch');assert not dlg.record['errors'];assert dlg.record['candidate']['cells'][0]['specifications']==w.cell['specifications'];assert dlg.grab().save(str(out/'exchange-review.png'));dlg.close();passed('Xschem review roundtrip preserves native specifications and linked physical device identities')
# Recover persistent case manifests and input-validated results after reopening.
w.set_project(__import__('icstudio.model',fromlist=['load_project']).load_project(out/'goals.icproj'));assert w._case_manifests;assert not pending(w._case_manifests[0],w.run_manager.rows);passed('Reopening the saved project restores studies and validated completed results')
# PVT target choices follow a selected saved fixture even while its DUT is active.
from icstudio.model import device,uid
from icstudio.testbenches import create
p=example('empty');dut=p['cells'][0];dut['ports']=['inp','out'];dut['devices']=[device('R','R1',nets={'p':'inp','n':'out'})];bench={'id':uid(),'name':'bench','ports':[],'devices':[device('X','DUT',500,300,cell=dut['id'],nets={'inp':'vin','out':'vout'}),device('V','VDD',100,200,value='1.8',nets={'p':'vin','n':'0'}),device('C','LOAD',800,300,value='10p',nets={'p':'vout','n':'0'})],'shapes':[]};p['cells'].append(bench);p['testbenches']=[create(p,bench['id'],'Saved_fixture')];w.set_project(p);w.case_bench.setCurrentIndex(1);dlg=w.case_dialog('pvt');assert dlg.fields['target'].text()=='VDD.value';dlg.reject();passed('PVT setup uses the selected saved-testbench supply while its DUT is active')
assert not errors,errors
w.live_check.setChecked(False);wait_until(lambda:w._live_worker is None);w.saved_hash=digest(w.project);w.close();app.processEvents();(out/'report.json').write_text(json.dumps({'checks':checks,'count':len(checks),'errors':errors},indent=2));print(json.dumps({'checks':len(checks),'errors':errors}))
