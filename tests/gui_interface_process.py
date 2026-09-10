"""Reviewed process-cell rename followed by real DRC, LVS and bench comparison."""
import argparse,json,os,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')];a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--pdks',required=True)
for key in ('magic','netgen','ngspice'):a.add_argument('--'+key,required=True)
args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['XDG_CONFIG_HOME']=str(out/'profile/config');os.environ['XDG_DATA_HOME']=str(out/'profile/data')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest,save_project
from icstudio.analog import reference
from icstudio.analog_layout import generate_mirror
from icstudio import capture_ops,interface_update
from icstudio.symbol_geometry import enriched
from icstudio.symbol_io import default_symbol
from icstudio.sky130_layout import audit
from test_consistency import rename
errors=[];sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb));app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.show()
root=Path(args.pdks).resolve()/'sky130A';manifest=json.loads((root/'package.json').read_text());tech=manifest['technology'];tech.update(package_root=str(root),package_lock={k:manifest[k] for k in ('id','revision','files')});p,cid,key=reference(tech);generate_mirror(p,cid);c=capture_ops.cell(p,cid);c['symbol']=enriched(default_symbol(c['ports']));old=next(n for n in c['ports'] if n=='OUT');new='OUTPUT';base=clone(c['symbol']);s=rename(base,old,new)
# Renaming the nets in a record must not refresh stale transistor dimensions.
stale=clone(p);capture_ops.cell(stale,cid)['devices'][0]['params']['w']='2u';candidate=interface_update.plan(stale,cid,s,base)['candidate'];assert any(i['code']=='PDK.STALE' for i in audit(candidate,cid))
w.set_project(p);w.cid=cid;w.refresh(True);w.open_symbol_editor(w.cell);editor=w._symbol_dialog;editor.pad.apply(s);editor.save();review=w._interface_review;assert review.apply_button.isEnabled(),review.error.text();review.apply();assert editor.saved and not audit(w.project,cid),audit(w.project,cid)
for key in ('magic','netgen','ngspice'):w.settings.setValue('engine/'+key,str(Path(getattr(args,key)).resolve()))
w.run_silicon();deadline=time.monotonic()+360
while w.process and time.monotonic()<deadline:QTest.qWait(40)
assert not w.process and w._silicon_result,w.console.toPlainText();result=w._silicon_result;assert result['silicon_report']['status']=='passed',result['silicon_report'];(out/'physical-report.json').write_text(json.dumps(result['silicon_report'],indent=2));save_project(w.project,out/'sky130-renamed-mirror.icproj');w.open_silicon();w.resize(1520,980);QTest.qWait(80);w.grab().save(str(out/'verified-interface.png'));assert not errors,errors
report={'status':'passed','checks':['native reviewed OUT to OUTPUT rename preserves saved fixture nets','stale geometry parameters remain stale after net rename','actual SKY130 full DRC passes','actual extracted Netgen LVS passes with renamed physical labels','actual ngspice pre/post-layout saved-bench comparison passes'],'evidence_directory':result['evidence_directory'],'qualification':'Bounded SKY130 current-mirror engineering flow; not foundry signoff or a verified amplifier.'};(out/'report.json').write_text(json.dumps(report,indent=2));w.saved_hash=digest(w.project);w.close();print(json.dumps(report))
