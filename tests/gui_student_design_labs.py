"""Exercise the new teaching panels, real bias runs, geometry and report export."""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'build/student-design-labs')
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    profile=Path(tempfile.mkdtemp(prefix='profile-',dir=out))
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication,QFileDialog
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import digest
    from icstudio.student_hub_ui import show
    from icstudio.student_hub import evaluate
    app=QApplication([]);app.setStyle('Fusion')
    if sys.platform=='win32' and app.platformName()=='offscreen':
        fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        for name in ('segoeui.ttf','segoeuib.ttf','arial.ttf'):QFontDatabase.addApplicationFont(str(fonts/name))
    settings=QSettings(str(profile/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False)
    with patch('icstudio.gui.QSettings',return_value=settings),patch.object(QStandardPaths,'writableLocation',return_value=str(profile/'data')):
        w=Studio(recover=False)
    errors=[];w.error=errors.append;w.maybe_save=lambda:True;w.jobs_dir=out/'runs';w.resize(1500,1000);w.show()
    h=show(w);g=h.guide;h.select_lesson('a-gmid-size');QTest.qWait(50)
    assert h.lessons.count()==10 and 'sizing worksheet' in h.details.toPlainText()
    h.grab().save(str(out/'student-hub-design-paths.png'))
    h.start_selected();assert g.lesson_tabs.currentIndex()==0
    assert '9.804' in g.design_notes.toPlainText() and 'Worked example' in g.design_notes.toPlainText()
    g.setFloating(True);g.resize(560,880);QTest.qWait(50);g.grab().save(str(out/'student-gmid-guide.png'))
    # Use the real inspector, including its pending-edit flush, to repair width.
    m=next(d for d in w.project['cells'][0]['devices'] if d['name']=='M1')
    w.select([m['id']],'schematic');w.form_fields['param:w'].setText('9.804u')
    g.run();deadline=time.monotonic()+40
    while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
    assert not w.run_manager.busy and w.run_manager.rows[-1]['state']=='Complete'
    evidence=evaluate(g.lesson['steps'][2],g.lesson,w.project,w.run_manager.rows)
    assert abs(evidence['device_metrics']['gmid']-10)<.01
    g.results();assert g.bias_inspector.isVisible();g.bias_inspector.close()
    # Complete this lesson in practice mode only after actual prerequisite credit.
    g.steps.setCurrentIndex(2);g.call(g.check);assert 'prerequisites' in g.feedback.text()
    h.select_lesson('l-width');h.start_selected();assert w.mode_combo.currentIndex()==1
    assert not g.controls['Run lesson'].isEnabled()
    shape=w.project['cells'][0]['shapes'][0];w.select([shape['id']],'layout')
    w.form_fields['Height'].setText('0.2');g.flush()
    evaluate(g.lesson['steps'][2],g.lesson,w.project)
    # Follow the other geometry repairs through the same micrometre fields.
    for key,edits in [
        ('l-spacing',[(1,{'Top':'0.4'})]),
        ('l-via',[(2,{'Left':'0.175','Top':'0.175'})]),
        ('l-centroid',[(1,{'Left':'3.2'}),(3,{'Left':'0.8'}),(1,{'Left':'2.4'})]),
    ]:
        h.select_lesson(key);h.start_selected()
        for index,fields in edits:
            shape=w.project['cells'][0]['shapes'][index];w.select([shape['id']],'layout')
            for field,value in fields.items():w.form_fields[field].setText(value)
            g.flush()
        evaluate(g.lesson['steps'][2],g.lesson,w.project)
    h.select_lesson('l-centroid');h.show();QTest.qWait(50);h.grab().save(str(out/'student-layout-path.png'))
    # Preserve pending reflection edits, escape HTML, and honor Save cancellation.
    g.steps.setCurrentIndex(3);g.notes.setPlainText('My <layout> review: repaired a 100 nm route to 200 nm; generic checks are not foundry signoff.')
    destination=out/'sample-portfolio.html'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(destination),'')):h.export(report=True)
    text=destination.read_text(encoding='utf-8');assert '&lt;layout&gt;' in text and 'My <layout>' not in text
    with patch.object(w,'save',return_value=False),patch.object(QFileDialog,'getSaveFileName') as choose:
        h.export(report=True);choose.assert_not_called()
    for scale in (100,200):
        h.set_text_scale(scale);h.resize(720,600);g.resize(420,700);QTest.qWait(50)
        assert h.scroll.horizontalScrollBar().maximum()==0
        assert g.scroll.horizontalScrollBar().maximum()==0
    h.close();g.close();w.saved_hash=digest(w.project);w.close();app.processEvents();assert not errors,errors
    result=dict(status='PASS',platform=sys.platform,qt_platform=app.platformName(),checks=[
        'six paths and teaching panels','gm/ID edit through inspector and real solver','operating point inspector',
        'practice cannot earn prerequisite credit','layout repair through inspector','HTML export and save cancellation',
        '100 and 200 percent text without horizontal overflow'])
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
