"""Use the source desktop's existing IHP action with both physical coil formats."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for name in ('APPDATA','LOCALAPPDATA','XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME'):os.environ[name]=str(out/'profile'/name)
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.model import digest
    from icstudio.catalog import link_technology
    from icstudio.layout_import import read_layout
    from scripts.qualify_standard_mos import load_technology
    from scripts.qualify_ihp_inductor_layouts import stream,selected,SOURCE_SHA
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);w=Studio(recover=False);w.live_check.setChecked(False);w.maybe_save=lambda:True
    errors=[];jobs=[];w.error=lambda e:errors.append(str(e));w.start_job=lambda settings:jobs.append(settings)
    tech,_=load_technology('ihp-sg13g2');sources=ROOT/'icstudio/assets/qualification/ihp-inductors'
    action=next(a for a in w.findChildren(QAction) if a.text()=='Verify IHP layout with KLayout extraction…')
    assert not w.unmapped_commands,w.unmapped_commands
    for model in SOURCE_SHA:
        gds=out/(model+'.gds');stream(sources/(model+'.gds'),gds,model,270)
        p,_=read_layout(gds);link_technology(p,tech);ref=selected(model);p['cells'][0]['ports']=ref['ports'];w.set_project(p)
        path=out/(model+'.spice');path.write_text(ref['text'],encoding='utf-8')
        w.simple_form=lambda *a,**kw:{'Schematic SPICE file':str(path),'Schematic cell':'coil_coupon'}
        action.trigger();app.processEvents()
        assert not errors and jobs[-1]['lvs_extractor']=='ihp-klayout' and jobs[-1]['reference']['text']==ref['text'],(errors,jobs)
    assert len(jobs)==2
    w.saved_hash=digest(w.project);w.analysis_dirty=False;w.close()
    (out/'report.json').write_text(json.dumps(dict(status='PASS',scope='Source desktop job capture; not installed-release acceptance.',jobs=jobs),indent=2)+'\n',encoding='utf-8')
    print('PASS: both physical coil formats captured by the source IHP verification action.')


if __name__=='__main__':main()
