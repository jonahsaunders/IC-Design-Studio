"""Exercise the bounded RF diode action in the real source desktop."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--sky130',type=Path,required=True);a=ap.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for name in ('APPDATA','LOCALAPPDATA','XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME'):os.environ[name]=str(out/'profile'/name)
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.model import example,digest
    from scripts.qualify_standard_mos_layout import technology
    from scripts.qualify_sky130_rf_layouts import stream,project,selected
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);w=Studio(recover=False);w.live_check.setChecked(False);w.maybe_save=lambda:True
    errors=[];jobs=[];w.error=lambda e:errors.append(str(e));w.start_job=lambda settings:jobs.append(settings)
    tech,_=technology('sky130A',a.sky130);stream(out/'layout.gds',2,4,270);w.set_project(project(out/'layout.gds',tech))
    text=selected(2,4)['text'];path=out/'reference.spice';path.write_text(text,encoding='utf-8')
    w.simple_form=lambda *args,**kwargs:{'Schematic SPICE file':str(path),'Schematic cell':'rf_coupon'}
    action=next(a for a in w.findChildren(QAction) if a.text()=='Verify SKY130 RF n-well diode…')
    action.trigger();app.processEvents()
    assert not errors and len(jobs)==1 and jobs[0]['lvs_extractor']=='sky130-rf-nwell-klayout' and jobs[0]['reference']['text']==text,(errors,jobs)
    w.run_layout_verification();assert jobs[-1]['lvs_extractor']=='magic'
    w.set_project(example('empty'));action.trigger();app.processEvents()
    assert len(jobs)==2 and len(errors)==1 and 'SKY130A' in errors[0],errors
    w.saved_hash=digest(w.project);w.analysis_dirty=False;w.close()
    (out/'report.json').write_text(json.dumps(dict(status='PASS',scope='Source desktop action/captured job, not installed release.',checks=['RF action and exact reference','Default verifier retained','Wrong process rejected'],jobs=jobs),indent=2),encoding='utf-8')
    print('PASS: source RF desktop action, captured reference and process rejection')


if __name__=='__main__':main()
