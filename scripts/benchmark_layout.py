"""Repeatable bounded layout measurements; timings are evidence, not pass thresholds.

Run with a native display for platform qualification, or QT_QPA_PLATFORM=offscreen
for CPU-rendering evidence. --source can measure an extracted historical source.
"""
import argparse
import gc
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path


def summary(samples):
    values=sorted(samples)
    return {'median_ms':round(statistics.median(values),3),
            'p95_ms':round(values[math.ceil(len(values)*.95)-1],3),'samples':len(values)}


def retained_bytes(value, seen=None):
    seen=set() if seen is None else seen
    if id(value) in seen:return 0
    seen.add(id(value));size=sys.getsizeof(value)
    if isinstance(value,dict):size+=sum(retained_bytes(k,seen)+retained_bytes(v,seen) for k,v in value.items())
    elif isinstance(value,(tuple,list,set,frozenset)):size+=sum(retained_bytes(v,seen) for v in value)
    return size


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--sizes',type=int,nargs='+',default=[1000,10000])
    parser.add_argument('--frames',type=int,default=20)
    args=parser.parse_args()
    if not all(1<=n<=20000 for n in args.sizes) or not 5<=args.frames<=100:parser.error('Use 1–20,000 shapes and 5–100 frames.')
    sys.path.insert(0,str(args.source.resolve()))
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication
    from icstudio import __version__
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    from icstudio.canvas import Canvas
    from icstudio.model import example,History,clone
    from icstudio.layout import rect
    from icstudio.design_ops import flatten_layout
    try:from icstudio.layout_scene import LayoutScene
    except ImportError:LayoutScene=None
    app=QApplication.instance() or QApplication([])
    report={'version':__version__,'workflow_hash':WORKFLOW_SOURCE_HASH,
            'host':{'platform':platform.platform(),'processor':platform.processor(),
                    'python':platform.python_version(),'qt_platform':app.platformName(),
                    'viewport_pixels':[1000,700]},'workloads':[],
            'scope':'Synthetic Canvas rendering and History microbenchmarks. No full Studio refresh, recovery I/O, connected edit solver, GPU presentation or native Windows qualification.'}
    for count in args.sizes:
        for hierarchical in (False,True):
            p=example('empty');c=p['cells'][0];cols=math.ceil(math.sqrt(count))
            shapes=[]
            for i in range(count if not hierarchical else 1):
                s=rect('metal1',(i%cols)*1000,(i//cols)*1000,600,600);s['id']='shape_'+str(i);shapes.append(s)
            if hierarchical:
                child={'id':'tile_cell','name':'tile','ports':[],'devices':[],'shapes':shapes,'layout_instances':[]}
                p['cells'].append(child)
                c['layout_instances']=[{'id':'array','name':'array','cell':'tile_cell','x':0,'y':0,'nx':cols,'ny':math.ceil(count/cols),'a':[1000,0],'b':[0,1000],'rotation':0,'mirror':False}]
                start=time.perf_counter()
                if LayoutScene is not None:
                    scene=LayoutScene().update(p,c['id']);drawing={**c,'_layout_scene':scene}
                else:drawing={**c,'shapes':flatten_layout(p,c['id'])}
                expand_ms=(time.perf_counter()-start)*1000
            else:c['shapes']=shapes;drawing=c;expand_ms=0
            canvas=Canvas('layout');canvas.resize(1000,700);canvas.auto_fit=False;canvas.show();app.processEvents()
            builds=[0];original_path=canvas.path
            def counted(shape):builds[0]+=1;return original_path(shape)
            canvas.path=counted
            start=time.perf_counter();canvas.set_data(drawing,p['pdk']);canvas.scale=.045;canvas.offset=QPointF(20,20);canvas.grab();cold_ms=(time.perf_counter()-start)*1000
            def frames(change):
                samples=[]
                for frame in range(args.frames):
                    change(frame);start=time.perf_counter();canvas.grab();samples.append((time.perf_counter()-start)*1000)
                return summary(samples)
            pan=frames(lambda i:setattr(canvas,'offset',QPointF(20+i*2,20)))
            close_scale=canvas.scale
            zoom=frames(lambda i:setattr(canvas,'scale',close_scale*(1+i*.02)))
            canvas.fit();overview=frames(lambda i:setattr(canvas,'offset',canvas.offset+QPointF(1,0)))
            canvas.auto_fit=False;canvas.scale=close_scale;canvas.offset=QPointF(20,20)
            pick=[]
            for i in range(args.frames):
                start=time.perf_counter();canvas.editor_candidates(QPointF(300,300));pick.append((time.perf_counter()-start)*1000)
            canvas.selection=['array' if hierarchical else drawing['shapes'][0]['id']];canvas.anchor=QPointF(200,200);canvas.drag=QPointF(300,300);canvas.moving=True
            initial=builds[0];drag=frames(lambda i:setattr(canvas,'drag',QPointF(300+i*5,300)));drag_builds=builds[0]-initial
            canvas.cancel_gesture()
            if hierarchical and LayoutScene is not None:
                edited=clone(p);edited['cells'][1]['shapes'][0]['points'][0][0]+=5;scene.update(edited,c['id']);changed={**edited['cells'][0],'_layout_scene':scene}
            else:changed=clone(drawing);changed['shapes'][0]['points'][0][0]+=5
            initial=builds[0];start=time.perf_counter();canvas.set_data(changed,p['pdk']);canvas.grab();edit_cache_ms=(time.perf_counter()-start)*1000;edit_builds=builds[0]-initial
            canvas.close();canvas.deleteLater();app.processEvents()
            h=History(p);commits=[];undos=[];redos=[]
            def edit(q):
                target=q['cells'][0]
                if hierarchical:target['layout_instances'][0]['x']+=5
                else:target['shapes'][0]['points'][0][0]+=5
            for i in range(10):
                start=time.perf_counter();h.commit(edit,'Measured local edit');commits.append((time.perf_counter()-start)*1000)
            memory=retained_bytes(h.undo_stack)
            for i in range(10):
                start=time.perf_counter();h.undo();undos.append((time.perf_counter()-start)*1000)
            for i in range(10):
                start=time.perf_counter();h.redo();redos.append((time.perf_counter()-start)*1000)
            # Separate allocation measurement so instrumentation does not distort
            # the timing samples. This excludes native Qt/KLayout allocations.
            tracemalloc.start();h.commit(edit,'Allocation probe');_,python_peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            report['workloads'].append({'kind':'hierarchical_array' if hierarchical else 'flat','requested_shapes':count,'display_shapes':scene.expanded_count if hierarchical and LayoutScene is not None else len(drawing['shapes']),
                'hierarchy_expansion_ms':round(expand_ms,3),'native_master_shapes':scene.stats['master_shapes'] if hierarchical and LayoutScene is not None else None,'cold_canvas_ms':round(cold_ms,3),'pan':pan,'zoom':zoom,'overview':overview,'drag':drag,'selection':summary(pick),
                'drag_path_builds':drag_builds,'single_shape_cache_update_ms':round(edit_cache_ms,3),'single_shape_path_builds':edit_builds,
                'history_commit':summary(commits),'history_undo':summary(undos),'history_redo':summary(redos),'ten_undo_records_bytes':memory,
                'one_commit_peak_python_allocated_bytes':python_peak})
            del h,p,c,drawing,changed,canvas;gc.collect()
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
