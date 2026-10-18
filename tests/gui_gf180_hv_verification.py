"""Exercise the GF180 HV source desktop action with real imported layouts."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--font',type=Path);a=ap.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for name in ('APPDATA','LOCALAPPDATA','XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME'):os.environ[name]=str(out/'profile'/name)
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtGui import QAction,QFontDatabase,QFont
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.model import example,digest
    from scripts.qualify_standard_mos import load_technology
    from scripts.qualify_gf180_hv_layouts import stream,project,selected
    from scripts.qualify_gf180_resistor_layouts import native_layers
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([])
    if a.font:
        fid=QFontDatabase.addApplicationFont(str(a.font));assert fid>=0
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    w=Studio(recover=False);w.live_check.setChecked(False);w.maybe_save=lambda:True;errors=[];jobs=[]
    w.error=lambda e:errors.append(str(e));w.start_job=lambda settings:jobs.append(settings)
    stream(out/'layout.gds',4,.6)
    text=selected(4,.6)['text'];path=out/'reference.spice';path.write_text(text,encoding='utf-8')
    w.simple_form=lambda *args,**kwargs:{'Schematic SPICE file':str(path),'Schematic cell':'coupon'}
    action=next(a for a in w.findChildren(QAction) if a.text()=='Verify GF180 high-voltage layout…')
    for target in ('gf180mcuC','gf180mcuD'):
        tech,_=load_technology(target);native_layers(tech);w.set_project(project(out/'layout.gds',tech))
        action.trigger();app.processEvents()
        assert not errors and jobs[-1]['lvs_extractor']=='gf180-hv-klayout' and jobs[-1]['reference']['text']==text,(errors,jobs)
    assert len(jobs)==2
    w.run_layout_verification();assert jobs[-1]['lvs_extractor']=='magic'
    w.set_project(example('empty'));action.trigger();app.processEvents()
    assert len(jobs)==3 and len(errors)==1 and 'GF180 C or D' in errors[0],errors
    w.saved_hash=digest(w.project);w.analysis_dirty=False;w.close()
    report=dict(status='PASS',scope='Source desktop action and job capture; not installed-release qualification.',
        checks=['C and D high-voltage action','Exact schematic capture','Default Magic action retained','Wrong process rejected'],jobs=jobs)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS: both GF180 desktop routes, reference capture and wrong-process rejection.')


if __name__=='__main__':main()
