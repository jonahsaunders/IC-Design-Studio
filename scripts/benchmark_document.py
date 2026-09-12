"""Separate distinct stored geometry from repeated hierarchy; measure real edit costs."""
import argparse,gc,json,platform,statistics,sys,time,tracemalloc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import example,History,uid
from icstudio.layout import rect
from benchmark_layout import retained_bytes


def project(count,repeated=False):
    p=example('empty');top=p['cells'][0]
    for part,start in enumerate(range(0,1 if repeated else count,250000)):
        c=top if part==0 else dict(id=uid(),name='master_'+str(part),ports=[],devices=[],shapes=[])
        if c is not top:
            p['cells'].append(c);top.setdefault('layout_instances',[]).append(dict(id=uid(),name='placed_'+str(part),cell=c['id'],x=part*1200000,y=0))
        c['shapes']=[rect('metal1',(i%1000)*1000,(i//1000)*1000,500,500) for i in range(1 if repeated else min(250000,count-start))]
    if repeated:
        master=top;top=dict(id=uid(),name='array_top',ports=[],devices=[],shapes=[],layout_instances=[]);p['cells'].append(top);p['top']=top['id']
        for i,start in enumerate(range(0,count,1000000)):
            size=min(1000000,count-start);nx=min(1000,size);ny=size//nx
            top['layout_instances'].append(dict(id=uid(),name='array_'+str(i),cell=master['id'],x=i*1200000,y=0,nx=nx,ny=ny,a=[1000,0],b=[0,1000]))
    return p


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--sizes',type=int,nargs='+',default=[10000,100000,1000000]);args=parser.parse_args()
    if any(n not in (10000,100000,1000000) for n in args.sizes):parser.error('Choose 10000, 100000 or 1000000.')
    args.out.mkdir(parents=True,exist_ok=True);report=dict(host=platform.platform(),python=platform.python_version(),scope='Document commit/undo allocation only. Distinct geometry and repeated instances measured separately. No UI, disk, or DRC timing included.',workloads=[])
    for repeated in (False,True):
        for count in args.sizes:
            p=project(count,repeated);start=time.perf_counter();h=History(p);load_ms=(time.perf_counter()-start)*1000;del p;gc.collect()
            c=h.project['cells'][0];cid=c['id'];sid=c['shapes'][0]['id'];samples=[]
            for _ in range(3):
                before=h.project;points=before['cells'][0]['shapes'][0]['points'];start=time.perf_counter();assert h.commit_shape_move(cid,[sid],5,0);elapsed=(time.perf_counter()-start)*1000
                assert h.project['cells'][0]['shapes'][0]['points']==[[x+5,y] for x,y in points]
                assert all(a is b for a,b in zip(before['cells'][0]['shapes'][1:],h.project['cells'][0]['shapes'][1:]))
                start=time.perf_counter();h.undo();undo_ms=(time.perf_counter()-start)*1000;assert h.project['cells']==before['cells']
                start=time.perf_counter();h.redo();redo_ms=(time.perf_counter()-start)*1000;samples.append(dict(commit_ms=elapsed,undo_ms=undo_ms,redo_ms=redo_ms))
            tracemalloc.start();h.commit_shape_move(cid,[sid],5,0);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            row=dict(kind='repeated hierarchy' if repeated else 'distinct stored shapes',visible_occurrences=count,stored_shapes=sum(len(c['shapes']) for c in h.project['cells']),stored_cells=len(h.project['cells']),initial_validate_and_copy_ms=load_ms,
                     median={key:round(statistics.median(s[key] for s in samples),3) for key in samples[0]},one_edit_peak_allocated_bytes=peak,undo_history_bytes=retained_bytes(h.undo_stack))
            report['workloads'].append(row);(args.out/'document.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
            del h,c,before;gc.collect()
    return 0


if __name__=='__main__':raise SystemExit(main())
