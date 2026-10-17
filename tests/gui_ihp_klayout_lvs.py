"""Source desktop action captures the selected IHP extractor and reference."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--font',type=Path);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for name in ('APPDATA','LOCALAPPDATA','XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME'):os.environ[name]=str(out/'profile'/name)
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase,QFont
    from icstudio.gui import Studio
    from icstudio.model import example,digest
    from scripts.qualify_standard_mos import load_technology
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([])
    if a.font:
        fid=QFontDatabase.addApplicationFont(str(a.font));assert fid>=0;app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    w=Studio(recover=False);w.live_check.setChecked(False);w.maybe_save=lambda:True;errors=[];jobs=[]
    w.error=lambda e:errors.append(str(e));w.start_job=lambda settings:jobs.append(settings)
    p=example('empty');p['pdk']=load_technology('ihp-sg13g2')[0];w.set_project(p)
    text='.subckt coupon C B E\nX1 C B E pnpMPA a=1.4p p=5.4u\n.ends coupon\n';path=out/'reference.spice';path.write_text(text)
    w.simple_form=lambda *args,**kwargs:{'Schematic SPICE file':str(path),'Schematic cell':'coupon'}
    from PySide6.QtGui import QAction
    actions=w.findChildren(QAction)
    action=next((a for a in actions if a.text()=='Verify IHP layout with KLayout extraction…'),None)
    assert action is not None,[a.text() for a in actions if 'IHP' in a.text() or 'LVS' in a.text()]
    action.trigger();app.processEvents()
    assert not errors and len(jobs)==1 and jobs[0]['lvs_extractor']=='ihp-klayout' and jobs[0]['reference']['text']==text,(errors,jobs)
    w.run_layout_verification();assert jobs[-1]['lvs_extractor']=='magic'
    w.set_project(example('empty'));action.trigger();app.processEvents();assert len(jobs)==2 and len(errors)==1 and 'IHP SG13G2' in errors[0],errors
    w.saved_hash=digest(w.project);w.analysis_dirty=False;w.close()
    report=dict(status='PASS',scope='Source desktop action and captured job settings; not an installed-release acceptance run.',checks=['IHP action selects public KLayout extraction','Self-contained reference captured before queueing','Default action retains Magic extraction','Other PDKs rejected'],job=jobs[0])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS: IHP desktop action, reference capture, default route and process guard.')

if __name__=='__main__':main()
