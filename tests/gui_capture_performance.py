"""Repeatable native capture workloads; baseline and release use this same driver."""
import argparse,json,os,sys,time,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--source-root',default=str(ROOT));args=a.parse_args();sys.path.insert(0,args.source_root);out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['XDG_CONFIG_HOME']=str(out/'profile/config');os.environ['XDG_DATA_HOME']=str(out/'profile/data')
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.model import example,device,uid,clone,digest
from icstudio import wiring
from icstudio.canvas import Canvas
from icstudio.symbol_editor import SymbolPad
from icstudio.symbol_geometry import enriched
from icstudio.symbol_io import default_symbol
app=QApplication([]);app.setStyle('Fusion');p=example('empty');c=p['cells'][0];c['devices']=[device('R','R'+str(i),(i%25)*250,(i//25)*200) for i in range(500)];c['wires']=[{'id':uid(),'points':[[x*120,y*100+25],[x*120+80,y*100+25]]} for y in range(40) for x in range(50)];c['labels']=[];c['junctions']=[]
for d in c['devices']:d['net_labels']={}
timings={};start=time.perf_counter();wiring.rebuild(c,p);timings['rebuild_500_devices_2000_wires']=time.perf_counter()-start
canvas=Canvas('schematic');canvas.resize(1000,700);canvas.set_data(c,p['pdk'],[],'');start=time.perf_counter();canvas.show();canvas.fit();app.processEvents();timings['initial_schematic_paint']=time.perf_counter()-start
start=time.perf_counter()
for i in range(500):
    pt=QPointF((i%25)*250,(i//25)*200-50);target=canvas.wire_target(pt);assert target and target[1][0]=='pin'
timings['500_exact_pin_snaps']=time.perf_counter()-start;before=digest(c);elapsed=[]
for i in range(20):start=time.perf_counter();canvas.selection=[c['devices'][i]['id']];canvas.repaint();app.processEvents();elapsed.append(time.perf_counter()-start)
timings['schematic_selection_median']=statistics.median(elapsed);assert before==digest(c)
old=canvas.cell;c=clone(c);c['devices'][0]['x']+=15;canvas.set_data(c,p['pdk'],[],'');target=canvas.wire_target(QPointF(15,-50));assert target and target[1][1:]==(c['devices'][0]['id'],'p');canvas.close()
s=enriched(default_symbol(['a','b']));s['primitives']=[{'kind':'rect','points':[[(i%40)*20-400,(i//40)*20-250],[(i%40)*20-390,(i//40)*20-240]]} for i in range(1000)];pad=SymbolPad(s,True);pad.resize(900,700);start=time.perf_counter();pad.show();pad.fit();app.processEvents();timings['initial_1000_primitive_symbol_paint']=time.perf_counter()-start;elapsed=[]
for i in range(20):start=time.perf_counter();pad.selection=i;pad.selections={i};pad.repaint();app.processEvents();elapsed.append(time.perf_counter()-start)
timings['symbol_selection_median']=statistics.median(elapsed);pad.command('mirror');pad.undo();assert pad.symbol['primitives']==s['primitives'];pad.close()
report={'status':'passed','workload':{'schematic_devices':500,'wires':2000,'pin_queries':500,'selection_repaints':20,'symbol_primitives':1000},'seconds':{key:round(value,5) for key,value in timings.items()},'checks':['exact pin targets remain correct','selection does not mutate circuit','geometry change invalidates pin lookup','symbol transform and undo preserve artwork'],'qualification':'Synthetic offscreen build-host timing; not a fresh desktop or production-size qualification.'};(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
