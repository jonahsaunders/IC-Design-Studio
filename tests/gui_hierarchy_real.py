"""Optional actual-engine desktop gate for a saved hierarchical testbench."""
import os,sys,time,json,argparse,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
a=argparse.ArgumentParser();a.add_argument('--project',required=True);a.add_argument('--output',required=True)
for tool in ('magic','netgen','ngspice'):a.add_argument('--'+tool,required=True)
args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import load_project,digest
app=QApplication([]);app.setStyle('Fusion');errors=[];sys.excepthook=lambda t,v,tb:errors.append(''.join(traceback.format_exception(t,v,tb)));w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1640,1080);w.show();p=load_project(args.project);w.set_project(p);t=p['testbenches'][0]
for name in ('magic','netgen','ngspice'):w.settings.setValue('engine/'+name,getattr(args,name))
def wait():
    deadline=time.monotonic()+180
    while w.process and time.monotonic()<deadline:QTest.qWait(40)
    assert not w.process,'worker timed out';assert not errors,errors
# Physical result must belong to the DUT even when started from its fixture.
w.cid=t['bench_cell'];w.refresh(True);w.run_silicon();wait();assert w.result['silicon_report']['status']=='passed',w.console.toPlainText();assert w.result['cell_id']==t['dut_cell'];physical_directory=w.result['evidence_directory'];w.cid=t['dut_cell'];w.mode_combo.setCurrentIndex(1);w.refresh(True);w.open_silicon();w.resizeDocks([w.results_dock],[400],Qt.Vertical);w.fit_active();QTest.qWait(60);w.grab().save(str(out/'verified-ring.png'))
w.silicon_waveform('post-layout');assert len(w.plot.result['x'])>3000;QTest.qWait(60);w.grab().save(str(out/'ring-post-layout.png'))
# Standalone saved bench result must belong to the fixture when started in DUT.
w.run_testbench();wait();assert w.result['cell_id']==t['bench_cell'];assert w.result['measurements']['status']=='passed';w.open_testbenches();assert w.bench_measurements.rowCount()==2;QTest.qWait(60);w.grab().save(str(out/'saved-measurements.png'));w.edit_testbench();QTest.qWait(40);w._testbench_dialog.grab().save(str(out/'testbench-editor.png'));w._testbench_dialog.close()
w.commit(lambda p:p['testbenches'][0]['analysis'].update(temperature='85'),'Change bench temperature');assert 'STALE' in w.bench_note.text();w.open_silicon();assert 'STALE' in w.silicon_status.text();assert not errors,errors
(out/'desktop-report.json').write_text(json.dumps({'status':'passed','checks':['physical worker from fixture publishes DUT result','seven verified hierarchical stages','post-layout saved probe waveforms','saved bench worker from DUT publishes fixture result','saved measurements table','native testbench editor','changed saved bench marks both reports stale'],'physical_evidence':physical_directory},indent=2));w.saved_hash=digest(w.project);w.close();print('PASS: hierarchical physical workflow and configurable saved bench from native desktop.')
