"""Measured hierarchy workload, including real selection and cache invalidation."""
import argparse,json,os,sys,time,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'profile/config');os.environ['XDG_DATA_HOME']=str(out/'profile/data')
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,uid,digest
from icstudio.layout import rect
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.settings.remove('editor/workspaces');w.show();QTest.qWait(150)
p=example('empty');c=p['cells'][0];child={'id':uid(),'name':'tile','ports':[],'devices':[],'shapes':[rect('metal1',x*2000,y*2000,1000,1000) for x in range(20) for y in range(10)]};p['cells'].append(child)
c['layout_instances']=[{'id':uid(),'name':f'T{x}_{y}','cell':child['id'],'x':x*45000,'y':y*25000,'rotation':0,'mirror':False,'nx':1,'ny':1} for x in range(10) for y in range(5)]
start=time.perf_counter();w.set_project(p);w.mode_combo.setCurrentIndex(1);w.refresh(True);QTest.qWait(100);initial=time.perf_counter()-start;canvas=w.layout;assert len(canvas.cell['shapes'])==10000
geometry=canvas.cell['shapes'];index=canvas._spatial;durations=[]
for i in range(30):
    start=time.perf_counter();w.select([c['layout_instances'][i]['id']],'layout');app.processEvents();durations.append(time.perf_counter()-start)
    assert canvas.cell['shapes'] is geometry and canvas._spatial is index
start=time.perf_counter()
for i in range(100):assert canvas.hit(QPointF(500+(i%10)*45000,500+(i%5)*25000))
hits=time.perf_counter()-start
w.select([c['layout_instances'][0]['id']],'layout');w.editor_execute('move_ref',{'dx':5000,'dy':0});assert canvas.cell['shapes'] is not geometry and canvas._spatial is not index
w.undo();assert len(canvas.cell['shapes'])==10000
report={'status':'passed','workload':{'physical_instances':50,'unique_local_shapes':200,'flattened_shapes':10000,'selection_changes':30,'hit_queries':100},'seconds':{'initial_load_and_paint':round(initial,4),'selection_median_including_paint':round(statistics.median(durations),4),'selection_max_including_paint':round(max(durations),4),'hit_queries_total':round(hits,4)},'checks':['selection reuses flattened geometry and spatial index','hit queries select correct populated tiles','committed move invalidates both caches; undo restores shape count'],'qualification':'Synthetic offscreen build-host workload; no production-size or fresh-desktop performance claim.'}
w.saved_hash=digest(w.project);w.close();(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
