"""Desktop acceptance: persisted learning, prerequisite practice, editors and real jobs."""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'build/student-hub-ui');args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    from PySide6.QtCore import QSettings,QStandardPaths
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.student_hub_ui import show
    from icstudio.student_hub import Portfolio,complete
    from icstudio.model import clone,digest,save_project
    from icstudio.student_capstone import project as sensor_project
    app=QApplication([]);app.setStyle('Fusion');errors=[]
    old=sys.excepthook
    def exception(t,v,tb):errors.append(str(v));old(t,v,tb)
    sys.excepthook=exception
    settings=QSettings(str(out/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False)
    with patch('icstudio.gui.QSettings',return_value=settings):w=Studio(recover=False)
    w.error=errors.append;w.jobs_dir=out/'runs';w.maybe_save=lambda:True;w.resize(1560,1050);w.show()
    for n in ('ngspice','iverilog','vvp'):
        tool=os.environ.get('ICSTUDIO_TEST_'+n.upper()) or shutil.which(n);assert tool,'Install '+n
        w.settings.setValue('student/tools/'+n,tool)
    h=show(w);assert h.lessons.count()==6
    for key in [p['id'] for p in h.data['paths']]+['capstone']:
        h.choose_path(key);assert h.lessons.count()==sum(l['path']==key for l in h.data['lessons'])
    h.select_lesson('f-first');QTest.qWait(60);h.grab().save(str(out/'hub.png'))
    h.start_selected();g=h.guide;assert g.isVisible();assert w.path.is_file()
    g.answer.setCurrentIndex(1);g.call(g.check);assert 'Try again' in g.feedback.text()
    g.answer.setCurrentIndex(2);g.check();assert g.steps.currentIndex()==0;g.advance();assert g.steps.currentIndex()==1
    g.check();g.advance();assert g.steps.currentIndex()==2
    g.run()
    def wait():
        deadline=time.monotonic()+180
        while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
        assert not w.run_manager.busy,'Worker timeout';app.processEvents();assert not errors,errors
    wait();assert w.run_manager.rows[-1]['state']=='Complete',w.run_manager.rows[-1]['log']
    g.results();QTest.qWait(50);w.grab().save(str(out/'guided-lesson.png'))
    # A pending parameter edit invalidates the old run before awarding a step.
    w.commit(lambda p:p['cells'][0]['devices'][1].update(value='20k'),'Stale evidence probe')
    g.call(g.check);assert 'latest edits' in g.feedback.text()
    w.undo();g.run();wait();g.check();g.advance();assert g.steps.currentIndex()==3
    g.notes.setPlainText('At 12 microseconds the output is approximately 1.14 V: the capacitor has acquired about 63 percent of the input step.')
    g.check();assert complete(h.portfolio.state,h.by_id['f-first'])
    g.save_work();first_path=w.path
    reloaded=Portfolio(h.portfolio.root);assert complete(reloaded.state,h.by_id['f-first'])
    # Save-cancel never changes the current document or attaches a new workspace.
    h.select_lesson('f-connect');original=digest(w.project);replace=w._replace_document;w._replace_document=lambda:False
    h.start_selected();assert digest(w.project)==original and not h.portfolio.workspace(h.by_id['f-connect'])
    w._replace_document=replace
    h.start_selected();assert w.path!=first_path
    h.select_lesson('f-first');h.start_selected();assert w.path==first_path
    # Practice can open later topics without granting progression credit.
    h.select_lesson('d-counter');h.start_selected();assert w._digital_window.isVisible()
    g.answer.setCurrentIndex(1);g.call(g.check);assert 'prerequisites' in g.feedback.text()
    g.run();wait();assert w.run_manager.rows[-1]['state']=='Complete',w.run_manager.rows[-1]['log']
    g.steps.setCurrentIndex(2);g.call(g.check);assert 'prerequisites' in g.feedback.text()
    # Capstone milestones share one editable project; no reset when advancing.
    h.select_lesson('c-filter');h.start_selected();pid=w.project['id'];w.commit(lambda p:p.update(name='My sensor system'),'Rename capstone');g.save_work()
    h.select_lesson('c-sar');h.start_selected();assert w.project['id']==pid and w.project['name']=='My sensor system'
    # Run complete real-engine acceptance on a reviewed reference design.
    p=sensor_project();path=out/'reviewed-sensor.icproj';save_project(p,path);w.set_project(p,path)
    lesson=h.by_id['c-qualify'];h.portfolio.attach(lesson,p,path);g.open_lesson(lesson)
    before=digest(w.project);g.qualification();wait();assert digest(w.project)==before
    from icstudio.student_hub import evaluate
    evidence=evaluate(lesson['steps'][2],lesson,w.project,w.run_manager.rows,path)
    assert len(evidence['cases'])==4
    # Second-pass audit: Results must select this lesson's latest captured run,
    # and the mixed-signal picker must never show another project's evidence.
    from copy import deepcopy
    foreign=deepcopy({k:v for k,v in w.run_manager.rows[-1].items() if k!='process'})
    foreign['id']='foreign-audit-run';foreign['job']['project']['id']='another-project'
    w.run_manager.rows.append(foreign)
    g.results();QTest.qWait(50)
    dialog=w._mixed_signal_dialog
    assert dialog.selected()['id']==w.run_manager.rows[-2]['id']
    assert dialog.runs.findData('foreign-audit-run')==-1
    w.run_manager.rows.remove(foreign)
    dialog.grab().save(str(out/'capstone.png'));dialog.close()
    h.portfolio.export(out/'learning-record.json',h.data)
    assert len(json.loads((out/'learning-record.json').read_text())['projects'])>=4
    # Note drafts persist even without awarding the reflection.
    g.steps.setCurrentIndex(3);g.notes.setPlainText('Draft final review: compare nominal, rail and hold-step evidence before making implementation claims.');QTest.qWait(700)
    assert Portfolio(h.portfolio.root).state['lessons']['c-qualify']['notes']['explain'].startswith('Draft')
    g.run();cancelled=w.run_manager.rows[-1];QTest.qWait(30);g.cancel();wait();assert cancelled['state']=='Cancelled'
    h.select_lesson('c-filter');h.show();QTest.qWait(40);h.grab().save(str(out/'advanced-project.png'))
    h.close();g.close();w.saved_hash=digest(w.project);w.close();app.processEvents();assert not errors,errors
    report=dict(status='PASS',qt_platform=app.platformName(),checks=['six paths and capstone navigation','wrong answer rejected',
        'real analog worker and stale-result rejection','persisted completion and lesson resume','save-cancel preserves work',
        'locked lesson practice without credit','real RTL simulation','shared capstone workspace','four real acceptance cases',
        'non-mutating campaign','portfolio export','autosaved reflection','cancellation'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
