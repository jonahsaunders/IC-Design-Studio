"""Compare attachment-heavy edits and long drags against an extracted source."""
import argparse,hashlib,json,platform,statistics,sys,time
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--samples',type=int,default=3);a=ap.parse_args()
    if not 1<=a.samples<=10:ap.error('Use 1–10 samples.')
    sys.path.insert(0,str(a.source.resolve()))
    from icstudio.model import example,clone,History
    from icstudio.layout import rect
    from icstudio.layout_arrange import arrange
    from icstudio.layout_topology import partition
    from icstudio.canvas import Canvas
    from icstudio.layout_scene import LayoutScene
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPointF
    from icstudio import __version__
    def stats(v):
        return {'samples_ms':v,'median_ms':statistics.median(v),'p95_ms':sorted(v)[max(0,__import__('math').ceil(.95*len(v))-1)]}
    rows=[]
    for count in (250,1000):
        p=example('empty');c=p['cells'][0];ids=[]
        for i in range(count):
            x=(i%11)*25;y=i*2000;s=rect('metal1',x,y,600,600);ids.append(s['id']);c['shapes'].append(s)
            c['shapes'].append({'id':'route'+str(i),'kind':'path','layer':'metal1','width':200,'points':[[x+600,y+300],[x+1600,y+300]]})
        original=partition(p,c['id']);times=[]
        for _ in range(a.samples):
            q=clone(p);start=time.perf_counter();arrange(q,c['id'],ids,'left',connected=True);times.append((time.perf_counter()-start)*1000)
            assert partition(q,c['id'])==original
        rows.append({'name':'align_with_attached_routes','footprints':count,'total_shapes':2*count,**stats(times)})
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',i*500,0,600,600) for i in range(count)];ids=[s['id'] for s in c['shapes']]
        h=History(p);times=[]
        for _ in range(a.samples):
            start=time.perf_counter();assert h.commit_layout_move(c['id'],ids,5,0);times.append((time.perf_counter()-start)*1000)
        rows.append({'name':'move_one_large_connected_component','shapes':count,**stats(times)})
    app=QApplication.instance() or QApplication([]);p=example('empty');top=p['cells'][0]
    p['cells'].append({'id':'tile','name':'tile','ports':[],'devices':[],'shapes':[rect('metal1',0,0,600,600)]})
    top['layout_instances']=[{'id':'array','name':'array','cell':'tile','x':0,'y':0,'nx':100,'ny':100,'a':[1000,0],'b':[0,1000]}]
    scene=LayoutScene().update(p,top['id']);w=Canvas('layout');w.resize(1000,700);w.show();app.processEvents();w.auto_fit=False;w.scale=.045;w.offset=QPointF(20,20)
    w.set_data({**top,'_layout_scene':scene},p['pdk'],['array']);w.anchor=QPointF(0,0);w.moving=True
    for name,step in [('fine_array_drag',5),('long_array_drag',500)]:
        times=[]
        for i in range(40):
            w.drag=QPointF(i*step,500);start=time.perf_counter();w.grab();times.append((time.perf_counter()-start)*1000)
        rows.append({'name':name,'expanded_shapes':10000,'frames':40,'step_nm':step,**stats(times)})
    w.close();app.processEvents()
    h=hashlib.sha256()
    for p in sorted((a.source/'icstudio').glob('*.py')):
        if p.name!='build_info.py':h.update(p.name.encode()+p.read_bytes())
    report={'version':__version__,'workflow_hash':h.hexdigest(),'platform':platform.platform(),'qt_platform':app.platformName(),'workloads':rows,
            'scope':'Operation-local geometry and history, plus CPU Qt Canvas rendering. Actual topology assertions; excludes durable recovery, full Studio refresh, external DRC and display presentation.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
