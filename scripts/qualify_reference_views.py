"""Exercise captured views and hierarchical rendering on the real reference files.

Runs electrical comparisons, not fresh DRC/LVS or extraction. The optional
Franck source must match Studio's committed source lock. Never edits sources.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.model import load_project,save_project,validate,file_digest,clone,digest
from icstudio.testbenches import create,compare_implementation
from icstudio.implementation_views import capture


def attach_view(p,bench,name,text,top,kind):
    t=create(p,bench['id'],name);t['analysis']={**p['analysis'],'type':'op','temperature':27,'corner':'nominal'}
    p.setdefault('testbenches',[]).append(t);validate(p)
    view=capture(p,t['dut_cell'],name,text,top,kind)
    p.setdefault('implementation_views',[]).append(view);t['implementation_view']=view['id']
    validate(p);return t


def banba(output,executable):
    p=load_project(ROOT/'examples/gf180-banba/layout/banba-layout.icproj')
    bench=next(c for c in p['cells'] if c['name']=='tb_dc')
    source=ROOT/'examples/gf180-banba/layout/physical-evidence/extracted-c.spice'
    t=attach_view(p,bench,'banba_capacitance',source.read_text(encoding='utf-8'),'banba_layout','capacitance')
    t['probes']=['VREF'];t['measurements']=[{'name':'reference_voltage','kind':'voltage','node':'VREF','min':'.57','max':'.63'}]
    save_project(p,output/'banba-views.icproj')
    result=compare_implementation(load_project(output/'banba-views.icproj'),t,executable,output/'banba-op')
    return {'status':result['implementation_comparison']['status'],'source_sha256':file_digest(source),
            'comparison':result['implementation_comparison'],'project':'banba-views.icproj'}


def franck(source,output,executable):
    from icstudio.native_migration import review_path
    from scripts.open_project_bench import create as create_bench
    lock=json.loads((ROOT/'examples/open-projects/overvoltage-lock.json').read_text())
    for relative,expected in lock['files'].items():
        if file_digest(source/relative)!=expected:raise ValueError('Franck source differs from the lock: '+relative)
    review=review_path(source/'xschem'/ (lock['top']+'.sch'))
    if review.get('candidate') is None:raise ValueError(str(review.get('errors')))
    setup=output/'franck-setup';setup.mkdir()
    p=create_bench(review['candidate'],setup);bench=next(c for c in p['cells'] if c['id']==p['top'])
    extracted=source/'netlist/layout'/ (lock['top']+'.spice')
    t=attach_view(p,bench,'detector_layout',extracted.read_text(encoding='utf-8'),lock['top'],'external')
    t['analysis']=clone(p['analysis']);t['probes']=['ovout']
    t['measurements']=[{'name':'low_endpoint','kind':'voltage','node':'ovout','at':'3','max':'.2'},
                       {'name':'high_endpoint','kind':'voltage','node':'ovout','at':'6','min':'1.6'}]
    t['specifications']=[{'name':'Code zero rising trip','expression':'crossing(V("ovout"),0.9,1)','unit':'V','min':'3.25','max':'3.35'}]
    save_project(p,output/'franck-views.icproj')
    result=compare_implementation(load_project(output/'franck-views.icproj'),t,executable,output/'franck-dc')
    return {'status':result['implementation_comparison']['status'],'source_commit':lock['commit'],
            'source_files':len(lock['files']),'layout_netlist_sha256':file_digest(extracted),
            'comparison':result['implementation_comparison'],'project':'franck-views.icproj',
            'scope':'Original archived layout netlist, nominal 27 C rising DC, code zero; no fresh LVS or extraction.'}


def layout_workload(path):
    from icstudio.layout_import import read_layout
    if path.suffix=='.gds':p,_=read_layout(path);cid=p['top']
    else:
        p=load_project(path);cid=next(c['id'] for c in p['cells'] if c['name']=='banba_layout')
    return p,cid


def benchmark_layout(path,p,cid,scene_type,iterations):
    scene=scene_type().update(p,cid);box=scene.bounds
    window=(box.left-1,box.bottom-1,box.right+1,box.top+1)
    samples=[];refresh=[]
    for _ in range(iterations):
        start=time.perf_counter();rows=scene.query(window,render=True,cache=False);samples.append((time.perf_counter()-start)*1000)
        start=time.perf_counter();scene.update(p,cid);refresh.append((time.perf_counter()-start)*1000)
    detail=scene.query((box.left,box.bottom,box.left+1000,box.bottom+1000),render=False,cache=False)
    return {'overview_ms':samples,'overview_median_ms':statistics.median(samples),
            'unchanged_update_ms':refresh,'update_median_ms':statistics.median(refresh),
            'master_shapes':len(scene.sources),'expanded_shapes':scene.expanded_count,'render_rows':len(rows),
            'detail_rows':len(detail),'detail_sha256':digest(detail),'input_sha256':file_digest(path)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--ngspice',required=True)
    parser.add_argument('--franck-source',type=Path);parser.add_argument('--baseline-ref')
    parser.add_argument('--iterations',type=int,default=5)
    args=parser.parse_args();output=args.output.resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Choose a new evidence directory.')
    if not 1<=args.iterations<=50:raise ValueError('Use 1–50 benchmark iterations.')
    output.mkdir(parents=True,exist_ok=True)
    report={'status':'failed','checks':{},'scope':'Source execution; archived extracted netlists, no new physical-engine qualification.',
            'python':sys.version,'ngspice_sha256':file_digest(args.ngspice),
            'implementation_sources':{name:file_digest(ROOT/name) for name in ('icstudio/testbenches.py','icstudio/implementation_views.py','icstudio/catalog.py','icstudio/dc_startup.py','scripts/qualify_reference_views.py')}}
    def check(name,fn):
        try:report['checks'][name]=fn()
        except Exception as exc:report['checks'][name]={'status':'failed','error':str(exc)}
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    check('banba',lambda:banba(output,args.ngspice))
    if args.franck_source:check('franck',lambda:franck(args.franck_source.resolve(),output,args.ngspice))
    from icstudio.layout_scene import LayoutScene
    def performance():
        classes={'current':LayoutScene};hashes={'current':file_digest(ROOT/'icstudio/layout_scene.py')}
        if args.baseline_ref:
            source=subprocess.check_output(['git','show',args.baseline_ref+':icstudio/layout_scene.py'],cwd=ROOT)
            module=types.ModuleType('icstudio._reference_baseline');exec(compile(source,'baseline_layout_scene.py','exec'),module.__dict__)
            classes['baseline']=module.LayoutScene;hashes['baseline']=hashlib.sha256(source).hexdigest()
        cases={}
        for name,relative in [('bandgap_core','examples/gf180-banba/layout/banba-layout.icproj'),
                              ('bandgap_fill','examples/gf180-banba/layout/density/banba-density.gds')]:
            path=ROOT/relative;p,cid=layout_workload(path);original=digest(p)
            cases[name]={key:benchmark_layout(path,p,cid,cls,args.iterations) for key,cls in classes.items()}
            if digest(p)!=original:raise ValueError('Layout query changed its source project.')
        if any(len({r['detail_sha256'] for r in case.values()})!=1 for case in cases.values()):
            raise ValueError('Exact detail query differs from the baseline.')
        return {'status':'passed','scope':'Native KLayout spatial query and unchanged scene update, excluding Qt presentation and live checks.',
                'source_hashes':hashes,'workloads':cases}
    check('layout_performance',performance)
    report['status']='passed' if all(r['status']=='passed' for r in report['checks'].values()) else 'failed'
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':sys.exit(main())
