"""Optional installed-engine desktop gate; requires explicit project/tool paths."""
import os,sys,time,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
a=argparse.ArgumentParser();a.add_argument('--project',required=True);a.add_argument('--output',required=True)
for tool in ('magic','netgen','ngspice'):a.add_argument('--'+tool,required=True)
args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import load_project,digest,clone
app=QApplication([]);app.setStyle('Fusion');errors=[];sys.excepthook=lambda t,v,tb:errors.append(str(v));w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1640,1080);w.show()
p=load_project(args.project);w.set_project(p);w.cid=next(c['id'] for c in p['cells'] if c['name']=='custom_inverter');w.mode_combo.setCurrentIndex(1);w.refresh(True)
for name in ('magic','netgen','ngspice'):w.settings.setValue('engine/'+name,getattr(args,name))
w.run_silicon();deadline=time.monotonic()+240
while w.process and time.monotonic()<deadline:QTest.qWait(50)
assert not w.process,'worker timed out';assert w.result['silicon_report']['status']=='passed',w.result['silicon_report'];assert w.silicon_table.rowCount()==7
w.resizeDocks([w.results_dock],[405],__import__('PySide6.QtCore',fromlist=['Qt']).Qt.Vertical);w.fit_active();QTest.qWait(80);w.grab().save(str(out/'verified-desktop.png'))
w.silicon_waveform('post-layout');assert len(w.plot.result['x'])>3000;QTest.qWait(50);w.grab().save(str(out/'post-layout-waveform.png'))
w.open_silicon();w.commit(lambda p:next(c for c in p['cells'] if c['id']==w.cid)['devices'][0]['params'].update(w='1.5u'),'Change W');assert 'STALE' in w.silicon_status.text()
assert not errors,errors
(out/'desktop-report.json').write_text(json.dumps({'status':'passed','checks':['native worker runs complete physical flow','seven passing stage rows','post-layout waveform opens','changed design marked stale'],'evidence_directory':w.result['evidence_directory']},indent=2));w.saved_hash=digest(w.project);w.close();print('PASS: real engine workflow from the native desktop.')
