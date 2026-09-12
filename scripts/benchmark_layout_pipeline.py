"""Measure a complete Studio move, durable recovery, repaint and live checks.

Use --source with an extracted earlier source tree for a same-script baseline.
Windows: run benchmark-windows.bat. Offscreen results are CPU/Qt evidence only.
"""
import argparse
import cProfile
import io
import hashlib
import json
import os
import platform
import pstats
import statistics
import sys
import time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--sizes',type=int,nargs='+',default=[1000,10000]);parser.add_argument('--samples',type=int,default=3)
    args=parser.parse_args()
    if not all(1<=n<=10000 for n in args.sizes) or not 1<=args.samples<=10:parser.error('Use 1–10,000 shapes and 1–10 samples.')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'qt-profile/config');os.environ['XDG_DATA_HOME']=str(out/'qt-profile/data')
    sys.path.insert(0,str(args.source.resolve()))
    from PySide6.QtCore import QPointF,QSettings
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.model import example,clone,digest
    from icstudio.layout import rect
    from icstudio import recovery,__version__
    # Source runs must identify the code actually measured, even when a prior
    # packaging run left an older generated build_info.py in the checkout.
    WORKFLOW_SOURCE_HASH=hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in sorted((args.source/'icstudio').glob('*.py')) if p.name!='build_info.py')).hexdigest()
    from icstudio.live_geometry import full
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'qt-profile/settings'))
    app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear()
    w=Studio(recover=False);w.maybe_save=lambda:True;errors=[];w.error=lambda value:errors.append(str(value));w.resize(1400,900);w.show();app.processEvents()
    # Compare equal canvas workloads even when versions add new dock panels.
    if hasattr(w,'workflow_dock'):w.workflow_dock.hide()
    w.layout.setFixedSize(1000,400);app.processEvents()
    w.live_check.setChecked(False);w.preview_timer.stop();rows=[]
    real_recovery=recovery.write;real_refresh=w.refresh;stages={}
    def timed(name,fn):
        def wrapped(*a,**kw):
            start=time.perf_counter()
            try:return fn(*a,**kw)
            finally:stages[name]=stages.get(name,0)+(time.perf_counter()-start)*1000
        return wrapped
    recovery.write=timed('recovery_ms',real_recovery);w.refresh=timed('refresh_ms',real_refresh)
    try:
        for count in args.sizes:
            p=example('empty');c=p['cells'][0]
            c['shapes']=[rect('metal1',(i%100)*1000,(i//100)*1000,600,600) for i in range(count)]
            w.set_project(p);w.mode_combo.setCurrentIndex(1);w.live_timer.stop();w.preview_timer.stop();app.processEvents()
            w.layout.auto_fit=False;w.layout.scale=.035;w.layout.offset=QPointF(30,30);w.select([c['shapes'][0]['id']],'layout');w.layout.grab()
            original_commit=w.history.commit;w.history.commit=timed('history_ms',original_commit)
            if hasattr(w.history,'commit_layout_move'):w.history.commit_layout_move=timed('history_ms',w.history.commit_layout_move)
            if hasattr(w,'refresh_layout_edit') and not getattr(w,'_profile_refresh_wrapped',False):w.refresh_layout_edit=timed('refresh_ms',w.refresh_layout_edit);w._profile_refresh_wrapped=True
            samples=[]
            for i in range(args.samples):
                stages.clear();before=clone(w.cell['shapes'][0]);start=time.perf_counter()
                w.move([before['id']],5 if i%2==0 else -5,0,'layout')
                commit_ms=(time.perf_counter()-start)*1000
                assert not errors,errors
                assert w.cell['shapes'][0]['points']!=before['points']
                start=time.perf_counter();w.layout.grab();paint_ms=(time.perf_counter()-start)*1000
                start=time.perf_counter()
                if hasattr(w,'finish_recovery'):w.finish_recovery()
                durability_wait_ms=(time.perf_counter()-start)*1000
                # The durable stage may use a journal in the current build; verify
                # its recovery reader, not an assumption about its file format.
                start=time.perf_counter();restored,_=recovery.read(w.recovery_dir/(p['id']+'.icproj'));read_ms=(time.perf_counter()-start)*1000
                assert restored['cells']==w.project['cells']
                start=time.perf_counter();check=(w.check_layout_incremental() if hasattr(w,'check_layout_incremental') else full(w.project,w.cid));check_ms=(time.perf_counter()-start)*1000
                assert not check.get('error'),check
                samples.append({**stages,'commit_total_ms':commit_ms,'first_paint_ms':paint_ms,'durability_wait_ms':durability_wait_ms,'recovery_reopen_ms':read_ms,'live_checks_ms':check_ms,'complete_with_checks_ms':commit_ms+paint_ms+durability_wait_ms+check_ms,'check_issue_count':len(check['issues']),'incremental_stats':check.get('stats',{}),'edit_stats':getattr(w.history,'layout_stats',{})})
            # One separately profiled move avoids distorting the timing samples.
            profiler=cProfile.Profile();profiler.enable();w.move([c['shapes'][0]['id']],5,0,'layout');profiler.disable()
            stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumtime').print_stats(25)
            (out/f'profile-{count}.txt').write_text(stream.getvalue())
            rows.append({'shapes':count,'canvas_size':[w.layout.width(),w.layout.height()],'samples':samples,'median':{key:round(statistics.median(s[key] for s in samples),3) for key in samples[0] if key.endswith('_ms')}})
        report={'version':__version__,'workflow_hash':WORKFLOW_SOURCE_HASH,'host':{'platform':platform.platform(),'python':platform.python_version(),'qt_platform':app.platformName()},'workloads':rows,'scope':'Full Studio connected move, first paint, wait for durable recovery, and live declared-rule/terminal checks. Timing stages can be nested; use totals rather than summing stage columns. No foundry deck or native Windows claim unless run there.'}
        (out/'pipeline.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    finally:
        recovery.write=real_recovery;w.saved_hash=digest(w.project);w.close();app.processEvents()


if __name__=='__main__':main()
