"""Run encrypted-host and annotation acceptance in an isolated desktop profile."""
import argparse
import json
from pathlib import Path
import sys
import traceback


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.host_annotations_probe import run
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');errors=[]
    sys.excepthook=lambda t,v,tb:errors.append(''.join(traceback.format_exception(t,v,tb)))
    w=Studio(recover=False);w.maybe_save=lambda:True;w.show();report=dict(status='failed')
    try:
        report['checks']=[run(w,out)];assert not errors,errors;report['status']='passed'
    except Exception:report['error']=traceback.format_exc();report['qt_errors']=errors
    finally:
        w.close();(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
