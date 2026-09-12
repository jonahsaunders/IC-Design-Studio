"""Source desktop acceptance for the six experimental usability priorities."""
import argparse,json,sys,traceback
from pathlib import Path
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.experimental_probe import run
    app=QApplication([]);app.setStyle('Fusion');errors=[];w=None
    sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
    try:
        settings=QSettings(str(out/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False);settings.clear()
        with patch('icstudio.gui.QSettings',return_value=settings),patch('icstudio.gui.QStandardPaths.writableLocation',return_value=str(out/'profile')):
            w=Studio(recover=False)
        w.error=lambda e:errors.append(str(e));w.maybe_save=lambda:True;w.live_check.setChecked(False)
        w.resize(1400,960);w.show();assert QTest.qWaitForWindowExposed(w)
        report=run(w,out)
        from icstudio.live_probe import run as live_probe
        report['checks'].append(live_probe(w,out))
        assert not errors,errors;report['status']='passed'
    except Exception:report=dict(status='failed',error=traceback.format_exc(),errors=errors)
    finally:
        if w:w.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
