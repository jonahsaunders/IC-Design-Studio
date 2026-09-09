"""Align identical 1k/10k selections in Studio and the native geometry database.

The native database loop excludes selection UI, history and recovery; it is an
engine reference, not a measurement of another desktop application's GUI.
"""
import argparse, hashlib, json, platform, statistics, sys, time
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--sizes',type=int,nargs='+',default=[1000,10000]);ap.add_argument('--samples',type=int,default=3);a=ap.parse_args()
    if not 1<=a.samples<=10 or not all(2<=v<=10000 for v in a.sizes):ap.error('Use 2–10,000 objects and 1–10 samples.')
    sys.path.insert(0,str(a.source.resolve()))
    from icstudio.model import example,clone,History
    from icstudio.layout import rect,kdb,polygon
    from icstudio.layout_edit import align
    from icstudio import __version__
    def measure(fn):
        start=time.perf_counter();fn();return (time.perf_counter()-start)*1000
    def stats(values):return {'samples_ms':values,'median_ms':statistics.median(values),'first_ms':values[0],'max_ms':max(values)}
    rows=[]
    for n in a.sizes:
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',(i%11)*25,i*1000,600,600) for i in range(n)];ids=[s['id'] for s in c['shapes']]
        kernels=[];history=[];native=[];connected=[]
        for _ in range(a.samples):
            q=clone(p);kernels.append(measure(lambda:align(q,c['id'],ids,'left')))
            assert all(polygon(s).bbox().left==0 and s['points'][0][1]==i*1000 for i,s in enumerate(q['cells'][0]['shapes']))
            h=History(p);history.append(measure(lambda:h.commit_layout_arrange(c['id'],ids,'left') if hasattr(h,'commit_layout_arrange') else h.commit(lambda q:align(q,c['id'],ids,'left'),'Align')))
            cells=clone(h.project['cells']);h.undo();assert h.project['cells']==p['cells'];h.redo();assert h.project['cells']==cells
            import inspect
            if 'connected' in inspect.signature(align).parameters:
                q=clone(p);connected.append(measure(lambda:align(q,c['id'],ids,'left',connected=True)))
                assert all(polygon(s).bbox().left==0 for s in q['cells'][0]['shapes'])
            db=kdb();ly=db.Layout();cell=ly.create_cell('TOP');layer=ly.layer(1,0)
            for s in c['shapes']:cell.shapes(layer).insert(polygon(s))
            def operation():
                for shape in cell.shapes(layer).each():shape.transform(db.Trans(-shape.bbox().left,0))
            native.append(measure(operation));assert all(s.bbox().left==0 for s in cell.shapes(layer).each())
        rows.append({'shapes':n,'studio_geometry_with_validation':stats(kernels),'studio_history_transaction':stats(history),'studio_connected_alignment':stats(connected) if connected else {'status':'not_available_in_source'},'klayout_database_transform_only':stats(native)})
        print(n,'objects:',round(statistics.median(kernels),2),'ms geometry',flush=True)
    h=hashlib.sha256()
    for p in sorted((a.source/'icstudio').glob('*.py')):
        if p.name!='build_info.py':h.update(p.name.encode()+p.read_bytes())
    report={'version':__version__,'workflow_hash':h.hexdigest(),'host':platform.platform(),'python':platform.python_version(),'workloads':rows,
            'scope':'Same flat rect geometry and fixed first reference. Studio includes grouping, grid checks and validation; history also includes cloning/delta/undo bookkeeping. KLayout database loop excludes import, selection, validation, history, display and durable I/O. Not a GUI parity benchmark.',
            'full_gui_with_recovery':'Run the durable integration gate separately; these measurements do not include save, refresh or first paint.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
