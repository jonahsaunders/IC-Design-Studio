"""Bounded cursor-query latency; excludes painting, setup and edit commits."""
import argparse,json,math,statistics,sys,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication
    from icstudio.canvas import Canvas
    from icstudio.layout import rect
    from icstudio.layout_scene import LayoutScene
    from icstudio.model import example
    from icstudio import __version__
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    app=QApplication([]);canvas=Canvas('layout');canvas.tool='path';canvas.scale=.1;rows=[]
    try:
        for count in (1000,10000):
            for hierarchical in (False,True):
                p=example('empty');c=p['cells'][0];columns=100
                c['layout_ports']=[{'id':str(i),'layer':'metal1','point':[(i%columns)*1000,(i//columns)*1000]} for i in range(count)]
                if hierarchical:
                    master={'id':'master','name':'master','devices':[],'ports':[],'shapes':[rect('metal1',0,0,600,600)]};p['cells'].append(master)
                    c['layout_instances']=[{'id':'array','name':'X','cell':'master','x':0,'y':0,'nx':columns,'ny':count//columns,'a':[1000,0],'b':[0,1000]}]
                    scene=LayoutScene().update(p,c['id']);scene.query((-100,-100,100000,100000));prior_cache=scene.cache
                    c={**c,'_layout_scene':scene}
                else:c['shapes']=[rect('metal1',(i%columns)*1000,(i//columns)*1000,600,600) for i in range(count)]
                canvas.set_data(c,p['pdk']);samples=[]
                for i in range(320):
                    n=(i*193)%count;point=QPointF((n%columns)*1000+607,(n//columns)*1000+235)
                    start=time.perf_counter();snapped=canvas.snap(point);elapsed=(time.perf_counter()-start)*1000
                    assert snapped==QPointF((n%columns)*1000+600,(n//columns)*1000+235)
                    if i>=20:samples.append(elapsed)
                    if hierarchical:assert scene.cache is prior_cache,'Snap evicted the viewport geometry cache'
                rows.append({'shapes':count,'terminals':count,'hierarchical':hierarchical,'samples':len(samples),
                    'median_ms':statistics.median(samples),'p95_ms':sorted(samples)[math.ceil(.95*len(samples))-1],'max_ms':max(samples),
                    'viewport_cache_preserved':True if hierarchical else None})
    finally:canvas.close()
    result={'version':__version__,'workflow_hash':WORKFLOW_SOURCE_HASH,'status':'passed','qt_platform':app.platformName(),
            'scope':'Canvas snap lookup only, 0.1 pixels per layout unit; setup, painting, commits and recovery excluded','rows':rows}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
