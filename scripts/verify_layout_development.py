"""Small real-worker layout checks, file-comparison workload, and optional Qt acceptance."""
import argparse,json,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import example,clone,save_project,file_digest,digest
from icstudio.layout import rect,kdb
from icstudio.layout_routing import install
from icstudio.layout_topology import partition


def run(out,gui=False):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    report={'status':'running','checks':[],'qualification':'Geometric and worker checks only. No process verification or electrical qualification.'}
    def record(name,**data):report['checks'].append({'name':name,**data})
    p=example('empty');p['name']='Multilayer routing example';c=p['cells'][0];cid=c['id']
    c['shapes']=[rect('metal1',2000,-10000,1000,20000,net='block')]
    job={'project':clone(p),'cell':cid,'engine':'builtin','settings':{'type':'layout_route','operation':'route','arguments':{
        'start':{'layer':'metal1','point':[0,0]},'end':{'layer':'metal1','point':[5000,0]},'net':'signal','width':400,'margin':2000}}}
    work=out/'routing-worker';work.mkdir(exist_ok=True);(work/'input.json').write_text(json.dumps(job))
    started=time.monotonic();completed=subprocess.run([sys.executable,str(ROOT/'main.py'),'--worker',str(work/'input.json'),str(work/'result.json')],cwd=ROOT,text=True,capture_output=True,timeout=60)
    (work/'worker.log').write_text(completed.stdout+completed.stderr)
    if completed.returncode:raise ValueError('Routing worker failed: '+completed.stdout+completed.stderr)
    from icstudio.job_store import read_result
    result=read_result(work/'result.json',p['id'],False);proposal=result['layout_proposal'];ids=install(p,proposal)
    assert proposal['via_count']==2 and len(set(partition(p,cid).values()))==2
    save_project(p,out/'multilayer-route.icproj')
    record('real_routing_worker',status='passed',seconds=time.monotonic()-started,via_count=2,installed_shapes=len(ids),result_sha256=file_digest(work/'result.json'))
    from icstudio.layout_inspection import compare_files
    db=kdb();ly=db.Layout();ly.dbu=.001;top=ly.create_cell('top');child=ly.create_cell('tile');li=ly.layer(4,0);child.shapes(li).insert(db.Box(0,0,400,400))
    top.insert(db.CellInstArray(child.cell_index(),db.Trans(),db.Vector(1000,0),db.Vector(0,1000),100,100))
    a=out/'array-10000.gds';b=out/'array-10000.oas';ly.write(str(a));ly.write(str(b));started=time.monotonic();comparison=compare_files(a,b)
    assert comparison['equal_geometry'] and comparison['expanded_shapes']==[10000,10000]
    record('hierarchical_gds_oasis_comparison',status='passed',seconds=time.monotonic()-started,**comparison)
    # A second real worker checks that comparison results retain job provenance.
    from icstudio.interchange import export_layout
    reference=out/'route-reference.oas';export_layout(p,reference)
    cmp_work=out/'comparison-worker';cmp_work.mkdir(exist_ok=True)
    cmp_job={'project':clone(p),'cell':cid,'engine':'builtin','settings':{'type':'layout_compare','reference':str(reference),'reference_sha256':file_digest(reference),'reference_top':'top'}}
    (cmp_work/'input.json').write_text(json.dumps(cmp_job));completed=subprocess.run([sys.executable,str(ROOT/'main.py'),'--worker',str(cmp_work/'input.json'),str(cmp_work/'result.json')],cwd=ROOT,text=True,capture_output=True,timeout=60)
    (cmp_work/'worker.log').write_text(completed.stdout+completed.stderr)
    if completed.returncode:raise ValueError('Comparison worker failed: '+completed.stdout+completed.stderr)
    compared=read_result(cmp_work/'result.json',p['id'],False);assert compared['layout_comparison']['equal_geometry']
    record('real_comparison_worker',status='passed',result_sha256=file_digest(cmp_work/'result.json'))
    if gui:
        try:
            from PySide6.QtCore import QSettings
            from PySide6.QtWidgets import QApplication,QPushButton,QLabel
            from icstudio.gui import Studio
            from icstudio.layout_routing import plan
            QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'qt-profile'))
            app=QApplication.instance() or QApplication([]);app.setApplicationName('IC Studio layout acceptance');app.setOrganizationName('ICDesignStudioTests')
            window=Studio(recover=False);window.set_project(clone(job['project']));window.cid=cid;window.refresh(True);window.show();app.processEvents()
            assert window.connected_layout_action.isChecked()
            assert any('Plan matched pair' in action.text() for _,action in window._commands)
            opened=clone(window.project)
            # Opening a legacy fixture initializes wires/junctions. A proposal
            # captured before that migration must be rejected, not installed.
            window.review_layout_proposal(proposal);app.processEvents()
            button=next(b for b in window._layout_proposal_dialog.findChildren(QPushButton) if b.text()=='Install route');button.click();app.processEvents()
            assert window.project==opened
            assert any('design changed' in label.text().lower() for label in window._layout_proposal_dialog.findChildren(QLabel))
            window._layout_proposal_dialog.reject()
            # Real GUI jobs plan from the already-open document snapshot.
            gui_proposal=plan(window.project,cid,**job['settings']['arguments'])
            window.review_layout_proposal(gui_proposal);app.processEvents()
            window._layout_proposal_dialog.grab().save(str(out/'route-preview.png'))
            button=next(b for b in window._layout_proposal_dialog.findChildren(QPushButton) if b.text()=='Install route');button.click();app.processEvents()
            assert len(window.cell['shapes'])==len(p['cells'][0]['shapes'])
            assert window.mode_combo.currentIndex()==1 and window.current_mode=='layout'
            assert window.layout.isVisible() and not window.schematic.isVisible()
            installed=clone(window.project['cells'])
            window.undo();assert window.project['cells']==opened['cells']
            window.redo();window.layout_query_dialog();app.processEvents()
            assert window.project['cells']==installed
            window.grab().save(str(out/'layout-tools.png'))
            window.saved_hash=digest(window.project);window.close();app.processEvents()
            record('qt_commands_proposal_undo_redo',status='passed',stale_proposal_rejected=True,installed_shapes=len(gui_proposal['shapes']),exact_undo_redo=True,layout_canvas_visible=True)
        except ImportError as exc:record('qt_commands_proposal_undo_redo',status='blocked',reason=str(exc))
        except Exception as exc:record('qt_commands_proposal_undo_redo',status='failed',reason=str(exc),traceback=traceback.format_exc())
    else:record('qt_commands_proposal_undo_redo',status='not_run')
    report['status']='passed' if all(v['status']=='passed' for v in report['checks']) else 'partial'
    (out/'workflow-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    return 0 if all(v['status'] in ('passed','not_run') for v in report['checks']) else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--gui',action='store_true');args=parser.parse_args()
    raise SystemExit(run(args.out,args.gui))
